"""Утилита для запуска LibreOffice headless в изолированном профиле.

Проблема: soffice — это скрипт-обёртка, который запускает реальный
soffice.bin как дочерний процесс. При capture_output=True дочерний процесс
наследует открытые концы пайпов stdout/stderr. Когда subprocess.run()
убивает родителя по timeout, soffice.bin продолжает жить и держит пайп
открытым — communicate() ждёт EOF бесконечно.

Решение:
  1. start_new_session=True — помещает LibreOffice и все его дочерние
     процессы в отдельную группу (setsid). При таймауте убиваем всю
     группу через os.killpg(SIGKILL), после чего пайпы закрываются.
  2. -env:UserInstallation=file://... — каждый вызов получает изолированный
     профиль, предотвращая конфликты lock-файлов между параллельными
     или последовательными вызовами.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

_logger = logging.getLogger(__name__)

# Если воркер поднял unoserver, сюда прилетит порт через env UNOSERVER_PORT.
# При пустой строке — прямой вызов soffice (дефолт для dev и API-процесса).
_UNOSERVER_PORT: str = os.environ.get("UNOSERVER_PORT", "")
_UNOSERVER_HOST: str = "127.0.0.1"

# На macOS LibreOffice устанавливается как .app — бинарник не в PATH.
# Ищем в стандартных местах; переопределяется через env SOFFICE_BIN.
def _find_soffice() -> str:
    if override := os.environ.get("SOFFICE_BIN"):
        return override
    candidates = [
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/usr/bin/soffice",
        "/usr/local/bin/soffice",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return "soffice"  # полагаемся на PATH
# UNO-модули живут в системном dist-packages; без этого PYTHONPATH
# импорт uno падает в pip-окружении (Python 3.12 не знает о системных пакетах).
_UNO_PYTHONPATH = "/usr/lib/python3/dist-packages"
_URE_BOOTSTRAP = "file:///usr/lib/libreoffice/program/fundamentalrc"

_EMBED_FONTS_XCU = """\
<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry"
           xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <item oor:path="/org.openoffice.Office.Common/Filter/PDF/Export">
  <prop oor:name="EmbedStandardFonts" oor:op="fuse">
   <value xsi:type="xs:boolean">true</value>
  </prop>
 </item>
</oor:items>
"""


def convert_via_unoconvert(
    input_path: Path,
    output_path: Path,
    timeout: int = 90,
) -> bool:
    """Конвертирует файл через уже запущенный unoserver (без старта нового LO).

    Возвращает True при успехе. При ЛЮБОЙ ошибке (нет unoserver, нет unoconvert,
    timeout, пустой файл) — False, вызывающий код использует run_soffice.
    Fallback гарантирован — функция никогда не кидает исключение.
    """
    if not _UNOSERVER_PORT:
        return False
    unoconvert = shutil.which("unoconvert")
    if not unoconvert:
        return False
    env = {
        **os.environ,
        "PYTHONPATH": _UNO_PYTHONPATH,
        "URE_BOOTSTRAP": _URE_BOOTSTRAP,
    }
    try:
        proc = subprocess.run(
            [unoconvert, "--host", _UNOSERVER_HOST, "--port", _UNOSERVER_PORT,
             str(input_path), str(output_path)],
            timeout=timeout,
            capture_output=True,
            env=env,
        )
        if proc.returncode != 0:
            _logger.debug(
                "unoconvert exit %d: %s",
                proc.returncode,
                proc.stderr.decode(errors="replace")[:200],
            )
            return False
        return output_path.exists() and output_path.stat().st_size > 0
    except Exception as exc:
        _logger.debug("unoconvert failed (%s) — fallback to soffice", exc)
        return False


def run_soffice(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    """Запускает `soffice --headless` с изолированным профилем и надёжным kill.

    Принимает аргументы команды БЕЗ `soffice` и `--headless` — они
    добавляются автоматически. Профиль удаляется после завершения.
    В профиль вшивается XCU-конфиг, который включает встраивание шрифтов
    в PDF — без этого кириллица на чужих машинах отображается квадратиками.
    """
    profile_dir = Path(tempfile.mkdtemp(prefix="lo-profile-"))
    try:
        user_dir = profile_dir / "user"
        user_dir.mkdir()
        (user_dir / "registrymodifications.xcu").write_text(_EMBED_FONTS_XCU, encoding="utf-8")

        cmd = [
            _find_soffice(),
            "--headless",
            "--norestore",
            f"-env:UserInstallation=file://{profile_dir}",
            *args,
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = proc.communicate()
            return subprocess.CompletedProcess(cmd, -signal.SIGKILL, stdout, stderr)
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)
