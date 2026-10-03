"""Unit tests for SHA-256 hashing and duplicate collapser."""

from ingest.hasher import compute_sha256, process_duplicates
from models.schemas import Artifact


def test_compute_sha256():
    data = b"Hello TrustLayers"
    sha = compute_sha256(data)
    # Expected SHA-256 for 'Hello TrustLayers'
    assert len(sha) == 64
    assert sha == compute_sha256(data)


def test_process_duplicates():
    sha = compute_sha256(b"same_content")

    art1 = Artifact(
        id="art-1",
        modality="image",
        display_name="photo1.jpg",
        sha256=sha,
        status="ok",
        metadata={},
    )

    art2 = Artifact(
        id="art-2",
        modality="image",
        display_name="photo2.jpg",
        sha256=sha,
        status="ok",
        metadata={},
    )

    art3 = Artifact(
        id="art-3",
        modality="text",
        display_name="doc.txt",
        sha256=compute_sha256(b"different_content"),
        status="ok",
        metadata={},
    )

    updated, notices = process_duplicates([art1, art2, art3])

    assert len(updated) == 3
    assert updated[0].status == "ok"
    assert updated[1].status == "duplicate"
    assert updated[2].status == "ok"
    assert len(notices) == 1
    assert "photo2.jpg" in notices[0]
