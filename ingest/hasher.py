"""SHA-256 hashing and exact duplicate collapser module for TrustLayers (T²).

Enforces RULE R-UP-06:
- Hash with SHA-256 at ingest.
- Collapse exact duplicates with a visible notice.
- A duplicate artifact is marked with status 'duplicate' and never counts as independent corroboration.
"""

import hashlib
from typing import Tuple, List, Set
from models.schemas import Artifact


def compute_sha256(file_bytes: bytes) -> str:
    """Compute Hex SHA-256 hash of raw file bytes."""
    hasher = hashlib.sha256()
    hasher.update(file_bytes)
    return hasher.hexdigest()


def process_duplicates(artifacts: List[Artifact]) -> Tuple[List[Artifact], List[str]]:
    """Inspect artifacts list for duplicate SHA-256 hashes (R-UP-06).

    Args:
        artifacts: List of ingested Artifact objects.

    Returns:
        Tuple of (updated_artifacts_list, list_of_notice_messages)
    """
    seen_hashes: Set[str] = set()
    notices: List[str] = []
    updated_artifacts: List[Artifact] = []

    for art in artifacts:
        if art.status == "rejected" or not art.sha256:
            updated_artifacts.append(art)
            continue

        if art.sha256 in seen_hashes:
            # Mark duplicate artifact
            art_dict = art.model_dump()
            art_dict["status"] = "duplicate"
            dup_art = Artifact(**art_dict)
            updated_artifacts.append(dup_art)
            notices.append(
                f"Artifact '{art.display_name}' is an exact duplicate (SHA-256: {art.sha256[:8]}...) "
                "and was collapsed. It will not count as independent corroboration."
            )
        else:
            seen_hashes.add(art.sha256)
            updated_artifacts.append(art)

    return updated_artifacts, notices
