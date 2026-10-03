"""Unit tests for HTML Report Service."""

from models.schemas import Case, Fusion, Artifact
from services.report import generate_report_html, save_report_html
from services.storage import StorageManager, delete_case


def test_generate_report_html_escaping():
    fusion = Fusion(
        manip_evidence=0.85,
        auth_support=0.1,
        sufficiency=0.8,
        checks_completed=8,
        checks_applicable=10,
        verdict="MANIPULATED",
        reason_codes=["SYNTHETIC_ARTIFACT"],
        confidence_level="high",
        limitations=["Test limitation statement"],
    )

    artifact = Artifact(
        id="art-1",
        modality="text",
        display_name="<script>alert('xss')</script>.txt",  # XSS payload
        sha256="hash",
        status="ok",
        metadata={},
    )

    case = Case(
        id="case_xss_test",
        description="XSS Escape test case",
        job_status="completed",
        artifacts=[artifact],
        relations=[],
        fusion=fusion,
    )

    html = generate_report_html(case)

    assert "<script>alert('xss')</script>" not in html
    assert "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in html or "&lt;script&gt;" in html
    assert "MANIPULATED" in html


def test_save_report_html():
    session_id = "test_report_save_session"
    storage = StorageManager(session_id)

    fusion = Fusion(
        manip_evidence=0.1,
        auth_support=0.9,
        sufficiency=0.8,
        checks_completed=8,
        checks_applicable=10,
        verdict="AUTHENTIC",
        reason_codes=[],
        confidence_level="high",
    )

    case = Case(
        id=session_id,
        job_status="completed",
        artifacts=[],
        relations=[],
        fusion=fusion,
    )

    report_path = save_report_html(case, storage.derived_dir)

    assert report_path.exists()
    assert report_path.name.endswith(".html")
    assert "AUTHENTIC" in report_path.read_text(encoding="utf-8")

    delete_case(session_id)
