"""Session storage manager and SQLite working store for TrustLayers (T²).

Enforces:
- R-UP-04: Store uploads under generated names inside session directory. User filename is never used in paths.
- R-DATA-04: 'Delete case' removes every derived item and session directory immediately.
- SQLite working store for case state, artifacts, evidence, relations, and fusion results.
"""

import os
import shutil
import sqlite3
import uuid
import time
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

from core.config import SESSIONS_DIR
from models.schemas import Case


class StorageManager:
    """Manages session directories and SQLite working store for a single case session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.session_dir = SESSIONS_DIR / session_id
        self.files_dir = self.session_dir / "files"
        self.derived_dir = self.session_dir / "derived"
        self.db_path = self.session_dir / "working_store.db"

        # Ensure session directory structure exists
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.derived_dir.mkdir(parents=True, exist_ok=True)
        self._init_sqlite()

    def _init_sqlite(self) -> None:
        """Initialize SQLite working store schema."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS case_store (
                    case_id TEXT PRIMARY KEY,
                    job_status TEXT NOT NULL,
                    case_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def save_upload_bytes(self, file_bytes: bytes, extension: str) -> Tuple[str, Path]:
        """Save file bytes under a generated filename (R-UP-04).

        Args:
            file_bytes: Raw file content bytes.
            extension: File extension (e.g. '.jpg', '.mp4', '.pdf').

        Returns:
            Tuple of (generated_artifact_id, file_path_on_disk)
        """
        artifact_id = f"art_{uuid.uuid4().hex[:12]}"
        clean_ext = extension.lstrip(".")
        generated_filename = f"{artifact_id}.{clean_ext}" if clean_ext else artifact_id
        file_path = self.files_dir / generated_filename

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        return artifact_id, file_path

    def save_case_state(self, case: Case) -> None:
        """Persist Case Pydantic model to SQLite working store."""
        case_json = case.model_dump_json()
        now = time.time()
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO case_store (case_id, job_status, case_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(case_id) DO UPDATE SET
                    job_status = excluded.job_status,
                    case_json = excluded.case_json,
                    updated_at = excluded.updated_at
            """, (case.id, case.job_status, case_json, now, now))
            conn.commit()
        finally:
            conn.close()

    def get_case_state(self, case_id: str) -> Optional[Case]:
        """Retrieve Case Pydantic model from SQLite working store."""
        if not self.db_path.exists():
            return None
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT case_json FROM case_store WHERE case_id = ?", (case_id,))
            row = cursor.fetchone()
            if row:
                return Case.model_validate_json(row[0])
        finally:
            conn.close()
        return None

    def delete_session(self) -> None:
        """Immediately delete session directory and all contents (R-DATA-04)."""
        if self.session_dir.exists():
            shutil.rmtree(self.session_dir, ignore_errors=True)


def delete_case(session_id: str) -> None:
    """Global convenience function to delete a session directory (R-DATA-04)."""
    manager = StorageManager(session_id)
    manager.delete_session()


def sweep_stale_sessions(max_age_hours: int = 24) -> List[str]:
    """Sweeper that deletes sessions older than max_age_hours.

    Returns:
        List of deleted session IDs.
    """
    deleted_sessions: List[str] = []
    if not SESSIONS_DIR.exists():
        return deleted_sessions

    now = time.time()
    max_age_seconds = max_age_hours * 3600

    for item in SESSIONS_DIR.iterdir():
        if item.is_dir():
            try:
                mtime = item.stat().st_mtime
                if (now - mtime) > max_age_seconds:
                    shutil.rmtree(item, ignore_errors=True)
                    deleted_sessions.append(item.name)
            except Exception:
                pass

    return deleted_sessions
