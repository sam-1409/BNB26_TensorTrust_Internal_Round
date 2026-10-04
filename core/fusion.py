"""Deterministic Fusion Engine for TrustLayers (T²).

Enforces:
- R-ML-01: Verdict is computed strictly by deterministic code.
- R-ML-02: AUTHENTIC requires positive support above tau_a and low manipulation evidence.
- R-ML-03: Low quality lowers reliability/sufficiency only, never raises manipulation evidence.
- R-ML-07: An unavailable check is never counted as completed.
- R-ML-10: Every verdict includes a limitations statement.
"""

import math
from typing import List, Dict, Any, Tuple, Optional
from models.schemas import Artifact, EvidenceItem, Relation, Fusion
from core.config import THRESHOLDS, CHECK_CATALOG
from core.uncertainty import compute_confidence_level


def compute_applicable_checks(
    artifacts: List[Artifact],
    catalog: Optional[Dict[str, Dict[str, Any]]] = None,
) -> int:
    """Compute the count of applicable checks from the check catalog for the given artifacts.

    A check is applicable if and only if:
    1. The check is enabled in the catalog (enabled != False).
    2. The case contains at least the min_artifacts total valid artifacts required.
    3. All required modalities for the check are present among valid artifacts.
       - A required modality of "text" is satisfied by either "text" or "document" (PDF text).
       - Modality-specific artifact count minimums (e.g., min_artifacts=2 on single-modality
         checks like perceptual coordination) are strictly checked against modality counts.

    Args:
        artifacts: List of ingested Artifact objects.
        catalog: Optional catalog dictionary. Defaults to CHECK_CATALOG from core.config.

    Returns:
        Integer count of dynamically applicable checks.
    """
    if catalog is None:
        catalog = CHECK_CATALOG

    valid_arts = [a for a in artifacts if a.status in ("ok", "pending", "degraded")]
    if not valid_arts:
        return 0

    modality_counts: Dict[str, int] = {}
    for a in valid_arts:
        modality_counts[a.modality] = modality_counts.get(a.modality, 0) + 1

    case_modalities = set(modality_counts.keys())
    total_valid_arts = len(valid_arts)

    applicable_count = 0
    for check_id, check_def in catalog.items():
        if not check_def.get("enabled", True):
            continue

        req_modalities = check_def.get("modalities", [])
        min_artifacts = check_def.get("min_artifacts", 1)

        # Check overall artifact count requirement
        if total_valid_arts < min_artifacts:
            continue

        # Check required modalities
        applies = True
        for req_mod in req_modalities:
            if req_mod == "text":
                if not (case_modalities & {"text", "document"}):
                    applies = False
                    break
            else:
                if req_mod not in case_modalities:
                    applies = False
                    break

        if not applies:
            continue

        # For single-modality checks requiring multiple artifacts (e.g. coordination across >=2 images)
        if len(req_modalities) == 1 and min_artifacts > 1:
            req_mod = req_modalities[0]
            if modality_counts.get(req_mod, 0) < min_artifacts:
                continue

        applicable_count += 1

    return applicable_count


def compute_fusion(
    artifacts: List[Artifact],
    evidence_items: List[EvidenceItem],
    relations: List[Relation],
    unavailable_checks: Optional[List[str]] = None,
    catalog: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Fusion:
    """Compute deterministic fusion formulas, verdict rules, reason codes, and limitations.

    Args:
        artifacts: List of grounded artifacts.
        evidence_items: List of grounded evidence items.
        relations: List of relations between artifacts.
        unavailable_checks: List of check IDs that were unavailable/failed.
        catalog: Optional check catalog dictionary override.

    Returns:
        Strict Fusion schema model.
    """
    if unavailable_checks is None:
        unavailable_checks = []

    tau_m = THRESHOLDS["tau_m"]
    tau_a = THRESHOLDS["tau_a"]
    tau_s = THRESHOLDS["tau_s"]
    tau_l = THRESHOLDS.get("tau_l", 0.25)
    tau_r = THRESHOLDS["tau_rel_low"]

    # 1. Separate evidence items by direction
    manip_items = [item for item in evidence_items if item.direction == "manipulated"]
    auth_items = [item for item in evidence_items if item.direction == "authentic"]

    # 2. Noisy-OR Fusion formula for manipulation evidence m
    # m = 1 - prod(1 - s_i * r_i)
    prod_m = 1.0
    for item in manip_items:
        impact = item.strength * item.reliability
        prod_m *= (1.0 - impact)
    m = max(0.0, min(1.0, 1.0 - prod_m))

    # 3. Noisy-OR Fusion formula for authenticity support a
    # a = 1 - prod(1 - s_j * r_j)
    prod_a = 1.0
    for item in auth_items:
        impact = item.strength * item.reliability
        prod_a *= (1.0 - impact)
    a = max(0.0, min(1.0, 1.0 - prod_a))

    # 4. Compute sufficiency sigma = (reliable checks completed) / (checks applicable)
    total_applicable_checks = compute_applicable_checks(artifacts, catalog=catalog)
    completed_checks = len(evidence_items)
    reliable_completed_checks = sum(1 for item in evidence_items if item.reliability >= tau_r)

    if total_applicable_checks > 0:
        sufficiency = max(0.0, min(1.0, reliable_completed_checks / float(total_applicable_checks)))
    else:
        sufficiency = 0.0

    # 5. Check set-level coordination (LINKED/MATCHES relations)
    linked_relations = [
        r for r in relations
        if r.relation in ("LINKED", "MATCHES")
        and r.conflict_type in ("set_coordination", "near_duplicate", "text_repost")
    ]
    # Check if >= 2 artifacts have artifact-level m > tau_m and are linked
    arts_with_manip = set()
    for item in manip_items:
        arts_with_manip.update(item.artifact_ids)

    is_coordinated_synthetic = False
    if len(linked_relations) > 0 and len(arts_with_manip) >= 2:
        for rel in linked_relations:
            if rel.source_id in arts_with_manip and rel.target_id in arts_with_manip:
                is_coordinated_synthetic = True
                break

    # 6. Verdict Evaluation Rules (First match wins)
    verdict = "INCONCLUSIVE"
    inconclusive_label = None
    reason_codes: List[str] = []

    # Rule 1: Sufficiency check or conflicting signals
    if sufficiency < tau_s:
        verdict = "INCONCLUSIVE"
        inconclusive_label = "insufficient evidence to establish authenticity or manipulation"
        reason_codes.append("INSUFFICIENT_EVIDENCE")
    elif m > tau_m and a > tau_a:
        verdict = "INCONCLUSIVE"
        inconclusive_label = "conflicting evidence signals detected"
        reason_codes.append("CONFLICTING_SIGNALS")
    # Rule 2: Coordinated synthetic set
    elif is_coordinated_synthetic:
        verdict = "COORDINATED_SYNTHETIC"
        reason_codes.append("LINKED_SYNTHETIC_SET")
        reason_codes.append("SYNTHETIC_ARTIFACT")
    # Rule 3: Manipulated
    elif m > tau_m:
        verdict = "MANIPULATED"
        # Determine dominant reason code
        if any(r.conflict_type for r in relations if r.relation == "CONTRADICTS"):
            reason_codes.append("CROSS_MODAL_CONTRADICTION")
        else:
            reason_codes.append("SYNTHETIC_ARTIFACT")
    # Rule 4: Authentic
    elif m < tau_l and a > tau_a and sufficiency >= tau_s:
        verdict = "AUTHENTIC"
    # Rule 5: Otherwise Inconclusive
    else:
        verdict = "INCONCLUSIVE"
        inconclusive_label = "no manipulation detected; authenticity not established"
        reason_codes.append("INSUFFICIENT_EVIDENCE")

    # 7. Limitations statement formulation (R-ML-10)
    limitations: List[str] = []
    if unavailable_checks:
        limitations.append(f"The following checks were unavailable: {', '.join(unavailable_checks)}")
    if sufficiency < tau_s:
        limitations.append("Overall evidence sufficiency is below the recommended confidence threshold.")
    if not auth_items and verdict == "INCONCLUSIVE":
        limitations.append("No positive content credentials or corroborating sources were available.")

    # 8. Confidence level evaluation
    confidence_level = compute_confidence_level(
        verdict=verdict,
        sufficiency=sufficiency,
        evidence_items=evidence_items,
        tau_s=tau_s,
    )

    return Fusion(
        manip_evidence=round(m, 4),
        auth_support=round(a, 4),
        sufficiency=round(sufficiency, 4),
        checks_completed=completed_checks,
        checks_applicable=total_applicable_checks,
        verdict=verdict,
        reason_codes=reason_codes,
        confidence_level=confidence_level,
        inconclusive_label=inconclusive_label,
        limitations=limitations,
        unavailable_checks=unavailable_checks,
    )
