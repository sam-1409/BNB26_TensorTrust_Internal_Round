"""Video artifact adapter for TrustLayers (T²).

Extracts video frame rate, dimensions, duration, samples keyframes,
extracts audio streams via FFmpeg (safe subprocess, no shell=True),
transcribes video audio via Gemini ASR, and profiles video reliability.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional
import cv2

from models.schemas import Artifact, EvidenceItem, EvidenceRef
from core.reliability import compute_reliability_score
from core.config import VIDEO_SAMPLE_FPS, MAX_VIDEO_DURATION_SECONDS, FFMPEG_TIMEOUT_SECONDS


def detect_audio_stream(
    video_path: Path,
    timeout_seconds: int = 10,
) -> Optional[bool]:
    """Detect if video contains an audio stream using ffprobe with safe argument list.

    Returns:
        True if audio stream found, False if no audio stream, None if ffprobe unavailable.
    """
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin or not video_path.exists():
        return None

    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        if proc.returncode == 0:
            stdout_str = proc.stdout.decode("utf-8", errors="replace").strip()
            return "audio" in stdout_str.lower()
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError, OSError):
        return None


def extract_audio_track(
    video_path: Path,
    derived_dir: Path,
    artifact_id: str,
    timeout_seconds: int = FFMPEG_TIMEOUT_SECONDS,
) -> Optional[Path]:
    """Extract audio track from video using FFmpeg without shell=True.

    Enforces:
    - Safe subprocess argument list (no shell=True).
    - Path safety: destination strictly inside derived_dir.
    - Graceful degradation if ffmpeg is absent, corrupt, or fails.

    Args:
        video_path: Path to input video file.
        derived_dir: Directory where extracted audio should be stored.
        artifact_id: ID of the video artifact for unique naming.
        timeout_seconds: Subprocess timeout in seconds.

    Returns:
        Path to extracted WAV file if successful, None otherwise.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return None

    if not video_path.exists() or not derived_dir.is_dir():
        return None

    # Validate output path stays strictly within derived_dir
    derived_dir_resolved = derived_dir.resolve()
    output_filename = f"audio_{artifact_id}.wav"
    output_path = (derived_dir / output_filename).resolve()

    try:
        if not output_path.is_relative_to(derived_dir_resolved):
            return None
    except AttributeError:
        if not str(output_path).startswith(str(derived_dir_resolved)):
            return None

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(output_path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )

        if proc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            return output_path

        # Clean up empty or partial output
        if output_path.exists():
            output_path.unlink(missing_ok=True)
        return None

    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError, OSError):
        if output_path.exists():
            output_path.unlink(missing_ok=True)
        return None


def analyze_video(
    artifact: Artifact,
    file_path: Path,
    derived_dir: Path,
    llm_client: Optional[Any] = None,
) -> Tuple[Artifact, List[EvidenceItem]]:
    """Analyze video file, extract metadata, sample keyframes, extract audio, profile reliability.

    Args:
        artifact: Input Artifact model.
        file_path: Absolute path to video file.
        derived_dir: Directory to store extracted sampled frames and audio.
        llm_client: Optional GeminiClient for audio transcription.

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

        # Frame sampling (existing visual evidence preserved)
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

                cv2.imwrite(str(frame_out_path), frame)
                sampled_frames.append({
                    "frame_index": frame_idx,
                    "timestamp_sec": round(timestamp_sec, 2),
                    "frame_path": str(frame_out_path),
                })
                saved_count += 1
                if saved_count >= 60:
                    break

            frame_idx += 1

        cap.release()

        metadata["sampled_frames_count"] = saved_count
        metadata["sampled_frames"] = sampled_frames

        # Audio stream detection & FFmpeg extraction (Phase 1)
        audio_stream_exists = detect_audio_stream(file_path)
        if audio_stream_exists is False:
            metadata["has_audio"] = False
            metadata["audio_extraction_status"] = "no_audio_stream"
        else:
            extracted_audio = extract_audio_track(file_path, derived_dir, artifact.id)
            if extracted_audio:
                metadata["has_audio"] = True
                metadata["audio_track_path"] = str(extracted_audio)
                metadata["audio_extraction_status"] = "extracted"

                # Audio transcription via Gemini if client available
                from adapters.audio import transcribe_audio_with_gemini
                transcript_info = transcribe_audio_with_gemini(
                    audio_path=extracted_audio,
                    artifact_sha256=artifact.sha256,
                    mime_type="audio/wav",
                    llm_client=llm_client,
                )
                if transcript_info and transcript_info.get("transcript"):
                    metadata["transcript"] = transcript_info["transcript"]
                    metadata["transcript_confidence"] = transcript_info["confidence"]
                    metadata["transcript_segments"] = transcript_info["segments"]
                    metadata["transcript_language"] = transcript_info.get("language", "en")
                    metadata["transcript_status"] = "completed"

                    # Add grounded ASR evidence item
                    ev = EvidenceItem(
                        id=f"ev_video_asr_{artifact.id}",
                        artifact_ids=[artifact.id],
                        direction="neutral",
                        strength=0.0,
                        reliability=round(transcript_info["confidence"], 4),
                        scope="artifact",
                        evidence_ref=EvidenceRef(type="timestamp", value="0.0"),
                        description=f"Extracted video audio transcript ({len(transcript_info['transcript'])} chars, confidence: {transcript_info['confidence']:.2f})",
                        source="llm",
                        check_id="CHK_AUDIO_ASR",
                    )
                    evidence_list.append(ev)
                else:
                    metadata["transcript"] = ""
                    metadata["transcript_status"] = "unavailable"
            else:
                metadata["has_audio"] = False
                if shutil.which("ffmpeg") is None:
                    metadata["audio_extraction_status"] = "ffmpeg_unavailable"
                else:
                    metadata["audio_extraction_status"] = "no_audio_stream"

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
        art_dict["transcript"] = metadata.get("transcript") or None
        art_dict["transcript_confidence"] = metadata.get("transcript_confidence")
        return Artifact(**art_dict), evidence_list

    except Exception as err:
        art_dict = artifact.model_dump()
        art_dict["status"] = "degraded"
        art_dict["error_code"] = "PREPROCESS_FAILED"
        art_dict["metadata"]["error"] = str(err)
        return Artifact(**art_dict), []
