"""Audio artifact adapter for TrustLayers (T²).

Extracts audio duration, sample rate, channels, acoustic signals,
transcribes speech via Gemini multimodal ASR, and profiles audio reliability.
"""

import wave
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional

from models.schemas import Artifact, EvidenceItem, EvidenceRef
from core.reliability import compute_reliability_score
from services.llm_client import GeminiClient, LLMClientError


def detect_audio_mime_type(file_path: Path) -> str:
    """Determine MIME type from audio file extension."""
    ext = file_path.suffix.lower()
    if ext == ".wav":
        return "audio/wav"
    elif ext in (".mp3", ".mpeg"):
        return "audio/mpeg"
    elif ext == ".ogg":
        return "audio/ogg"
    elif ext == ".flac":
        return "audio/flac"
    elif ext in (".m4a", ".mp4"):
        return "audio/mp4"
    return "audio/wav"


def transcribe_audio_with_gemini(
    audio_path: Path,
    artifact_sha256: str,
    mime_type: Optional[str] = None,
    llm_client: Optional[GeminiClient] = None,
) -> Optional[Dict[str, Any]]:
    """Transcribe audio artifact using Gemini API with graceful error handling.

    Args:
        audio_path: Path to local audio file.
        artifact_sha256: SHA-256 hash of artifact for caching.
        mime_type: MIME type of audio (e.g., audio/wav).
        llm_client: Optional existing GeminiClient instance.

    Returns:
        Dict with 'transcript', 'confidence', 'language', 'segments' or None on failure.
    """
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        return None

    resolved_mime = mime_type or detect_audio_mime_type(audio_path)
    client = llm_client or GeminiClient()

    try:
        audio_bytes = audio_path.read_bytes()
        result = client.transcribe_audio(
            audio_bytes=audio_bytes,
            mime_type=resolved_mime,
            artifact_sha256=artifact_sha256,
        )

        transcript = str(result.get("transcript", "")).strip()
        confidence = float(result.get("confidence", 0.85))
        confidence = max(0.0, min(1.0, confidence))
        language = str(result.get("language", "en"))
        segments = result.get("segments", [])
        if not isinstance(segments, list):
            segments = []

        return {
            "transcript": transcript,
            "confidence": confidence,
            "language": language,
            "segments": segments,
        }

    except (LLMClientError, Exception):
        return None


def analyze_audio(
    artifact: Artifact,
    file_path: Path,
    llm_client: Optional[GeminiClient] = None,
) -> Tuple[Artifact, List[EvidenceItem]]:
    """Analyze audio file, extract metadata, transcribe speech via ASR, profile reliability.

    Args:
        artifact: Input Artifact schema.
        file_path: Absolute path to audio file.
        llm_client: Optional GeminiClient instance for transcription.

    Returns:
        Tuple of (updated_artifact, list_of_evidence_items)
    """
    evidence_list: List[EvidenceItem] = []
    metadata = dict(artifact.metadata)

    try:
        # Check standard WAV metadata if applicable
        duration = 0.0
        if file_path.suffix.lower() == ".wav":
            try:
                with wave.open(str(file_path), "rb") as wf:
                    channels = wf.getnchannels()
                    sample_width = wf.getsampwidth()
                    framerate = wf.getframerate()
                    n_frames = wf.getnframes()
                    duration = n_frames / float(framerate) if framerate > 0 else 0.0

                    metadata["channels"] = channels
                    metadata["sample_width_bytes"] = sample_width
                    metadata["sample_rate_hz"] = framerate
                    metadata["duration_seconds"] = round(duration, 2)

                    norm_sr = min(1.0, framerate / 44100.0)
            except Exception:
                norm_sr = 0.8
        else:
            norm_sr = 0.8  # Default baseline for compressed audio formats

        # Audio transcription via Gemini multimodal API (Phase 1)
        transcript_info = transcribe_audio_with_gemini(
            audio_path=file_path,
            artifact_sha256=artifact.sha256,
            mime_type=detect_audio_mime_type(file_path),
            llm_client=llm_client,
        )

        asr_confidence = 0.50
        if transcript_info and transcript_info.get("transcript"):
            metadata["transcript"] = transcript_info["transcript"]
            metadata["transcript_confidence"] = transcript_info["confidence"]
            metadata["transcript_segments"] = transcript_info["segments"]
            metadata["transcript_language"] = transcript_info["language"]
            metadata["transcript_status"] = "completed"
            asr_confidence = transcript_info["confidence"]

            # Add grounded ASR evidence item
            ev = EvidenceItem(
                id=f"ev_asr_{artifact.id}",
                artifact_ids=[artifact.id],
                direction="neutral",
                strength=0.0,
                reliability=round(asr_confidence, 4),
                scope="artifact",
                evidence_ref=EvidenceRef(type="timestamp", value="0.0"),
                description=f"Audio transcription extracted ({len(transcript_info['transcript'])} chars, confidence: {asr_confidence:.2f})",
                source="llm",
                check_id="CHK_AUDIO_ASR",
            )
            evidence_list.append(ev)
        else:
            metadata["transcript"] = ""
            metadata["transcript_status"] = "unavailable"

        # Compute reliability profiling
        reliability = compute_reliability_score(
            resolution=round(norm_sr, 4),
            compression=0.85,
            noise=0.8,
            asr_confidence=asr_confidence,
        )

        art_dict = artifact.model_dump()
        art_dict["status"] = "ok"
        art_dict["metadata"] = metadata
        art_dict["reliability"] = reliability
        art_dict["evidence"] = evidence_list
        art_dict["transcript"] = metadata.get("transcript") or None
        art_dict["transcript_confidence"] = metadata.get("transcript_confidence")
        return Artifact(**art_dict), evidence_list

    except Exception as err:
        art_dict = artifact.model_dump()
        art_dict["status"] = "degraded"
        art_dict["error_code"] = "PREPROCESS_FAILED"
        art_dict["metadata"]["error"] = str(err)
        return Artifact(**art_dict), []
