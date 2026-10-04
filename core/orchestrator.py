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
from reasoning.cross_modal import run_cross_modal_reasoning
from reasoning.artifact_analyzer import analyze_artifact_semantics
from reasoning.evidence_graph import build_evidence_graph
from services.platform_client import PlatformInvestigationManager
from services.report import save_report_html
from core.fusion import compute_fusion
from services.llm_client import GeminiClient


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

    # Initialize GeminiClient with session cache directory
    llm_cache_dir = storage.derived_dir / "llm_cache"
    llm_client = GeminiClient(cache_dir=llm_cache_dir)

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
                updated_art, evidence_items = analyze_video(
                    art, file_path, storage.derived_dir, llm_client=llm_client
                )
                if updated_art.metadata.get("audio_extraction_status") == "ffmpeg_unavailable":
                    if "CHK_VIDEO_AUDIO_EXTRACTION" not in diagnostics["unavailable_checks"]:
                        diagnostics["unavailable_checks"].append("CHK_VIDEO_AUDIO_EXTRACTION")
            elif art.modality == "audio":
                updated_art, evidence_items = analyze_audio(
                    art, file_path, llm_client=llm_client
                )
                if updated_art.metadata.get("transcript_status") == "unavailable":
                    if "CHK_AUDIO_ASR" not in diagnostics["unavailable_checks"]:
                        diagnostics["unavailable_checks"].append("CHK_AUDIO_ASR")
            elif art.modality == "text":
                updated_art, evidence_items = analyze_text_file(art, file_path)
            elif art.modality == "document":
                updated_art, evidence_items = analyze_pdf_document(art, file_path)

            # 3. Semantic Claim & Entity Extraction (Phase 2)
            updated_art, sem_evidence = analyze_artifact_semantics(updated_art, llm_client=llm_client)
            evidence_items.extend(sem_evidence)

            processed_artifacts.append(updated_art)
            all_evidence.extend(evidence_items)

        emit_progress("preprocessing", "done", "Preprocessing and semantic extraction complete.")

        # 4. Cross-Platform Investigation (Phase 7 - FAST-FIRST / CONDITIONAL-DEEP)
        platform_artifacts = []
        comment_evidences = []
        cross_platform_activated = False

        if case_input.platform_urls:
            emit_progress("platform", "running", "Investigating platform sources and discourse...")
            plat_manager = PlatformInvestigationManager(cache_dir=storage.derived_dir / "platform_cache")
            platform_artifacts, comment_evidences, plat_ev_items = plat_manager.investigate(
                case_input.platform_urls,
                case_input.investigation_query,
            )
            all_evidence.extend(plat_ev_items)
            cross_platform_activated = len(platform_artifacts) > 0
            emit_progress("platform", "done", f"Retrieved {len(platform_artifacts)} platform source(s).")

        # 5. Grounding Verification
        emit_progress("grounding", "running", "Verifying evidence references...")
        grounded_evidence, ev_rejections = filter_grounded_evidence(processed_artifacts, all_evidence)
        diagnostics["grounding_rejection_count"] += ev_rejections
        emit_progress("grounding", "done", "Grounding check complete.")

        # 6. Cross-Artifact Reasoning, Coordination & Cross-Modal Adjudication (Phase 4 & 5)
        emit_progress("reasoning", "running", "Evaluating cross-artifact relations, coordination, and cross-modal consistency...")
        det_relations = run_deterministic_pair_checks(processed_artifacts)
        coord_relations = detect_coordination(processed_artifacts)
        cm_relations, cm_ev_items, cross_modal_activated = run_cross_modal_reasoning(
            processed_artifacts, llm_client=llm_client
        )

        # Ground any cross-modal evidence items
        if cm_ev_items:
            grounded_cm_ev, cm_ev_rejections = filter_grounded_evidence(processed_artifacts, cm_ev_items)
            grounded_evidence.extend(grounded_cm_ev)
            diagnostics["grounding_rejection_count"] += cm_ev_rejections

        # Emit check items for deterministic timeline/date relations
        for rel in det_relations:
            if rel.relation in ("SUPPORTS", "CONTRADICTS", "UNCERTAIN") and rel.evidence_refs:
                ev_dir = "authentic" if rel.relation == "SUPPORTS" else ("manipulated" if rel.relation == "CONTRADICTS" else "neutral")
                ev_str = 0.50 if rel.confidence_level == "medium" else (0.85 if rel.confidence_level == "high" else 0.25)
                ev_item = EvidenceItem(
                    id=f"{rel.source_id}:{rel.target_id}:chk_cross_date",
                    artifact_ids=[rel.source_id, rel.target_id],
                    direction=ev_dir,
                    strength=ev_str,
                    reliability=0.85,
                    scope="pair",
                    evidence_ref=rel.evidence_refs[0],
                    description=rel.explanation or "Cross-artifact timeline check",
                    source="deterministic",
                    check_id="CHK_CROSS_DATE",
                )
                grounded_evidence.append(ev_item)

        # Emit check items for coordination / perceptual relations
        for rel in coord_relations:
            if rel.conflict_type == "near_duplicate" and rel.evidence_refs:
                ev_item = EvidenceItem(
                    id=f"{rel.source_id}:{rel.target_id}:chk_coord_perceptual",
                    artifact_ids=[rel.source_id, rel.target_id],
                    direction="neutral",
                    strength=0.25,
                    reliability=0.85,
                    scope="pair",
                    evidence_ref=rel.evidence_refs[0],
                    description=rel.explanation or "Perceptual hash match",
                    source="deterministic",
                    check_id="CHK_COORD_PERCEPTUAL",
                )
                grounded_evidence.append(ev_item)

        raw_relations = det_relations + coord_relations + cm_relations
        grounded_relations, rel_rejections = filter_grounded_relations(processed_artifacts, raw_relations)
        diagnostics["grounding_rejection_count"] += rel_rejections
        emit_progress("reasoning", "done", "Reasoning complete.")

        # 7. Deterministic Fusion Stage
        emit_progress("fusing", "running", "Computing deterministic fusion and verdict...")
        fusion_output = compute_fusion(
            artifacts=processed_artifacts,
            evidence_items=grounded_evidence,
            relations=grounded_relations,
            unavailable_checks=diagnostics["unavailable_checks"],
        )
        fusion_output.cross_modal_checks_run = len(cm_relations)
        fusion_output.cross_platform_checks_run = len(platform_artifacts)
        emit_progress("fusing", "done", f"Verdict calculated: {fusion_output.verdict}")

        # 8. Evidence Graph Construction (Phase 3)
        temp_case = Case(
            id=case_id,
            description=case_input.description,
            job_status="completed",
            artifacts=processed_artifacts,
            relations=grounded_relations,
            fusion=fusion_output,
            diagnostics=diagnostics,
            platform_artifacts=platform_artifacts,
            cross_modal_activated=cross_modal_activated,
            cross_platform_activated=cross_platform_activated,
        )
        ev_graph = build_evidence_graph(temp_case)

        # 9. HTML Report Generation
        report_path_str: Optional[str] = None
        try:
            report_file = save_report_html(temp_case, storage.derived_dir)
            report_path_str = str(report_file)
        except Exception:
            pass

        # Construct final Case model with evidence graph attached
        final_case = Case(
            id=case_id,
            description=case_input.description,
            job_status="completed",
            artifacts=processed_artifacts,
            relations=grounded_relations,
            fusion=fusion_output,
            diagnostics=diagnostics,
            platform_artifacts=platform_artifacts,
            evidence_graph=ev_graph,
            cross_modal_activated=cross_modal_activated,
            cross_platform_activated=cross_platform_activated,
        )

        # Save to SQLite working store
        storage.save_case_state(final_case)

        return CaseResult(
            case=final_case,
            report_path=report_path_str,
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
