"""Unit tests for Grounding Verifier."""

from models.schemas import Artifact, EvidenceItem, EvidenceRef, Relation
from reasoning.grounding import verify_evidence_ref, filter_grounded_evidence, filter_grounded_relations


def test_verify_evidence_ref_valid():
    artifact = Artifact(
        id="art-001",
        modality="image",
        display_name="photo.jpg",
        sha256="hash",
        status="ok",
        metadata={"width": 1920, "height": 1080},
    )

    ref_valid = EvidenceRef(type="region", value="100,100,500,500")
    assert verify_evidence_ref(ref_valid, artifact) is True

    ref_metadata = EvidenceRef(type="region", value="metadata")
    assert verify_evidence_ref(ref_metadata, artifact) is True


def test_verify_evidence_ref_unresolvable():
    artifact = Artifact(
        id="art-doc-001",
        modality="document",
        display_name="paper.pdf",
        sha256="hash",
        status="ok",
        metadata={"page_count": 5},
    )

    ref_invalid_page = EvidenceRef(type="page", value="99")
    assert verify_evidence_ref(ref_invalid_page, artifact) is False


def test_filter_grounded_evidence():
    artifact = Artifact(
        id="art-video",
        modality="video",
        display_name="clip.mp4",
        sha256="hash",
        status="ok",
        metadata={"duration_seconds": 30.0},
    )

    valid_ev = EvidenceItem(
        id="ev-1",
        artifact_ids=["art-video"],
        direction="manipulated",
        strength=0.8,
        reliability=0.9,
        scope="artifact",
        evidence_ref=EvidenceRef(type="timestamp", value="15.0"),
        description="Deepfake audio detected at 15s",
        source="detector",
        check_id="CHK_AUD_DEEPFAKE",
    )

    invalid_ev = EvidenceItem(
        id="ev-2",
        artifact_ids=["art-video"],
        direction="manipulated",
        strength=0.8,
        reliability=0.9,
        scope="artifact",
        evidence_ref=EvidenceRef(type="timestamp", value="999.0"),  # Exceeds duration
        description="Invalid timestamp evidence",
        source="detector",
        check_id="CHK_AUD_DEEPFAKE",
    )

    grounded, rejections = filter_grounded_evidence([artifact], [valid_ev, invalid_ev])
    assert len(grounded) == 1
    assert grounded[0].id == "ev-1"
    assert rejections == 1
