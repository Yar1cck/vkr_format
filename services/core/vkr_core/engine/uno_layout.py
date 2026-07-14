"""Точное измерение пагинации таблиц через LibreOffice UNO.

Для «Продолжение таблицы N» нужно знать, на какой физической странице
оказывается каждая строка таблицы ПОСЛЕ реального рендера. Раньше это
делалось эвристикой по `pdftotext -tsv` (поиск слов строки в текстовом
потоке PDF) — ненадёжно на плотных/широких таблицах: распределение
получалось «шумным», и таблица резалась на рваные куски.

Здесь — точный путь: поднимаем headless-LibreOffice с UNO-сокетом,
открываем документ и для каждой строки таблицы спрашиваем у движка
реальный номер страницы (`XPageCursor.getPage()`). Это то же самое
число, что увидит пользователь, открыв документ.

Граничные требования:
  * Работает только там, где есть LibreOffice + python-uno (в нашем
    docker-образе `vkr-format-api`/`worker` — есть; на «голом» хосте
    обычно нет). При ЛЮБОЙ ошибке возвращаем пустой dict — вызывающий
    код откатывается на эвристику по объёму (table_continuation.py).
  * `import uno` в системном python видит модуль только при выставленных
    PYTHONPATH и URE_BOOTSTRAP — выставляем их в окружении до импорта.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

_logger = logging.getLogger(__name__)

# Где системный python ищет uno.py и какой rc грузит UNO-рантайм.
# Без этих переменных `import uno` падает ModuleNotFoundError даже при
# установленном LibreOffice.
_UNO_PYTHONPATH = "/usr/lib/python3/dist-packages"
_URE_BOOTSTRAP = "file:///usr/lib/libreoffice/program/fundamentalrc"


def _uno_available() -> bool:
    """True, если в окружении вообще есть LibreOffice + uno.py."""
    if not Path("/usr/lib/libreoffice/program/fundamentalrc").exists():
        return False
    if not Path(_UNO_PYTHONPATH, "uno.py").exists():
        return False
    return shutil.which("soffice") is not None


def _free_port() -> int:
    """Свободный TCP-порт. Параллельные worker'ы не должны делить порт."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _first_cell_per_row(table) -> dict[int, str]:
    """{номер_строки(1-based): имя первой ячейки}, напр. {1:'A1', 2:'A2'}.

    Имена ячеек UNO: 'A1','B1',...,'A2'. Первый столбец строки r — буква
    с наименьшим алфавитным порядком при числовом суффиксе r.
    """
    by_row: dict[int, str] = {}
    for name in table.getCellNames():
        digits = "".join(ch for ch in name if ch.isdigit())
        letters = "".join(ch for ch in name if ch.isalpha())
        if not digits or not letters:
            continue
        r = int(digits)
        if r not in by_row or letters < by_row[r][0]:
            by_row[r] = name
    return by_row


def measure_table_row_pages(
    docx_path: Path, timeout: int = 120
) -> dict[int, list[int]]:
    """Возвращает {индекс_таблицы: [номер_страницы для каждой строки]}.

    Индекс таблицы соответствует порядку обхода в `doc.getTextTables()`,
    который совпадает с порядком `python-docx` `doc.tables` (оба идут по
    телу документа последовательно).

    При недоступности UNO / любой ошибке — пустой dict (вызывающий код
    откатится на эвристику). Сам soffice-процесс гарантированно убивается.
    """
    if not _uno_available():
        _logger.info("uno_layout: LibreOffice/uno недоступны — пропуск UNO-измерения")
        return {}

    # PYTHONPATH в os.environ влияет только на дочерние процессы; для
    # текущего интерпретатора uno.py надо добавить прямо в sys.path.
    # URE_BOOTSTRAP читает нативный pyuno при импорте — его в os.environ.
    import sys
    if _UNO_PYTHONPATH not in sys.path:
        sys.path.insert(0, _UNO_PYTHONPATH)
    os.environ.setdefault("URE_BOOTSTRAP", _URE_BOOTSTRAP)

    try:
        import uno  # noqa: F401  (доступен только в окружении с LibreOffice)
        from com.sun.star.beans import PropertyValue
    except Exception:
        _logger.warning("uno_layout: import uno не удался", exc_info=True)
        return {}

    port = _free_port()
    profile = Path(tempfile.mkdtemp(prefix="uno-layout-"))
    accept = (
        f"socket,host=127.0.0.1,port={port};urp;StarOffice.ServiceManager"
    )
    proc = subprocess.Popen(
        [
            "soffice", "--headless", "--invisible", "--norestore", "--nologo",
            f"-env:UserInstallation=file://{profile}",
            f"--accept={accept}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # отдельная группа процессов → killpg
    )

    result: dict[int, list[int]] = {}
    doc = None
    try:
        local_ctx = uno.getComponentContext()
        resolver = local_ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", local_ctx
        )
        connect_url = (
            f"uno:socket,host=127.0.0.1,port={port};urp;"
            "StarOffice.ComponentContext"
        )
        ctx = None
        deadline = time.time() + min(timeout, 60)
        while time.time() < deadline:
            try:
                ctx = resolver.resolve(connect_url)
                break
            except Exception:
                time.sleep(0.5)
        if ctx is None:
            _logger.warning("uno_layout: soffice-сокет не поднялся за отведённое время")
            return {}

        smgr = ctx.ServiceManager
        desktop = smgr.createInstanceWithContext(
            "com.sun.star.frame.Desktop", ctx
        )
        hidden = PropertyValue()
        hidden.Name = "Hidden"
        hidden.Value = True
        read_only = PropertyValue()
        read_only.Name = "ReadOnly"
        read_only.Value = True
        url = Path(docx_path).resolve().as_uri()
        doc = desktop.loadComponentFromURL(url, "_blank", 0, (hidden, read_only))
        if doc is None:
            _logger.warning("uno_layout: документ не открылся через UNO")
            return {}

        vc = doc.getCurrentController().getViewCursor()
        tables = doc.getTextTables()
        for ti in range(tables.Count):
            table = tables.getByIndex(ti)
            rows = table.getRows().Count
            by_row = _first_cell_per_row(table)
            pages: list[int] = []
            for r in range(1, rows + 1):
                cell_name = by_row.get(r)
                if cell_name is None:
                    pages.append(-1)
                    continue
                try:
                    cell = table.getCellByName(cell_name)
                    vc.gotoRange(cell.getText().getStart(), False)
                    pages.append(int(vc.getPage()))
                except Exception:
                    pages.append(-1)
            result[ti] = pages
        _logger.info(
            "uno_layout: измерено таблиц=%d (через UNO getPage)", len(result)
        )
        return result
    except Exception:
        _logger.warning("uno_layout: ошибка UNO-измерения", exc_info=True)
        return {}
    finally:
        try:
            if doc is not None:
                doc.close(False)
        except Exception:
            pass
        # Глушим весь процесс-группу soffice (родитель + soffice.bin).
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:
            _logger.debug("uno_layout: не удалось убить soffice", exc_info=True)
        shutil.rmtree(profile, ignore_errors=True)


