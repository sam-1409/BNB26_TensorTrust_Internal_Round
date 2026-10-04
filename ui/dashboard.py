"""Streamlit UI dashboard for TrustLayers.

Enforces:
- R-UX-01 to R-UX-10: visual and interaction rules.
- R-SEC-08: artifact-derived text is escaped before HTML render.
- R-DATA-06: processing notice is shown before the first analysis.
"""

import base64
import html
import json
import math
import time
import uuid
import streamlit as st
import streamlit.components.v1 as components
from typing import Any, Dict, List, Optional

from core.config import ALL_SUPPORTED_MIME_TYPES, BASE_DIR, EVAL_RESULTS_DIR, GEMINI_TIER
from models.schemas import Case, CaseInput, ProgressEvent
from core.orchestrator import delete_case, run_case
from services.report import generate_report_html


STAGE_ORDER = [
    ("ingest", "INGESTING EVIDENCE"),
    ("preprocessing", "EXTRACTING SIGNALS"),
    ("grounding", "BUILDING EVIDENCE"),
    ("reasoning", "CHECKING RELATIONSHIPS"),
    ("platform", "ANALYZING CONTRADICTIONS"),
    ("fusing", "ASSESSING CONFIDENCE"),
    ("report", "GENERATING REPORT"),
]

FORMAT_GROUPS = [
    ("Images", "JPEG, PNG, WebP"),
    ("Audio", "WAV, MP3, FLAC, OGG, M4A"),
    ("Video", "MP4, WebM, MOV"),
    ("Documents", "PDF"),
    ("Text", "TXT"),
]

EXT_MODALITY = {
    "jpg": ("Image", "JPEG"),
    "jpeg": ("Image", "JPEG"),
    "png": ("Image", "PNG"),
    "webp": ("Image", "WebP"),
    "mp3": ("Audio", "MP3"),
    "wav": ("Audio", "WAV"),
    "ogg": ("Audio", "OGG"),
    "flac": ("Audio", "FLAC"),
    "m4a": ("Audio", "M4A"),
    "mp4": ("Video", "MP4"),
    "webm": ("Video", "WebM"),
    "mov": ("Video", "MOV"),
    "pdf": ("Document", "PDF"),
    "txt": ("Text", "TXT"),
}


def _esc(value: Any) -> str:
    """Escape untrusted values before any HTML render (R-SEC-08)."""
    return html.escape("" if value is None else str(value), quote=True)


def _inject_styles() -> None:
    """Load the visual + cinematic Three.js system into the parent document."""
    css = (BASE_DIR / "static" / "theme.css").read_text(encoding="utf-8")
    motion_js = (BASE_DIR / "static" / "motion.js").read_text(encoding="utf-8")
    cinema_js = (BASE_DIR / "static" / "cinematic.js").read_text(encoding="utf-8")
    components.html(
        f"""
        <script>
        const parentDoc = window.parent.document;
        if (parentDoc) {{
            if (!parentDoc.getElementById("tl-font")) {{
                const font = parentDoc.createElement("link");
                font.id = "tl-font";
                font.rel = "stylesheet";
                font.href = "https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap";
                parentDoc.head.appendChild(font);
            }}
            let style = parentDoc.getElementById("tl-theme");
            if (!style) {{
                style = parentDoc.createElement("style");
                style.id = "tl-theme";
                parentDoc.head.appendChild(style);
            }}
            style.textContent = {css!r};

            let cinemaSrc = parentDoc.getElementById("tl-cinema-src");
            if (!cinemaSrc) {{
                cinemaSrc = parentDoc.createElement("script");
                cinemaSrc.id = "tl-cinema-src";
                cinemaSrc.type = "text/plain";
                parentDoc.body.appendChild(cinemaSrc);
            }}
            cinemaSrc.textContent = {cinema_js!r};

            const win = parentDoc.defaultView;
            const motionVersion = "flow-v6";
            if (win && win.__tlMotionVersion !== motionVersion) {{
                const old = parentDoc.getElementById("tl-motion");
                if (old) old.remove();
                const oldEng = parentDoc.getElementById("tl-cinema-engine");
                if (oldEng) oldEng.remove();
                const oldUni = parentDoc.getElementById("tl-universe");
                if (oldUni) oldUni.remove();
                win.__tlMotionBooted = false;
                win.__tlCinemaBooted = false;
                win.__tlMotionVersion = motionVersion;
                const fresh = parentDoc.createElement("script");
                fresh.id = "tl-motion";
                fresh.textContent = {motion_js!r};
                parentDoc.body.appendChild(fresh);
            }} else if (win && win.__tlMotionRefresh) {{
                win.__tlMotionRefresh();
            }} else if (!parentDoc.getElementById("tl-motion")) {{
                const motion = parentDoc.createElement("script");
                motion.id = "tl-motion";
                motion.textContent = {motion_js!r};
                parentDoc.body.appendChild(motion);
            }}
        }}
        </script>
        """,
        height=0,
    )


def _logo_html() -> str:
    logo_path = BASE_DIR / "assets" / "logo.png"
    if not logo_path.exists():
        return ""
    b64_logo = base64.b64encode(logo_path.read_bytes()).decode("utf-8")
    return f'<img src="data:image/png;base64,{b64_logo}" class="tl-logo" alt="TrustLayers" />'


def _status_label() -> str:
    result = st.session_state.get("case_result")
    if not result:
        return "SYSTEM READY"
    if result.case.job_status == "completed" and result.case.fusion:
        return result.case.fusion.verdict.replace("_", " ")
    if result.case.job_status == "failed":
        return "INVESTIGATION FAILED"
    return "ANALYSIS READY"


def _status_class() -> str:
    result = st.session_state.get("case_result")
    if not result:
        return ""
    if result.case.job_status == "failed":
        return "is-failed"
    if result.case.job_status == "completed" and result.case.fusion:
        return f"is-{result.case.fusion.verdict.lower()}"
    return ""


def render_header() -> None:
    """Minimal brand header."""
    _inject_styles()
    status_klass = f"tl-status {_status_class()}".strip()
    st.html(
        f"""
        <div class="tl-topbar">
            <div class="tl-brand">
                {_logo_html()}
                <div>
                    <div class="tl-wordmark">TrustLayers</div>
                    <div class="tl-caption">AI-Powered Digital Authenticity Investigation</div>
                </div>
            </div>
            <div class="{status_klass}"><i></i>{_esc(_status_label())}</div>
        </div>
        """
    )


def _paint(target_id: str, markup: str) -> None:
    """Insert markup Streamlit would otherwise strip, such as SVG."""
    components.html(
        f"""
        <script>
        const markup = {markup!r};
        let tries = 0;
        const paint = () => {{
            const node = window.parent.document.getElementById({target_id!r});
            if (node) {{
                node.innerHTML = markup;
                return;
            }}
            if (tries++ < 40) setTimeout(paint, 50);
        }};
        paint();
        </script>
        """,
        height=0,
    )


def _graph_iframe(svg_body: str, height: int = 380, interactive: bool = False) -> None:
    """Render an evidence graph SVG inside an iframe so Streamlit cannot strip it."""
    interact_js = ""
    if interactive:
        interact_js = """
<script>
(() => {
  const svg = document.querySelector('svg');
  if (!svg) return;
  const nodes = [...svg.querySelectorAll('.node-g')];
  const edges = [...svg.querySelectorAll('.edge-g')];
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  function dimAll(exceptIds) {
    nodes.forEach(g => {
      const id = g.dataset.id;
      const on = !exceptIds || exceptIds.has(id);
      g.classList.toggle('is-hot', on && !!exceptIds);
      g.classList.toggle('is-dim', !on);
    });
    edges.forEach(g => {
      const hot = !exceptIds || exceptIds.has(g.dataset.src) || exceptIds.has(g.dataset.tgt);
      g.classList.toggle('is-hot', hot && !!exceptIds);
      g.classList.toggle('is-dim', !hot);
    });
  }
  nodes.forEach(g => {
    g.style.cursor = 'pointer';
    g.addEventListener('pointerenter', () => {
      const id = g.dataset.id;
      const linked = new Set([id]);
      edges.forEach(e => {
        if (e.dataset.src === id) linked.add(e.dataset.tgt);
        if (e.dataset.tgt === id) linked.add(e.dataset.src);
      });
      dimAll(linked);
    });
    g.addEventListener('pointerleave', () => dimAll(null));
  });
  edges.forEach(g => {
    g.style.cursor = 'pointer';
    g.addEventListener('pointerenter', () => dimAll(new Set([g.dataset.src, g.dataset.tgt])));
    g.addEventListener('pointerleave', () => dimAll(null));
  });
  if (!reduce) {
    edges.forEach(g => {
      const path = g.querySelector('path');
      if (path) path.style.animation = 'flow 7s linear infinite';
    });
  }
})();
</script>
"""
    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html,body {{ margin:0; background:transparent; overflow:hidden; height:100%; }}
  svg {{ width:100%; height:{height}px; display:block; }}
  .edge {{ fill:none; stroke:rgba(61,220,151,0.55); stroke-width:1.25; stroke-dasharray:6 8; }}
  .edge-contradicts {{ stroke:rgba(226,91,74,0.75); }}
  .node {{ fill:#101614; stroke:rgba(61,220,151,0.75); stroke-width:1.1; filter:drop-shadow(0 0 8px rgba(61,220,151,0.2)); }}
  .label {{ fill:#f4f7f5; font:700 11px "Plus Jakarta Sans",sans-serif; letter-spacing:0.08em; }}
  .rel {{ fill:#3ddc97; font:700 9px "Plus Jakarta Sans",sans-serif; letter-spacing:0.12em; }}
  .rel-contradicts {{ fill:#e25b4a; }}
  .is-dim {{ opacity:0.22; transition:opacity .25s ease; }}
  .is-hot {{ opacity:1; }}
  .node-g.is-hot .node {{ stroke:#3ddc97; stroke-width:1.6; }}
  @keyframes flow {{ to {{ stroke-dashoffset:-140; }} }}
  @media (prefers-reduced-motion: reduce) {{ .edge {{ animation:none !important; }} }}
</style></head><body>{svg_body}{interact_js}</body></html>"""
    components.html(html_doc, height=height)


def _canvas_iframe(js_source: str, height: int = 420, stage_id: str = "stage", canvas_id: str = "field", extra_svg: bool = True) -> None:
    """Self-contained cinematic canvas scene (particles / discovery / signature)."""
    js = (BASE_DIR / "static" / js_source).read_text(encoding="utf-8")
    svg = '<svg id="net" aria-hidden="true"></svg>' if extra_svg else ""
    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@700&display=swap">
<style>
  html,body {{ margin:0; background:transparent; overflow:hidden; height:100%; }}
  #stage {{
    position:relative; width:100%; height:{height}px;
    border:1px solid rgba(244,247,245,0.10); border-radius:20px;
    background:
      radial-gradient(280px 180px at 50% 48%, rgba(61,220,151,0.16), transparent 70%),
      linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01));
    overflow:hidden;
  }}
  #stage::before {{
    content:""; position:absolute; inset:0; pointer-events:none; opacity:.4;
    background-image:
      linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px);
    background-size:42px 42px;
    mask-image:radial-gradient(circle at 50% 50%, black 20%, transparent 75%);
  }}
  canvas, svg {{ position:absolute; inset:0; width:100%; height:100%; }}
  svg {{ pointer-events:none; }}
  .node {{ fill:#101614; stroke:rgba(61,220,151,0.78); stroke-width:1.15; }}
  .label {{ fill:#f4f7f5; font:700 11px "Plus Jakarta Sans",sans-serif; letter-spacing:0.08em; }}
  .rel {{ fill:#3ddc97; font:700 9px "Plus Jakarta Sans",sans-serif; letter-spacing:0.14em; }}
  .rel-contradict {{ fill:#e25b4a; }}
  .edge {{ stroke:rgba(61,220,151,0.55); }}
  .edge-contradict {{ stroke:rgba(226,91,74,0.8); }}
  .edge-link {{ stroke:rgba(61,220,151,0.35); }}
  .bead {{ fill:#3ddc97; }}
  .bead-contradict {{ fill:#e25b4a; }}
  .is-dim {{ opacity:0.2; }}
  .is-hot .node {{ stroke:#3ddc97; stroke-width:1.7; }}
  .edge.is-hot {{ stroke-width:2; }}
  .edge.is-dim {{ opacity:0.15; }}
  .scan {{
    position:absolute; left:0; right:0; height:2px; top:-10%;
    background:linear-gradient(90deg, transparent, rgba(61,220,151,0.55), transparent);
    box-shadow:0 0 18px rgba(61,220,151,0.35);
    animation:scan 5.5s ease-in-out infinite;
    pointer-events:none;
  }}
  @keyframes scan {{ 0% {{ top:-5%; opacity:0; }} 15% {{ opacity:1; }} 50% {{ top:55%; }} 85% {{ opacity:.4; }} 100% {{ top:105%; opacity:0; }} }}
  @media (prefers-reduced-motion: reduce) {{ .scan {{ animation:none; opacity:0; }} }}
</style></head>
<body>
  <div id="{stage_id}">
    <div class="scan" aria-hidden="true"></div>
    <canvas id="{canvas_id}"></canvas>
    {svg}
  </div>
  <script>{js}</script>
</body></html>"""
    components.html(html_doc, height=height)


def _go_investigate_workbench() -> None:
    """Nav callback: Home → workbench. Runs before widgets are instantiated."""
    st.session_state["nav_radio"] = "Investigate"
    st.session_state["investigate_phase"] = "workbench"
    st.session_state["tl_transition"] = "home-to-workbench"


def _go_benchmark() -> None:
    """Nav callback: Home → Benchmark."""
    st.session_state["nav_radio"] = "Benchmark"


def render_landing() -> None:
    """Home: only the hero evidence-network scene. No scroll storytelling."""
    st.html('<div id="tl-view" data-view="home" hidden></div>')
    st.html(
        """
        <div class="tl-cinema-intro">
          <h1 class="tl-display">Connect the evidence.<br>Find the truth.</h1>
          <div class="tl-kicker">Digital evidence investigation</div>
          <p class="tl-lead tl-cinema-hint">Start an investigation when you are ready.</p>
        </div>
        """
    )
    st.button(
        "Start Investigation",
        type="primary",
        width="stretch",
        key="home_start",
        on_click=_go_investigate_workbench,
    )
    st.button(
        "View Benchmark",
        type="secondary",
        width="stretch",
        key="hero_benchmark",
        on_click=_go_benchmark,
    )

    # Hero only — storytelling scenes play after ASSESSING CONFIDENCE during live investigation.
    st.html(
        """
        <div id="tl-cinema-track" class="tl-cinema-track-hero" data-tl-hero-only="1" aria-hidden="true"></div>
        """
    )


def _file_kind(filename: str) -> tuple[str, str]:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return EXT_MODALITY.get(ext, ("File", ext.upper() or "Unknown"))


def render_processing_notice() -> None:
    """Mandatory processing notice (R-DATA-06) — compact expandable row."""
    with st.expander("Data & privacy", expanded=False):
        st.markdown(
            "Analysis runs on this machine and also sends parts of your files to Google's Gemini API: "
            "images, video frames, audio, and extracted text. Google's paid-service terms say it does not use "
            "this content to improve its products. TrustLayers does not keep your files after the session and does not use "
            "them for training. You can delete the case at any time."
        )


def _pipeline_html(active: Optional[str] = None, done: Optional[List[str]] = None) -> str:
    done = done or []
    chips = []
    for key, label in STAGE_ORDER:
        klass = "tl-step"
        if key == active:
            klass += " is-on"
        elif key in done:
            klass += " is-done"
        chips.append(f'<span class="{klass}" data-stage="{_esc(key)}">{label}</span>')
    stage_class = "tl-pipeline is-live" if active else "tl-pipeline"
    return f'<div class="{stage_class}" data-active="{_esc(active or "")}">{"".join(chips)}</div>'


def render_upload_screen() -> None:
    """Investigation workbench. Visual console only — homepage cinema stays off."""
    st.html('<div id="tl-view" data-view="workbench" hidden></div>')
    st.html(
        """
        <div class="tl-wb tl-wb-intro">
          <div class="tl-wb-head">
            <div>
              <div class="tl-kicker">Investigation workbench</div>
              <h2 class="tl-wb-title">Add evidence</h2>
              <p class="tl-wb-lead">
                Upload whatever evidence is relevant to this investigation.
                TrustLayers adapts its analysis automatically.
                One artifact is enough. Missing modalities are not errors.
              </p>
            </div>
            <div class="tl-wb-case">
              CASE #TL-READY
              <div class="tl-status"><i></i>ANALYSIS READY</div>
            </div>
          </div>
        </div>
        """
    )

    if GEMINI_TIER != "paid":
        st.warning(
            "GEMINI_TIER is set to 'free/sample'. Live user uploads are disabled. "
            "Please select a pre-loaded sample case below."
        )
        st.selectbox("Sample cases", ["Sample Case 1: Image & Document Pair", "Sample Case 2: Synthetic Audio"])
        if st.button("Load sample case", type="primary"):
            st.session_state["active_case_id"] = f"sample_{uuid.uuid4().hex[:8]}"
            st.rerun()
        return

    st.html('<div class="tl-wb tl-wb-tight"><div class="tl-wb-label">Evidence</div></div>')
    uploaded_files = st.file_uploader(
        "Add evidence",
        accept_multiple_files=True,
        label_visibility="collapsed",
        help="Images, audio, video, documents, or text. " + ", ".join(sorted(ALL_SUPPORTED_MIME_TYPES)),
    )

    excluded = set(st.session_state.get("excluded_uploads", []))
    file_payloads: List[Dict[str, Any]] = []
    visible = []
    if uploaded_files:
        for index, uploaded in enumerate(uploaded_files):
            if uploaded.name in excluded:
                continue
            data = uploaded.read()
            visible.append((index, uploaded.name, data))
            file_payloads.append({"filename": uploaded.name, "bytes": data})

    if visible:
        for index, name, data in visible:
            kind, _fmt = _file_kind(name)
            size = (
                f"{len(data) / (1024 * 1024):.1f} MB"
                if len(data) >= 1024 * 1024
                else f"{len(data) / 1024:.1f} KB"
            )
            row, action = st.columns([8, 1])
            row.html(
                f'<div class="tl-wb-file">'
                f'<div class="tl-wb-file-main"><strong>{_esc(name)}</strong>'
                f'<span class="tl-wb-file-size">{_esc(size)}</span></div>'
                f'<span class="tl-wb-file-kind">{_esc(kind.upper())}</span>'
                f"</div>"
            )
            if action.button("Remove", key=f"remove_upload_{index}"):
                excluded.add(name)
                st.session_state["excluded_uploads"] = sorted(excluded)
                st.rerun()

    tags = "".join(f'<span class="tl-wb-tag">{_esc(name)}</span>' for name, _ in FORMAT_GROUPS)
    formats_line = " · ".join(fmts.replace(",", "") for _, fmts in FORMAT_GROUPS)
    st.html(
        f"""
        <div class="tl-wb tl-wb-supported">
          <div class="tl-wb-tags">{tags}</div>
          <div class="tl-wb-formats-line">{_esc(formats_line)}</div>
        </div>
        """
    )

    q_col, s_col = st.columns(2, gap="medium")
    with q_col:
        st.html('<div class="tl-wb-label">Investigation question</div>')
        question = st.text_area(
            "Investigation Question",
            placeholder="What do you want TrustLayers to investigate?",
            label_visibility="collapsed",
            help="A claim, question, date, or background. Example: Verify whether this announcement is authentic and whether the available evidence supports the claim.",
            height=100,
            key="workbench_question",
        )
    with s_col:
        st.html('<div class="tl-wb-label">External sources</div>')
        platform_urls_input = st.text_area(
            "External Sources",
            placeholder="Paste public URLs relevant to this investigation…",
            label_visibility="collapsed",
            help="Related posts, articles, videos, or official pages. YouTube and Reddit are retrieved live. Other links are kept with the case.",
            height=100,
            key="workbench_sources",
        )
    platform_urls = [line.strip() for line in (platform_urls_input or "").splitlines() if line.strip()]

    render_processing_notice()

    analyze_disabled = len(file_payloads) == 0 and len(platform_urls) == 0
    ready_col, cta_col = st.columns([2.2, 1], gap="medium")
    with ready_col:
        st.html('<div class="tl-wb-ready"><i></i> Ready to investigate</div>')
    with cta_col:
        if st.button(
            "Start Investigation",
            type="primary",
            disabled=analyze_disabled,
            key="workbench_start",
            width="stretch",
        ):
            st.session_state["pending_run"] = {
                "case_id": f"case_{uuid.uuid4().hex[:10]}",
                "files": file_payloads,
                "description": question or "",
                "platform_urls": platform_urls,
                "file_names": [item["filename"] for item in file_payloads],
            }
            st.session_state["investigate_phase"] = "running"
            st.session_state["tl_transition"] = "workbench-to-live"
            st.rerun()


# Storytelling beats formerly on the Home scroll — play after ASSESSING CONFIDENCE.
REVEAL_BEATS = [
    (0.12, "One artifact", "is not the whole story."),
    (0.22, "Cross-modal reasoning", "Signals converge across modalities."),
    (0.32, "The system adapts", "to the evidence available."),
    (0.42, "Extract signals", "Visual · OCR · Metadata · Audio · Provenance"),
    (0.52, "Build the evidence graph", "Relationships form between artifacts and claims."),
    (0.64, "Contradiction check", "The network reacts only to real conflicts."),
    (0.76, "Consistency does not prove authenticity", "Look for coordination."),
    (0.88, "When evidence is missing, we don't guess", "Uncertainty stays visible."),
    (0.97, "Trust decision", "Evidence → Relationships → Reasoning → Verdict"),
]


def _live_hud_html(
    *,
    kicker: str,
    title: str,
    lead: str,
    chips: str,
    pipeline: str,
    stage: str = "",
    show_signals: bool = False,
    reveal: bool = False,
) -> str:
    """Corner caption over full-bleed WebGL — no rectangular card."""
    signals = (
        '<div class="tl-signal-split" aria-hidden="true">'
        "<span>VISUAL</span><span>AUDIO</span><span>TEXT</span><span>METADATA</span>"
        "</div>"
        if show_signals
        else ""
    )
    klass = "tl-live-stage is-active"
    if reveal:
        klass += " tl-live-reveal"
    return (
        f'<div class="tl-live-spacer" aria-hidden="true"></div>'
        f'<div class="{klass}" id="tl-live-stage" data-stage="{_esc(stage)}">'
        f'<div class="tl-kicker">{_esc(kicker)}</div>'
        f'<h2 class="tl-live-title">{_esc(title)}</h2>'
        f'<p class="tl-lead">{_esc(lead)}</p>'
        f'<div class="tl-live-files">{chips}</div>'
        f"{signals}"
        f"{pipeline}"
        f"</div>"
    )


def render_live_investigation() -> None:
    """Full-screen live analysis. Form is hidden. Stages follow the real pipeline."""
    pending = st.session_state.get("pending_run")
    if not pending:
        st.session_state["investigate_phase"] = "workbench"
        st.rerun()
        return

    names = pending.get("file_names") or []
    chips = "".join(f'<span class="tl-live-file">{_esc(name)}</span>' for name in names[:8])
    if not chips:
        chips = '<span class="tl-live-file">EXTERNAL SOURCES</span>'
    st.html('<div id="tl-view" data-view="running" hidden></div>')
    stage_box = st.empty()
    stage_box.html(
        _live_hud_html(
            kicker="Live investigation",
            title="INGESTING EVIDENCE",
            lead="Opening the investigation…",
            chips=chips,
            pipeline=_pipeline_html(active="ingest"),
            stage="ingest",
        )
    )
    components.html(
        """
        <script>
        (() => {
          const win = window.parent;
          const doc = win.document;
          doc.documentElement.dataset.tlView = "running";
          const uni = doc.getElementById("tl-universe");
          if (uni) { uni.classList.add("is-active", "is-live"); }
          if (win.__tlCinemaSetMode) win.__tlCinemaSetMode("ingest");
        })();
        </script>
        """,
        height=0,
    )

    seen: List[str] = []
    last_mode: List[str] = [""]
    last_hud: List[str] = [""]

    def on_progress(event: ProgressEvent) -> None:
        stage = event.stage if event.stage in dict(STAGE_ORDER) else None
        if stage and stage not in seen and event.status == "done":
            seen.append(stage)
        active = stage if event.status == "running" else None
        label = dict(STAGE_ORDER).get(active or (seen[-1] if seen else "ingest"), event.stage.upper())
        hud_key = f"{active}|{label}|{event.message}|{','.join(seen)}"
        if hud_key != last_hud[0]:
            last_hud[0] = hud_key
            stage_box.html(
                _live_hud_html(
                    kicker="Live investigation",
                    title=label,
                    lead=event.message,
                    chips=chips,
                    pipeline=_pipeline_html(active=active, done=seen),
                    stage=active or "",
                    show_signals=True,
                )
            )
        mode_map = {
            "ingest": "ingest",
            "preprocessing": "extract",
            "grounding": "graph",
            "reasoning": "graph",
            "platform": "contradict",
            "fusing": "fuse",
            "report": "fuse",
        }
        mode = mode_map.get(active or "ingest", "graph")
        if mode != last_mode[0]:
            last_mode[0] = mode
            components.html(
                f"""
                <script>
                (() => {{
                  const win = window.parent;
                  if (win.__tlCinemaSetMode) win.__tlCinemaSetMode({mode!r});
                }})();
                </script>
                """,
                height=0,
            )

    case_input = CaseInput(
        case_id=pending["case_id"],
        files=pending["files"],
        description=pending.get("description") or "",
        platform_urls=pending.get("platform_urls") or [],
    )
    st.session_state["active_case_id"] = pending["case_id"]
    result = run_case(case_input, on_progress=on_progress)

    fusion = result.case.fusion if result and result.case else None
    verdict = fusion.verdict.replace("_", " ") if fusion and fusion.verdict else "INCONCLUSIVE"
    done_through_fuse = [key for key, _ in STAGE_ORDER if key not in ("report",)]

    # After ASSESSING CONFIDENCE: one continuous JS timeline — no per-beat Streamlit re-renders.
    captions = [
        {"p": p, "title": title, "sub": subtitle, "kicker": "Evidence reconstruction"}
        for p, title, subtitle in REVEAL_BEATS
    ]
    story_ms = max(9000, len(REVEAL_BEATS) * 1050)
    stage_box.html(
        _live_hud_html(
            kicker="Live investigation",
            title="ASSESSING CONFIDENCE",
            lead=f"Verdict calculated: {verdict}. Reconstructing the evidence story…",
            chips=chips,
            pipeline=_pipeline_html(active="fusing", done=[k for k in done_through_fuse if k != "fusing"]),
            stage="fusing",
            reveal=True,
        )
    )
    components.html(
        f"""
        <script>
        (() => {{
          const win = window.parent;
          const doc = win.document;
          doc.documentElement.dataset.tlView = "running";
          const uni = doc.getElementById("tl-universe");
          if (uni) uni.classList.add("is-active", "is-live");
          // Hide Streamlit HUD while JS caption drives the story (avoids DOM thrash).
          const stage = doc.getElementById("tl-live-stage");
          if (stage) stage.style.visibility = "hidden";
          if (win.__tlCinemaPlayStory) {{
            win.__tlCinemaPlayStory({{
              captions: {captions!r},
              from: 0.12,
              to: 0.99,
              duration: {story_ms},
            }});
          }} else if (win.__tlCinemaSeek) {{
            win.__tlCinemaSeek(0.12);
          }}
        }})();
        </script>
        """,
        height=0,
    )
    time.sleep(story_ms / 1000.0 + 0.35)

    stage_box.html(
        _live_hud_html(
            kicker="Investigation result",
            title=verdict,
            lead="Opening the full investigation report…",
            chips="",
            pipeline=_pipeline_html(done=[key for key, _ in STAGE_ORDER]),
            stage="report",
            reveal=True,
        )
    )
    components.html(
        """
        <script>
        (() => {
          const win = window.parent;
          const doc = win.document;
          if (win.__tlCinemaHideCaption) win.__tlCinemaHideCaption();
          const stage = doc.getElementById("tl-live-stage");
          if (stage) stage.style.visibility = "visible";
          if (win.__tlCinemaSeek) win.__tlCinemaSeek(0.99);
        })();
        </script>
        """,
        height=0,
    )
    time.sleep(1.2)

    st.session_state.pop("pending_run", None)
    st.session_state["case_result"] = result
    st.session_state["investigate_phase"] = "result"
    st.session_state["goto"] = "Investigate"
    st.rerun()


def _verdict_copy(case: Case) -> str:
    fusion = case.fusion
    if not fusion:
        return "No verdict was produced for this case."
    if fusion.verdict == "AUTHENTIC":
        return "The artifacts support each other and show no sign of manipulation. This is an assessment, not proof."
    if fusion.verdict == "MANIPULATED":
        return "At least one artifact shows strong signs of manipulation or of being presented out of context."
    if fusion.verdict == "COORDINATED_SYNTHETIC":
        return "Several artifacts show signs of manipulation and share traces that link them."
    return fusion.inconclusive_label or "Available evidence does not support a confident authenticity decision."


def _why_rows(case: Case) -> str:
    rows = []
    for art in case.artifacts:
        for item in art.evidence:
            if item.direction == "authentic":
                mark, klass = "✓", "tl-mark-ok"
            elif item.direction == "manipulated":
                mark, klass = "⚠", "tl-mark-bad"
            else:
                mark, klass = "·", "tl-mark-q"
            rows.append(
                f'<div class="tl-finding"><span class="{klass}">{mark}</span><div>{_esc(item.description)}</div></div>'
            )
    for rel in case.relations:
        if rel.relation == "CONTRADICTS":
            mark, klass = "⚠", "tl-mark-bad"
        elif rel.relation in ("SUPPORTS", "MATCHES"):
            mark, klass = "✓", "tl-mark-ok"
        else:
            mark, klass = "?", "tl-mark-q"
        text = rel.explanation or f"{rel.relation} between artifacts"
        rows.append(f'<div class="tl-finding"><span class="{klass}">{mark}</span><div>{_esc(text)}</div></div>')
    if not rows:
        rows.append('<div class="tl-finding"><span class="tl-mark-q">?</span><div>No grounded findings were recorded for this case.</div></div>')
    return "".join(rows)


def _graph_markup(case: Case) -> tuple[str, str]:
    graph = case.evidence_graph
    if not graph or not graph.nodes:
        return "", '<div class="tl-empty">No evidence graph was produced for this case.</div>'

    columns: Dict[str, list] = {"artifact": [], "claim": [], "entity": [], "platform_source": []}
    for node in graph.nodes:
        columns.setdefault(node.node_type, []).append(node)
    used = [(name, nodes) for name, nodes in columns.items() if nodes]
    if not used:
        return "", '<div class="tl-empty">No evidence graph was produced for this case.</div>'

    col_w, row_h = 210, 72
    width = 40 + len(used) * col_w
    height = 48 + max(len(nodes) for _, nodes in used) * row_h
    pos = {}
    for col_index, (_, nodes) in enumerate(used):
        for row_index, node in enumerate(nodes[:12]):
            pos[node.node_id] = (30 + col_index * col_w, 28 + row_index * row_h)

    parts = [f'<svg viewBox="0 0 {width} {max(height, 220)}" width="100%" height="{max(height, 220)}">']
    for edge in graph.edges:
        if edge.source_node_id not in pos or edge.target_node_id not in pos:
            continue
        x1, y1 = pos[edge.source_node_id]
        x2, y2 = pos[edge.target_node_id]
        rel_class = f"edge edge-{_esc(edge.relation.lower())}"
        parts.append(
            f'<g class="edge-g" data-src="{_esc(edge.source_node_id)}" data-tgt="{_esc(edge.target_node_id)}">'
            f'<path class="{rel_class}" d="M{x1+70} {y1+16} C{(x1+x2)/2+70} {y1+16}, {(x1+x2)/2} {y2+16}, {x2} {y2+16}" />'
            f'<text class="rel rel-{_esc(edge.relation.lower())}" x="{(x1+x2)/2+35}" y="{(y1+y2)/2+10}">{_esc(edge.relation)}</text>'
            f"</g>"
        )
    for node_id, (x, y) in pos.items():
        node = next(item for item in graph.nodes if item.node_id == node_id)
        label = node.label[:22]
        parts.append(
            f'<g class="node-g" data-id="{_esc(node_id)}">'
            f'<rect class="node" x="{x}" y="{y}" width="150" height="34" rx="17" />'
            f'<text class="label" x="{x+75}" y="{y+22}" text-anchor="middle">{_esc(label)}</text>'
            f"</g>"
        )
    parts.append("</svg>")

    timeline = []
    for edge in graph.edges:
        timeline.append(
            f'<div class="tl-rel tl-rel-{edge.relation.lower()}">'
            f'<div class="tl-rel-title">{_esc(edge.relation)}</div>'
            f'<div class="tl-muted">{_esc(edge.explanation or edge.source_node_id)}</div></div>'
        )
    hidden = max(0, len(graph.nodes) - len(pos))
    note = f'<div class="tl-help">{hidden} additional nodes are listed below.</div>' if hidden else ""
    return "".join(parts), f'{note}<div class="tl-timeline">{"".join(timeline)}</div>'


def _missing_items(case: Case) -> List[str]:
    fusion = case.fusion
    if not fusion:
        return ["No fusion result was produced."]
    items: List[str] = []
    items.extend(fusion.limitations or [])
    items.extend(f"Unavailable check: {name}" for name in (fusion.unavailable_checks or []))
    modalities = {art.modality for art in case.artifacts if art.status in ("ok", "degraded", "pending")}
    if len(modalities) < 2:
        items.append("Only one modality was available, so cross-modal corroboration could not run.")
    if not case.platform_artifacts:
        items.append("No external platform sources were provided for provenance checks.")
    if not any(art.evidence for art in case.artifacts):
        items.append("No strong grounded authenticity or manipulation signals were recorded.")
    # Deduplicate while preserving order
    seen = set()
    out = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    if not out:
        out.append("Evidence was too thin for a confident authenticity decision.")
    return out


def _next_step_copy(case: Case) -> List[str]:
    modalities = {art.modality for art in case.artifacts}
    tips = []
    if "image" in modalities and "audio" not in modalities and "video" not in modalities:
        tips.append("Add a related video, audio clip, or document that describes the same event.")
    if "document" not in modalities:
        tips.append("Upload a source document, caption, or post text that can be cross-checked.")
    if not case.platform_artifacts:
        tips.append("Paste a platform URL so provenance and upload context can be inspected.")
    if len(case.artifacts) < 2:
        tips.append("A second independent artifact often changes sufficiency more than deeper analysis of one file.")
    tips.append("TrustLayers will keep the verdict inconclusive when evidence is incomplete rather than guess.")
    return tips[:4]


def _verdict_badge(verdict: str) -> str:
    if verdict == "INCONCLUSIVE":
        return "Abstention · not enough evidence"
    if verdict == "AUTHENTIC":
        return "Assessment · supporting evidence"
    if verdict == "MANIPULATED":
        return "Alert · manipulation signals"
    if verdict == "COORDINATED_SYNTHETIC":
        return "Alert · coordinated synthetic signals"
    return "Investigation result"


def _short_missing_title(item: str) -> str:
    text = item.strip()
    lower = text.lower()
    if "sufficiency" in lower or "threshold" in lower:
        return "Evidence sufficiency below threshold"
    if "platform" in lower or "provenance" in lower or "external" in lower:
        return "No corroborating / provenance source"
    if "one modality" in lower or "cross-modal" in lower:
        return "Only one modality available"
    if "unavailable check" in lower:
        return text.replace("Unavailable check:", "Unavailable:").strip()
    if "grounded" in lower or "signals" in lower:
        return "No strong grounded signals"
    if len(text) <= 64:
        return text
    return text[:61].rstrip() + "…"


def _help_action_label(tip: str) -> str:
    lower = tip.lower()
    if "video" in lower or "audio" in lower:
        return "Add a related video or audio"
    if "document" in lower or "caption" in lower:
        return "Provide an original document"
    if "platform" in lower or "url" in lower or "provenance" in lower:
        return "Add platform provenance"
    if "second independent" in lower or "second" in lower:
        return "Add an independent source"
    if "inconclusive" in lower:
        return "Keep abstaining when evidence is thin"
    if len(tip) <= 48:
        return tip
    return tip[:45].rstrip() + "…"


def _pipeline_timeline_html(done: List[str], active: Optional[str] = None) -> str:
    short = {
        "ingest": "INGEST EVIDENCE",
        "preprocessing": "EXTRACT SIGNALS",
        "grounding": "BUILD EVIDENCE",
        "reasoning": "CHECK RELATIONSHIPS",
        "platform": "ANALYZE CONTRADICTIONS",
        "fusing": "ASSESS CONFIDENCE",
        "report": "GENERATE REPORT",
    }
    parts = ['<div class="tl-rx-trace" role="list">']
    for i, (key, _) in enumerate(STAGE_ORDER):
        klass = "tl-rx-trace-step"
        mark = "○"
        if key == active:
            klass += " is-on"
            mark = "●"
        elif key in done:
            klass += " is-done"
            mark = "✓"
        parts.append(
            f'<div class="{klass}" role="listitem">'
            f'<span class="tl-rx-trace-mark">{mark}</span>'
            f'<span class="tl-rx-trace-label">{short.get(key, key.upper())}</span>'
            f"</div>"
        )
        if i < len(STAGE_ORDER) - 1:
            parts.append('<div class="tl-rx-trace-arrow" aria-hidden="true"></div>')
    parts.append("</div>")
    return "".join(parts)


def _why_numbered_html(case: Case) -> str:
    """Compact numbered reasons from real findings / limitations only."""
    items: List[str] = []
    for miss in _missing_items(case):
        title = _short_missing_title(miss)
        if title not in items:
            items.append(title)
    for art in case.artifacts:
        for item in art.evidence[:2]:
            desc = (item.description or "").strip()
            if desc and desc not in items:
                items.append(desc if len(desc) <= 72 else desc[:69].rstrip() + "…")
    if case.relations:
        items.append(f"{len(case.relations)} relationship(s) were recorded across evidence.")
    elif case.artifacts:
        items.append("No independent relationships were recorded between artifacts.")
    # Deduplicate while preserving order
    seen = set()
    ordered = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(item)
    if not ordered:
        ordered = ["No grounded findings were recorded for this case."]
    lis = "".join(
        f'<li><span>{i:02d}</span><div>{_esc(text)}</div></li>'
        for i, text in enumerate(ordered[:6], start=1)
    )
    return f'<ol class="tl-rx-why-num">{lis}</ol>'


def _help_chips_html(tips: List[str]) -> str:
    chips = []
    for tip in tips:
        label = _help_action_label(tip).upper()
        chip = (
            label.replace("PROVIDE AN ORIGINAL DOCUMENT", "ADD DOCUMENT")
            .replace("ADD A RELATED VIDEO OR AUDIO", "ADD VIDEO / AUDIO")
            .replace("ADD PLATFORM PROVENANCE", "ADD SOURCE URL")
            .replace("ADD AN INDEPENDENT SOURCE", "ADD INDEPENDENT SOURCE")
        )
        if not chip.startswith("+"):
            chip = f"+ {chip}"
        chips.append(f'<span class="tl-rx-help-chip" title="{_esc(tip)}">{_esc(chip)}</span>')
    return (
        f'<div class="tl-rx-help-chips">{"".join(chips)}</div>'
        f'<p class="tl-rx-help-note">Independent evidence can increase confidence.</p>'
    )


def _build_result_graph_svg(case: Case, focus_id: str = "") -> tuple[str, int]:
    """Large investigation SVG from real nodes/edges only."""
    graph = case.evidence_graph
    nodes = list(graph.nodes) if graph and graph.nodes else []
    edges = list(graph.edges) if graph and graph.edges else []
    w, h = 720, 420

    # Fallback: claim + single artifact, no invented relationship semantics beyond containment.
    if not nodes and case.artifacts:
        arts = case.artifacts[:5]
        cx, cy = 360, 168
        parts = [
            f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" xmlns="http://www.w3.org/2000/svg">',
            '<defs><radialGradient id="gglow" cx="50%" cy="45%" r="45%">'
            '<stop offset="0%" stop-color="rgba(61,220,151,0.18)"/>'
            '<stop offset="100%" stop-color="rgba(61,220,151,0)"/></radialGradient></defs>',
            f'<circle class="ambient" cx="{cx}" cy="{cy}" r="120" fill="url(#gglow)" />',
            f'<g class="node-g is-core" data-id="claim">'
            f'<circle class="node core" cx="{cx}" cy="{cy}" r="28" />'
            f'<text class="label" x="{cx}" y="{cy + 4}" text-anchor="middle">CLAIM</text></g>',
        ]
        for i, art in enumerate(arts):
            if len(arts) == 1:
                ax, ay = cx, cy + 118
            else:
                ang = math.pi * 0.15 + (math.pi * 0.7) * (i / max(len(arts) - 1, 1))
                ax = cx + math.cos(ang) * 160
                ay = cy + 40 + math.sin(ang) * 110
            nid = art.id
            hot = " is-focus" if focus_id and focus_id == nid else ""
            parts.append(
                f'<g class="edge-g" data-src="claim" data-tgt="{_esc(nid)}">'
                f'<path class="edge edge-muted" d="M{cx} {cy + 28} L{ax:.1f} {ay - 18:.1f}" /></g>'
            )
            label = (art.modality or "FILE").upper()[:10]
            parts.append(
                f'<g class="node-g{hot}" data-id="{_esc(nid)}">'
                f'<rect class="node" x="{ax - 54:.1f}" y="{ay - 16:.1f}" width="108" height="32" rx="16" />'
                f'<text class="label" x="{ax:.1f}" y="{ay + 4:.1f}" text-anchor="middle">{_esc(label)}</text></g>'
            )
        parts.append("</svg>")
        note = '<div class="tl-rx-canvas-note">No relationships recorded.</div>'
        return "".join(parts) + note, h

    if not nodes:
        empty = (
            f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}">'
            f'<text class="label" x="{w/2}" y="{h/2}" text-anchor="middle" opacity="0.5">'
            f"No evidence graph produced</text></svg>"
            '<div class="tl-rx-canvas-note">No relationships recorded.</div>'
        )
        return empty, h

    center = next((n for n in nodes if n.node_type == "claim"), nodes[0])
    others = [n for n in nodes if n.node_id != center.node_id][:8]
    cx, cy = w / 2, h / 2 - 10
    pos = {center.node_id: (cx, cy)}
    for i, node in enumerate(others):
        ang = -math.pi / 2 + (2 * math.pi * i / max(len(others), 1))
        r = 150 if len(others) > 3 else 130
        pos[node.node_id] = (cx + r * math.cos(ang), cy + r * math.sin(ang) * 0.85)

    parts = [
        f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" xmlns="http://www.w3.org/2000/svg">',
        '<defs><radialGradient id="gglow" cx="50%" cy="45%" r="48%">'
        '<stop offset="0%" stop-color="rgba(61,220,151,0.16)"/>'
        '<stop offset="100%" stop-color="rgba(61,220,151,0)"/></radialGradient></defs>',
        f'<circle class="ambient" cx="{cx}" cy="{cy}" r="150" fill="url(#gglow)" />',
    ]
    for edge in edges:
        if edge.source_node_id not in pos or edge.target_node_id not in pos:
            continue
        x1, y1 = pos[edge.source_node_id]
        x2, y2 = pos[edge.target_node_id]
        rel = edge.relation.lower()
        eklass = "edge"
        if rel == "contradicts":
            eklass = "edge edge-contradicts"
        elif rel in ("uncertain", "linked", "linked_to"):
            eklass = "edge edge-muted"
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 18
        parts.append(
            f'<g class="edge-g" data-src="{_esc(edge.source_node_id)}" data-tgt="{_esc(edge.target_node_id)}">'
            f'<path class="{eklass}" d="M{x1:.1f} {y1:.1f} Q{mx:.1f} {my:.1f} {x2:.1f} {y2:.1f}" />'
            f"</g>"
        )

    for node in [center, *others]:
        if node.node_id not in pos:
            continue
        x, y = pos[node.node_id]
        hot = " is-focus" if focus_id and (
            focus_id == node.node_id or focus_id == (node.artifact_id or "")
        ) else ""
        if node.node_id == center.node_id:
            parts.append(
                f'<g class="node-g is-core{hot}" data-id="{_esc(node.node_id)}">'
                f'<circle class="node core" cx="{x:.1f}" cy="{y:.1f}" r="30" />'
                f'<text class="label" x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle">CLAIM</text></g>'
            )
        else:
            tag = (node.node_type or "node").upper()[:10]
            if node.node_type == "artifact":
                art = next((a for a in case.artifacts if a.id == node.artifact_id), None)
                if art:
                    tag = (art.modality or "FILE").upper()[:10]
            parts.append(
                f'<g class="node-g{hot}" data-id="{_esc(node.node_id)}" data-art="{_esc(node.artifact_id or "")}">'
                f'<rect class="node" x="{x - 52:.1f}" y="{y - 16:.1f}" width="104" height="32" rx="16" />'
                f'<text class="label" x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle">{_esc(tag)}</text></g>'
            )
    parts.append("</svg>")
    note = ""
    if not edges:
        note = '<div class="tl-rx-canvas-note">No relationships recorded.</div>'
    return "".join(parts) + note, h


def _result_graph_canvas(case: Case, focus_id: str = "") -> None:
    svg, height = _build_result_graph_svg(case, focus_id=focus_id)
    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html,body {{ margin:0; background:transparent; overflow:hidden; }}
    .wrap {{
    position:relative; width:100%; height:{height}px;
    border:1px solid rgba(244,247,245,0.12); border-radius:10px;
    background:
      radial-gradient(420px 240px at 50% 42%, rgba(61,220,151,0.10), transparent 70%),
      rgba(255,255,255,0.015);
    overflow:hidden;
  }}
  canvas.dust {{
    position:absolute; inset:0; width:100%; height:100%;
    pointer-events:none; opacity:0.55;
  }}
  svg {{ position:relative; z-index:1; width:100%; height:{height}px; display:block; }}
  .edge {{ fill:none; stroke:rgba(61,220,151,0.55); stroke-width:1.35; stroke-dasharray:5 7; animation: flow 9s linear infinite; }}
  .edge-contradicts {{ stroke:rgba(226,91,74,0.72); }}
  .edge-muted {{ stroke:rgba(143,154,147,0.45); stroke-dasharray:3 6; }}
  .node {{ fill:#0d1210; stroke:rgba(61,220,151,0.7); stroke-width:1.15; }}
  .node.core {{ fill:rgba(61,220,151,0.10); stroke:rgba(61,220,151,0.85); animation: pulse 3.6s ease-in-out infinite; }}
  .label {{ fill:#f4f7f5; font:700 11px "Plus Jakarta Sans",sans-serif; letter-spacing:0.08em; }}
  .node-g {{ transition: opacity .25s ease; }}
  .node-g.is-dim {{ opacity:0.22; }}
  .node-g.is-hot .node, .node-g.is-focus .node {{
    stroke:#3ddc97; stroke-width:1.7;
    filter: drop-shadow(0 0 10px rgba(61,220,151,0.35));
  }}
  .edge-g.is-dim {{ opacity:0.18; }}
  .edge-g.is-hot .edge {{ stroke-width:2; }}
  .tl-rx-canvas-note {{
    position:absolute; left:0; right:0; bottom:12px; z-index:2;
    text-align:center; color:#8f9a93; font:600 11px "Plus Jakarta Sans",sans-serif;
    letter-spacing:0.06em;
  }}
  @keyframes flow {{ to {{ stroke-dashoffset: -120; }} }}
  @keyframes pulse {{
    0%,100% {{ filter: drop-shadow(0 0 6px rgba(61,220,151,0.15)); }}
    50% {{ filter: drop-shadow(0 0 14px rgba(61,220,151,0.35)); }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    .edge, .node.core {{ animation: none !important; }}
    canvas.dust {{ display:none; }}
  }}
</style></head>
<body><div class="wrap"><canvas class="dust"></canvas>{svg}</div>
<script>
(() => {{
  const nodes = [...document.querySelectorAll('.node-g')];
  const edges = [...document.querySelectorAll('.edge-g')];
  function dim(exceptIds) {{
    nodes.forEach(g => {{
      const id = g.dataset.id;
      const art = g.dataset.art || '';
      const on = !exceptIds || exceptIds.has(id) || (art && exceptIds.has(art));
      g.classList.toggle('is-hot', on && !!exceptIds);
      g.classList.toggle('is-dim', !on);
    }});
    edges.forEach(g => {{
      const hot = !exceptIds || exceptIds.has(g.dataset.src) || exceptIds.has(g.dataset.tgt);
      g.classList.toggle('is-hot', hot && !!exceptIds);
      g.classList.toggle('is-dim', !hot);
    }});
  }}
  nodes.forEach(g => {{
    g.style.cursor = 'pointer';
    g.addEventListener('pointerenter', () => {{
      const linked = new Set([g.dataset.id]);
      if (g.dataset.art) linked.add(g.dataset.art);
      edges.forEach(e => {{
        if (e.dataset.src === g.dataset.id) linked.add(e.dataset.tgt);
        if (e.dataset.tgt === g.dataset.id) linked.add(e.dataset.src);
      }});
      dim(linked);
    }});
    g.addEventListener('pointerleave', () => dim(null));
  }});
  const canvas = document.querySelector('canvas.dust');
  if (canvas && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {{
    const ctx = canvas.getContext('2d');
    const wrap = canvas.parentElement;
    const resize = () => {{
      canvas.width = wrap.clientWidth;
      canvas.height = wrap.clientHeight;
    }};
    resize();
    const dots = Array.from({{length: 18}}, () => ({{
      x: Math.random(), y: Math.random(),
      r: 0.6 + Math.random() * 1.2,
      vx: (Math.random() - 0.5) * 0.00018,
      vy: (Math.random() - 0.5) * 0.00018,
    }}));
    const tick = () => {{
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      dots.forEach(d => {{
        d.x = (d.x + d.vx + 1) % 1;
        d.y = (d.y + d.vy + 1) % 1;
        ctx.beginPath();
        ctx.fillStyle = 'rgba(61,220,151,0.28)';
        ctx.arc(d.x * canvas.width, d.y * canvas.height, d.r, 0, Math.PI * 2);
        ctx.fill();
      }});
      requestAnimationFrame(tick);
    }};
    tick();
  }}
}})();
</script>
</body></html>"""
    components.html(html_doc, height=height + 8)


def _evidence_rail_html(case: Case, focus_id: str = "") -> str:
    if not case.artifacts:
        return '<div class="tl-rx-empty">No artifacts were retained.</div>'
    rows = []
    for art in case.artifacts:
        reliability = f"{art.reliability.score:.2f}" if art.reliability else "n/a"
        hash_bit = "Hash present" if art.perceptual_hash else "No hash"
        hot = " is-active" if focus_id == art.id else ""
        rows.append(
            f'<div class="tl-rx-rail-item{hot}" data-art="{_esc(art.id)}">'
            f'<div class="tl-rx-rail-kind">{_esc(art.modality.upper())}</div>'
            f'<div class="tl-rx-rail-main"><strong>{_esc(art.display_name)}</strong>'
            f'<span>Reliability {_esc(reliability)} · {_esc(hash_bit)}</span></div>'
            f"</div>"
        )
    return f'<div class="tl-rx-rail">{"".join(rows)}</div>'


def _why_structured_html(case: Case) -> str:
    fusion = case.fusion
    blocks = []
    evidence_bits = []
    for art in case.artifacts:
        for item in art.evidence:
            evidence_bits.append(item.description)
    if evidence_bits:
        lis = "".join(f"<li>{_esc(bit)}</li>" for bit in evidence_bits[:8])
        blocks.append(
            f'<div class="tl-rx-why-block"><div class="tl-rx-why-h">Evidence</div><ul>{lis}</ul></div>'
        )
    if case.relations:
        lis = "".join(
            f"<li><b>{_esc(rel.relation)}</b> — {_esc(rel.explanation or 'Recorded relation')}</li>"
            for rel in case.relations[:8]
        )
        blocks.append(
            f'<div class="tl-rx-why-block"><div class="tl-rx-why-h">Relationships</div><ul>{lis}</ul></div>'
        )
    contras = (case.evidence_graph.contradiction_list if case.evidence_graph else None) or []
    if contras:
        lis = "".join(
            f"<li>{_esc(c.get('explanation') or 'Contradiction recorded')}</li>" for c in contras[:6]
        )
        blocks.append(
            f'<div class="tl-rx-why-block"><div class="tl-rx-why-h">Contradictions</div><ul>{lis}</ul></div>'
        )
    if fusion:
        blocks.append(
            f'<div class="tl-rx-why-block"><div class="tl-rx-why-h">Confidence</div>'
            f"<p>Ordinal level: <b>{_esc(fusion.confidence_level.upper())}</b>. "
            f"This is not a probability.</p></div>"
        )
        codes = ", ".join(fusion.reason_codes) if fusion.reason_codes else "None recorded"
        blocks.append(
            f'<div class="tl-rx-why-block"><div class="tl-rx-why-h">Verdict basis</div>'
            f"<p>{_esc(_verdict_copy(case))}</p>"
            f'<p class="tl-rx-muted">Reason codes: {_esc(codes)}</p></div>'
        )
    if not blocks:
        blocks.append('<div class="tl-rx-empty">No grounded findings were recorded for this case.</div>')
    return "".join(blocks)

def render_result_screen(case: Case) -> None:
    """Rebuild result page as a forensics console. Data only from completed case."""
    st.html('<div id="tl-view" data-view="result" hidden></div>')
    fusion = case.fusion
    if not fusion:
        st.error("No verdict was produced for this case.")
        return

    supports = sum(1 for rel in case.relations if rel.relation in ("SUPPORTS", "MATCHES"))
    contradictions = sum(1 for rel in case.relations if rel.relation == "CONTRADICTS")
    analyzed = sum(1 for art in case.artifacts if art.status in ("ok", "degraded", "pending"))
    m_ordinal = "High" if fusion.manip_evidence > 0.65 else ("Moderate" if fusion.manip_evidence > 0.3 else "Low")
    a_ordinal = "High" if fusion.auth_support > 0.60 else ("Moderate" if fusion.auth_support > 0.3 else "Low")
    m_pct = max(6, min(100, int(round(fusion.manip_evidence * 100))))
    a_pct = max(6, min(100, int(round(fusion.auth_support * 100))))
    verdict_key = fusion.verdict.lower()
    verdict_label = fusion.verdict.replace("_", " ")
    next_steps = _next_step_copy(case)

    focus_id = st.session_state.get("rx_focus_art", "")
    if case.artifacts and focus_id not in {a.id for a in case.artifacts}:
        focus_id = ""

    # —— 1. Case header ——
    st.html(
        f"""
        <div class="tl-rx-shell">
          <div class="tl-rx-casebar">
            <div class="tl-rx-caseid">CASE #{_esc(case.id)}</div>
            <div class="tl-status is-{verdict_key}"><i></i>{_esc(verdict_label)}</div>
          </div>
        </div>
        """
    )

    # —— 2. Main investigation: ~70 / 30 ——
    left, right = st.columns([2.15, 1], gap="medium")
    with left:
        st.html('<div class="tl-rx-label">Evidence graph</div>')
        _result_graph_canvas(case, focus_id=focus_id)
        st.html('<div class="tl-rx-label tl-rx-label-spaced">Evidence</div>')
        st.html(_evidence_rail_html(case, focus_id=focus_id))
        if case.artifacts:
            options = {f"{art.modality.upper()} · {art.display_name}": art.id for art in case.artifacts}
            labels = ["— Highlight artifact in graph —", *options.keys()]
            st.session_state["_rx_focus_map"] = options
            if "rx_focus_pick" not in st.session_state:
                reverse = {aid: lab for lab, aid in options.items()}
                st.session_state["rx_focus_pick"] = reverse.get(focus_id, labels[0])

            def _on_focus_pick() -> None:
                picked_label = st.session_state.get("rx_focus_pick", labels[0])
                fmap = st.session_state.get("_rx_focus_map", {})
                st.session_state["rx_focus_art"] = fmap.get(picked_label, "")

            st.selectbox(
                "Highlight artifact",
                labels,
                label_visibility="collapsed",
                key="rx_focus_pick",
                on_change=_on_focus_pick,
            )

    with right:
        st.html(
            f"""
            <div class="tl-rx-verdict tl-verdict-{verdict_key}">
              <div class="tl-rx-label">Investigation result</div>
              <div class="tl-rx-verdict-title">{_esc(verdict_label)}</div>
              <p class="tl-rx-verdict-copy">{_esc(_verdict_copy(case))}</p>
              <div class="tl-rx-metrics">
                <div><span>Confidence</span><strong>{_esc(fusion.confidence_level.upper())}</strong></div>
                <div><span>Artifacts</span><strong>{analyzed}</strong></div>
                <div><span>Supporting</span><strong>{supports}</strong></div>
                <div><span>Contradictions</span><strong>{contradictions}</strong></div>
                <div><span>Sources</span><strong>{len(case.platform_artifacts)}</strong></div>
              </div>
            </div>
            <div class="tl-rx-sideblock">
              <div class="tl-rx-label">Why this result</div>
              {_why_numbered_html(case)}
            </div>
            <div class="tl-rx-sideblock">
              <div class="tl-rx-label">What would change the verdict?</div>
              {_help_chips_html(next_steps)}
            </div>
            """
        )

    # —— 3. Full-width detailed reasoning ——
    with st.expander("Why this result (detailed findings)", expanded=False):
        st.html(_why_structured_html(case))
        if case.evidence_graph and case.evidence_graph.contradiction_list:
            for contra in case.evidence_graph.contradiction_list:
                st.write(contra.get("explanation", ""))
                st.caption(
                    f"{contra.get('conflict_type', 'semantic')} · "
                    f"{contra.get('artifact_a')} / {contra.get('artifact_b')} · "
                    f"{str(contra.get('confidence_level', '')).upper()}"
                )

    # —— 4. Evidence inspector ——
    st.html('<div class="tl-rx-label tl-rx-label-spaced">Evidence inspector</div>')
    labels: List[str] = []
    node_map: List[Any] = []
    if case.evidence_graph and case.evidence_graph.nodes:
        for node in case.evidence_graph.nodes:
            labels.append(f"{node.node_type}: {node.label}")
            node_map.append(node)
    elif case.artifacts:
        for art in case.artifacts:
            labels.append(f"artifact: {art.display_name}")
            node_map.append(art)

    if labels:
        selected = st.selectbox("Inspect", labels, label_visibility="collapsed", key="rx_inspect_node")
        obj = node_map[labels.index(selected)]
        art = None
        typ = ""
        if hasattr(obj, "node_type"):
            typ = obj.node_type.upper()
            if obj.artifact_id:
                art = next((a for a in case.artifacts if a.id == obj.artifact_id), None)
            if art is None and obj.node_type == "artifact":
                art = next((a for a in case.artifacts if a.display_name == obj.label), None)
            related = []
            if case.evidence_graph:
                related = [
                    e for e in case.evidence_graph.edges
                    if e.source_node_id == obj.node_id or e.target_node_id == obj.node_id
                ]
        else:
            art = obj
            typ = art.modality.upper()
            related = []
        rel_score = f"{art.reliability.score:.2f}" if art and art.reliability else "—"
        hash_state = "Present" if art and art.perceptual_hash else "—"
        st.html(
            f'<div class="tl-rx-inspect-strip">'
            f'<div><span>Type</span><strong>{_esc(typ)}</strong></div>'
            f'<div><span>Reliability</span><strong>{_esc(rel_score)}</strong></div>'
            f'<div><span>Hash</span><strong>{_esc(hash_state)}</strong></div>'
            f"</div>"
        )
        if related:
            for edge in related:
                st.caption(f"{edge.relation}: {edge.explanation or edge.target_node_id} · {edge.method}")
        else:
            st.caption("No relationships recorded for this node.")

    st.html(
        f"""
        <div class="tl-rx-meters">
          <div class="tl-rx-meter">
            <div class="tl-rx-meter-head"><span>Manipulation evidence</span><strong>{_esc(m_ordinal)}</strong></div>
            <div class="tl-bar tl-bar-m"><i style="width:{m_pct}%"></i></div>
          </div>
          <div class="tl-rx-meter">
            <div class="tl-rx-meter-head"><span>Authenticity support</span><strong>{_esc(a_ordinal)}</strong></div>
            <div class="tl-bar tl-bar-a"><i style="width:{a_pct}%"></i></div>
          </div>
        </div>
        """
    )

    with st.expander("Internal scores", expanded=False):
        st.caption("Rule-based internal scores. They are not probabilities.")
        st.html(
            f"""
            <div class="tl-rx-score-grid">
              <div><span>Manipulation (m)</span><strong>{fusion.manip_evidence:.4f}</strong></div>
              <div><span>Authenticity (a)</span><strong>{fusion.auth_support:.4f}</strong></div>
              <div><span>Sufficiency</span><strong>{fusion.sufficiency:.4f}</strong></div>
              <div><span>Checks</span><strong>{fusion.checks_completed} / {fusion.checks_applicable}</strong></div>
            </div>
            """
        )

    if case.platform_artifacts:
        with st.expander(f"External sources ({len(case.platform_artifacts)})", expanded=False):
            for plat in case.platform_artifacts:
                st.write(f"**{plat.platform}:** {plat.title or plat.url}")
                st.caption(plat.url)

    done = [key for key, _ in STAGE_ORDER]
    if not case.cross_modal_activated and not case.relations:
        done = ["ingest", "preprocessing", "grounding", "fusing", "report"]
    st.html(
        '<div class="tl-rx-label tl-rx-label-spaced">Investigation trace</div>'
        + _pipeline_timeline_html(done=done)
    )

    report_col, new_col, delete_col = st.columns([1.35, 1, 1], gap="small")
    with report_col:
        st.download_button(
            "Download HTML Report",
            data=generate_report_html(case),
            file_name=f"report_{case.id}.html",
            mime="text/html",
            type="primary",
            width="stretch",
        )
    with new_col:
        if st.button("New investigation", width="stretch", key="rx_new"):
            st.session_state.pop("case_result", None)
            st.session_state.pop("rx_focus_art", None)
            st.session_state.pop("rx_focus_pick", None)
            st.session_state["goto"] = "Investigate"
            st.session_state["investigate_phase"] = "workbench"
            st.rerun()
    with delete_col:
        if st.button("Delete case", type="secondary", width="stretch", key="rx_delete"):
            delete_case(case.id)
            st.session_state.pop("active_case_id", None)
            st.session_state.pop("case_result", None)
            st.session_state.pop("rx_focus_art", None)
            st.session_state.pop("rx_focus_pick", None)
            st.session_state["investigate_phase"] = "workbench"
            st.success("This case was deleted.")
            st.rerun()

def render_evidence_page() -> None:
    """Evidence view for the current case, or an empty state."""
    result = st.session_state.get("case_result")
    st.html(
        """
        <div class="tl-kicker">Evidence</div>
        <h2 class="tl-statement" style="font-size:48px;">The graph is the case.</h2>
        <p class="tl-lead">Nodes are artifacts, claims, entities, and sources from the investigation. Relationships are only those the pipeline recorded.</p>
        """
    )
    if not result or result.case.job_status != "completed":
        st.html('<div class="tl-empty">Evidence appears after an investigation completes. Start one from Investigate.</div>')
        return
    render_result_screen(result.case)


def _load_eval() -> Optional[Dict[str, Any]]:
    results_file = EVAL_RESULTS_DIR / "summary.json"
    if not results_file.exists():
        return None
    try:
        return json.loads(results_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _split_accuracy(details: List[Dict[str, Any]], split: str) -> Optional[tuple[int, int]]:
    rows = [row for row in details if row.get("split") == split]
    if not rows:
        return None
    correct = sum(1 for row in rows if row.get("correct_trustlayers"))
    return correct, len(rows)


def render_evaluation_tab() -> None:
    """Research evaluation console. Numbers come only from a completed eval run."""
    st.html('<div id="tl-view" data-view="benchmark" hidden></div>')
    st.html('<div id="tl-benchmark-jump"></div>')

    st.html(
        """
        <div class="tl-bm-shell">
          <div class="tl-bm-kicker">Research benchmark</div>
          <h2 class="tl-bm-title">Measure what the system actually knows.</h2>
          <p class="tl-bm-lead">Selected cases are scored with the same investigation pipeline. Held-out cases stay separate from development cases. This is not a claim about every future manipulation.</p>
        </div>
        """
    )
    run_clicked = st.button("Run Benchmark", type="primary", key="bm_run")

    eval_data = _load_eval()
    if run_clicked:
        from eval.run_eval import evaluate_split

        with st.spinner("Running the local benchmark on the real pipeline. This can take several minutes."):
            try:
                eval_data = evaluate_split("all")
            except Exception as err:
                st.error(f"Benchmark did not finish: {err}")
                eval_data = _load_eval()

    if not eval_data:
        st.html(
            """
            <div class="tl-bm-empty">
              <strong>Evaluation not yet run</strong>
              <p>The benchmark measures verdict accuracy, coverage, false confidence, and whether development cases and held-out cases behave differently.</p>
            </div>
            """
        )
        return

    details = eval_data.get("case_details") or []
    counts = {"AUTHENTIC": 0, "MANIPULATED": 0, "COORDINATED_SYNTHETIC": 0, "INCONCLUSIVE": 0}
    for row in details:
        label = row.get("ground_truth")
        if label in counts:
            counts[label] += 1

    cases_n = int(eval_data.get("cases_evaluated") or 0)
    macro_f1 = float(eval_data.get("macro_f1") or 0)
    coverage = float(eval_data.get("coverage_rate") or 0)
    false_conf = float(eval_data.get("false_confidence_rate") or 0)
    split_label = str(eval_data.get("split") or "unknown")

    st.html(
        f"""
        <section class="tl-bm-section">
          <div class="tl-bm-label">Overall performance</div>
          <div class="tl-bm-strip">
            <div class="tl-bm-metric">
              <span>Cases</span>
              <strong data-tl-count="{cases_n}" data-tl-decimals="0">{cases_n}</strong>
            </div>
            <div class="tl-bm-metric">
              <span>Macro-F1</span>
              <strong data-tl-count="{macro_f1:.4f}" data-tl-decimals="4">{macro_f1:.4f}</strong>
            </div>
            <div class="tl-bm-metric">
              <span>Coverage</span>
              <strong data-tl-count="{coverage:.4f}" data-tl-decimals="4">{coverage:.4f}</strong>
            </div>
            <div class="tl-bm-metric">
              <span>False confidence</span>
              <strong data-tl-count="{false_conf:.4f}" data-tl-decimals="4">{false_conf:.4f}</strong>
            </div>
            <div class="tl-bm-metric">
              <span>Split</span>
              <strong>{_esc(split_label)}</strong>
            </div>
          </div>
        </section>
        """
    )

    if details:
        max_count = max(counts.values()) if any(counts.values()) else 1
        dist_rows = []
        display_names = {
            "AUTHENTIC": "AUTHENTIC",
            "MANIPULATED": "MANIPULATED",
            "COORDINATED_SYNTHETIC": "COORDINATED SYNTHETIC",
            "INCONCLUSIVE": "INCONCLUSIVE",
        }
        for name, count in counts.items():
            pct = int(round(100 * count / max(1, max_count)))
            dist_rows.append(
                f'<div class="tl-bm-dist-row is-{name.lower()}">'
                f'<div class="tl-bm-dist-name">{_esc(display_names[name])}</div>'
                f'<div class="tl-bm-dist-track"><i style="--bm-w:{pct}%"></i></div>'
                f'<div class="tl-bm-dist-n">{count}</div>'
                f"</div>"
            )
        st.html(
            f"""
            <section class="tl-bm-section">
              <div class="tl-bm-label">Verdict distribution</div>
              <div class="tl-bm-dist">{"".join(dist_rows)}</div>
            </section>
            """
        )

    per_class = eval_data.get("per_class_metrics") or {}
    if per_class:
        body = []
        for name, metrics in per_class.items():
            f1_val = float(metrics.get("f1") or 0)
            body.append(
                "<tr>"
                f'<td class="tl-bm-class">{_esc(name)}</td>'
                f"<td>{float(metrics.get('precision') or 0):.4f}</td>"
                f"<td>{float(metrics.get('recall') or 0):.4f}</td>"
                f'<td class="tl-bm-f1">{f1_val:.4f}</td>'
                f"<td>{int(metrics.get('support') or 0)}</td>"
                "</tr>"
            )
        st.html(
            f"""
            <section class="tl-bm-section">
              <div class="tl-bm-label">Category performance</div>
              <table class="tl-bm-table">
                <thead>
                  <tr>
                    <th>Class</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th>
                  </tr>
                </thead>
                <tbody>{"".join(body)}</tbody>
              </table>
            </section>
            """
        )

    dev = _split_accuracy(details, "dev")
    held = _split_accuracy(details, "held_out")
    gen_panels = []
    if dev:
        pct = int(round(100 * dev[0] / max(1, dev[1])))
        gen_panels.append(
            f'<div class="tl-bm-gen-panel">'
            f'<div class="tl-bm-gen-title">Known patterns</div>'
            f'<div class="tl-bm-gen-copy">{dev[0]} / {dev[1]} development cases matched the label.</div>'
            f'<div class="tl-bm-bar" data-width="{pct}"><i style="--bm-w:{pct}%"></i></div>'
            f"</div>"
        )
    if held:
        pct = int(round(100 * held[0] / max(1, held[1])))
        gen_panels.append(
            f'<div class="tl-bm-gen-panel">'
            f'<div class="tl-bm-gen-title">Held-out patterns</div>'
            f'<div class="tl-bm-gen-copy">{held[0]} / {held[1]} held-out cases matched the label.</div>'
            f'<div class="tl-bm-bar" data-width="{pct}"><i style="--bm-w:{pct}%"></i></div>'
            f"</div>"
        )
    if not gen_panels:
        gen_panels.append(
            '<div class="tl-bm-gen-panel tl-bm-gen-wide">'
            "<div class=\"tl-bm-gen-title\">Held-out comparison</div>"
            "<div class=\"tl-bm-gen-copy\">This result file does not include both splits. Run the full benchmark to compare them.</div>"
            "</div>"
        )

    abstain_html = ""
    inconclusive = [row for row in details if row.get("ground_truth") == "INCONCLUSIVE"]
    if inconclusive:
        correct_abstain = sum(1 for row in inconclusive if row.get("trustlayers_verdict") == "INCONCLUSIVE")
        pct = int(round(100 * correct_abstain / max(1, len(inconclusive))))
        abstain_html = (
            f'<div class="tl-bm-abstain">'
            f'<div class="tl-bm-gen-title">Abstention</div>'
            f'<div class="tl-bm-gen-copy">{correct_abstain} / {len(inconclusive)} labeled inconclusive cases stayed inconclusive.</div>'
            f'<div class="tl-bm-bar is-abstain" data-width="{pct}"><i style="--bm-w:{pct}%"></i></div>'
            f"</div>"
        )

    st.html(
        f"""
        <section class="tl-bm-section">
          <div class="tl-bm-label">Generalization</div>
          <p class="tl-bm-note">Development cases and held-out cases are counted separately when both are present in the result file.</p>
          <div class="tl-bm-gen-grid">{"".join(gen_panels)}</div>
          {abstain_html}
        </section>
        """
    )

    matrix = eval_data.get("confusion_matrix") or {}
    if matrix:
        labels = list(matrix.keys())
        max_cell = 1
        for actual in labels:
            for predicted in labels:
                max_cell = max(max_cell, int(matrix.get(actual, {}).get(predicted, 0)))
        header = "".join(
            f'<th title="{_esc(label)}">{_esc(label.replace("COORDINATED_SYNTHETIC", "SYNTHETIC"))}</th>'
            for label in labels
        )
        rows = []
        delay = 0.0
        for actual in labels:
            cells = []
            for i, predicted in enumerate(labels):
                val = int(matrix.get(actual, {}).get(predicted, 0))
                intensity = val / max_cell
                klass = "tl-bm-cell"
                if actual == predicted:
                    klass += " is-diag"
                elif val > 0:
                    klass += " is-off"
                cells.append(
                    f'<td class="{klass}" style="--bm-i:{intensity:.3f};animation-delay:{delay + i * 0.04:.2f}s">'
                    f"{val}</td>"
                )
            rows.append(
                f"<tr><th>{_esc(actual.replace('COORDINATED_SYNTHETIC', 'SYNTHETIC'))}</th>"
                f"{''.join(cells)}</tr>"
            )
            delay += 0.08
        st.html(
            f"""
            <section class="tl-bm-section">
              <div class="tl-bm-label">Confusion matrix</div>
              <p class="tl-bm-note">Rows are labels. Columns are TrustLayers verdicts.</p>
              <div class="tl-bm-matrix-wrap">
                <table class="tl-bm-matrix">
                  <tr><th>Label</th>{header}</tr>
                  {"".join(rows)}
                </table>
              </div>
            </section>
            """
        )

    ablation = eval_data.get("ablation") or {}
    if ablation:
        tl_f1 = float(ablation.get("trustlayers_macro_f1") or 0)
        base_f1 = float(ablation.get("baseline_macro_f1") or 0)
        delta = float(ablation.get("macro_f1_delta") or 0)
        scale = max(tl_f1, base_f1, 0.0001)
        tl_pct = int(round(100 * tl_f1 / scale))
        base_pct = int(round(100 * base_f1 / scale))
        delta_txt = f"+{delta:.4f}" if delta >= 0 else f"{delta:.4f}"
        st.html(
            f"""
            <section class="tl-bm-section tl-bm-section-last">
              <div class="tl-bm-label">Independent-artifact baseline</div>
              <div class="tl-bm-base-strip">
                <div class="tl-bm-metric">
                  <span>TrustLayers F1</span>
                  <strong data-tl-count="{tl_f1:.4f}" data-tl-decimals="4">{tl_f1:.4f}</strong>
                </div>
                <div class="tl-bm-metric">
                  <span>Baseline F1</span>
                  <strong data-tl-count="{base_f1:.4f}" data-tl-decimals="4">{base_f1:.4f}</strong>
                </div>
                <div class="tl-bm-metric is-delta">
                  <span>Delta</span>
                  <strong data-tl-count="{delta:.4f}" data-tl-decimals="4" data-tl-prefix="{'+' if delta >= 0 else ''}">{_esc(delta_txt)}</strong>
                </div>
              </div>
              <div class="tl-bm-compare">
                <div class="tl-bm-compare-row">
                  <span>Baseline</span>
                  <div class="tl-bm-bar is-baseline"><i style="--bm-w:{base_pct}%"></i></div>
                  <em>{base_f1:.4f}</em>
                </div>
                <div class="tl-bm-compare-row">
                  <span>TrustLayers</span>
                  <div class="tl-bm-bar"><i style="--bm-w:{tl_pct}%"></i></div>
                  <em>{tl_f1:.4f}</em>
                </div>
              </div>
            </section>
            """
        )

    components.html(
        """
        <script>
        (() => {
          const doc = window.parent.document;
          doc.documentElement.dataset.tlView = "benchmark";
          const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

          function animateCount(el) {
            const target = parseFloat(el.getAttribute("data-tl-count") || "0");
            const decimals = parseInt(el.getAttribute("data-tl-decimals") || "0", 10);
            const prefix = el.getAttribute("data-tl-prefix") || "";
            const format = (v) => prefix + (decimals ? v.toFixed(decimals) : String(Math.round(v)));
            if (reduce || !Number.isFinite(target)) {
              el.textContent = format(target);
              return;
            }
            const start = performance.now();
            const dur = 700;
            const tick = (now) => {
              const t = Math.min(1, (now - start) / dur);
              const eased = 1 - Math.pow(1 - t, 3);
              el.textContent = format(target * eased);
              if (t < 1) requestAnimationFrame(tick);
            };
            requestAnimationFrame(tick);
          }

          const run = () => {
            doc.querySelectorAll("[data-tl-count]").forEach(animateCount);
          };
          run();
          setTimeout(run, 120);
        })();
        </script>
        """,
        height=0,
    )


def main_dashboard() -> None:
    """Route Home / Investigate / Evidence / Benchmark with separated states."""
    render_header()
    pages = ("Home", "Investigate", "Evidence", "Benchmark")
    if "investigate_phase" not in st.session_state:
        st.session_state["investigate_phase"] = "workbench"

    # Migrate legacy key and apply pending navigation BEFORE the radio exists.
    if "nav_radio" not in st.session_state and st.session_state.get("page") in pages:
        st.session_state["nav_radio"] = st.session_state["page"]
    if st.session_state.get("goto") in pages:
        st.session_state["nav_radio"] = st.session_state.pop("goto")
    requested = st.query_params.get("nav")
    if requested in pages and requested != st.session_state.get("_last_nav_q"):
        st.session_state["nav_radio"] = requested
        st.session_state["_last_nav_q"] = requested
    if "nav_radio" not in st.session_state:
        st.session_state["nav_radio"] = "Home"

    page = st.radio(
        "Section",
        list(pages),
        horizontal=True,
        label_visibility="collapsed",
        key="nav_radio",
    )
    st.session_state["page"] = page
    if st.query_params.get("nav") != page:
        st.query_params["nav"] = page
        st.session_state["_last_nav_q"] = page

    # Kill leftover home cinema chrome when not on Home (keep WebGL alive during live run).
    phase_now = st.session_state.get("investigate_phase", "workbench")
    if page != "Home" and not (page == "Investigate" and (phase_now == "running" or st.session_state.get("pending_run"))):
        components.html(
            """
            <script>
            (() => {
              const doc = window.parent.document;
              doc.documentElement.dataset.tlView = "workbench";
              const uni = doc.getElementById("tl-universe");
              if (uni) uni.classList.remove("is-active", "is-live");
              doc.querySelectorAll(".tl-cap").forEach((el) => {
                el.classList.remove("is-on");
                el.style.visibility = "hidden";
                el.style.opacity = "0";
              });
              const rail = doc.getElementById("tl-rail");
              if (rail) rail.style.display = "none";
            })();
            </script>
            """,
            height=0,
        )

    if page == "Home":
        components.html(
            """
            <script>
            (() => {
              const doc = window.parent.document;
              doc.documentElement.dataset.tlView = "home";
              const rail = doc.getElementById("tl-rail");
              if (rail) rail.style.display = "";
            })();
            </script>
            """,
            height=0,
        )
        render_landing()
        return

    if page == "Evidence":
        render_evidence_page()
        return
    if page == "Benchmark":
        render_evaluation_tab()
        return

    # Investigate surface
    phase = st.session_state.get("investigate_phase", "workbench")
    result = st.session_state.get("case_result")

    if phase == "running" or st.session_state.get("pending_run"):
        render_live_investigation()
        return

    if result:
        if result.case.job_status == "completed":
            st.session_state["investigate_phase"] = "result"
            render_result_screen(result.case)
        else:
            message = result.diagnostics.get("error_message") or result.case.diagnostics.get("error_message") or "Unknown error"
            st.error(f"Investigation failed: {message}")
            if st.button("Start new case"):
                del st.session_state["case_result"]
                st.session_state["investigate_phase"] = "workbench"
                st.rerun()
        return

    st.session_state["investigate_phase"] = "workbench"
    render_upload_screen()

