"""Unit tests for Phase 0 Dynamic Check Catalog and Sufficiency Calculation.

Verifies:
- Single-image case gets 2 applicable checks (CHK_IMG_EXIF_SOFTWARE, CHK_IMG_C2PA_VALID).
- Image + text case gets 4 applicable checks.
- Full multimodal case gets 8 applicable checks.
- Two images case gets 3 applicable checks (including CHK_COORD_PERCEPTUAL).
- Unsupported modality checks are not counted against artifacts.
- Disabled checks (enabled=False) are not counted.
- Dynamic applicable-check count is reflected correctly in fusion/sufficiency logic.
"""

from models.schemas import Artifact, EvidenceItem, EvidenceRef
from core.fusion import compute_applicable_checks, compute_fusion
from core.config import CHECK_CATALOG


def _make_art(art_id: str, modality: str) -> Artifact:
    return Artifact(
        id=art_id,
        modality=modality,
        display_name=f"{art_id}.{modality}",
        sha256=f"hash_{art_id}",
        status="ok",
        metadata={},
    )


def test_single_image_applicable_checks():
    img = _make_art("img-1", "image")
    count = compute_applicable_checks([img])
    # CHK_IMG_EXIF_SOFTWARE, CHK_IMG_C2PA_VALID
    assert count == 2


def test_image_plus_text_applicable_checks():
    img = _make_art("img-1", "image")
    txt = _make_art("txt-1", "text")
    count = compute_applicable_checks([img, txt])
    # CHK_IMG_EXIF_SOFTWARE, CHK_IMG_C2PA_VALID, CHK_CROSS_DATE, CHK_CROSS_CAPTION
    assert count == 4


def test_two_images_applicable_checks():
    img1 = _make_art("img-1", "image")
    img2 = _make_art("img-2", "image")
    count = compute_applicable_checks([img1, img2])
    # CHK_IMG_EXIF_SOFTWARE, CHK_IMG_C2PA_VALID, CHK_COORD_PERCEPTUAL (requires >= 2 images)
    assert count == 3


def test_single_audio_applicable_checks():
    aud = _make_art("aud-1", "audio")
    count = compute_applicable_checks([aud])
    # CHK_AUDIO_ASR
    assert count == 1


def test_single_document_applicable_checks():
    doc = _make_art("doc-1", "document")
    count = compute_applicable_checks([doc])
    # CHK_TXT_PDF_PROVENANCE
    assert count == 1


def test_full_multimodal_applicable_checks():
    arts = [
        _make_art("img-1", "image"),
        _make_art("img-2", "image"),
        _make_art("vid-1", "video"),
        _make_art("aud-1", "audio"),
        _make_art("txt-1", "text"),
        _make_art("doc-1", "document"),
    ]
    count = compute_applicable_checks(arts)
    # All 8 catalog checks applicable:
    # CHK_IMG_EXIF_SOFTWARE, CHK_IMG_C2PA_VALID, CHK_COORD_PERCEPTUAL,
    # CHK_TXT_PDF_PROVENANCE, CHK_AUDIO_ASR, CHK_CROSS_DATE,
    # CHK_CROSS_CAPTION, CHK_CROSS_AV_SYNC
    assert count == 8


def test_unsupported_modality_checks_not_counted():
    """Verify that video, audio, and cross-modality checks do not count against an image-only case."""
    img = _make_art("img-1", "image")
    count = compute_applicable_checks([img])
    assert count == 2
    assert count < len(CHECK_CATALOG)


def test_disabled_checks_not_counted():
    img = _make_art("img-1", "image")
    txt = _make_art("txt-1", "text")

    # Custom catalog where CHK_CROSS_CAPTION is disabled
    custom_catalog = {
        "CHK_IMG_EXIF_SOFTWARE": {"modalities": ["image"], "min_artifacts": 1, "enabled": True},
        "CHK_CROSS_CAPTION": {"modalities": ["image", "text"], "min_artifacts": 2, "enabled": False},
    }

    count = compute_applicable_checks([img, txt], catalog=custom_catalog)
    # Only CHK_IMG_EXIF_SOFTWARE should be counted
    assert count == 1


def test_empty_artifacts_and_zero_division_protection():
    count = compute_applicable_checks([])
    assert count == 0

    fusion = compute_fusion([], [], [])
    assert fusion.sufficiency == 0.0
    assert fusion.checks_applicable == 0
    assert fusion.verdict == "INCONCLUSIVE"


def test_dynamic_check_sufficiency_calculation():
    img = _make_art("img-1", "image")
    ev1 = EvidenceItem(
        id="ev-1",
        artifact_ids=["img-1"],
        direction="authentic",
        strength=0.85,
        reliability=0.9,
        scope="artifact",
        evidence_ref=EvidenceRef(type="region", value="metadata"),
        description="Reliable check 1",
        source="forensic",
        check_id="CHK_IMG_C2PA_VALID",
    )

    # For 1 image, applicable = 2
    # 1 reliable completed check -> sufficiency = 1 / 2 = 0.50
    fusion = compute_fusion([img], [ev1], [])
    assert fusion.checks_applicable == 2
    assert fusion.checks_completed == 1
    assert fusion.sufficiency == 0.50

    # 2 reliable completed checks -> sufficiency = 2 / 2 = 1.00
    ev2 = EvidenceItem(
        id="ev-2",
        artifact_ids=["img-1"],
        direction="authentic",
        strength=0.85,
        reliability=0.9,
        scope="artifact",
        evidence_ref=EvidenceRef(type="region", value="metadata"),
        description="Reliable check 2",
        source="forensic",
        check_id="CHK_IMG_EXIF_SOFTWARE",
    )
    fusion2 = compute_fusion([img], [ev1, ev2], [])
    assert fusion2.checks_applicable == 2
    assert fusion2.checks_completed == 2
    assert fusion2.sufficiency == 1.00
