from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Окружение
    env: str = "dev"

    # JWT-аутентификация
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 10080

    # База данных
    database_url: str = "postgresql+asyncpg://vkr:vkr@postgres:5432/vkr"

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"
    sync_processing: bool = False  # true → обрабатывать в request-thread, минуя Celery

    # S3-совместимое хранилище (MinIO)
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "vkr-documents"
    s3_region: str = "us-east-1"
    use_s3: bool = True
    local_storage_path: str = "./storage"  # запасное локальное хранилище, если use_s3=False

    # CORS
    allowed_cors_origins_raw: str = Field(
        default="http://localhost:5173,http://localhost",
        alias="ALLOWED_CORS_ORIGINS",
    )

    # Путь к YAML с нормативными правилами (загружается при первом старте)
    rules_file_path: str = "services/core/vkr_core/config/rules_v1.yaml"

    # Антивирусное сканирование загруженных файлов через clamscan.
    # В dev-окружении clamscan может быть не установлен — тогда оставлять
    # False. В prod ставить True; на старте API проверяется наличие
    # бинарника и при отсутствии сервис не запускается.
    antivirus_required: bool = False

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_cors_origins_raw.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
