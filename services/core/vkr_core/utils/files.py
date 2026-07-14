from __future__ import annotations

import mimetypes
import zipfile
from pathlib import Path

SUPPORTED_EXTENSIONS = {".docx"}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

MAGIC_SIGNATURES = {
    ".docx": [b"PK\x03\x04"],
}


class FileValidationError(Exception):
    pass


def validate_upload(path: Path, original_name: str) -> str:
    ext = Path(original_name).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise FileValidationError("Unsupported extension. Allowed: .docx")

    if path.stat().st_size > MAX_FILE_SIZE_BYTES:
        raise FileValidationError("File too large (max 50MB)")

    with path.open("rb") as fh:
        head = fh.read(8)
    valid_magic = any(head.startswith(signature) for signature in MAGIC_SIGNATURES[ext])
    if not valid_magic:
        raise FileValidationError("Magic bytes mismatch for uploaded file")

    mime, _ = mimetypes.guess_type(original_name)
    if mime is None:
        raise FileValidationError("Unable to determine MIME type")

    # PK\x03\x04 — сигнатура любого ZIP, а не именно docx. Любой ZIP-архив
    # (rar-обёртка, ещё хуже — переименованный .exe в zip-контейнере)
    # пройдёт magic-проверку. Чтобы отсечь spoof, открываем как ZIP и
    # требуем `word/document.xml` внутри — это часть OOXML-спецификации и
    # обязана быть в каждом валидном .docx.
    try:
        with zipfile.ZipFile(path) as zf:
            if "word/document.xml" not in zf.namelist():
                raise FileValidationError(
                    "Файл не похож на .docx (внутри отсутствует word/document.xml)"
                )
    except zipfile.BadZipFile as exc:
        raise FileValidationError("Файл повреждён или не является .docx") from exc

    return ext
