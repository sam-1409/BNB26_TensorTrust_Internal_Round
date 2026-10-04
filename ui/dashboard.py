"""Streamlit UI dashboard for TrustLayers.

Enforces:
- R-UX-01 to R-UX-10: Strict adherence to visual and interaction design rules.
- R-SEC-08: UI escapes all artifact-derived text. Never renders raw HTML for user content.
- R-DATA-06: Shows processing notice before first analysis in session.
"""

import base64
import uuid
import streamlit as st
from typing import List, Dict, Any

from core.config import GEMINI_TIER, ALL_SUPPORTED_MIME_TYPES, BASE_DIR
from models.schemas import CaseInput, Case, ProgressEvent
from core.orchestrator import run_case, delete_case
from services.report import generate_report_html


def render_header():
    """Render top brand header with logo and wordmark."""
    logo_path = BASE_DIR / "assets" / "logo.png"
    logo_html = ""
    if logo_path.exists():
        b64_logo = base64.b64encode(logo_path.read_bytes()).decode("utf-8")
        logo_html = f'<img src="data:image/png;base64,{b64_logo}" class="tl-logo" alt="TrustLayers Logo" />'

    st.markdown(
        f"""
        <style>
        .brand-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 2px;
        }}
        .tl-logo {{
            width: 36px;
            height: 36px;
            object-fit: contain;
            display: block;
        }}
        .tl-wordmark {{
            font-family: 'Plus Jakarta Sans', sans-serif;
            font-weight: 800;
            font-size: 28px;
            color: #1C1B1F;
            margin: 0;
            line-height: 1;
        }}
        .tl-caption {{
            font-size: 14px;
            color: #49454F;
            margin-top: 4px;
            margin-bottom: 24px;
        }}
        .verdict-box-authentic {{
            border-left: 5px solid #1E6E4E;
            background-color: #F7F2FA;
            padding: 16px;
            margin-bottom: 20px;
        }}
        .verdict-box-manipulated {{
            border-left: 5px solid #B3261E;
            background-color: #F7F2FA;
            padding: 16px;
            margin-bottom: 20px;
        }}
        .verdict-box-coordinated {{
            border-left: 5px solid #7D5700;
            background-color: #F7F2FA;
            padding: 16px;
            margin-bottom: 20px;
        }}
        .verdict-box-inconclusive {{
            border-left: 5px solid #49454F;
            background-color: #F7F2FA;
            padding: 16px;
            margin-bottom: 20px;
        }}
        </style>
        <div class="brand-header">
            {logo_html}
            <span class="tl-wordmark">TrustLayers</span>
        </div>
        <div class="tl-caption">Multimodal Digital Authenticity Investigation Tool</div>
        """,
        unsafe_allow_html=True,
    )


def render_processing_notice():
    """Render mandatory processing notice (R-DATA-06)."""
    st.info(
        "Analysis runs on this machine and also sends parts of your files to Google's Gemini API: "
        "images, video frames, audio, and extracted text. Google's paid-service terms say it does not use "
        "this content to improve its products. TrustLayers does not keep your files after the session and does not use "
        "them for training. You can delete the case at any time."
    )


def render_upload_screen():
    """Render UI-002 Upload Screen."""
    st.header("Start a case")
    st.write("Add the files you want to compare. You can mix images, video, audio, text, and PDFs.")

    # Check tier enforcement (R-DATA-03)
    if GEMINI_TIER != "paid":
        st.warning(
            "GEMINI_TIER is set to 'free/sample'. Live user uploads are disabled. "
            "Please select a pre-loaded sample case below."
        )
        sample_case = st.selectbox("Sample cases", ["Sample Case 1: Image & Document Pair", "Sample Case 2: Synthetic Audio"])
        if st.button("Load sample case", type="primary"):
            st.session_state["active_case_id"] = f"sample_{uuid.uuid4().hex[:8]}"
            st.rerun()
        return

    uploaded_files = st.file_uploader(
        "Choose files for analysis",
        accept_multiple_files=True,
    )

    file_payloads: List[Dict[str, Any]] = []
    if uploaded_files:
        st.subheader("Ingested Files Status")
        for f in uploaded_files:
            bytes_data = f.read()
            file_payloads.append({
                "filename": f.name,
                "bytes": bytes_data,
            })
            st.write(f"📁 **{f.name}** — {len(bytes_data) / 1024:.1f} KB — Ready for analysis")

    description = st.text_area(
        "Context for this case (optional)",
        placeholder="Captions, claims, or where the files came from...",
    )

    platform_urls_input = st.text_area(
        "External Platform URLs (Optional - YouTube or Reddit)",
        placeholder="https://www.youtube.com/watch?v=...\nhttps://reddit.com/r/...",
    )
    platform_urls = [line.strip() for line in platform_urls_input.splitlines() if line.strip()]

    st.markdown("---")
    render_processing_notice()

    analyze_disabled = len(file_payloads) == 0 and len(platform_urls) == 0
    if st.button("Analyze case", type="primary", disabled=analyze_disabled):
        case_id = f"case_{uuid.uuid4().hex[:10]}"
        st.session_state["active_case_id"] = case_id

        # Execute investigation pipeline
        progress_placeholder = st.empty()
        progress_logs: List[str] = []

        def on_progress(event: ProgressEvent):
            msg = f"[{event.stage.upper()}] {event.message}"
            progress_logs.append(msg)
            with progress_placeholder.container():
                st.write(msg)

        case_input = CaseInput(
            case_id=case_id,
            files=file_payloads,
            description=description,
            platform_urls=platform_urls,
            investigation_query=description if description else None,
        )

        result = run_case(case_input, on_progress=on_progress)
        st.session_state["case_result"] = result
        st.rerun()


def render_result_screen(case: Case):
    """Render UI-005 Result Screen with Full Multimodal and Platform Evidence."""
    fusion = case.fusion
    if not fusion:
        st.error("No verdict was produced for this case.")
        return

    # 1. Verdict Banner
    verdict = fusion.verdict
    box_class = f"verdict-box-{verdict.lower()}"

    st.markdown(f'<div class="{box_class}">', unsafe_allow_html=True)
    st.subheader(f"Verdict: {verdict}")

    if verdict == "AUTHENTIC":
        st.write("The artifacts support each other and show no sign of manipulation. This is an assessment, not proof.")
    elif verdict == "MANIPULATED":
        st.write("At least one artifact shows strong signs of manipulation or of being presented out of context.")
    elif verdict == "COORDINATED_SYNTHETIC":
        st.write("Several artifacts show signs of manipulation and share traces that link them.")
    else:
        st.write(fusion.inconclusive_label or "The available evidence does not establish whether these artifacts are genuine.")

    col1, col2, col3 = st.columns(3)
    col1.metric("Confidence Level", fusion.confidence_level.upper())
    col2.metric("Sufficiency", f"{min(fusion.checks_completed, fusion.checks_applicable)} / {fusion.checks_applicable} checks")
    col3.metric("Reason Codes", ", ".join(fusion.reason_codes) if fusion.reason_codes else "None")
    st.markdown('</div>', unsafe_allow_html=True)

    # 2. Evidence Balance & Internal Scores
    st.subheader("Evidence Balance")
    m_ordinal = "High" if fusion.manip_evidence > 0.65 else ("Moderate" if fusion.manip_evidence > 0.3 else "Low")
    a_ordinal = "High" if fusion.auth_support > 0.60 else ("Moderate" if fusion.auth_support > 0.3 else "Low")

    col_m, col_a = st.columns(2)
    col_m.write(f"**Manipulation Evidence:** {m_ordinal}")
    col_a.write(f"**Authenticity Support:** {a_ordinal}")

    with st.expander("Internal scores (Disclosure)"):
        st.caption("Rule-based internal scores. They are not probabilities.")
        st.write(f"- Manipulation score ($m$): `{fusion.manip_evidence:.4f}`")
        st.write(f"- Authenticity score ($a$): `{fusion.auth_support:.4f}`")
        st.write(f"- Sufficiency ($\\sigma$): `{fusion.sufficiency:.4f}`")

    # 3. Explicit Contradiction Map
    if case.evidence_graph and case.evidence_graph.contradiction_list:
        st.subheader("⚠️ Explicit Contradictions & Discrepancies")
        for contra in case.evidence_graph.contradiction_list:
            with st.container():
                st.error(f"**Conflict Type: {contra.get('conflict_type', 'semantic').upper()}**")
                st.write(contra.get("explanation", ""))
                st.caption(f"Between Artifact `{contra.get('artifact_a')}` and `{contra.get('artifact_b')}` | Confidence: {contra.get('confidence_level', '').upper()}")
                st.markdown("---")

    # 4. Cross-Modal & Cross-Artifact Relationships
    st.subheader("Cross-Modal & Cross-Artifact Relationships")
    if case.cross_modal_activated:
        st.success("✅ **Cross-Modal Reasoning: ACTIVATED** (Multiple distinct media modalities evaluated)")
    else:
        st.info("ℹ️ **Cross-Modal Reasoning: BYPASSED** (Single modality present)")

    if case.relations:
        for rel in case.relations:
            with st.container():
                icon = "🟢" if rel.relation in ("SUPPORTS", "MATCHES") else ("🔴" if rel.relation == "CONTRADICTS" else "⚪")
                st.write(f"{icon} **[{rel.relation}]** `{rel.source_id}` &harr; `{rel.target_id}`")
                if rel.explanation:
                    st.write(rel.explanation)
                st.caption(f"Method: {rel.method} | Confidence: {rel.confidence_level.upper()}")
                st.markdown("---")
    else:
        st.write("No cross-artifact relationships were triggered.")

    # 5. Cross-Platform Source Findings
    if case.platform_artifacts:
        st.subheader("🌐 Cross-Platform Investigation Findings")
        for plat in case.platform_artifacts:
            with st.expander(f"{plat.platform.upper()}: {plat.title or plat.url}", expanded=True):
                st.write(f"**URL:** [{plat.url}]({plat.url})")
                if plat.upload_date:
                    st.write(f"**Upload Date:** {plat.upload_date}")
                if plat.view_count is not None:
                    st.write(f"**View Count:** {plat.view_count:,}")
                if plat.comments_sample:
                    st.write("**Sampled User Comments:**")
                    st.caption(f"⚠️ *Notice: {plat.comment_reliability_note} Their reliability is lower than forensic evidence.*")
                    for comm in plat.comments_sample:
                        st.write(f"- \"{comm}\"")

    # 6. Artifact Details & Semantic Extraction
    st.subheader("Artifact Details & Semantic Claims")
    for art in case.artifacts:
        with st.expander(f"📁 {art.display_name} ({art.modality.upper()}) — Status: {art.status.upper()}"):
            if art.reliability:
                st.write(f"**Reliability Score:** `{art.reliability.score:.2f}`")
            if art.transcript:
                st.write(f"**Transcript (ASR):** \"{art.transcript}\" (Confidence: `{art.transcript_confidence or 0.0:.2f}`)")
            if art.perceptual_hash:
                st.write(f"**Perceptual Hash (dHash):** `{art.perceptual_hash}`")
            if art.semantic_claims:
                st.write("**Extracted Claims:**")
                for c in art.semantic_claims:
                    st.write(f"- {c.get('claim_text')} *({c.get('category')})*")
            entities = art.metadata.get("entities", {})
            if entities:
                st.write(f"**Entities:** {entities}")

    # 7. Limitations
    st.subheader("Investigation Limitations")
    if fusion.limitations:
        for lim in fusion.limitations:
            st.write(f"- {lim}")
    else:
        st.write("- No specific limitations were flagged during analysis.")

    # 8. Actions
    st.subheader("Actions")
    act_col1, act_col2 = st.columns(2)

    with act_col1:
        report_html = generate_report_html(case)
        st.download_button(
            "Download HTML Report",
            data=report_html,
            file_name=f"report_{case.id}.html",
            mime="text/html",
            type="primary",
        )

    with act_col2:
        if st.button("Delete case", type="secondary"):
            delete_case(case.id)
            if "active_case_id" in st.session_state:
                del st.session_state["active_case_id"]
            if "case_result" in st.session_state:
                del st.session_state["case_result"]
            st.success("This case was deleted.")
            st.rerun()


def render_evaluation_tab():
    """Render UI-007 Evaluation Tab with real loaded evaluation results."""
    st.header("Evaluation Results & Benchmark")

    import json
    from core.config import EVAL_RESULTS_DIR

    results_file = EVAL_RESULTS_DIR / "summary.json"
    if results_file.exists():
        try:
            with open(results_file, "r", encoding="utf-8") as f:
                eval_data = json.load(f)

            st.success(f"Loaded Real Benchmark Evaluation: **{eval_data.get('cases_evaluated', 0)} cases evaluated**")

            col1, col2, col3 = st.columns(3)
            col1.metric("Macro-F1", f"{eval_data.get('macro_f1', 0.0):.4f}")
            col2.metric("Coverage Rate", f"{eval_data.get('coverage_rate', 0.0):.4f}")
            col3.metric("False-Confidence Rate", f"{eval_data.get('false_confidence_rate', 0.0):.4f}")

            if "confusion_matrix" in eval_data:
                st.subheader("Confusion Matrix")
                st.json(eval_data["confusion_matrix"])

            if "ablation" in eval_data:
                st.subheader("Baseline vs TrustLayers Ablation")
                st.json(eval_data["ablation"])
            return
        except Exception:
            pass

    st.info("Evaluation benchmark not yet executed. Run 'python -m eval.run_eval' to generate real metrics.")


def main_dashboard():
    """Main Streamlit dashboard router."""
    render_header()

    tab1, tab2 = st.tabs(["Investigation", "Evaluation Benchmark"])

    with tab1:
        if "case_result" in st.session_state:
            result = st.session_state["case_result"]
            if result.case.job_status == "completed":
                render_result_screen(result.case)
            else:
                st.error(f"Investigation failed: {result.diagnostics.get('error_message', 'Unknown error')}")
                if st.button("Start new case"):
                    del st.session_state["case_result"]
                    st.rerun()
        else:
            render_upload_screen()

    with tab2:
        render_evaluation_tab()

