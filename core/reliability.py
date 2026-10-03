"""Quality and reliability profiler for TrustLayers (T²).

Enforces RULE R-ML-03:
- Low quality lowers reliability and sufficiency only.
- It NEVER raises manipulation evidence.
"""

from typing import Optional
from models.schemas import Reliability
from core.config import THRESHOLDS


def compute_reliability_score(
    resolution: Optional[float] = None,
    compression: Optional[float] = None,
    noise: Optional[float] = None,
    asr_confidence: Optional[float] = None,
    language_flag: Optional[str] = None,
) -> Reliability:
    """Calculate aggregated reliability object for an artifact (R-ML-03).

    Args:
        resolution: Normalized resolution score [0..1].
        compression: Quality factor/compression score [0..1].
        noise: Signal-to-noise ratio score [0..1].
        asr_confidence: Local ASR confidence score [0..1].
        language_flag: ISO language code string.

    Returns:
        Reliability schema object with aggregated score [0..1].
    """
    scores = []
    if resolution is not None:
        scores.append(resolution)
    if compression is not None:
        scores.append(compression)
    if noise is not None:
        scores.append(noise)
    if asr_confidence is not None:
        scores.append(asr_confidence)

    if not scores:
        agg_score = 0.5  # Neutral default if no quality metrics available
    else:
        # Aggregation formula: arithmetic mean of available quality signals
        # Aggregation method tagged TBD per ML-003 / ARCHITECTURE
        agg_score = max(0.0, min(1.0, sum(scores) / len(scores)))

    return Reliability(
        resolution=resolution,
        compression=compression,
        noise=noise,
        asr_confidence=asr_confidence,
        language_flag=language_flag,
        score=round(agg_score, 4),
    )
