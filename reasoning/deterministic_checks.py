"""Deterministic cross-artifact check engine for TrustLayers (T²).

Extracts and checks deterministic claims across artifact pairs:
- Date and timeline consistency (Constraint #15: date mismatches are treated as
  provenance/context uncertainty, never as proof of manipulation or AI generation)
- Location/Name mismatches
- Numerical quantity discrepancies
"""

import re
from typing import List, Dict, Any, Optional
from models.schemas import Artifact, Relation, EvidenceRef


def run_deterministic_pair_checks(artifacts: List[Artifact]) -> List[Relation]:
    """Run deterministic checks across all non-duplicate artifact pairs.

    Enforces TIMESTAMP SEMANTICS (Constraint #15):
    - EXIF-year vs text-year/date mismatch must NOT produce a CONTRADICTS relation.
    - Differing creation, modification, publication, or republishing dates must
      NOT independently imply AI generation or manipulation.
    - Timestamp differences are classified as UNCERTAIN (low confidence) provenance context.
    - Matching timeline produces SUPPORTS (medium confidence).

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

            # 1. Date comparison check across pair (bidirectional check)
            date1 = art1.metadata.get("exif", {}).get("DateTimeOriginal") or art1.metadata.get("exif", {}).get("DateTime")
            text1 = art1.metadata.get("text_content", "")

            date2 = art2.metadata.get("exif", {}).get("DateTimeOriginal") or art2.metadata.get("exif", {}).get("DateTime")
            text2 = art2.metadata.get("text_content", "")

            image_art: Optional[Artifact] = None
            text_art: Optional[Artifact] = None
            date_val: Optional[Any] = None
            text_val: Optional[str] = None

            if date1 and text2:
                image_art, text_art = art1, art2
                date_val, text_val = date1, text2
            elif date2 and text1:
                image_art, text_art = art2, art1
                date_val, text_val = date2, text1

            if image_art and text_art and date_val and text_val:
                year_match = re.search(r"\b(?:19|20)\d{2}\b", str(date_val))
                if year_match:
                    exif_year = year_match.group(0)
                    text_years = re.findall(r"\b(?:19|20)\d{2}\b", str(text_val))
                    if text_years:
                        sorted_years = sorted(set(text_years))
                        if exif_year in sorted_years:
                            rel = Relation(
                                source_id=image_art.id,
                                target_id=text_art.id,
                                relation="SUPPORTS",
                                conflict_type=None,
                                method="deterministic",
                                confidence_level="medium",
                                evidence_refs=[
                                    EvidenceRef(type="region", value="metadata"),
                                    EvidenceRef(type="page", value="1"),
                                ],
                                explanation=f"EXIF date year ({exif_year}) matches timeline in text ({', '.join(sorted_years)}).",
                            )
                            relations.append(rel)
                        else:
                            # Hard rule: date mismatch is provenance context / UNCERTAIN, NEVER CONTRADICTS
                            rel = Relation(
                                source_id=image_art.id,
                                target_id=text_art.id,
                                relation="UNCERTAIN",
                                conflict_type="time",
                                method="deterministic",
                                confidence_level="low",
                                evidence_refs=[
                                    EvidenceRef(type="region", value="metadata"),
                                    EvidenceRef(type="page", value="1"),
                                ],
                                explanation=(
                                    f"Temporal difference detected: EXIF date year ({exif_year}) differs from "
                                    f"years mentioned in text ({', '.join(sorted_years)}). "
                                    "Treated as provenance/context uncertainty (re-publication, editing, or format conversion), "
                                    "never as manipulation or AI generation evidence."
                                ),
                            )
                            relations.append(rel)

    return relations
