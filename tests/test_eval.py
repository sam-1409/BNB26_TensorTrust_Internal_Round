"""Unit tests for Evaluation Runner."""

from eval.run_eval import run_evaluation_benchmark


def test_eval_runner(tmp_path):
    metrics = run_evaluation_benchmark(output_dir=tmp_path)
    assert metrics["cases_evaluated"] >= 2
    assert 0.0 <= metrics["macro_f1"] <= 1.0
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "results_dev.json").exists()
