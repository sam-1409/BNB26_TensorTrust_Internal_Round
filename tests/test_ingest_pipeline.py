"""Unit tests for ingest stage pipeline."""

import pytest
from services.storage import StorageManager, delete_case
from ingest.pipeline import ingest_files
from ingest.type_verifier import IngestValidationError


def test_ingest_files_pipeline():
    session_id = "test_ingest_session"
    storage_manager = StorageManager(session_id)

    files = [
        {"filename": "test1.jpg", "bytes": b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01"},
        {"filename": "test2.png", "bytes": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"},
        {"filename": "bad.exe", "bytes": b"MZ\x90\x00\x03\x00\x00\x00\x04\x00"},
        {"filename": "dup.jpg", "bytes": b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01"},  # Exact duplicate of test1
    ]

    artifacts, notices = ingest_files(session_id, files, storage_manager)

    assert len(artifacts) == 4
    assert artifacts[0].status == "pending"
    assert artifacts[0].modality == "image"
    assert artifacts[1].status == "pending"
    assert artifacts[1].modality == "image"
    assert artifacts[2].status == "rejected"
    assert artifacts[2].error_code == "UNSUPPORTED_TYPE"
    assert artifacts[3].status == "duplicate"

    assert any("UNSUPPORTED_TYPE" in n for n in notices)
    assert any("exact duplicate" in n for n in notices)

    delete_case(session_id)


def test_ingest_files_all_rejected_raises():
    session_id = "test_all_reject_session"
    storage_manager = StorageManager(session_id)

    files = [
        {"filename": "bad1.exe", "bytes": b"\x7F\x45\x4C\x46\x01\x01\x01\x00\x00\x00\x00\x00"},
        {"filename": "bad2.bin", "bytes": b"\x00\x01\x02\x03\x04\x05\xFF\xFE"},
    ]

    with pytest.raises(IngestValidationError) as exc:
        ingest_files(session_id, files, storage_manager)
    assert exc.value.error_code == "EMPTY_CONTENT"

    delete_case(session_id)
