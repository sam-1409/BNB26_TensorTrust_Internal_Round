"""Audio artifact adapter for TrustLayers (T²).

Extracts audio duration, sample rate, channels, acoustic signals,
and profiles audio reliability.
"""

import wave
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional

from models.schemas import Artifact, EvidenceItem, EvidenceRef
from core.reliability import compute_reliability_score


def analyze_audio(artifact: Artifact, file_path: Path) -> Tuple[Artifact, List[EvidenceItem]]:
    """Analyze audio file, extract metadata, profile reliability.

    Args:
        artifact: Input Artifact schema.
        file_path: Absolute path to audio file.

    Returns:
        Tuple of (updated_artifact, list_of_evidence_items)
    """
    evidence_list: List[EvidenceItem] = []
    metadata = dict(artifact.metadata)

    try:
        # Check standard WAV metadata if applicable
        if file_path.suffix.lower() == ".wav":
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
        else:
            norm_sr = 0.8  # Default baseline for compressed audio formats

        # Compute reliability
        reliability = compute_reliability_score(
            resolution=round(norm_sr, 4),
            compression=0.85,
            noise=0.8,
            asr_confidence=0.90,  # Baseline signal
        )

        art_dict = artifact.model_dump()
        art_dict["status"] = "ok"
        art_dict["metadata"] = metadata
        art_dict["reliability"] = reliability
        art_dict["evidence"] = evidence_list
        return Artifact(**art_dict), evidence_list

    except Exception as err:
        art_dict = artifact.model_dump()
        art_dict["status"] = "degraded"
        art_dict["error_code"] = "PREPROCESS_FAILED"
        art_dict["metadata"]["error"] = str(err)
        return Artifact(**art_dict), []
