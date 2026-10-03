"""Limits enforcer module for TrustLayers (T²).

Enforces RULE R-UP-03:
- Enforce size, count, duration, page, and dimension limits before any preprocessing.
- Limits live ONLY in core/config.py.
- Breaches raise IngestValidationError with error_code 'LIMIT_EXCEEDED'.
"""

from typing import List
from core.config import (
    MAX_FILE_SIZE_BYTES,
    MAX_FILES_PER_CASE,
    MAX_PDF_PAGES,
)
from ingest.type_verifier import IngestValidationError


def validate_case_file_count(file_count: int) -> None:
    """Enforce maximum files per case limit."""
    if file_count > MAX_FILES_PER_CASE:
        raise IngestValidationError(
            "LIMIT_EXCEEDED",
            f"File count ({file_count}) exceeds maximum allowed ({MAX_FILES_PER_CASE})"
        )


def validate_file_size(size_bytes: int, display_name: str = "File") -> None:
    """Enforce file size limit."""
    if size_bytes > MAX_FILE_SIZE_BYTES:
        max_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
        size_mb = size_bytes / (1024 * 1024)
        raise IngestValidationError(
            "LIMIT_EXCEEDED",
            f"File '{display_name}' size ({size_mb:.1f} MB) exceeds maximum allowed ({max_mb:.1f} MB)"
        )


def validate_pdf_pages(page_count: int, display_name: str = "PDF") -> None:
    """Enforce PDF page count limit."""
    if page_count > MAX_PDF_PAGES:
        raise IngestValidationError(
            "LIMIT_EXCEEDED",
            f"PDF '{display_name}' page count ({page_count}) exceeds limit ({MAX_PDF_PAGES})"
        )
