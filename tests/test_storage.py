"""Unit tests for StorageManager and session persistence."""

import os
from pathlib import Path
from services.storage import StorageManager, delete_case
from models.schemas import Case


def test_storage_manager_lifecycle():
    session_id = "test_session_001"
    manager = StorageManager(session_id)

    # Check directory creation
    assert manager.session_dir.exists()
    assert manager.files_dir.exists()

    # Save file bytes under generated filename (R-UP-04)
    art_id, file_path = manager.save_upload_bytes(b"dummy image bytes", ".jpg")
    assert art_id.startswith("art_")
    assert file_path.exists()
    assert "dummy image bytes" in file_path.read_bytes().decode("latin1")

    # Save case state to SQLite
    case = Case(
        id="case-001",
        description="Test case for storage",
        job_status="ingesting",
        artifacts=[],
        relations=[],
    )
    manager.save_case_state(case)

    # Retrieve case state from SQLite
    retrieved = manager.get_case_state("case-001")
    assert retrieved is not None
    assert retrieved.id == "case-001"
    assert retrieved.description == "Test case for storage"

    # Delete session (R-DATA-04)
    delete_case(session_id)
    assert not manager.session_dir.exists()
