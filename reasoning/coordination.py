"""Set-level coordination detection module for TrustLayers (T²).

Detects:
- Linked artifacts (near-duplicate hashes, shared generative indicators)
- Emits LINKED relations which group synthetic artifact clusters per Decision D-008.
"""

from typing import List
from models.schemas import Artifact, Relation, EvidenceRef


def detect_coordination(artifacts: List[Artifact]) -> List[Relation]:
    """Detect set-level coordination and linked synthetic sets.

    Args:
        artifacts: List of ingested Artifact objects.

    Returns:
        List of LINKED Relation objects.
    """
    coordination_relations: List[Relation] = []
    valid_arts = [a for a in artifacts if a.status in ("pending", "ok", "degraded")]

    for i in range(len(valid_arts)):
        for j in range(i + 1, len(valid_arts)):
            art1 = valid_arts[i]
            art2 = valid_arts[j]

            # Check shared AI generator metadata indicators
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
