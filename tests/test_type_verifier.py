"""Unit tests for magic-byte content verification."""

import pytest
from ingest.type_verifier import detect_content_type, IngestValidationError


def test_detect_jpeg():
    header = b"\xFF\xD8\xFF\xE0\x00\x10JFIF"
    mime, modality = detect_content_type(header)
    assert mime == "image/jpeg"
    assert modality == "image"


def test_detect_png():
    header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    mime, modality = detect_content_type(header)
    assert mime == "image/png"
    assert modality == "image"


def test_detect_pdf():
    header = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
    mime, modality = detect_content_type(header)
    assert mime == "application/pdf"
    assert modality == "document"


def test_detect_text():
    text_content = b"This is a sample plain text artifact file for analysis."
    mime, modality = detect_content_type(text_content)
    assert mime == "text/plain"
    assert modality == "text"


def test_reject_empty_file():
    with pytest.raises(IngestValidationError) as exc_info:
        detect_content_type(b"")
    assert exc_info.value.error_code == "EMPTY_CONTENT"


def test_reject_unsupported_binary():
    random_binary = b"\x7F\x45\x4C\x46\x02\x01\x01\x00\x00\x00\x00\x00"
    with pytest.raises(IngestValidationError) as exc_info:
        detect_content_type(random_binary)
    assert exc_info.value.error_code == "UNSUPPORTED_TYPE"
