"""Unit tests for Image Artifact Adapter."""

from pathlib import Path
from PIL import Image
from models.schemas import Artifact
from adapters.image import analyze_image, extract_exif
from services.storage import StorageManager, delete_case


def test_analyze_image_basic():
    session_id = "test_img_adapter_session"
    storage = StorageManager(session_id)

    # Create a small test JPEG image
    img_path = storage.files_dir / "test_image.jpg"
    img = Image.new("RGB", (800, 600), color="blue")
    img.save(img_path, format="JPEG")

    artifact = Artifact(
        id="art_img_001",
        modality="image",
        display_name="test_image.jpg",
        sha256="dummyhash",
        status="pending",
        metadata={"mime_type": "image/jpeg"},
    )

    updated_art, evidence = analyze_image(artifact, img_path)

    assert updated_art.status == "ok"
    assert updated_art.metadata.get("width") == 800
    assert updated_art.metadata.get("height") == 600
    assert updated_art.reliability is not None
    assert updated_art.reliability.score > 0.0

    delete_case(session_id)
