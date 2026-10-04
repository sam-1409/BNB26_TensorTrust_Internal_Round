"""Unit tests for Phase 2: reasoning/artifact_analyzer.py."""

from unittest.mock import MagicMock
from models.schemas import Artifact, Reliability, EvidenceItem
from reasoning.artifact_analyzer import analyze_artifact_semantics
from services.llm_client import GeminiClient, LLMClientError


def test_artifact_analyzer_local_heuristic():
    art = Artifact(
        id="art-1",
        modality="text",
        display_name="document.txt",
        sha256="abc1234",
        status="ok",
        metadata={"text_content": "In 2024, the conference was held in Paris. Published in 2025."},
    )

    updated_art, evidence = analyze_artifact_semantics(art, llm_client=None)

    assert updated_art.metadata.get("semantic_analysis_status") == "local_heuristic"
    dates = updated_art.metadata.get("entities", {}).get("dates", [])
    assert "2024" in dates
    assert "2025" in dates
    assert len(updated_art.semantic_claims) > 0


def test_artifact_analyzer_llm_mocked():
    mock_client = MagicMock(spec=GeminiClient)
    mock_client.api_key = "test-key"
    mock_client.generate_structured_json.return_value = {
        "claims": [
            {
                "claim_text": "Meeting occurred at HQ",
                "category": "event",
                "grounding_ref_type": "page",
                "grounding_ref_value": "1"
            }
        ],
        "entities": {
            "people": ["Alice"],
            "organizations": ["Acme"],
            "locations": ["Geneva"],
            "dates": ["2023"]
        },
        "semantic_summary": "Meeting minutes summary",
        "ocr_text": None,
        "manipulation_signals": [
            {
                "description": "Inconsistent font rendering",
                "direction": "manipulated",
                "strength_class": "moderate",
                "grounding_ref_type": "page",
                "grounding_ref_value": "1"
            }
        ]
    }

    art = Artifact(
        id="art-2",
        modality="document",
        display_name="report.pdf",
        sha256="pdf1234",
        status="ok",
        reliability=Reliability(score=0.9),
        metadata={"page_count": 5},
    )

    updated_art, evidence = analyze_artifact_semantics(art, llm_client=mock_client)

    assert updated_art.metadata.get("semantic_analysis_status") == "llm_complete"
    assert len(updated_art.semantic_claims) == 1
    assert updated_art.semantic_claims[0]["claim_text"] == "Meeting occurred at HQ"
    assert len(evidence) == 1
    assert evidence[0].direction == "manipulated"
    assert evidence[0].strength == 0.50  # moderate -> 0.50
    assert evidence[0].source == "llm"


def test_artifact_analyzer_llm_failure_graceful():
    mock_client = MagicMock(spec=GeminiClient)
    mock_client.api_key = "test-key"
    mock_client.generate_structured_json.side_effect = LLMClientError("LLM_RATE_LIMITED", "429 Rate limited")

    art = Artifact(
        id="art-3",
        modality="image",
        display_name="photo.jpg",
        sha256="img1234",
        status="ok",
        metadata={"exif": {"DateTimeOriginal": "2022:05:01 12:00:00"}},
    )

    updated_art, evidence = analyze_artifact_semantics(art, llm_client=mock_client)

    # Must gracefully fall back to local extraction
    assert updated_art.metadata.get("semantic_analysis_status") == "local_heuristic"
    assert "2022" in updated_art.metadata.get("entities", {}).get("dates", [])
