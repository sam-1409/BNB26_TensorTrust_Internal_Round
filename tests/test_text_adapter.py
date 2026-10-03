"""Unit tests for Text and PDF Document Adapters."""

import pytest
from PIL import Image
from models.schemas import Artifact
from adapters.text import analyze_text_file, analyze_pdf_document
from services.storage import StorageManager, delete_case

fitz = pytest.importorskip("fitz")


def test_analyze_text_file():
    session_id = "test_text_adapter_session"
    storage = StorageManager(session_id)

    txt_path = storage.files_dir / "sample.txt"
    txt_path.write_text("This is a sample document for authenticity investigation.", encoding="utf-8")

    artifact = Artifact(
        id="art_txt_001",
        modality="text",
        display_name="sample.txt",
        sha256="dummyhash",
        status="pending",
        metadata={"mime_type": "text/plain"},
    )

    updated_art, evidence = analyze_text_file(artifact, txt_path)

    assert updated_art.status == "ok"
    char_count = updated_art.metadata.get("char_count")
    assert char_count is not None and char_count > 0
    assert updated_art.reliability is not None

    delete_case(session_id)


def test_analyze_pdf_document():
    session_id = "test_pdf_adapter_session"
    storage = StorageManager(session_id)

    # Create a small valid PDF file using PyMuPDF
    pdf_path = storage.files_dir / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "TrustLayers PDF Test Page 1")
    doc.save(pdf_path)
    doc.close()

    artifact = Artifact(
        id="art_pdf_001",
        modality="document",
        display_name="sample.pdf",
        sha256="pdfhash",
        status="pending",
        metadata={"mime_type": "application/pdf"},
    )

    updated_art, evidence = analyze_pdf_document(artifact, pdf_path)

    assert updated_art.status == "ok"
    assert updated_art.metadata.get("page_count") == 1
    assert "TrustLayers PDF Test" in updated_art.metadata.get("text_content", "")

    delete_case(session_id)
