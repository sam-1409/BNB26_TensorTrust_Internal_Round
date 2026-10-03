"""Uncertainty and confidence level evaluator for TrustLayers (T²).

Enforces:
- R-ML-04: Never display a bare percentage. Confidence is expressed as ordinal words ('low', 'medium', 'high').
- Fusion rules: INCONCLUSIVE always receives 'low' confidence level.
"""

from typing import Literal, List
from models.schemas import EvidenceItem


def compute_confidence_level(
    verdict: str,
    sufficiency: float,
    evidence_items: List[EvidenceItem],
    tau_s: float = 0.40,
) -> Literal["low", "medium", "high"]:
    """Compute verdict confidence level ('low', 'medium', 'high').

    Args:
        verdict: Computed verdict label.
        sufficiency: Sufficiency score sigma [0..1].
        evidence_items: List of grounded evidence items used in verdict.
        tau_s: Sufficiency threshold.

    Returns:
        Confidence level literal ('low' | 'medium' | 'high').
    """
    if verdict == "INCONCLUSIVE":
        return "low"

    # Count independent non-LLM supporting items matching verdict direction
    target_direction = "manipulated" if verdict in ("MANIPULATED", "COORDINATED_SYNTHETIC") else "authentic"

    matching_items = [
        item for item in evidence_items
        if item.direction == target_direction
    ]

    non_llm_items = [item for item in matching_items if item.source != "llm"]

    if len(non_llm_items) >= 2 and sufficiency >= tau_s:
        return "high"
    elif len(non_llm_items) >= 1 or len(matching_items) >= 1:
        return "medium"
    else:
        return "low"
