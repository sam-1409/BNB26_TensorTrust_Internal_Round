"""Unit tests for Fusion Engine and Verdict Determination."""

from models.schemas import Artifact, EvidenceItem, EvidenceRef, Relation
from core.fusion import compute_fusion


def test_fusion_manipulated_verdict():
    artifact = Artifact(
        id="art-1",
        modality="image",
        display_name="fake.jpg",
        sha256="hash",
        status="ok",
        metadata={},
    )

    ev1 = EvidenceItem(
        id="ev-1",
        artifact_ids=["art-1"],
        direction="manipulated",
        strength=0.85,
        reliability=0.9,
        scope="artifact",
        evidence_ref=EvidenceRef(type="region", value="metadata"),
        description="Deepfake synthesis detected",
        source="detector",
        check_id="CHK_IMG_DEEPFAKE",
    )

    # Provide multiple reliable evidence items to pass sufficiency tau_s
    items = [ev1] * 5

    fusion = compute_fusion([artifact], items, [])

    assert fusion.verdict == "MANIPULATED"
    assert fusion.manip_evidence > 0.65
    assert fusion.confidence_level in ("medium", "high")


def test_fusion_inconclusive_low_sufficiency():
    artifact = Artifact(
        id="art-1",
        modality="image",
        display_name="low_quality.jpg",
        sha256="hash",
        status="ok",
        metadata={},
    )

    # Only 1 item, sufficiency < tau_s (0.40)
    ev1 = EvidenceItem(
        id="ev-1",
        artifact_ids=["art-1"],
        direction="authentic",
        strength=0.5,
        reliability=0.5,
        scope="artifact",
        evidence_ref=EvidenceRef(type="region", value="metadata"),
        description="Weak signal",
        source="detector",
        check_id="CHK_IMG_WEAK",
    )

    fusion = compute_fusion([artifact], [ev1], [])

    assert fusion.verdict == "INCONCLUSIVE"
    assert fusion.inconclusive_label is not None
    assert fusion.confidence_level == "low"
