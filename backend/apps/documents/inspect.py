"""Content inspection for uploads (P04-T03; docs/06 §3, EC-DOC-05/07/08).

Pure functions over bytes. The authoritative type check is our own signature detection for the four
accepted formats; ``python-magic`` (libmagic, Linux/Docker) adds a second opinion when installed.
Nothing here executes or renders file content beyond PyMuPDF's metadata/page-count read and Pillow's
decode for re-encoding images.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PNG_MIME = "image/png"
JPEG_MIME = "image/jpeg"

EXTENSION_MIME = {
    ".pdf": PDF_MIME,
    ".docx": DOCX_MIME,
    ".png": PNG_MIME,
    ".jpg": JPEG_MIME,
    ".jpeg": JPEG_MIME,
}

# DOCX (zip) guards against archive bombs (EC-DOC-07).
MAX_ZIP_ENTRIES = 1000
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_IMAGE_PIXELS = 40_000_000


class RejectedFileError(Exception):
    """The file must not be accepted. ``reason`` is a short machine code, never shown verbatim."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


@dataclass
class Inspection:
    mime: str
    page_count: int | None = None
    replacement: bytes | None = None  # re-encoded content to store instead (images)
    notes: list[str] = field(default_factory=list)


def sniff(data: bytes) -> str:
    """Detect the type from leading bytes; ``application/octet-stream`` when unknown."""
    head = data[:16]
    if head.startswith(b"%PDF-"):
        return PDF_MIME
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG_MIME
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG_MIME
    if head.startswith(b"PK\x03\x04"):
        return "application/zip"
    if head.startswith((b"MZ", b"\x7fELF", b"#!")):
        return "application/x-executable"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "application/x-ole-storage"  # legacy .doc/.xls (EC-DOC-04)
    return "application/octet-stream"


def libmagic_mime(data: bytes) -> str | None:
    try:
        import magic  # type: ignore[import-not-found,unused-ignore]
    except ImportError:  # Windows dev hosts: libmagic not installed
        return None
    try:
        return str(magic.from_buffer(data[:8192], mime=True))
    except Exception:
        return None


def check_docx(data: bytes) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise RejectedFileError("corrupt", "not a valid zip") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise RejectedFileError("archive_limits", "too many entries")
        total = sum(i.file_size for i in infos)
        compressed = sum(i.compress_size for i in infos) or 1
        if total > MAX_UNCOMPRESSED_BYTES or total / compressed > MAX_COMPRESSION_RATIO:
            raise RejectedFileError("archive_limits", "decompression ratio or size too large")
        names = {i.filename for i in infos}
        if "[Content_Types].xml" not in names or "word/document.xml" not in names:
            raise RejectedFileError("type_mismatch", "zip is not a Word document")
        if any(n.lower().endswith("vbaproject.bin") for n in names):
            raise RejectedFileError("macros", "macro-enabled documents are not accepted")
        if any(n.startswith("/") or ".." in n.split("/") for n in names):
            raise RejectedFileError("archive_limits", "unsafe paths in archive")
        content_types = archive.read("[Content_Types].xml")
        if b"macroEnabled" in content_types:
            raise RejectedFileError("macros", "macro-enabled documents are not accepted")


def check_pdf(data: bytes, max_pages: int | None) -> int:
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise RejectedFileError("corrupt", "unreadable PDF") from exc
    with doc:
        if doc.needs_pass or doc.is_encrypted:
            raise RejectedFileError("encrypted", "password-protected PDF")
        pages = doc.page_count
    if pages == 0:
        raise RejectedFileError("corrupt", "PDF has no pages")
    if max_pages is not None and pages > max_pages:
        raise RejectedFileError("too_many_pages", f"{pages} pages (limit {max_pages})")
    return pages


def reencode_image(data: bytes, mime: str) -> bytes:
    """Decode and re-encode, dropping EXIF/metadata and anything appended (polyglots)."""
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            out = io.BytesIO()
            if mime == PNG_MIME:
                img.save(out, format="PNG", optimize=True)
            else:
                img.convert("RGB").save(out, format="JPEG", quality=90)
    except Exception as exc:
        raise RejectedFileError("corrupt", "unreadable image") from exc
    return out.getvalue()


def inspect(data: bytes, extension: str, max_pages: int | None) -> Inspection:
    expected = EXTENSION_MIME.get(extension.lower())
    if expected is None:
        raise RejectedFileError("type_mismatch", f"unsupported extension {extension}")
    sniffed = sniff(data)
    if expected == DOCX_MIME:
        if sniffed != "application/zip":
            raise RejectedFileError("type_mismatch", f"content looks like {sniffed}")
        check_docx(data)
    elif sniffed != expected:
        raise RejectedFileError("type_mismatch", f"content looks like {sniffed}")  # EC-DOC-05
    second = libmagic_mime(data)
    if second and ("executable" in second or "x-msdownload" in second or "x-dosexec" in second):
        raise RejectedFileError("type_mismatch", f"libmagic: {second}")
    result = Inspection(mime=expected)
    if expected == PDF_MIME:
        result.page_count = check_pdf(data, max_pages)
    elif expected in (PNG_MIME, JPEG_MIME):
        result.replacement = reencode_image(data, expected)
    return result
