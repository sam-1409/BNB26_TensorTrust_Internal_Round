"""Evaluation benchmark runner and ablation analysis for TrustLayers (T²).

Executes:
- Full TrustLayers pipeline on benchmark cases (DEV split or HELD-OUT split).
- Independent-artifact baseline ablation.
- Real mathematical computation of Confusion Matrix, Macro-F1, Coverage Rate,
  and False-Confidence Rate via eval/metrics.py.
- Side-by-side TrustLayers vs Baseline comparison.
"""

import json
import argparse
from pathlib import Path
from typing import Dict, Any, List

from core.config import EVAL_RESULTS_DIR
from models.schemas import CaseInput
from core.orchestrator import run_case
from eval.benchmark.manifest import get_benchmark_cases
from eval.metrics import (
    compute_confusion_matrix,
    compute_per_class_metrics,
    compute_macro_f1,
    compute_coverage_rate,
    compute_false_confidence_rate,
)
from eval.baseline import run_baseline_case


def evaluate_split(split: str = "dev", output_dir: Path = EVAL_RESULTS_DIR) -> Dict[str, Any]:
    """Execute evaluation benchmark for a given split ('dev', 'held_out', or 'all').

    Args:
        split: 'dev' | 'held_out' | 'all'
        output_dir: Directory where results JSON should be saved.

    Returns:
        Dictionary of computed metrics and ablation comparison.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    all_cases = get_benchmark_cases()

    if split != "all":
        selected_cases = [c for c in all_cases if c["split"] == split]
    else:
        selected_cases = all_cases

    if not selected_cases:
        raise ValueError(f"No cases found for split '{split}'")

    ground_truths: List[str] = []
    tl_predictions: List[str] = []
    tl_confidences: List[str] = []
    baseline_predictions: List[str] = []

    case_details: List[Dict[str, Any]] = []

    for c in selected_cases:
        case_id = c["case_id"]
        gt = c["label"]
        ground_truths.append(gt)

        # 1. Run TrustLayers Full Pipeline
        case_input = CaseInput(
            case_id=case_id,
            files=c["files"],
            description=c.get("description"),
            platform_urls=c.get("platform_urls", []),
        )
        tl_result = run_case(case_input)
        tl_verdict = tl_result.case.fusion.verdict if tl_result.case.fusion else "INCONCLUSIVE"
        tl_conf = tl_result.case.fusion.confidence_level if tl_result.case.fusion else "low"

        tl_predictions.append(tl_verdict)
        tl_confidences.append(tl_conf)

        # 2. Run Baseline Ablation
        base_verdict = run_baseline_case(c)
        baseline_predictions.append(base_verdict)

        case_details.append({
            "case_id": case_id,
            "split": c["split"],
            "ground_truth": gt,
            "trustlayers_verdict": tl_verdict,
            "trustlayers_confidence": tl_conf,
            "baseline_verdict": base_verdict,
            "correct_trustlayers": (tl_verdict == gt),
            "correct_baseline": (base_verdict == gt),
        })

    # Compute TrustLayers Metrics
    tl_matrix = compute_confusion_matrix(ground_truths, tl_predictions)
    tl_per_class = compute_per_class_metrics(tl_matrix)
    tl_macro_f1 = compute_macro_f1(tl_matrix)
    tl_coverage = compute_coverage_rate(tl_predictions)
    tl_false_conf = compute_false_confidence_rate(ground_truths, tl_predictions, tl_confidences)

    # Compute Baseline Metrics
    base_matrix = compute_confusion_matrix(ground_truths, baseline_predictions)
    base_macro_f1 = compute_macro_f1(base_matrix)
    base_coverage = compute_coverage_rate(baseline_predictions)
    base_false_conf = compute_false_confidence_rate(ground_truths, baseline_predictions, ["medium"] * len(baseline_predictions))

    summary = {
        "split": split,
        "cases_evaluated": len(selected_cases),
        "macro_f1": tl_macro_f1,
        "coverage_rate": tl_coverage,
        "false_confidence_rate": tl_false_conf,
        "confusion_matrix": tl_matrix,
        "per_class_metrics": tl_per_class,
        "ablation": {
            "trustlayers_macro_f1": tl_macro_f1,
            "baseline_macro_f1": base_macro_f1,
            "macro_f1_delta": round(tl_macro_f1 - base_macro_f1, 4),
            "trustlayers_coverage": tl_coverage,
            "baseline_coverage": base_coverage,
            "trustlayers_false_confidence": tl_false_conf,
            "baseline_false_confidence": base_false_conf,
        },
        "case_details": case_details,
    }

    # Save results to disk
    summary_path = output_dir / f"results_{split}.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Also save as latest summary.json
    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


def run_evaluation_benchmark(output_dir: Path = EVAL_RESULTS_DIR) -> Dict[str, Any]:
    """Backward compatible alias for running evaluation benchmark."""
    return evaluate_split(split="dev", output_dir=output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TrustLayers Evaluation Runner")
    parser.add_argument("--output", type=str, default=str(EVAL_RESULTS_DIR))
    parser.add_argument("--split", type=str, default="dev", help="Evaluation split (dev | held_out | all)")
    args = parser.parse_args()

    results = evaluate_split(split=args.split, output_dir=Path(args.output))
    print(f"Evaluation complete for split '{args.split}'. Results written to {args.output}")
    print(json.dumps({
        "cases_evaluated": results["cases_evaluated"],
        "macro_f1": results["macro_f1"],
        "coverage_rate": results["coverage_rate"],
        "false_confidence_rate": results["false_confidence_rate"],
        "confusion_matrix": results["confusion_matrix"],
        "ablation": results["ablation"],
    }, indent=2))
