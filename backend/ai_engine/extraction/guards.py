"""Ingest guards (docs/05 §2): format sniffing, size/page limits, DOCX zip-bomb checks."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from ai_engine.contracts import Flag

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass(frozen=True)
class Limits:
    max_bytes: int = 10 * 1024 * 1024
    max_pages: int = 30  # CV; supporting documents may pass 50
    docx_max_uncompressed: int = 50 * 1024 * 1024
    docx_max_entries: int = 2_000
    docx_max_ratio: float = 100.0
    soft_seconds: int = 60
    hard_seconds: int = 90
    memory_bytes: int = 1024 * 1024 * 1024


class ExtractionError(Exception):
    """A document that cannot be read. ``code`` is shown to staff; ``flag`` is recorded."""

    def __init__(self, code: str, flag: Flag, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.flag = flag


def sniff(data: bytes) -> str:
    """Return the MIME type from magic bytes; never trust the extension or declared type."""
    if data.startswith(b"%PDF-") or data[:1024].lstrip().startswith(b"%PDF-"):
        return PDF_MIME
    if data.startswith(b"PK\x03\x04"):
        return DOCX_MIME  # confirmed (or refused) by check_docx
    raise ExtractionError("unsupported_format", Flag.UNSUPPORTED_FORMAT, "not a PDF or DOCX file")


def check_size(data: bytes, limits: Limits) -> None:
    if not data:
        raise ExtractionError("corrupt", Flag.CORRUPT, "empty file")
    if len(data) > limits.max_bytes:
        raise ExtractionError("too_large", Flag.UNSUPPORTED_FORMAT, "file too large")


def check_docx(data: bytes, limits: Limits) -> None:
    """Refuse zip bombs, macro documents and ZIPs that are not Word documents."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        infos = archive.infolist()
    except (zipfile.BadZipFile, ValueError, OSError) as exc:
        raise ExtractionError("corrupt", Flag.CORRUPT, "damaged DOCX") from exc
    if len(infos) > limits.docx_max_entries:
        raise ExtractionError("zip_bomb", Flag.UNSUPPORTED_FORMAT, "too many entries")
    total = sum(i.file_size for i in infos)
    packed = sum(i.compress_size for i in infos) or 1
    if total > limits.docx_max_uncompressed or total / packed > limits.docx_max_ratio:
        raise ExtractionError("zip_bomb", Flag.UNSUPPORTED_FORMAT, "suspicious compression")
    names = {i.filename for i in infos}
    if "[Content_Types].xml" not in names or "word/document.xml" not in names:
        raise ExtractionError("unsupported_format", Flag.UNSUPPORTED_FORMAT, "not a Word document")
    content_types = archive.read("[Content_Types].xml").lower()
    if b"macroenabled" in content_types or any(n.lower().endswith("vbaproject.bin") for n in names):
        raise ExtractionError("macro_document", Flag.UNSUPPORTED_FORMAT, "macro-enabled document")
