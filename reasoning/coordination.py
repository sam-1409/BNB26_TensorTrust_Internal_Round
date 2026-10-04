"""Set-level coordination and duplicate/near-duplicate detection module for TrustLayers (T²).

Detects:
- Exact SHA-256 duplicates (marked as non-independent corroboration)
- Near-duplicate images via perceptual difference hashing (dHash)
- Text repost / high-overlap statements via token similarity
- Coordinated generative AI indicators via software metadata
- Emits LINKED and MATCHES relations connecting artifacts without false manipulation leaps.
"""

import re
from pathlib import Path
from typing import List, Optional
from PIL import Image

from models.schemas import Artifact, Relation, EvidenceRef
from core.config import PERCEPTUAL_HASH_DISTANCE_THRESHOLD, TEXT_SIMILARITY_THRESHOLD


def compute_dhash(image_input) -> str:
    """Compute 64-bit difference hash (dHash) for an image.

    Args:
        image_input: PIL Image or Path/str to an image.

    Returns:
        16-character hexadecimal string representing the 64-bit dHash.
    """
    try:
        if isinstance(image_input, (str, Path)):
            img = Image.open(image_input)
        else:
            img = image_input

        # Convert to grayscale and resize to (9, 8)
        gray = img.convert("L").resize((9, 8), Image.Resampling.BILINEAR)
        if hasattr(gray, "get_flattened_data"):
            pixels = list(gray.get_flattened_data())
        else:
            pixels = list(gray.getdata())

        # Compare adjacent pixels in each row
        diff = []
        for row in range(8):
            for col in range(8):
                idx = row * 9 + col
                diff.append(pixels[idx] > pixels[idx + 1])

        # Convert 64 booleans to 16 hex characters
        decimal_val = 0
        for bit in diff:
            decimal_val = (decimal_val << 1) | (1 if bit else 0)

        return f"{decimal_val:016x}"
    except Exception:
        return ""


def hamming_distance(hash1: str, hash2: str) -> int:
    """Compute Hamming distance between two hex hash strings."""
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        return 999
    try:
        val1 = int(hash1, 16)
        val2 = int(hash2, 16)
        xor_val = val1 ^ val2
        return bin(xor_val).count("1")
    except ValueError:
        return 999


def compute_text_similarity(text1: str, text2: str) -> float:
    """Compute token Jaccard similarity between two text snippets."""
    words1 = set(re.findall(r"\b\w{3,}\b", text1.lower()))
    words2 = set(re.findall(r"\b\w{3,}\b", text2.lower()))
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def detect_coordination(artifacts: List[Artifact]) -> List[Relation]:
    """Detect set-level coordination, exact duplicates, and near-duplicates.

    Args:
        artifacts: List of ingested Artifact objects.

    Returns:
        List of LINKED / MATCHES Relation objects.
    """
    coordination_relations: List[Relation] = []
    valid_arts = [a for a in artifacts if a.status in ("pending", "ok", "degraded", "duplicate")]

    for i in range(len(valid_arts)):
        for j in range(i + 1, len(valid_arts)):
            art1 = valid_arts[i]
            art2 = valid_arts[j]

            # 1. Exact SHA-256 duplicate check
            if art1.sha256 and art2.sha256 and art1.sha256 == art2.sha256:
                rel = Relation(
                    source_id=art1.id,
                    target_id=art2.id,
                    relation="MATCHES",
                    conflict_type="exact_duplicate",
                    method="deterministic",
                    confidence_level="high",
                    evidence_refs=[
                        EvidenceRef(type="region", value="metadata"),
                    ],
                    explanation=(
                        "Artifacts share identical cryptographic SHA-256 hash. "
                        "Exact duplicate files are linked and do NOT count as independent corroboration."
                    ),
                )
                coordination_relations.append(rel)
                continue

            # 2. Perceptual near-duplicate check for images
            phash1 = art1.perceptual_hash or art1.metadata.get("perceptual_hash")
            phash2 = art2.perceptual_hash or art2.metadata.get("perceptual_hash")

            if phash1 and phash2:
                dist = hamming_distance(phash1, phash2)
                if dist <= PERCEPTUAL_HASH_DISTANCE_THRESHOLD:
                    rel = Relation(
                        source_id=art1.id,
                        target_id=art2.id,
                        relation="MATCHES",
                        conflict_type="near_duplicate",
                        method="deterministic",
                        confidence_level="high",
                        evidence_refs=[
                            EvidenceRef(type="region", value="metadata"),
                        ],
                        explanation=(
                            f"Visual perceptual hash match (dHash Hamming distance {dist} <= {PERCEPTUAL_HASH_DISTANCE_THRESHOLD}). "
                            "Indicates near-duplicate, re-compressed, or reposted visual media."
                        ),
                    )
                    coordination_relations.append(rel)

            # 3. Text content repost check
            text1 = art1.transcript or art1.metadata.get("text_content", "")
            text2 = art2.transcript or art2.metadata.get("text_content", "")
            if text1 and text2:
                sim = compute_text_similarity(str(text1), str(text2))
                if sim >= TEXT_SIMILARITY_THRESHOLD:
                    rel = Relation(
                        source_id=art1.id,
                        target_id=art2.id,
                        relation="MATCHES",
                        conflict_type="text_repost",
                        method="deterministic",
                        confidence_level="medium",
                        evidence_refs=[
                            EvidenceRef(type="page", value="1"),
                        ],
                        explanation=(
                            f"High textual content overlap ({sim:.2f} >= {TEXT_SIMILARITY_THRESHOLD}). "
                            "Indicates near-duplicate, shared transcript, or reposted statement."
                        ),
                    )
                    coordination_relations.append(rel)

            # 4. Shared AI generator metadata indicators
            sw1 = str(art1.metadata.get("exif", {}).get("Software", "")).lower()
            sw2 = str(art2.metadata.get("exif", {}).get("Software", "")).lower()

            ai_tools = ("midjourney", "stable diffusion", "dall-e", "comfyui")
            is_ai1 = any(t in sw1 for t in ai_tools)
            is_ai2 = any(t in sw2 for t in ai_tools)

            if is_ai1 and is_ai2:
                rel = Relation(
                    source_id=art1.id,
                    target_id=art2.id,
                    relation="LINKED",
                    conflict_type="set_coordination",
                    method="deterministic",
                    confidence_level="high",
                    evidence_refs=[
                        EvidenceRef(type="region", value="metadata"),
                    ],
                    explanation="Artifacts share generative AI synthesis metadata indicators.",
                )
                coordination_relations.append(rel)

    return coordination_relations
