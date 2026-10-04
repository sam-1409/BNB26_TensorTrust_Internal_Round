"""Unit tests for Phase 5: Extended coordination, duplicate and near-duplicate detection."""

from PIL import Image
from models.schemas import Artifact
from reasoning.coordination import (
    compute_dhash,
    hamming_distance,
    compute_text_similarity,
    detect_coordination,
)


def test_dhash_and_hamming_distance():
    # Create two identical small images
    img1 = Image.new("RGB", (64, 64), color="blue")
    img2 = Image.new("RGB", (64, 64), color="blue")

    h1 = compute_dhash(img1)
    h2 = compute_dhash(img2)

    assert len(h1) == 16
    assert h1 == h2
    assert hamming_distance(h1, h2) == 0

    # Modify image slightly
    img3 = Image.new("RGB", (64, 64), color="red")
    h3 = compute_dhash(img3)
    assert len(h3) == 16


def test_text_similarity():
    text1 = "Breaking news: Major scientific announcement made at Geneva symposium today."
    text2 = "Breaking news: Major scientific announcement made at Geneva symposium this morning."
    sim = compute_text_similarity(text1, text2)
    assert sim > 0.70

    unrelated = "Completely different recipe for homemade blueberry pancakes and maple syrup."
    assert compute_text_similarity(text1, unrelated) < 0.10


def test_detect_coordination_exact_sha256_duplicates():
    art1 = Artifact(
        id="a1", modality="image", display_name="pic1.jpg",
        sha256="deadbeef1234", status="ok"
    )
    art2 = Artifact(
        id="a2", modality="image", display_name="pic2.jpg",
        sha256="deadbeef1234", status="ok"
    )

    relations = detect_coordination([art1, art2])
    assert len(relations) == 1
    assert relations[0].relation == "MATCHES"
    assert relations[0].conflict_type == "exact_duplicate"
    assert "not count as independent corroboration" in relations[0].explanation.lower()


def test_detect_coordination_perceptual_hash_near_duplicate():
    art1 = Artifact(
        id="a1", modality="image", display_name="orig.jpg",
        sha256="hash1", status="ok", perceptual_hash="0000ffff0000ffff"
    )
    # 1 bit difference
    art2 = Artifact(
        id="a2", modality="image", display_name="repost.jpg",
        sha256="hash2", status="ok", perceptual_hash="0000ffff0000fffe"
    )

    relations = detect_coordination([art1, art2])
    assert len(relations) == 1
    assert relations[0].relation == "MATCHES"
    assert relations[0].conflict_type == "near_duplicate"
    assert relations[0].confidence_level == "high"


def test_detect_coordination_text_repost():
    art1 = Artifact(
        id="t1", modality="text", display_name="post1.txt",
        sha256="h_t1", status="ok",
        metadata={"text_content": "Official statement regarding quarterly corporate earnings released today."}
    )
    art2 = Artifact(
        id="t2", modality="text", display_name="post2.txt",
        sha256="h_t2", status="ok",
        metadata={"text_content": "Official statement regarding quarterly corporate earnings released today in full."}
    )

    relations = detect_coordination([art1, art2])
    assert len(relations) == 1
    assert relations[0].relation == "MATCHES"
    assert relations[0].conflict_type == "text_repost"
