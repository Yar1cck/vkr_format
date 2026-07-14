from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from services.core.vkr_core.config.settings import get_settings

logger = logging.getLogger(__name__)


class AntivirusError(Exception):
    pass


# Чтобы не печатать одно и то же предупреждение на каждую загрузку в dev,
# логируем отсутствие clamscan один раз за процесс.
_warned_about_missing_scanner = False


def scan_file(path: Path) -> None:
    """Сканирует файл через clamscan.

    Поведение зависит от настройки `antivirus_required`:
      - True (prod): отсутствие clamscan — это `AntivirusError`. Файл не
        принимается. Параллельная защита: на старте API проверяется наличие
        бинарника, чтобы такой ошибки не возникало после деплоя.
      - False (dev): отсутствие clamscan — это warning в логах (один раз
        за процесс), сканирование пропускается. Это удобно для локальной
        разработки на машине без clamav.
    """
    global _warned_about_missing_scanner
    scanner = shutil.which("clamscan")
    settings = get_settings()
    if not scanner:
        if settings.antivirus_required:
            raise AntivirusError(
                "Antivirus scanning is required but clamscan binary is not "
                "available on PATH"
            )
        if not _warned_about_missing_scanner:
            logger.warning(
                "clamscan not found on PATH; uploads are not scanned. "
                "Set ANTIVIRUS_REQUIRED=true in production."
            )
            _warned_about_missing_scanner = True
        return

    # Timeout — защита от подвисшего clamscan на странных файлах:
    # без него subprocess.run будет ждать вечность и заблокирует upload-эндпоинт.
    # 60 секунд хватает для honest-сканирования любого docx до 50 МБ; всё, что
    # дольше — почти гарантированно зависание/баг.
    try:
        result = subprocess.run(
            [scanner, "--no-summary", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        raise AntivirusError(
            "Антивирусное сканирование превысило лимит времени (60 с)"
        ) from exc
    if result.returncode not in (0, 1):
        raise AntivirusError(f"Antivirus scan failed: {result.stderr.strip()}")
    if result.returncode == 1:
        raise AntivirusError("Malware detected in uploaded file")


def check_antivirus_available() -> None:
    """Вызывается при старте API. Если `antivirus_required=True`, но clamscan
    не найден в PATH — поднимает `RuntimeError`, чтобы сервис упал быстро и
    с понятной диагностикой, а не молча принимал документы без сканирования.
    """
    settings = get_settings()
    if not settings.antivirus_required:
        return
    if shutil.which("clamscan") is None:
        raise RuntimeError(
            "ANTIVIRUS_REQUIRED=true, but the `clamscan` binary is not "
            "available on PATH. Install clamav or set ANTIVIRUS_REQUIRED=false."
        )
