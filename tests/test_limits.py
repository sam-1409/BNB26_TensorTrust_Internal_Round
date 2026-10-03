"""Unit tests for limits enforcer."""

import pytest
from ingest.limits import (
    validate_case_file_count,
    validate_file_size,
    validate_pdf_pages,
)
from ingest.type_verifier import IngestValidationError
from core.config import MAX_FILE_SIZE_BYTES, MAX_FILES_PER_CASE, MAX_PDF_PAGES


def test_validate_case_file_count_valid():
    validate_case_file_count(5)  # Should not raise


def test_validate_case_file_count_exceeded():
    with pytest.raises(IngestValidationError) as exc:
        validate_case_file_count(MAX_FILES_PER_CASE + 1)
    assert exc.value.error_code == "LIMIT_EXCEEDED"


def test_validate_file_size_exceeded():
    with pytest.raises(IngestValidationError) as exc:
        validate_file_size(MAX_FILE_SIZE_BYTES + 100)
    assert exc.value.error_code == "LIMIT_EXCEEDED"


def test_validate_pdf_pages_exceeded():
    with pytest.raises(IngestValidationError) as exc:
        validate_pdf_pages(MAX_PDF_PAGES + 1)
    assert exc.value.error_code == "LIMIT_EXCEEDED"
