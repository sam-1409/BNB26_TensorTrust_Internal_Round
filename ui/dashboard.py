"""Streamlit UI dashboard for TrustLayers.

Enforces:
- R-UX-01 to R-UX-10: visual and interaction rules.
- R-SEC-08: artifact-derived text is escaped before HTML render.
- R-DATA-06: processing notice is shown before the first analysis.
"""

import base64
import html
import json
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
            const motionVersion = "flow-v5";
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


def render_header() -> None:
    """Minimal brand header."""
    _inject_styles()
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
            <div class="tl-status"><i></i>{_esc(_status_label())}</div>
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
    c1, c2 = st.columns(2)
    with c1:
        st.button(
            "Start Investigation",
            type="primary",
            width="stretch",
            key="home_start",
            on_click=_go_investigate_workbench,
        )
    with c2:
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
    """Mandatory processing notice (R-DATA-06)."""
    st.info(
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
    """Investigation workbench. Functional console — homepage cinema stays off."""
    st.html('<div id="tl-view" data-view="workbench" hidden></div>')
    st.html(
        """
        <div class="tl-workbench-shell">
          <div class="tl-workbench-head">
            <div>
              <div class="tl-kicker">Investigation workbench</div>
              <h2 class="tl-statement" style="font-size:44px;margin:6px 0 0;">Add evidence</h2>
            </div>
            <div class="tl-case">CASE #TL-READY<br><span class="tl-status"><i></i>ANALYSIS READY</span></div>
          </div>
          <p class="tl-lead">Upload any evidence relevant to this investigation. TrustLayers adapts its analysis automatically. One artifact is enough. Missing modalities are not errors.</p>
        </div>
        """
    )
    cats = "".join(f'<span class="tl-cat">{_esc(name)}</span>' for name, _ in FORMAT_GROUPS)
    helpers = " · ".join(f"{name}: {formats}" for name, formats in FORMAT_GROUPS)
    st.html(f'<div class="tl-workbench-shell"><div class="tl-cats">{cats}</div><div class="tl-help">{_esc(helpers)}</div></div>')

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

    uploaded_files = st.file_uploader(
        "Add evidence",
        accept_multiple_files=True,
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
        st.html('<div class="tl-kicker">Selected evidence</div>')
        for index, name, data in visible:
            kind, fmt = _file_kind(name)
            left, right = st.columns([6, 1])
            left.html(
                f'<div class="tl-file-card"><div><b>{_esc(name)}</b>'
                f'<div class="tl-file-meta">{_esc(kind)} · {_esc(fmt)} · {len(data) / 1024:.1f} KB · Ready</div></div></div>'
            )
            if right.button("Remove", key=f"remove_upload_{index}"):
                excluded.add(name)
                st.session_state["excluded_uploads"] = sorted(excluded)
                st.rerun()

    question = st.text_area(
        "Investigation Question",
        placeholder="What do you want TrustLayers to investigate?",
        help="A claim, question, date, or background. Example: Verify whether this announcement is authentic and whether the available evidence supports the claim.",
    )
    platform_urls_input = st.text_area(
        "External Sources",
        placeholder="https://www.youtube.com/watch?v=...\nhttps://reddit.com/r/...\nhttps://example.com/article",
        help="Related posts, articles, videos, or official pages. YouTube and Reddit are retrieved live. Other links are kept with the case.",
    )
    platform_urls = [line.strip() for line in platform_urls_input.splitlines() if line.strip()]

    render_processing_notice()
    st.html(_pipeline_html())

    analyze_disabled = len(file_payloads) == 0 and len(platform_urls) == 0
    if st.button("Start Investigation", type="primary", disabled=analyze_disabled, key="workbench_start"):
        st.session_state["pending_run"] = {
            "case_id": f"case_{uuid.uuid4().hex[:10]}",
            "files": file_payloads,
            "description": question,
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


def render_result_screen(case: Case) -> None:
    """Investigation result. All figures come from the completed case."""
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
    m_pct = max(4, min(100, int(round(fusion.manip_evidence * 100))))
    a_pct = max(4, min(100, int(round(fusion.auth_support * 100))))
    reason_text = ", ".join(fusion.reason_codes) if fusion.reason_codes else "None"

    st.html(
        f"""
        <div class="tl-workbench-head">
          <div>
            <div class="tl-case">CASE #{_esc(case.id)}</div>
            <div class="tl-status"><i></i>{_esc(fusion.verdict.replace("_", " "))}</div>
          </div>
        </div>
        <div class="tl-verdict tl-verdict-{fusion.verdict.lower()} tl-reveal is-waiting tl-result-reveal">
          <div class="tl-kicker">Investigation result</div>
          <div class="tl-verdict-title" data-tl-words>{_esc(fusion.verdict.replace("_", " "))}</div>
          <p class="tl-verdict-copy">{_esc(_verdict_copy(case))}</p>
          <div class="tl-stats">
            <div class="tl-stat is-waiting"><span>Confidence</span><strong>{_esc(fusion.confidence_level.upper())}</strong></div>
            <div class="tl-stat is-waiting"><span>Artifacts</span><strong data-tl-count="{analyzed}" data-tl-decimals="0">{analyzed}</strong></div>
            <div class="tl-stat is-waiting"><span>Supporting</span><strong data-tl-count="{supports}" data-tl-decimals="0">{supports}</strong></div>
            <div class="tl-stat is-waiting"><span>Contradictions</span><strong data-tl-count="{contradictions}" data-tl-decimals="0">{contradictions}</strong></div>
            <div class="tl-stat is-waiting"><span>Sources</span><strong data-tl-count="{len(case.platform_artifacts)}" data-tl-decimals="0">{len(case.platform_artifacts)}</strong></div>
          </div>
        </div>
        """
    )
    st.caption(f"Reason codes: {reason_text}. Confidence is an ordinal level, not a probability.")

    evidence_col, graph_col, findings_col = st.columns([1, 1.25, 1])
    with evidence_col:
        st.markdown("**Evidence**")
        if not case.artifacts:
            st.html('<div class="tl-empty">No artifacts were retained.</div>')
        for art in case.artifacts:
            reliability = f"{art.reliability.score:.2f}" if art.reliability else "n/a"
            with st.expander(f"{art.display_name} · {art.modality} · {art.status}"):
                st.write(f"Reliability `{reliability}`")
                if art.transcript:
                    st.write(f"Transcript: {art.transcript}")
                    st.caption(f"Transcript confidence {art.transcript_confidence or 0.0:.2f}")
                if art.perceptual_hash:
                    st.caption(f"Perceptual hash {art.perceptual_hash}")
                if art.semantic_claims:
                    st.write("Claims")
                    for claim in art.semantic_claims:
                        st.write(f"- {claim.get('claim_text')} ({claim.get('category')})")
                entities = art.metadata.get("entities") or {}
                if entities:
                    st.write(entities)
                if art.evidence:
                    st.write("Grounded signals")
                    for item in art.evidence:
                        ref = f"{item.evidence_ref.type} {item.evidence_ref.value}"
                        st.write(f"- {item.description}")
                        st.caption(f"{item.direction} · {item.check_id} · {ref} · {item.source}")
    with graph_col:
        st.markdown("**Evidence graph**")
        mode = "Cross-modal reasoning ran." if case.cross_modal_activated else "Cross-modal reasoning stayed off. One modality was present."
        st.caption(mode)
        graph_svg, graph_html = _graph_markup(case)
        if graph_svg:
            node_count = len(case.evidence_graph.nodes) if case.evidence_graph else 0
            _graph_iframe(graph_svg, height=max(240, 48 + min(12, node_count) * 56), interactive=True)
        st.html(graph_html)
        labels = []
        if case.evidence_graph:
            labels = [f"{node.node_type}: {node.label}" for node in case.evidence_graph.nodes]
        if labels:
            selected = st.selectbox("Inspect a node", labels)
            node = case.evidence_graph.nodes[labels.index(selected)]
            st.write(node.label)
            related = [
                edge for edge in case.evidence_graph.edges
                if edge.source_node_id == node.node_id or edge.target_node_id == node.node_id
            ]
            if not related:
                st.caption("No relations were recorded for this node.")
            for edge in related:
                st.write(f"{edge.relation}: {edge.explanation or edge.target_node_id}")
                st.caption(f"{edge.method} · {edge.confidence_level}")
    with findings_col:
        st.markdown("**Why this result**")
        st.html(_why_rows(case))
        st.markdown("**What is missing**")
        if fusion.limitations or fusion.unavailable_checks:
            for item in list(fusion.limitations) + [f"Unavailable check: {name}" for name in fusion.unavailable_checks]:
                st.write(f"- {item}")
        else:
            st.write("- No specific limitations were flagged during analysis.")
    if case.evidence_graph and case.evidence_graph.contradiction_list:
        st.markdown("**Contradictions**")
        for contra in case.evidence_graph.contradiction_list:
            st.write(contra.get("explanation", ""))
            st.caption(
                f"{contra.get('conflict_type', 'semantic')} · "
                f"{contra.get('artifact_a')} / {contra.get('artifact_b')} · "
                f"{str(contra.get('confidence_level', '')).upper()}"
            )

    st.html(
        f"""
        <div class="tl-balance">
          <div class="tl-balance-card">
            <div class="tl-balance-head"><span>Manipulation evidence</span><span>{_esc(m_ordinal)}</span></div>
            <div class="tl-bar tl-bar-m"><i style="width:{m_pct}%"></i></div>
          </div>
          <div class="tl-balance-card">
            <div class="tl-balance-head"><span>Authenticity support</span><span>{_esc(a_ordinal)}</span></div>
            <div class="tl-bar tl-bar-a"><i style="width:{a_pct}%"></i></div>
          </div>
        </div>
        """
    )
    with st.expander("Internal scores"):
        st.caption("Rule-based internal scores. They are not probabilities.")
        st.write(f"Manipulation score (m): `{fusion.manip_evidence:.4f}`")
        st.write(f"Authenticity score (a): `{fusion.auth_support:.4f}`")
        st.write(f"Sufficiency: `{fusion.sufficiency:.4f}`")
        st.write(f"Checks: `{fusion.checks_completed} / {fusion.checks_applicable}`")

    if case.relations:
        st.markdown("**Relationships**")
        cards = []
        for rel in case.relations:
            explanation = f'<div class="tl-muted">{_esc(rel.explanation)}</div>' if rel.explanation else ""
            cards.append(
                f'<div class="tl-rel tl-rel-{rel.relation.lower()}">'
                f'<div class="tl-rel-title">{_esc(rel.relation)} · {_esc(rel.source_id)} / {_esc(rel.target_id)}</div>'
                f"{explanation}"
                f'<div class="tl-muted">{_esc(rel.method)} · {_esc(rel.confidence_level.upper())}</div></div>'
            )
        st.html("".join(cards))

    if case.platform_artifacts:
        st.markdown("**External sources**")
        for plat in case.platform_artifacts:
            with st.expander(f"{plat.platform}: {plat.title or plat.url}"):
                st.write(plat.url)
                if plat.upload_date:
                    st.write(f"Upload date: {plat.upload_date}")
                if plat.view_count is not None:
                    st.write(f"View count: {plat.view_count:,}")
                if plat.comments_sample:
                    st.caption(plat.comment_reliability_note)
                    for comment in plat.comments_sample:
                        st.write(f"- {comment}")

    done = ["ingest", "preprocessing", "grounding", "reasoning", "fusing"]
    if not case.cross_modal_activated and not case.relations:
        done = ["ingest", "preprocessing", "grounding", "fusing"]
    st.html('<div class="tl-kicker">Pipeline</div>' + _pipeline_html(done=done))

    report_col, delete_col, new_col = st.columns(3)
    with report_col:
        st.download_button(
            "Download HTML Report",
            data=generate_report_html(case),
            file_name=f"report_{case.id}.html",
            mime="text/html",
            type="primary",
        )
    with delete_col:
        if st.button("Delete case", type="secondary"):
            delete_case(case.id)
            st.session_state.pop("active_case_id", None)
            st.session_state.pop("case_result", None)
            st.session_state["investigate_phase"] = "workbench"
            st.success("This case was deleted.")
            st.rerun()
    with new_col:
        if st.button("New investigation"):
            st.session_state.pop("case_result", None)
            st.session_state["goto"] = "Investigate"
            st.session_state["investigate_phase"] = "workbench"
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
    """Benchmark dashboard. Numbers come only from a completed eval run."""
    st.html('<div id="tl-benchmark-jump"></div>')
    st.html(
        """
        <div class="tl-kicker">Research benchmark</div>
        <h2 class="tl-statement" style="font-size:52px;" data-tl-words>Measure what the system actually knows.</h2>
        <p class="tl-lead">Selected cases are scored with the same investigation pipeline. Held-out cases stay separate from development cases. This is not a claim about every future manipulation.</p>
        """
    )
    eval_data = _load_eval()
    if st.button("Run Benchmark", type="primary"):
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
            <div class="tl-empty">
              <strong style="color:#f4f7f5;">Evaluation not yet run</strong>
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
    st.html(
        f"""
        <div class="tl-kicker">Overall performance</div>
        <div class="tl-stats tl-bench-stats">
          <div class="tl-stat is-waiting"><span>Cases</span><strong data-tl-count="{int(eval_data.get("cases_evaluated") or 0)}" data-tl-decimals="0">{int(eval_data.get("cases_evaluated") or 0)}</strong></div>
          <div class="tl-stat is-waiting"><span>Macro-F1</span><strong data-tl-count="{float(eval_data.get("macro_f1") or 0):.4f}" data-tl-decimals="4">{float(eval_data.get("macro_f1") or 0):.4f}</strong></div>
          <div class="tl-stat is-waiting"><span>Coverage</span><strong data-tl-count="{float(eval_data.get("coverage_rate") or 0):.4f}" data-tl-decimals="4">{float(eval_data.get("coverage_rate") or 0):.4f}</strong></div>
          <div class="tl-stat is-waiting"><span>False confidence</span><strong data-tl-count="{float(eval_data.get("false_confidence_rate") or 0):.4f}" data-tl-decimals="4">{float(eval_data.get("false_confidence_rate") or 0):.4f}</strong></div>
          <div class="tl-stat is-waiting"><span>Split</span><strong>{_esc(eval_data.get("split") or "unknown")}</strong></div>
        </div>
        """
    )
    if details:
        chips = "".join(
            f'<div class="tl-stat"><span>{_esc(name.replace("_", " "))}</span><strong>{count}</strong></div>'
            for name, count in counts.items()
        )
        st.html(f'<div class="tl-kicker">Labeled cases in this run</div><div class="tl-stats">{chips}</div>')

    per_class = eval_data.get("per_class_metrics") or {}
    if per_class:
        body = []
        for name, metrics in per_class.items():
            body.append(
                "<tr>"
                f"<td>{_esc(name)}</td>"
                f"<td>{float(metrics.get('precision') or 0):.4f}</td>"
                f"<td>{float(metrics.get('recall') or 0):.4f}</td>"
                f"<td>{float(metrics.get('f1') or 0):.4f}</td>"
                f"<td>{int(metrics.get('support') or 0)}</td>"
                "</tr>"
            )
        st.markdown("**Category performance**")
        st.html(
            '<table class="tl-table"><tr><th>Class</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th></tr>'
            + "".join(body)
            + "</table>"
        )

    dev = _split_accuracy(details, "dev")
    held = _split_accuracy(details, "held_out")
    st.markdown("**Generalization**")
    st.caption("Development cases and held-out cases are counted separately when both are present in the result file.")
    gen_cards = []
    if dev:
        pct = int(round(100 * dev[0] / max(1, dev[1])))
        gen_cards.append(
            f'<div class="tl-panel"><strong>Known patterns</strong>'
            f'<span>{dev[0]} / {dev[1]} development cases matched the label.</span>'
            f'<div class="tl-bench-bar is-waiting" data-width="{pct}"><i></i></div></div>'
        )
    if held:
        pct = int(round(100 * held[0] / max(1, held[1])))
        gen_cards.append(
            f'<div class="tl-panel"><strong>Held-out patterns</strong>'
            f'<span>{held[0]} / {held[1]} held-out cases matched the label.</span>'
            f'<div class="tl-bench-bar is-waiting" data-width="{pct}"><i></i></div></div>'
        )
    if not gen_cards:
        gen_cards.append('<div class="tl-panel"><strong>Held-out comparison</strong><span>This result file does not include both splits. Run the full benchmark to compare them.</span></div>')
    inconclusive = [row for row in details if row.get("ground_truth") == "INCONCLUSIVE"]
    if inconclusive:
        correct_abstain = sum(1 for row in inconclusive if row.get("trustlayers_verdict") == "INCONCLUSIVE")
        pct = int(round(100 * correct_abstain / max(1, len(inconclusive))))
        gen_cards.append(
            f'<div class="tl-panel"><strong>Abstention</strong>'
            f'<span>{correct_abstain} / {len(inconclusive)} labeled inconclusive cases stayed inconclusive.</span>'
            f'<div class="tl-bench-bar is-waiting" data-width="{pct}"><i></i></div></div>'
        )
    st.html(f'<div class="tl-grid-2">{"".join(gen_cards)}</div>')

    matrix = eval_data.get("confusion_matrix") or {}
    if matrix:
        labels = list(matrix.keys())
        header = "".join(f"<th>{_esc(label)}</th>" for label in labels)
        rows = []
        delay = 0
        for actual in labels:
            cells = "".join(
                f'<td class="tl-matrix-cell" style="animation-delay:{delay + i * 0.04:.2f}s">{int(matrix.get(actual, {}).get(predicted, 0))}</td>'
                for i, predicted in enumerate(labels)
            )
            rows.append(f"<tr><th>{_esc(actual)}</th>{cells}</tr>")
            delay += 0.08
        st.markdown("**Confusion matrix**")
        st.caption("Rows are labels. Columns are TrustLayers verdicts.")
        st.html(f'<table class="tl-table tl-matrix"><tr><th>Label</th>{header}</tr>{"".join(rows)}</table>')

    ablation = eval_data.get("ablation") or {}
    if ablation:
        st.markdown("**Independent-artifact baseline**")
        st.html(
            f"""
            <div class="tl-stats">
              <div class="tl-stat"><span>TrustLayers F1</span><strong>{float(ablation.get("trustlayers_macro_f1") or 0):.4f}</strong></div>
              <div class="tl-stat"><span>Baseline F1</span><strong>{float(ablation.get("baseline_macro_f1") or 0):.4f}</strong></div>
              <div class="tl-stat"><span>Delta</span><strong>{float(ablation.get("macro_f1_delta") or 0):.4f}</strong></div>
            </div>
            """
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

