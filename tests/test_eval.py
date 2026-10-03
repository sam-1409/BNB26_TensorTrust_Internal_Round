"""Unit tests for Evaluation Runner."""

from eval.run_eval import run_evaluation_benchmark


def test_eval_runner(tmp_path):
    metrics = run_evaluation_benchmark(output_dir=tmp_path)
    assert metrics["cases_evaluated"] == 2
    assert metrics["macro_f1"] == 0.92
    assert (tmp_path / "metrics_summary.json").exists()
