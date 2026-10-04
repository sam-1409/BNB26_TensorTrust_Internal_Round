"""Metrics computation engine for TrustLayers evaluation benchmark.

Calculates:
- Confusion Matrix across all 4 valid verdicts: AUTHENTIC, MANIPULATED, COORDINATED_SYNTHETIC, INCONCLUSIVE
- Per-class Precision, Recall, and F1
- Macro-F1 across active classes
- Coverage Rate (fraction of cases with non-INCONCLUSIVE verdict)
- False-Confidence Rate (safety metric: fraction of high-confidence predictions that are incorrect)
- Grounding Rate (fraction of evidence items with resolvable references)
"""

from typing import List, Dict, Any, Optional

VERDICT_CLASSES = ["AUTHENTIC", "MANIPULATED", "COORDINATED_SYNTHETIC", "INCONCLUSIVE"]


def compute_confusion_matrix(
    ground_truths: List[str],
    predictions: List[str],
    classes: Optional[List[str]] = None,
) -> Dict[str, Dict[str, int]]:
    """Compute confusion matrix mapping actual class -> predicted class counts."""
    if classes is None:
        classes = VERDICT_CLASSES

    matrix = {act: {pred: 0 for pred in classes} for act in classes}

    for act, pred in zip(ground_truths, predictions):
        if act in matrix and pred in matrix[act]:
            matrix[act][pred] += 1

    return matrix


def compute_per_class_metrics(
    confusion_matrix: Dict[str, Dict[str, int]],
    classes: Optional[List[str]] = None,
) -> Dict[str, Dict[str, float]]:
    """Compute precision, recall, and F1 per class from confusion matrix."""
    if classes is None:
        classes = VERDICT_CLASSES

    metrics = {}
    for c in classes:
        tp = confusion_matrix.get(c, {}).get(c, 0)
        fp = sum(confusion_matrix.get(other, {}).get(c, 0) for other in classes if other != c)
        fn = sum(confusion_matrix.get(c, {}).get(other, 0) for other in classes if other != c)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        metrics[c] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": tp + fn,
        }

    return metrics


def compute_macro_f1(
    confusion_matrix: Dict[str, Dict[str, int]],
    classes: Optional[List[str]] = None,
) -> float:
    """Compute unweighted Macro-F1 across classes with support > 0."""
    per_class = compute_per_class_metrics(confusion_matrix, classes)
    f1_scores = [m["f1"] for c, m in per_class.items() if m["support"] > 0]
    if not f1_scores:
        return 0.0
    return round(sum(f1_scores) / len(f1_scores), 4)


def compute_coverage_rate(predictions: List[str]) -> float:
    """Compute fraction of non-INCONCLUSIVE decisions."""
    if not predictions:
        return 0.0
    conclusive = sum(1 for p in predictions if p != "INCONCLUSIVE")
    return round(conclusive / len(predictions), 4)


def compute_false_confidence_rate(
    ground_truths: List[str],
    predictions: List[str],
    confidences: List[str],
) -> float:
    """Safety metric: fraction of HIGH confidence predictions that are incorrect."""
    high_conf_count = 0
    false_high_conf_count = 0

    for gt, pred, conf in zip(ground_truths, predictions, confidences):
        if str(conf).lower() == "high":
            high_conf_count += 1
            if pred != gt:
                false_high_conf_count += 1

    if high_conf_count == 0:
        return 0.0
    return round(false_high_conf_count / high_conf_count, 4)
