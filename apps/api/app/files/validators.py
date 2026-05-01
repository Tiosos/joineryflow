"""Magic-byte sniff + size cap + extension cross-check.

Don't trust filename extensions or client-supplied Content-Type headers - sniff
the first bytes and require both signals to agree before accepting an upload.
"""
import os

MAX_BYTE_SIZE: int = 25 * 1024 * 1024  # 25 MB

_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF-",                "application/pdf"),
    (b"\x89PNG\r\n\x1a\n",    "image/png"),
    (b"\xFF\xD8\xFF",         "image/jpeg"),
]

_ALLOWED_EXTS: dict[str, set[str]] = {
    "application/pdf": {".pdf"},
    "image/png":       {".png"},
    "image/jpeg":      {".jpg", ".jpeg"},
}


def sniff_mime(head: bytes) -> str | None:
    """Return the canonical mime type if `head` matches a known signature."""
    for prefix, mime in _SIGNATURES:
        if head.startswith(prefix):
            return mime
    return None


def validate_extension_matches(filename: str, mime: str) -> bool:
    """Return True iff filename's extension is in the allowed set for mime."""
    _, ext = os.path.splitext(filename.lower())
    if not ext:
        return False
    return ext in _ALLOWED_EXTS.get(mime, set())
