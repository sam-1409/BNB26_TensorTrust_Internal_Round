"""Comprehensive Phase 1 Tests for Audio + Video Understanding.

Tests all 11 required Phase 1 scenarios:
1. Video with audio -> extraction attempted/succeeds
2. Video without audio -> handled cleanly
3. Malformed/unsupported video -> no pipeline crash
4. Standalone audio -> ASR path invoked
5. ASR success -> transcript stored with grounding
6. ASR failure -> graceful degradation
7. Missing Gemini credentials/API failure -> pipeline still completes locally
8. FFmpeg failure/missing executable -> graceful degradation
9. shell=True is NOT used in subprocess calls
10. Existing video visual evidence remains intact
11. Backward compatibility with existing artifact/schema behavior
"""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import numpy as np
import cv2

from models.schemas import Artifact, CaseInput, EvidenceRef
from adapters.video import analyze_video, extract_audio_track, detect_audio_stream
from adapters.audio import analyze_audio, transcribe_audio_with_gemini
from reasoning.grounding import verify_evidence_ref
from services.llm_client import GeminiClient, LLMClientError
from core.orchestrator import run_case, delete_case


@pytest.fixture
def dummy_video(tmp_path) -> Path:
    """Create a minimal real MP4 video file using OpenCV."""
    vid_path = tmp_path / "test_sample.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(vid_path), fourcc, 10.0, (64, 64))
    for i in range(15):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        frame[:] = (i * 15, 128, 255 - i * 15)
        out.write(frame)
    out.release()
    return vid_path


@pytest.fixture
def dummy_wav(tmp_path) -> Path:
    """Create a minimal real WAV audio file."""
    import wave
    wav_path = tmp_path / "test_sample.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        # 0.5s of silence
        data = b"\x00\x00" * 8000
        wf.writeframes(data)
    return wav_path


# 1. Video with audio -> extraction attempted/succeeds
def test_video_with_audio_extraction_succeeds(dummy_video, tmp_path):
    art = Artifact(
        id="vid-1",
        modality="video",
        display_name="video_with_audio.mp4",
        sha256="hash_vid_1",
        status="ok",
        metadata={},
    )
    derived_dir = tmp_path / "derived"
    derived_dir.mkdir()

    fake_extracted_wav = derived_dir / "audio_vid-1.wav"
    fake_extracted_wav.write_bytes(b"RIFFfakeaudio")

    mock_llm = MagicMock()
    mock_llm.transcribe_audio.return_value = {
        "transcript": "Hello and welcome to the broadcast.",
        "confidence": 0.95,
        "language": "en",
        "segments": [{"start": 0.0, "end": 2.0, "text": "Hello and welcome"}],
    }

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("adapters.video.detect_audio_stream", return_value=True), \
         patch("adapters.video.extract_audio_track", return_value=fake_extracted_wav):

        updated_art, ev_list = analyze_video(art, dummy_video, derived_dir, llm_client=mock_llm)

    assert updated_art.status == "ok"
    assert updated_art.metadata.get("has_audio") is True
    assert updated_art.metadata.get("audio_extraction_status") == "extracted"
    assert updated_art.metadata.get("transcript") == "Hello and welcome to the broadcast."
    assert updated_art.transcript == "Hello and welcome to the broadcast."
    assert updated_art.transcript_confidence == 0.95

    asr_evidence = [e for e in ev_list if e.check_id == "CHK_AUDIO_ASR"]
    assert len(asr_evidence) == 1
    assert asr_evidence[0].direction == "neutral"
    assert verify_evidence_ref(asr_evidence[0].evidence_ref, updated_art)


# 2. Video without audio -> handled cleanly
def test_video_without_audio_handled_cleanly(dummy_video, tmp_path):
    art = Artifact(
        id="vid-2",
        modality="video",
        display_name="silent.mp4",
        sha256="hash_vid_2",
        status="ok",
        metadata={},
    )
    derived_dir = tmp_path / "derived"
    derived_dir.mkdir()

    with patch("adapters.video.detect_audio_stream", return_value=False):
        updated_art, ev_list = analyze_video(art, dummy_video, derived_dir)

    assert updated_art.status == "ok"
    assert updated_art.metadata.get("has_audio") is False
    assert updated_art.metadata.get("audio_extraction_status") == "no_audio_stream"
    assert updated_art.transcript is None
    # Visual frames are still sampled
    assert updated_art.metadata.get("sampled_frames_count") > 0


# 3. Malformed/unsupported video -> no pipeline crash
def test_malformed_unsupported_video_no_crash(tmp_path):
    corrupt_file = tmp_path / "corrupt.mp4"
    corrupt_file.write_bytes(b"not a valid video stream content")

    art = Artifact(
        id="vid-corrupt",
        modality="video",
        display_name="corrupt.mp4",
        sha256="hash_corrupt",
        status="ok",
        metadata={},
    )
    derived_dir = tmp_path / "derived"
    derived_dir.mkdir()

    updated_art, ev_list = analyze_video(art, corrupt_file, derived_dir)
    assert updated_art.status == "failed"
    assert updated_art.error_code == "CORRUPT_FILE"
    assert ev_list == []


# 4. Standalone audio -> ASR path invoked
def test_standalone_audio_asr_path_invoked(dummy_wav):
    art = Artifact(
        id="aud-1",
        modality="audio",
        display_name="clip.wav",
        sha256="hash_aud_1",
        status="ok",
        metadata={},
    )

    with patch("adapters.audio.transcribe_audio_with_gemini") as mock_asr:
        mock_asr.return_value = {
            "transcript": "Test speech",
            "confidence": 0.90,
            "language": "en",
            "segments": [],
        }
        updated_art, ev_list = analyze_audio(art, dummy_wav)
        mock_asr.assert_called_once()
        assert updated_art.transcript == "Test speech"
        assert updated_art.transcript_confidence == 0.90


# 5. ASR success -> transcript stored with grounding
def test_asr_success_transcript_stored_with_grounding(dummy_wav):
    art = Artifact(
        id="aud-2",
        modality="audio",
        display_name="speech.wav",
        sha256="hash_aud_2",
        status="ok",
        metadata={},
    )

    mock_llm = MagicMock()
    mock_llm.transcribe_audio.return_value = {
        "transcript": "Grounded acoustic evidence string",
        "confidence": 0.88,
        "language": "en",
        "segments": [{"start": 0.0, "end": 0.5, "text": "Grounded acoustic"}],
    }

    updated_art, ev_list = analyze_audio(art, dummy_wav, llm_client=mock_llm)

    assert updated_art.transcript == "Grounded acoustic evidence string"
    assert updated_art.transcript_confidence == 0.88
    assert updated_art.metadata["transcript_status"] == "completed"

    asr_items = [e for e in ev_list if e.check_id == "CHK_AUDIO_ASR"]
    assert len(asr_items) == 1
    ev = asr_items[0]
    assert ev.evidence_ref.type == "timestamp"
    assert verify_evidence_ref(ev.evidence_ref, updated_art) is True


# 6. ASR failure -> graceful degradation
def test_asr_failure_graceful_degradation(dummy_wav):
    art = Artifact(
        id="aud-3",
        modality="audio",
        display_name="error_clip.wav",
        sha256="hash_aud_3",
        status="ok",
        metadata={},
    )

    mock_llm = MagicMock()
    mock_llm.transcribe_audio.side_effect = LLMClientError("LLM_RATE_LIMITED", "429 quota exceeded")

    updated_art, ev_list = analyze_audio(art, dummy_wav, llm_client=mock_llm)

    assert updated_art.status == "ok"
    assert updated_art.transcript is None
    assert updated_art.metadata["transcript_status"] == "unavailable"
    assert ev_list == []


# 7. Missing Gemini credentials / API failure -> pipeline still completes locally
def test_missing_gemini_credentials_pipeline_completes_locally(dummy_wav):
    case_id = "test_phase1_no_key"
    case_input = CaseInput(
        case_id=case_id,
        files=[
            {"filename": "speech.wav", "bytes": dummy_wav.read_bytes()},
        ],
        description="Audio without API key",
    )

    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        result = run_case(case_input)

    assert result.case.job_status == "completed"
    assert len(result.case.artifacts) == 1
    art = result.case.artifacts[0]
    assert art.modality == "audio"
    assert art.metadata.get("transcript_status") == "unavailable"
    assert result.case.fusion is not None
    assert result.case.fusion.verdict in ("AUTHENTIC", "MANIPULATED", "INCONCLUSIVE")

    delete_case(case_id)


# 8. FFmpeg failure / missing executable -> graceful degradation
def test_ffmpeg_failure_missing_executable_graceful(dummy_video, tmp_path):
    art = Artifact(
        id="vid-no-ffmpeg",
        modality="video",
        display_name="no_ffmpeg.mp4",
        sha256="hash_vid_no_ffmpeg",
        status="ok",
        metadata={},
    )
    derived_dir = tmp_path / "derived"
    derived_dir.mkdir()

    with patch("shutil.which", return_value=None):
        res = extract_audio_track(dummy_video, derived_dir, "vid-no-ffmpeg")
        assert res is None

        updated_art, ev_list = analyze_video(art, dummy_video, derived_dir)
        assert updated_art.status == "ok"
        assert updated_art.metadata.get("audio_extraction_status") == "ffmpeg_unavailable"
        assert updated_art.metadata.get("sampled_frames_count") > 0


# 9. shell=True is NOT used in subprocess calls
def test_subprocess_never_uses_shell_true(dummy_video, tmp_path):
    derived_dir = tmp_path / "derived"
    derived_dir.mkdir()

    calls = []

    def mock_run(*args, **kwargs):
        calls.append((args, kwargs))
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"audio\n"
        mock_proc.stderr = b""
        return mock_proc

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("subprocess.run", side_effect=mock_run):

        extract_audio_track(dummy_video, derived_dir, "test-shell")

    assert len(calls) == 1
    args, kwargs = calls[0]
    # Verify shell argument is NOT True
    assert kwargs.get("shell") is not True
    # Verify command is a safe list of strings
    cmd = args[0]
    assert isinstance(cmd, list)
    assert cmd[0] == "/usr/bin/ffmpeg"


# 10. Existing video visual evidence remains intact
def test_existing_video_visual_evidence_remains_intact(dummy_video, tmp_path):
    art = Artifact(
        id="vid-visual",
        modality="video",
        display_name="visual.mp4",
        sha256="hash_vid_visual",
        status="ok",
        metadata={},
    )
    derived_dir = tmp_path / "derived"
    derived_dir.mkdir()

    updated_art, ev_list = analyze_video(art, dummy_video, derived_dir)

    assert updated_art.status == "ok"
    assert updated_art.metadata["width"] == 64
    assert updated_art.metadata["height"] == 64
    assert updated_art.metadata["fps"] == 10.0
    assert updated_art.metadata["total_frames"] == 15
    assert updated_art.metadata["sampled_frames_count"] > 0
    assert "sampled_frames" in updated_art.metadata
    assert updated_art.reliability is not None
    assert updated_art.reliability.score > 0.0


# 11. Backward compatibility with existing artifact/schema behavior
def test_backward_compatibility_artifact_schema():
    art = Artifact(
        id="compat-art-1",
        modality="image",
        display_name="test.jpg",
        sha256="hash",
        status="ok",
    )
    # Default values for new optional fields
    assert art.transcript is None
    assert art.transcript_confidence is None

    # Dumping and reloading schema preserves extra="forbid"
    dumped = art.model_dump()
    reloaded = Artifact.model_validate(dumped)
    assert reloaded.id == "compat-art-1"

    # Strict validation rejects invalid extra fields
    invalid_dump = dict(dumped)
    invalid_dump["unexpected_extra_field"] = "bad"
    with pytest.raises(Exception):
        Artifact.model_validate(invalid_dump)
