"""Video artifact adapter for TrustLayers (T²).

Extracts video frame rate, dimensions, duration, samples keyframes,
and profiles video reliability.
"""

from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional
import cv2

from models.schemas import Artifact, EvidenceItem, EvidenceRef
from core.reliability import compute_reliability_score
from core.config import VIDEO_SAMPLE_FPS, MAX_VIDEO_DURATION_SECONDS


def analyze_video(
    artifact: Artifact,
    file_path: Path,
    derived_dir: Path,
) -> Tuple[Artifact, List[EvidenceItem]]:
    """Analyze video file, extract metadata, sample keyframes, profile reliability.

    Args:
        artifact: Input Artifact model.
        file_path: Absolute path to video file.
        derived_dir: Directory to store extracted sampled frames.

    Returns:
        Tuple of (updated_artifact, list_of_evidence_items)
    """
    evidence_list: List[EvidenceItem] = []
    metadata = dict(artifact.metadata)

    try:
        cap = cv2.VideoCapture(str(file_path))
        if not cap.isOpened():
            art_dict = artifact.model_dump()
            art_dict["status"] = "failed"
            art_dict["error_code"] = "CORRUPT_FILE"
            art_dict["metadata"]["error"] = "Could not open video stream with OpenCV"
            return Artifact(**art_dict), []

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0.0

        metadata["width"] = width
        metadata["height"] = height
        metadata["fps"] = round(fps, 2)
        metadata["total_frames"] = total_frames
        metadata["duration_seconds"] = round(duration, 2)

        # Frame sampling
        frame_interval = int(fps / VIDEO_SAMPLE_FPS) if fps >= VIDEO_SAMPLE_FPS else 1
        sampled_frames: List[Dict[str, Any]] = []

        frame_idx = 0
        saved_count = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_interval == 0:
                timestamp_sec = frame_idx / fps
                frame_filename = f"frame_{artifact.id}_{saved_count:04d}.jpg"
                frame_out_path = derived_dir / frame_filename

                # Save sample frame
                cv2.imwrite(str(frame_out_path), frame)
                sampled_frames.append({
                    "frame_index": frame_idx,
                    "timestamp_sec": round(timestamp_sec, 2),
                    "frame_path": str(frame_out_path),
                })
                saved_count += 1
                if saved_count >= 60:  # Cap max sampled frames for performance
                    break

            frame_idx += 1

        cap.release()

        metadata["sampled_frames_count"] = saved_count
        metadata["sampled_frames"] = sampled_frames

        # Quality profiling
        norm_res = min(1.0, (width * height) / (1920 * 1080))
        reliability = compute_reliability_score(
            resolution=round(norm_res, 4),
            compression=0.85,
            noise=0.8,
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
