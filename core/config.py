"""Central configuration module for TrustLayers (T²).

All limits, thresholds, supported formats, and model identifiers live ONLY in this module
per RULES R-CODE-03.
"""

import os
from pathlib import Path
from typing import Final, Dict, Set, List

# Environment Settings
GEMINI_API_KEY: Final[str] = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL: Final[str] = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_TIER: Final[str] = os.environ.get("GEMINI_TIER", "paid")  # paid | free
APP_MODE: Final[str] = os.environ.get("APP_MODE", "interactive")  # interactive | eval

# Directory Paths
BASE_DIR: Final[Path] = Path(__file__).parent.parent
DATA_DIR: Final[Path] = BASE_DIR / "data"
SESSIONS_DIR: Final[Path] = DATA_DIR / "sessions"
SAMPLES_DIR: Final[Path] = BASE_DIR / "samples"
EVAL_RESULTS_DIR: Final[Path] = BASE_DIR / "eval" / "results"

# Supported Content Types & Magic Byte Signatures (R-UP-01)
# Mapping MIME type categories to supported extensions/magic signatures
SUPPORTED_IMAGE_TYPES: Final[Set[str]] = {"image/jpeg", "image/png", "image/webp"}
SUPPORTED_VIDEO_TYPES: Final[Set[str]] = {"video/mp4", "video/webm", "video/quicktime"}
SUPPORTED_AUDIO_TYPES: Final[Set[str]] = {"audio/mpeg", "audio/wav", "audio/mp4", "audio/ogg", "audio/flac"}
SUPPORTED_TEXT_TYPES: Final[Set[str]] = {"text/plain"}
SUPPORTED_DOCUMENT_TYPES: Final[Set[str]] = {"application/pdf"}

ALL_SUPPORTED_MIME_TYPES: Final[Set[str]] = (
    SUPPORTED_IMAGE_TYPES
    | SUPPORTED_VIDEO_TYPES
    | SUPPORTED_AUDIO_TYPES
    | SUPPORTED_TEXT_TYPES
    | SUPPORTED_DOCUMENT_TYPES
)

# Magic Bytes Signatures for Content Verification (R-UP-01)
MAGIC_SIGNATURES: Final[Dict[str, List[bytes]]] = {
    "image/jpeg": [b"\xFF\xD8\xFF"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"],  # Checked along with WEBP chunk
    "video/mp4": [b"ftyp"],   # Check offset 4
    "application/pdf": [b"%PDF-"],
}

# Ingest Limits (R-UP-03, R-UP-05)
MAX_FILE_SIZE_BYTES: Final[int] = 100 * 1024 * 1024  # 100 MB
MAX_FILES_PER_CASE: Final[int] = 20
MAX_VIDEO_DURATION_SECONDS: Final[float] = 600.0  # 10 minutes
MAX_AUDIO_DURATION_SECONDS: Final[float] = 600.0  # 10 minutes
MAX_PDF_PAGES: Final[int] = 50
MAX_IMAGE_PIXELS: Final[int] = 4096 * 4096  # 16 MP limit for bounds checking

# Preprocessing Settings
VIDEO_SAMPLE_FPS: Final[float] = 1.0  # 1 frame per second sampled for video

# Fusion & Decision Thresholds (TBD placeholders to be tuned per ML.md / EVAL.md)
# All values tagged TBD until Dev evaluation run (R-DOC-03)
THRESHOLDS: Final[Dict[str, float]] = {
    "tau_m": 0.65,          # Threshold for MANIPULATED verdict (TBD)
    "tau_a": 0.60,          # Threshold for AUTHENTIC verdict (TBD)
    "tau_s": 0.40,          # Threshold for MINIMUM SUFFICIENCY (TBD)
    "tau_coord": 0.70,      # Threshold for COORDINATED_SYNTHETIC verdict (TBD)
    "tau_rel_low": 0.30,    # Reliability gate lower limit (TBD)
}

# Strength Classes Mapping (DATA.md / ML.md)
STRENGTH_CLASS_WEIGHTS: Final[Dict[str, float]] = {
    "weak": 0.25,
    "moderate": 0.50,
    "strong": 0.85,
}

# Timeout Limits
STAGE_TIMEOUT_SECONDS: Final[int] = 120
LLM_RETRY_COUNT: Final[int] = 1
