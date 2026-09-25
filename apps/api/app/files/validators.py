"""Magic-byte sniff + size cap + extension cross-check.

Don't trust filename extensions or client-supplied Content-Type headers - sniff
the first bytes and require both signals to agree before accepting an upload.
"""
import os

MAX_BYTE_SIZE: int = 25 * 1024 * 1024  # 25 MB

SKP_MIME = "application/vnd.sketchup.skp"
CVJ_MIME = "application/x-cabinet-vision-job"

_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF-",                "application/pdf"),
    (b"\x89PNG\r\n\x1a\n",    "image/png"),
    (b"\xFF\xD8\xFF",         "image/jpeg"),
    (b"\xFF\xFE\xFF\x0E",     SKP_MIME),  # SketchUp 2021+ versioned file format
]

# An OLE compound document says nothing about what it holds: pre-2021 SketchUp
# and Cabinet Vision jobs both use it (as do .doc / .xls / .msi). The extension
# picks between the two we accept; any other name is refused.
_OLE_SIGNATURE = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"
_OLE_MIME_BY_EXT: dict[str, str] = {".skp": SKP_MIME, ".cvj": CVJ_MIME}

_ALLOWED_EXTS: dict[str, set[str]] = {
    "application/pdf": {".pdf"},
    "image/png":       {".png"},
    "image/jpeg":      {".jpg", ".jpeg"},
    SKP_MIME:          {".skp"},
    CVJ_MIME:          {".cvj"},
}


def sniff_mime(head: bytes, filename: str = "") -> str | None:
    """Return the canonical mime type if ``head`` matches a known signature.

    ``head`` must be at least 8 bytes (the longest signatures are 8 bytes);
    pass more (e.g. 16) for a safety margin. ``filename`` is consulted only to
    tell apart the formats that share the OLE signature. Returns None for
    unrecognised, truncated, or empty input.
    """
    for prefix, mime in _SIGNATURES:
        if head.startswith(prefix):
            return mime
    if head.startswith(_OLE_SIGNATURE):
        _, ext = os.path.splitext(filename.lower())
        return _OLE_MIME_BY_EXT.get(ext)
    return None


def validate_extension_matches(filename: str, mime: str) -> bool:
    """Return True iff filename's extension is in the allowed set for mime.

    Returns False for unrecognised mime types (treats them as never-allowed).
    Filename matching is case-insensitive.
    """
    _, ext = os.path.splitext(filename.lower())
    if not ext:
        return False
    return ext in _ALLOWED_EXTS.get(mime, set())
