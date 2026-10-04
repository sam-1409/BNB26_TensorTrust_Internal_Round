"""Baseline Ablation Runner for TrustLayers (T²).

Implements the independent-artifact ablation baseline:
- Analyzes each artifact independently without cross-modal reasoning, cross-platform queries, or set coordination.
- Rule: If any artifact is individually flagged as manipulated, case verdict is MANIPULATED.
- Else if any artifact shows coordinated synthetic markers, COORDINATED_SYNTHETIC.
- Else if any artifact achieves AUTHENTIC without conflicting signals, AUTHENTIC.
- Else INCONCLUSIVE.
- Comparing TrustLayers against this baseline proves the value of cross-modal + cross-platform evidence reasoning.
"""

from typing import List, Dict, Any, Tuple
from models.schemas import CaseInput
from core.orchestrator import run_case


def run_baseline_case(case_spec: Dict[str, Any]) -> str:
    """Run independent-artifact baseline on a case specification.

    Returns:
        Predicted verdict string.
    """
    files = case_spec.get("files", [])
    if not files:
        return "INCONCLUSIVE"

    individual_verdicts: List[str] = []

    # Run each artifact alone in isolation
    for idx, f in enumerate(files):
        sub_case_input = CaseInput(
            case_id=f"base_{case_spec['case_id']}_{idx}",
            files=[f],
            description=None,
            platform_urls=[],
        )
        res = run_case(sub_case_input)
        if res.case.fusion:
            individual_verdicts.append(res.case.fusion.verdict)
        else:
            individual_verdicts.append("INCONCLUSIVE")

    # Aggregate individual verdicts
    if "MANIPULATED" in individual_verdicts:
        return "MANIPULATED"
    if "COORDINATED_SYNTHETIC" in individual_verdicts:
        return "COORDINATED_SYNTHETIC"
    if "AUTHENTIC" in individual_verdicts:
        return "AUTHENTIC"
    return "INCONCLUSIVE"
