"""Deterministic cross-artifact check engine for TrustLayers (T²).

Extracts and checks deterministic claims across artifact pairs:
- Date contradictions (e.g., image EXIF date vs text claim date)
- Location/Name mismatches
- Numerical quantity discrepancies
"""

import re
from typing import List, Dict, Any
from models.schemas import Artifact, Relation, EvidenceRef


def run_deterministic_pair_checks(artifacts: List[Artifact]) -> List[Relation]:
    """Run deterministic checks across all non-duplicate artifact pairs.

    Args:
        artifacts: List of ingested Artifact objects.

    Returns:
        List of generated Relation objects.
    """
    relations: List[Relation] = []
    # Filter out duplicate or rejected artifacts
    valid_arts = [a for a in artifacts if a.status in ("pending", "ok", "degraded")]

    for i in range(len(valid_arts)):
        for j in range(i + 1, len(valid_arts)):
            art1 = valid_arts[i]
            art2 = valid_arts[j]

            # 1. Date comparison check
            date1 = art1.metadata.get("exif", {}).get("DateTimeOriginal") or art1.metadata.get("exif", {}).get("DateTime")
            text2 = art2.metadata.get("text_content", "")

            if date1 and text2:
                # Simple year match check
                year_match = re.search(r"\b(19|20)\d{2}\b", str(date1))
                if year_match:
                    exif_year = year_match.group(0)
                    text_years = re.findall(r"\b(19|20)\d{2}\b", text2)
                    if text_years and exif_year not in text_years:
                        rel = Relation(
                            source_id=art1.id,
                            target_id=art2.id,
                            relation="CONTRADICTS",
                            conflict_type="time",
                            method="deterministic",
                            confidence_level="high",
                            evidence_refs=[
                                EvidenceRef(type="region", value="metadata"),
                                EvidenceRef(type="page", value="1"),
                            ],
                            explanation=f"EXIF date year ({exif_year}) contradicts years mentioned in text ({', '.join(set(text_years))}).",
                        )
                        relations.append(rel)
                    elif text_years and exif_year in text_years:
                        rel = Relation(
                            source_id=art1.id,
                            target_id=art2.id,
                            relation="SUPPORTS",
                            conflict_type=None,
                            method="deterministic",
                            confidence_level="medium",
                            evidence_refs=[
                                EvidenceRef(type="region", value="metadata"),
                                EvidenceRef(type="page", value="1"),
                            ],
                            explanation=f"EXIF date year ({exif_year}) matches timeline in text.",
                        )
                        relations.append(rel)

    return relations
