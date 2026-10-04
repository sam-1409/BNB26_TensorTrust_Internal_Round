"""Unit tests for Phase 9: eval/metrics.py."""

from eval.metrics import (
    compute_confusion_matrix,
    compute_per_class_metrics,
    compute_macro_f1,
    compute_coverage_rate,
    compute_false_confidence_rate,
)


def test_confusion_matrix_and_f1():
    ground_truths = ["AUTHENTIC", "MANIPULATED", "AUTHENTIC", "COORDINATED_SYNTHETIC"]
    predictions = ["AUTHENTIC", "MANIPULATED", "INCONCLUSIVE", "COORDINATED_SYNTHETIC"]

    matrix = compute_confusion_matrix(ground_truths, predictions)
    assert matrix["AUTHENTIC"]["AUTHENTIC"] == 1
    assert matrix["AUTHENTIC"]["INCONCLUSIVE"] == 1
    assert matrix["MANIPULATED"]["MANIPULATED"] == 1
    assert matrix["COORDINATED_SYNTHETIC"]["COORDINATED_SYNTHETIC"] == 1

    per_class = compute_per_class_metrics(matrix)
    assert per_class["MANIPULATED"]["f1"] == 1.0
    assert per_class["COORDINATED_SYNTHETIC"]["f1"] == 1.0

    macro_f1 = compute_macro_f1(matrix)
    assert 0.0 < macro_f1 <= 1.0


def test_coverage_rate():
    preds = ["AUTHENTIC", "MANIPULATED", "INCONCLUSIVE", "AUTHENTIC"]
    coverage = compute_coverage_rate(preds)
    assert coverage == 0.75


def test_false_confidence_rate():
    # 2 high confidence predictions: 1 correct, 1 wrong
    gts = ["AUTHENTIC", "AUTHENTIC", "MANIPULATED"]
    preds = ["AUTHENTIC", "MANIPULATED", "MANIPULATED"]
    confs = ["high", "high", "low"]

    fcr = compute_false_confidence_rate(gts, preds, confs)
    # Among the 2 high conf predictions, 1 was wrong -> 0.50
    assert fcr == 0.50
