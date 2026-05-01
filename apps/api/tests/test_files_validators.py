"""Magic-byte mime sniff + extension cross-check."""
from app.files.validators import (
    MAX_BYTE_SIZE,
    sniff_mime,
    validate_extension_matches,
)


def test_sniff_mime_pdf():
    assert sniff_mime(b"%PDF-1.7\n%abc") == "application/pdf"


def test_sniff_mime_png():
    assert sniff_mime(b"\x89PNG\r\n\x1a\n\x00\x00") == "image/png"


def test_sniff_mime_jpeg():
    assert sniff_mime(b"\xFF\xD8\xFF\xE0\x00\x10JFIF") == "image/jpeg"


def test_sniff_mime_unknown_returns_none():
    assert sniff_mime(b"<svg xmlns=") is None
    assert sniff_mime(b"PK\x03\x04") is None  # zip / docx


def test_extension_matches_pdf():
    assert validate_extension_matches("kitchen.pdf", "application/pdf") is True


def test_extension_matches_png():
    assert validate_extension_matches("photo.png", "image/png") is True
    assert validate_extension_matches("photo.PNG", "image/png") is True


def test_extension_matches_jpeg_both_spellings():
    assert validate_extension_matches("a.jpg", "image/jpeg") is True
    assert validate_extension_matches("a.jpeg", "image/jpeg") is True


def test_extension_mismatch():
    assert validate_extension_matches("a.png", "application/pdf") is False
    assert validate_extension_matches("noext", "application/pdf") is False


def test_max_byte_size_is_25mb():
    assert MAX_BYTE_SIZE == 25 * 1024 * 1024


def test_sniff_mime_empty_bytes_returns_none():
    """Empty input is safely rejected."""
    assert sniff_mime(b"") is None


def test_sniff_mime_truncated_png_returns_none():
    """Input shorter than the PNG signature (8 bytes) cannot match PNG."""
    assert sniff_mime(b"\x89PNG") is None  # only 4 bytes; PNG needs 8
