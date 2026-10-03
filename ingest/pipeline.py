"""Ingest stage pipeline for TrustLayers (T²).

Orchestrates file validation, magic-byte type detection, SHA-256 calculation,
generated-name storage, and exact duplicate collapsing.

Enforces:
- R-UP-01, R-UP-02, R-UP-03, R-UP-04, R-UP-06, R-UP-07.
"""

from typing import List, Dict, Any, Tuple
from models.schemas import Artifact, Case
from ingest.type_verifier import detect_content_type, IngestValidationError
from ingest.hasher import compute_sha256, process_duplicates
from ingest.limits import validate_case_file_count, validate_file_size
from services.storage import StorageManager


def ingest_files(
    session_id: str,
    files: List[Dict[str, Any]],
    storage_manager: StorageManager,
) -> Tuple[List[Artifact], List[str]]:
    """Ingest uploaded files into session storage and build initial Artifact schemas.

    Args:
        session_id: Case session ID.
        files: List of file objects containing 'filename' and 'bytes'.
        storage_manager: Active StorageManager instance for session.

    Returns:
        Tuple of (list_of_artifacts, list_of_notice_messages)

    Raises:
        IngestValidationError: If file count limit exceeded or all files fail ingest.
    """
    validate_case_file_count(len(files))

    raw_artifacts: List[Artifact] = []
    notices: List[str] = []

    for item in files:
        display_name = item.get("filename", "unnamed_file")
        file_bytes = item.get("bytes", b"")

        try:
            # Enforce size limit
            validate_file_size(len(file_bytes), display_name)

            # Detect content MIME and modality strictly from magic bytes (R-UP-01)
            mime_type, modality = detect_content_type(file_bytes, display_name)

            # Calculate SHA-256 hash (R-UP-06)
            sha256_hash = compute_sha256(file_bytes)

            # Determine extension
            ext = display_name.split(".")[-1] if "." in display_name else ""

            # Save bytes under generated filename (R-UP-04)
            art_id, file_path = storage_manager.save_upload_bytes(file_bytes, ext)

            # Construct valid pending artifact
            artifact = Artifact(
                id=art_id,
                modality=modality,
                display_name=display_name,
                sha256=sha256_hash,
                status="pending",
                error_code=None,
                metadata={
                    "mime_type": mime_type,
                    "size_bytes": len(file_bytes),
                    "file_path": str(file_path),
                },
            )
            raw_artifacts.append(artifact)

        except IngestValidationError as err:
            # R-UP-02: Rejecting one artifact never stops the others
            rejected_art = Artifact(
                id=f"art_rejected_{len(raw_artifacts)}",
                modality="image",  # fallback for schema
                display_name=display_name,
                sha256="",
                status="rejected",
                error_code=err.error_code,
                metadata={"rejection_reason": err.message},
            )
            raw_artifacts.append(rejected_art)
            notices.append(f"Rejected '{display_name}': {err.message} ({err.error_code})")

    # Collapse exact duplicates (R-UP-06)
    artifacts, dup_notices = process_duplicates(raw_artifacts)
    notices.extend(dup_notices)

    # R-UP-07: A case fails only when every artifact fails or is rejected
    valid_count = sum(1 for a in artifacts if a.status in ("pending", "ok", "duplicate"))
    if valid_count == 0:
        raise IngestValidationError("EMPTY_CONTENT", "All uploaded artifacts were rejected or empty.")

    return artifacts, notices
