"""End-to-end integration tests for Orchestrator run_case."""

import pytest
from models.schemas import CaseInput
from core.orchestrator import run_case, delete_case


def test_run_case_full_pipeline():
    case_id = "test_orch_case_001"
    events = []

    def on_progress(event):
        events.append(event)

    case_input = CaseInput(
        case_id=case_id,
        files=[
            {"filename": "photo.jpg", "bytes": b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01"},
            {"filename": "doc.txt", "bytes": b"This document was published in year 2026."},
        ],
        description="Investigation test case",
    )

    result = run_case(case_input, on_progress=on_progress)

    assert result.case.job_status == "completed"
    assert len(result.case.artifacts) == 2
    assert result.case.fusion is not None
    assert result.case.fusion.verdict in ("AUTHENTIC", "MANIPULATED", "COORDINATED_SYNTHETIC", "INCONCLUSIVE")
    assert len(events) >= 5

    delete_case(case_id)
