"""Unit tests for Pydantic data schemas."""

import pytest
from pydantic import ValidationError
from models.schemas import (
    Reliability,
    EvidenceRef,
    EvidenceItem,
    Artifact,
    Relation,
    Fusion,
    Case,
)


def test_reliability_valid():
    rel = Reliability(
        resolution=0.9,
        compression=0.8,
        noise=0.1,
        asr_confidence=0.95,
        language_flag="en",
        score=0.85,
    )
    assert rel.score == 0.85


def test_reliability_strict_rejection():
    invalid_data = {"score": 0.8, "unknown_extra_field": "should_fail"}
    with pytest.raises(ValidationError):
        Reliability.model_validate(invalid_data)


def test_evidence_item_valid():
    ref = EvidenceRef(type="frame", value="42")
    item = EvidenceItem(
        id="ev-001",
        artifact_ids=["art-001"],
        direction="manipulated",
        strength=0.85,
        reliability=0.9,
        scope="artifact",
        evidence_ref=ref,
        description="Deepfake face artifact detected at frame 42",
        source="detector",
        check_id="CHK_IMG_DEEPFAKE",
    )
    assert item.id == "ev-001"
    assert item.evidence_ref.value == "42"


def test_fusion_verdict_choices():
    fusion = Fusion(
        manip_evidence=0.8,
        auth_support=0.1,
        sufficiency=0.7,
        checks_completed=5,
        checks_applicable=5,
        verdict="MANIPULATED",
        reason_codes=["SYNTHETIC_ARTIFACT"],
        confidence_level="high",
        limitations=["Low resolution in video audio"],
    )
    assert fusion.verdict == "MANIPULATED"

    invalid_fusion_data = {
        "manip_evidence": 0.8,
        "auth_support": 0.1,
        "sufficiency": 0.7,
        "checks_completed": 5,
        "checks_applicable": 5,
        "verdict": "INVALID_VERDICT_LABEL",
        "reason_codes": [],
        "confidence_level": "high",
    }
    with pytest.raises(ValidationError):
        Fusion.model_validate(invalid_fusion_data)


def test_case_model():
    case = Case(
        id="case-123",
        description="Test investigation case",
        job_status="created",
        artifacts=[],
        relations=[],
        diagnostics={"version": "0.1.0"},
    )
    assert case.id == "case-123"
    assert case.job_status == "created"
