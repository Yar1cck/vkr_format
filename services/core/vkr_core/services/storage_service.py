from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

import boto3
from botocore.client import Config

from services.core.vkr_core.config.settings import get_settings

_logger = logging.getLogger(__name__)

# Singleton-кэш boto3-клиента. Конструктор StorageService раньше создавал
# client + head_bucket на КАЖДЫЙ инстанс, а инстансы плодились в каждом
# хендлере (десятки раз за запрос) — лишний RTT к MinIO/S3 на пустом месте.
# Settings тоже singleton (`@lru_cache(maxsize=1)`), endpoint в рантайме
# не меняется, так что кэш безопасен.
_s3_client = None
_s3_bucket_initialized = False


def _build_s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


def _get_s3_client():
    """Возвращает кэшированный boto3-клиент. При первом обращении создаёт
    клиента и проверяет наличие бакета (создаёт, если нет — удобно в dev
    с пустым MinIO). В проде бакет обычно уже подготовлен."""
    global _s3_client, _s3_bucket_initialized
    settings = get_settings()
    if not settings.use_s3:
        return None
    if _s3_client is None:
        _s3_client = _build_s3_client()
    if not _s3_bucket_initialized:
        try:
            _s3_client.head_bucket(Bucket=settings.s3_bucket)
        except Exception:
            try:
                _s3_client.create_bucket(Bucket=settings.s3_bucket)
            except Exception:
                _logger.exception(
                    "Не удалось получить/создать бакет %s", settings.s3_bucket
                )
                raise
        _s3_bucket_initialized = True
    return _s3_client


class StorageService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.local_root = Path(self.settings.local_storage_path)
        self.local_root.mkdir(parents=True, exist_ok=True)
        self._s3 = _get_s3_client()

    def save_file(self, source: Path, category: str, suffix: str | None = None) -> str:
        object_name = f"{category}/{uuid.uuid4()}{suffix or source.suffix}"
        if self.settings.use_s3 and self._s3:
            self._s3.upload_file(str(source), self.settings.s3_bucket, object_name)
            return object_name

        target = self.local_root / object_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return str(target)

    def save_bytes(self, content: bytes, category: str, suffix: str) -> str:
        object_name = f"{category}/{uuid.uuid4()}{suffix}"
        if self.settings.use_s3 and self._s3:
            self._s3.put_object(Bucket=self.settings.s3_bucket, Key=object_name, Body=content)
            return object_name

        target = self.local_root / object_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return str(target)

    def load_to_local_path(self, path: str) -> Path:
        if not self.settings.use_s3:
            return Path(path)

        temp = self.local_root / "tmp" / f"{uuid.uuid4()}"
        temp.parent.mkdir(parents=True, exist_ok=True)
        assert self._s3 is not None
        self._s3.download_file(self.settings.s3_bucket, path, str(temp))
        return temp

    def delete(self, path: str) -> None:
        if self.settings.use_s3 and self._s3:
            self._s3.delete_object(Bucket=self.settings.s3_bucket, Key=path)
            return
        p = Path(path)
        if p.exists():
            p.unlink()
