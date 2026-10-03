"""Core Pydantic data models for TrustLayers (T²).

All models strictly conform to specifications in DATA.md section 2.
Strict validation is enforced (`extra = "forbid"`) per RULES R-CODE-04.
"""

from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    """Base model enforcing strict validation (extra fields forbidden)."""
    model_config = ConfigDict(extra="forbid")


class Reliability(StrictBaseModel):
    """Per-artifact quality and reliability profiling metrics."""
    resolution: Optional[float] = None
    compression: Optional[float] = None
    noise: Optional[float] = None
    asr_confidence: Optional[float] = None
    language_flag: Optional[str] = None
    score: float = Field(ge=0.0, le=1.0, description="Aggregated reliability score between 0 and 1")


class EvidenceRef(StrictBaseModel):
    """Grounded evidence reference indicating exact artifact region or location."""
    type: Literal["frame", "timestamp", "page", "region"]
    value: str  # e.g., "37", "00:00:20.4", "2", "x,y,w,h"


class EvidenceItem(StrictBaseModel):
    """Individual atomic evidence item derived from local or LLM checks."""
    id: str
    artifact_ids: List[str]  # 1 for artifact scope, 2+ for pair or set
    direction: Literal["manipulated", "authentic", "neutral"]
    strength: float = Field(ge=0.0, le=1.0, description="Mapped from strength class, never LLM-reported")
    reliability: float = Field(ge=0.0, le=1.0)
    scope: Literal["artifact", "pair", "set"]
    evidence_ref: EvidenceRef
    description: str
    source: Literal["detector", "forensic", "llm", "deterministic"]
    check_id: str


ModalityType = Literal["image", "video", "audio", "text", "document"]


class Artifact(StrictBaseModel):
    """Artifact metadata, derived metrics, and extracted evidence items."""
    id: str
    modality: ModalityType
    display_name: str  # Shown to user; never logged
    sha256: str
    status: Literal["pending", "ok", "degraded", "failed", "rejected", "duplicate"]
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    reliability: Optional[Reliability] = None
    semantic_claims: List[Dict[str, Any]] = Field(default_factory=list)
    detector_signals: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)


class Relation(StrictBaseModel):
    """Cross-modal or pair relation between artifacts."""
    source_id: str
    target_id: str
    relation: Literal["SUPPORTS", "CONTRADICTS", "MATCHES", "LINKED", "UNCERTAIN"]
    conflict_type: Optional[str] = None  # identity, object, event, location, time, speech_content, scene, quantity
    method: Literal["deterministic", "llm"]
    confidence_level: Literal["low", "medium", "high"]
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)
    explanation: Optional[str] = None


class Fusion(StrictBaseModel):
    """Deterministic fusion result and verdict calculation."""
    manip_evidence: float = Field(ge=0.0, le=1.0)
    auth_support: float = Field(ge=0.0, le=1.0)
    sufficiency: float = Field(ge=0.0, le=1.0)
    checks_completed: int = Field(ge=0)
    checks_applicable: int = Field(ge=0)
    verdict: Literal["AUTHENTIC", "MANIPULATED", "COORDINATED_SYNTHETIC", "INCONCLUSIVE"]
    reason_codes: List[str]
    confidence_level: Literal["low", "medium", "high"]
    inconclusive_label: Optional[str] = None
    limitations: List[str] = Field(default_factory=list)
    unavailable_checks: List[str] = Field(default_factory=list)


class Case(StrictBaseModel):
    """Root Case entity holding all artifacts, relations, and final verdict."""
    id: str
    description: Optional[str] = None
    job_status: Literal[
        "created", "ingesting", "preprocessing", "analyzing",
        "reasoning", "fusing", "completed", "failed", "timed_out"
    ]
    artifacts: List[Artifact] = Field(default_factory=list)
    relations: List[Relation] = Field(default_factory=list)
    fusion: Optional[Fusion] = None
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class CaseInput(StrictBaseModel):
    """Input payload to start case investigation."""
    case_id: str
    files: List[Dict[str, Any]]  # List of {'filename': str, 'bytes': bytes or 'path': str}
    description: Optional[str] = None


class ProgressEvent(StrictBaseModel):
    """Progress status update emitted during pipeline execution."""
    case_id: str
    stage: str
    artifact_id: Optional[str] = None
    status: Literal["waiting", "running", "done", "unavailable", "failed", "retrying"]
    message: str
    error_code: Optional[str] = None


class CaseResult(StrictBaseModel):
    """Final result container returned by run_case."""
    case: Case
    report_path: Optional[str] = None
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
