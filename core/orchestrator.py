"""Full pipeline orchestrator module for TrustLayers (T²).

Enforces:
- R-CODE-02: run_case is the single pipeline entry point called by UI and eval.
- Standard 11-stage pipeline execution and failure handling.
"""

from pathlib import Path
from typing import Callable, Optional, List, Dict, Any

from models.schemas import CaseInput, CaseResult, Case, ProgressEvent, Artifact, EvidenceItem, Relation
from services.storage import StorageManager, delete_case as storage_delete_case
from ingest.pipeline import ingest_files
from ingest.type_verifier import IngestValidationError
from adapters.image import analyze_image
from adapters.video import analyze_video
from adapters.audio import analyze_audio
from adapters.text import analyze_text_file, analyze_pdf_document
from reasoning.grounding import filter_grounded_evidence, filter_grounded_relations
from reasoning.deterministic_checks import run_deterministic_pair_checks
from reasoning.coordination import detect_coordination
from core.fusion import compute_fusion


def run_case(
    case_input: CaseInput,
    on_progress: Optional[Callable[[ProgressEvent], None]] = None,
) -> CaseResult:
    """Run full investigation pipeline for a case (R-CODE-02).

    Args:
        case_input: CaseInput payload with case_id and files.
        on_progress: Optional progress event callback.

    Returns:
        CaseResult container holding Case, fusion, report, and diagnostics.
    """
    case_id = case_input.case_id
    storage = StorageManager(case_id)
    diagnostics: Dict[str, Any] = {
        "grounding_rejection_count": 0,
        "unavailable_checks": [],
    }

    def emit_progress(stage: str, status: str, message: str, art_id: Optional[str] = None, error_code: Optional[str] = None):
        if on_progress:
            event = ProgressEvent(
                case_id=case_id,
                stage=stage,
                artifact_id=art_id,
                status=status,
                message=message,
                error_code=error_code,
            )
            on_progress(event)

    try:
        # 1. Ingestion Stage
        emit_progress("ingest", "running", "Ingesting and validating files...")
        artifacts, notices = ingest_files(case_id, case_input.files, storage)
        emit_progress("ingest", "done", f"Ingested {len(artifacts)} files.")

        # 2. Preprocessing & Modality Adapters
        emit_progress("preprocessing", "running", "Analyzing artifact content & profiling quality...")
        processed_artifacts: List[Artifact] = []
        all_evidence: List[EvidenceItem] = []

        for art in artifacts:
            if art.status in ("rejected", "duplicate"):
                processed_artifacts.append(art)
                continue

            file_path = Path(art.metadata.get("file_path", ""))
            updated_art = art
            evidence_items: List[EvidenceItem] = []

            if art.modality == "image":
                updated_art, evidence_items = analyze_image(art, file_path)
            elif art.modality == "video":
                updated_art, evidence_items = analyze_video(art, file_path, storage.derived_dir)
            elif art.modality == "audio":
                updated_art, evidence_items = analyze_audio(art, file_path)
            elif art.modality == "text":
                updated_art, evidence_items = analyze_text_file(art, file_path)
            elif art.modality == "document":
                updated_art, evidence_items = analyze_pdf_document(art, file_path)

            processed_artifacts.append(updated_art)
            all_evidence.extend(evidence_items)

        emit_progress("preprocessing", "done", "Preprocessing complete.")

        # 3. Grounding Verification
        emit_progress("grounding", "running", "Verifying evidence references...")
        grounded_evidence, ev_rejections = filter_grounded_evidence(processed_artifacts, all_evidence)
        diagnostics["grounding_rejection_count"] += ev_rejections
        emit_progress("grounding", "done", "Grounding check complete.")

        # 4. Cross-Artifact Reasoning & Coordination
        emit_progress("reasoning", "running", "Evaluating cross-artifact relations and set coordination...")
        det_relations = run_deterministic_pair_checks(processed_artifacts)
        coord_relations = detect_coordination(processed_artifacts)
        raw_relations = det_relations + coord_relations

        grounded_relations, rel_rejections = filter_grounded_relations(processed_artifacts, raw_relations)
        diagnostics["grounding_rejection_count"] += rel_rejections
        emit_progress("reasoning", "done", "Reasoning complete.")

        # 5. Deterministic Fusion Stage
        emit_progress("fusing", "running", "Computing deterministic fusion and verdict...")
        fusion_output = compute_fusion(
            artifacts=processed_artifacts,
            evidence_items=grounded_evidence,
            relations=grounded_relations,
            unavailable_checks=diagnostics["unavailable_checks"],
        )
        emit_progress("fusing", "done", f"Verdict calculated: {fusion_output.verdict}")

        # Construct final Case model
        case = Case(
            id=case_id,
            description=case_input.description,
            job_status="completed",
            artifacts=processed_artifacts,
            relations=grounded_relations,
            fusion=fusion_output,
            diagnostics=diagnostics,
        )

        # Save to SQLite working store
        storage.save_case_state(case)

        return CaseResult(
            case=case,
            report_path=None,
            diagnostics=diagnostics,
        )

    except IngestValidationError as err:
        emit_progress("ingest", "failed", err.message, error_code=err.error_code)
        case = Case(
            id=case_id,
            description=case_input.description,
            job_status="failed",
            artifacts=[],
            relations=[],
            fusion=None,
            diagnostics={"error_code": err.error_code, "error_message": err.message},
        )
        storage.save_case_state(case)
        return CaseResult(case=case, diagnostics=diagnostics)

    except Exception as err:
        emit_progress("pipeline", "failed", f"Internal failure: {err}", error_code="INTERNAL")
        case = Case(
            id=case_id,
            description=case_input.description,
            job_status="failed",
            artifacts=[],
            relations=[],
            fusion=None,
            diagnostics={"error_code": "INTERNAL", "error_message": str(err)},
        )
        storage.save_case_state(case)
        return CaseResult(case=case, diagnostics=diagnostics)


def delete_case(case_id: str) -> None:
    """Convenience pipeline function to delete case session (R-DATA-04)."""
    storage_delete_case(case_id)
