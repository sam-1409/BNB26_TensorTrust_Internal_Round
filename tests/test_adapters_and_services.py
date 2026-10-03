"""Unit tests for Video Adapter, Audio Adapter, and LLM Client."""

import pytest
import wave
import cv2
import numpy as np
from pathlib import Path
from PIL import Image

from models.schemas import Artifact
from adapters.video import analyze_video
from adapters.audio import analyze_audio
from services.llm_client import GeminiClient, LLMClientError
from services.storage import StorageManager, delete_case


def test_analyze_video():
    session_id = "test_video_adapter_session"
    storage = StorageManager(session_id)

    video_path = storage.files_dir / "sample_video.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 10.0, (320, 240))
    for _ in range(20):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        out.write(frame)
    out.release()

    artifact = Artifact(
        id="art_vid_001",
        modality="video",
        display_name="sample_video.mp4",
        sha256="dummyvidhash",
        status="pending",
        metadata={"mime_type": "video/mp4"},
    )

    updated_art, evidence = analyze_video(artifact, video_path, storage.derived_dir)

    assert updated_art.status == "ok"
    assert updated_art.metadata.get("width") == 320
    assert updated_art.metadata.get("height") == 240
    assert updated_art.metadata.get("duration_seconds") > 0

    delete_case(session_id)


def test_analyze_audio():
    session_id = "test_audio_adapter_session"
    storage = StorageManager(session_id)

    audio_path = storage.files_dir / "sample_audio.wav"
    with wave.open(str(audio_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(b"\x00\x00" * 44100)  # 1 second silence

    artifact = Artifact(
        id="art_aud_001",
        modality="audio",
        display_name="sample_audio.wav",
        sha256="dummyaudhash",
        status="pending",
        metadata={"mime_type": "audio/wav"},
    )

    updated_art, evidence = analyze_audio(artifact, audio_path)

    assert updated_art.status == "ok"
    assert updated_art.metadata.get("sample_rate_hz") == 44100
    assert updated_art.metadata.get("duration_seconds") == 1.0

    delete_case(session_id)


def test_llm_client_caching(tmp_path):
    client = GeminiClient(cache_dir=tmp_path)
    cache_key = client._compute_cache_key("test_hash", "v1", "v1")

    client.save_cache_response(cache_key, {"result": "cached_ok"})
    cached = client.get_cached_response(cache_key)

    assert cached is not None
    assert cached.get("result") == "cached_ok"
