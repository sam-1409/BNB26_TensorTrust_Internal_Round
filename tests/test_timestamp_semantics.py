"""Unit tests for Phase 0 Timestamp Semantics (Constraint #15).

Verifies:
- EXIF timestamp vs text date mismatch does NOT produce a CONTRADICTS relation.
- Mismatches are classified as UNCERTAIN (low confidence) provenance context.
- Legitimate re-publication, voice-over, metadata editing, and format conversions
  do not result in a MANIPULATED verdict.
- Matching dates produce SUPPORTS.
- Bidirectional pair ordering (image-text and text-image) works identically.
"""

from models.schemas import Artifact, Relation, EvidenceItem, EvidenceRef
from reasoning.deterministic_checks import run_deterministic_pair_checks
from core.fusion import compute_fusion


def test_exif_mismatch_produces_uncertain_relation():
    img_art = Artifact(
        id="art-img-1",
        modality="image",
        display_name="captured_2021.jpg",
        sha256="hash1",
        status="ok",
        metadata={
            "exif": {
                "DateTimeOriginal": "2021:05:12 14:30:00",
                "DateTime": "2021:05:12 14:30:00",
            }
        },
    )

    txt_art = Artifact(
        id="art-txt-1",
        modality="text",
        display_name="article_2024.txt",
        sha256="hash2",
        status="ok",
        metadata={
            "text_content": "The press release was announced in November 2024 following the summit.",
        },
    )

    relations = run_deterministic_pair_checks([img_art, txt_art])

    assert len(relations) == 1
    rel = relations[0]
    assert rel.relation == "UNCERTAIN"
    assert rel.conflict_type == "time"
    assert rel.confidence_level == "low"
    assert rel.method == "deterministic"
    assert "Temporal difference detected" in rel.explanation
    assert "never as manipulation or AI generation evidence" in rel.explanation


def test_exif_match_produces_supports_relation():
    img_art = Artifact(
        id="art-img-1",
        modality="image",
        display_name="event_2023.jpg",
        sha256="hash1",
        status="ok",
        metadata={
            "exif": {
                "DateTimeOriginal": "2023:10:15 09:00:00",
            }
        },
    )

    txt_art = Artifact(
        id="art-txt-1",
        modality="text",
        display_name="report_2023.txt",
        sha256="hash2",
        status="ok",
        metadata={
            "text_content": "The conference took place in autumn of 2023.",
        },
    )

    relations = run_deterministic_pair_checks([img_art, txt_art])

    assert len(relations) == 1
    rel = relations[0]
    assert rel.relation == "SUPPORTS"
    assert rel.conflict_type is None
    assert rel.confidence_level == "medium"
    assert "matches timeline" in rel.explanation


def test_bidirectional_pair_ordering():
    img_art = Artifact(
        id="art-img-1",
        modality="image",
        display_name="photo.jpg",
        sha256="hash1",
        status="ok",
        metadata={"exif": {"DateTimeOriginal": "2022:01:01 12:00:00"}},
    )
    txt_art = Artifact(
        id="art-txt-1",
        modality="text",
        display_name="doc.txt",
        sha256="hash2",
        status="ok",
        metadata={"text_content": "Document created in 2025."},
    )

    # Order 1: image first, then text
    rels_1 = run_deterministic_pair_checks([img_art, txt_art])
    # Order 2: text first, then image
    rels_2 = run_deterministic_pair_checks([txt_art, img_art])

    assert len(rels_1) == 1
    assert len(rels_2) == 1
    assert rels_1[0].relation == rels_2[0].relation == "UNCERTAIN"
    assert rels_1[0].conflict_type == rels_2[0].conflict_type == "time"


def test_timestamp_mismatch_alone_does_not_produce_manipulated():
    img_art = Artifact(
        id="art-img-1",
        modality="image",
        display_name="repost.jpg",
        sha256="hash1",
        status="ok",
        metadata={"exif": {"DateTimeOriginal": "2019:08:20 18:00:00"}},
    )
    txt_art = Artifact(
        id="art-txt-1",
        modality="text",
        display_name="post_2024.txt",
        sha256="hash2",
        status="ok",
        metadata={"text_content": "Shared again in 2024."},
    )

    relations = run_deterministic_pair_checks([img_art, txt_art])
    assert len(relations) == 1
    assert relations[0].relation == "UNCERTAIN"

    # Compute fusion with no manipulation evidence items
    fusion = compute_fusion(
        artifacts=[img_art, txt_art],
        evidence_items=[],
        relations=relations,
    )

    # Crucial constraint: must NOT be MANIPULATED
    assert fusion.verdict != "MANIPULATED"
    assert fusion.manip_evidence == 0.0
    assert "CROSS_MODAL_CONTRADICTION" not in fusion.reason_codes
    assert fusion.verdict == "INCONCLUSIVE"


def test_legitimate_republication_scenario():
    """Simulate recording/capture in 2020, converted/published in 2024.
    
    Even if an authentic credential exists (e.g. C2PA), the date discrepancy
    must never negate authenticity or trigger a manipulation verdict.
    """
    img_art = Artifact(
        id="art-img-1",
        modality="image",
        display_name="historical.jpg",
        sha256="hash1",
        status="ok",
        metadata={"exif": {"DateTimeOriginal": "2020:03:01 10:00:00"}},
    )
    txt_art = Artifact(
        id="art-txt-1",
        modality="text",
        display_name="syndicated_2024.txt",
        sha256="hash2",
        status="ok",
        metadata={"text_content": "Syndicated article published in 2024."},
    )

    relations = run_deterministic_pair_checks([img_art, txt_art])

    # Provide authentic evidence (C2PA)
    auth_ev = EvidenceItem(
        id="ev-c2pa-1",
        artifact_ids=["art-img-1"],
        direction="authentic",
        strength=0.85,
        reliability=0.95,
        scope="artifact",
        evidence_ref=EvidenceRef(type="region", value="metadata"),
        description="Valid C2PA credential",
        source="forensic",
        check_id="CHK_IMG_C2PA_VALID",
    )

    fusion = compute_fusion(
        artifacts=[img_art, txt_art],
        evidence_items=[auth_ev],
        relations=relations,
    )

    # Must NEVER be manipulated solely due to date difference
    assert fusion.verdict != "MANIPULATED"
    assert fusion.manip_evidence == 0.0
    assert "CROSS_MODAL_CONTRADICTION" not in fusion.reason_codes
