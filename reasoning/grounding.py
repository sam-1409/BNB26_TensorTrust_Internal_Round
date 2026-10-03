"""Grounding verifier module for TrustLayers (T²).

Enforces:
- R-LLM-04: Every reference in LLM or check output passes the grounding verifier before use.
- INV-11: An unresolvable reference is dropped from evidence and relations.
"""

from typing import List, Tuple, Dict, Any, Optional
from models.schemas import Artifact, EvidenceItem, EvidenceRef, Relation


def verify_evidence_ref(ref: EvidenceRef, artifact: Artifact) -> bool:
    """Verify whether an EvidenceRef points to a valid, resolvable location on the artifact.

    Args:
        ref: EvidenceRef object (type: frame | timestamp | page | region).
        artifact: Artifact metadata target.

    Returns:
        True if resolvable, False if unresolvable.
    """
    ref_type = ref.type
    val = ref.value.strip()
    metadata = artifact.metadata or {}

    if ref_type == "frame":
        try:
            frame_idx = int(val)
            total_frames = metadata.get("total_frames", metadata.get("sampled_frames_count", 0))
            if total_frames > 0:
                return 0 <= frame_idx < total_frames
            return frame_idx >= 0
        except ValueError:
            return False

    elif ref_type == "timestamp":
        try:
            # Timestamp can be "00:00:20.4" or "20.4"
            parts = val.split(":")
            if len(parts) == 3:
                secs = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                secs = float(parts[0]) * 60 + float(parts[1])
            else:
                secs = float(val)

            duration = metadata.get("duration_seconds", 0.0)
            if duration > 0.0:
                return 0.0 <= secs <= (duration + 2.0)  # Allow slight tolerance
            return secs >= 0.0
        except ValueError:
            return False

    elif ref_type == "page":
        try:
            page_num = int(val)
            page_count = metadata.get("page_count", 0)
            if page_count > 0:
                return 1 <= page_num <= page_count
            return page_num >= 1
        except ValueError:
            # Metadata string reference e.g., "metadata"
            return val.lower() in ("metadata", "manifest", "header")

    elif ref_type == "region":
        if not val:
            return False
        # Check if coordinates x,y,w,h format
        parts = val.split(",")
        if len(parts) == 4:
            try:
                x, y, w, h = [float(p.strip()) for p in parts]
                img_w = metadata.get("width", 0)
                img_h = metadata.get("height", 0)
                if img_w > 0 and img_h > 0:
                    return 0 <= x <= img_w and 0 <= y <= img_h and w > 0 and h > 0
                return w > 0 and h > 0
            except ValueError:
                return False
        # Text descriptor like "manifest", "metadata", "header" is valid
        return True

    return False


def filter_grounded_evidence(
    artifacts: List[Artifact],
    evidence_items: List[EvidenceItem],
) -> Tuple[List[EvidenceItem], int]:
    """Filter evidence items against artifact metadata (INV-11).

    Returns:
        Tuple of (grounded_evidence_items, rejection_count)
    """
    art_map = {a.id: a for a in artifacts}
    grounded: List[EvidenceItem] = []
    rejections = 0

    for item in evidence_items:
        # Resolve target artifacts
        target_arts = [art_map[aid] for aid in item.artifact_ids if aid in art_map]
        if not target_arts:
            rejections += 1
            continue

        # Check evidence reference against primary target artifact
        is_valid = verify_evidence_ref(item.evidence_ref, target_arts[0])
        if is_valid:
            grounded.append(item)
        else:
            rejections += 1

    return grounded, rejections


def filter_grounded_relations(
    artifacts: List[Artifact],
    relations: List[Relation],
) -> Tuple[List[Relation], int]:
    """Filter relations ensuring referenced evidence refs resolve."""
    art_map = {a.id: a for a in artifacts}
    grounded_relations: List[Relation] = []
    rejections = 0

    for rel in relations:
        source_art = art_map.get(rel.source_id)
        target_art = art_map.get(rel.target_id)
        if not source_art or not target_art:
            rejections += 1
            continue

        valid_refs: List[EvidenceRef] = []
        for ref in rel.evidence_refs:
            if verify_evidence_ref(ref, source_art) or verify_evidence_ref(ref, target_art):
                valid_refs.append(ref)
            else:
                rejections += 1

        rel_dict = rel.model_dump()
        rel_dict["evidence_refs"] = valid_refs
        grounded_relations.append(Relation(**rel_dict))

    return grounded_relations, rejections
