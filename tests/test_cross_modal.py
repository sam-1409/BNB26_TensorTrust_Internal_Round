"""Unit tests for Phase 4: reasoning/cross_modal.py."""

from unittest.mock import MagicMock
from models.schemas import Artifact, Reliability
from reasoning.cross_modal import run_cross_modal_reasoning
from services.llm_client import GeminiClient


def test_cross_modal_gating_single_modality():
    # Two images: only 1 modality present -> cross-modal NOT activated
    art1 = Artifact(id="a1", modality="image", display_name="img1.jpg", sha256="s1", status="ok")
    art2 = Artifact(id="a2", modality="image", display_name="img2.jpg", sha256="s2", status="ok")

    rels, evs, activated = run_cross_modal_reasoning([art1, art2], llm_client=None)

    assert activated is False
    assert len(rels) == 0
    assert len(evs) == 0


def test_cross_modal_asr_confidence_gate():
    # Audio with low transcript confidence (< 0.70) + text: should be skipped
    art_audio = Artifact(
        id="a_aud",
        modality="audio",
        display_name="voice.wav",
        sha256="s_aud",
        status="ok",
        transcript="some speech",
        transcript_confidence=0.50,  # Below 0.70 threshold
    )
    art_text = Artifact(
        id="a_txt",
        modality="text",
        display_name="caption.txt",
        sha256="s_txt",
        status="ok",
        metadata={"text_content": "some speech"},
    )

    rels, evs, activated = run_cross_modal_reasoning([art_audio, art_text], llm_client=None)

    assert activated is True
    # Pair should be skipped by ASR gate
    assert len(rels) == 0


def test_cross_modal_deterministic_corroboration_and_conflict():
    # Corroborating pair
    art_img = Artifact(
        id="a_img",
        modality="image",
        display_name="photo.jpg",
        sha256="s_img",
        status="ok",
        metadata={"entities": {"people": ["Alice"]}},
    )
    art_text = Artifact(
        id="a_txt",
        modality="text",
        display_name="article.txt",
        sha256="s_txt",
        status="ok",
        metadata={"entities": {"people": ["Alice"]}},
    )

    rels, evs, activated = run_cross_modal_reasoning([art_img, art_text], llm_client=None)

    assert activated is True
    assert len(rels) == 1
    assert rels[0].relation == "SUPPORTS"
    assert "Alice" in rels[0].explanation


def test_cross_modal_llm_mocked():
    mock_client = MagicMock(spec=GeminiClient)
    mock_client.api_key = "test-key"
    mock_client.generate_structured_json.return_value = {
        "relation": "CONTRADICTORY",
        "conflict_type": "event",
        "confidence_level": "high",
        "explanation": "Spoken claim describes flood while image shows severe drought.",
    }

    art_img = Artifact(
        id="a_img",
        modality="image",
        display_name="drought.jpg",
        sha256="s_img",
        status="ok",
        metadata={"semantic_summary": "Arid cracked desert soil under baking sun."},
    )
    art_aud = Artifact(
        id="a_aud",
        modality="audio",
        display_name="report.wav",
        sha256="s_aud",
        status="ok",
        transcript="Torrential floods have submerged all streets.",
        transcript_confidence=0.95,
    )

    rels, evs, activated = run_cross_modal_reasoning([art_img, art_aud], llm_client=mock_client)

    assert activated is True
    assert len(rels) == 1
    assert rels[0].relation == "CONTRADICTS"
    assert rels[0].conflict_type == "event"
    assert len(evs) == 1
    assert evs[0].direction == "manipulated"
