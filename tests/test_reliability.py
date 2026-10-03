"""Unit tests for quality and reliability profiler."""

from core.reliability import compute_reliability_score


def test_reliability_scoring():
    rel = compute_reliability_score(
        resolution=0.8,
        compression=0.9,
        noise=0.7,
    )
    assert rel.score == 0.8
    assert rel.resolution == 0.8
    assert rel.asr_confidence is None


def test_reliability_default():
    rel = compute_reliability_score()
    assert rel.score == 0.5
