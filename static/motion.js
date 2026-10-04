(() => {
  const DOC = document;
  const WIN = window;
  if (WIN.__tlMotionBooted && WIN.__tlMotionVersion === "flow-v5") {
    WIN.__tlCinemaRefresh && WIN.__tlCinemaRefresh();
    return;
  }
  WIN.__tlMotionBooted = true;
  WIN.__tlMotionVersion = "flow-v5";

  function loadScript(src, id) {
    return new Promise((resolve, reject) => {
      const existing = DOC.getElementById(id);
      if (existing) {
        resolve();
        return;
      }
      const s = DOC.createElement("script");
      s.id = id;
      s.src = src;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = reject;
      DOC.head.appendChild(s);
    });
  }

  function scrollRoot() {
    return (
      DOC.querySelector('[data-testid="stMain"]') ||
      DOC.querySelector("section.stMain") ||
      DOC.querySelector("section.main") ||
      DOC.scrollingElement ||
      DOC.documentElement
    );
  }

  function ensureRail() {
    if (DOC.getElementById("tl-rail")) return;
    const rail = DOC.createElement("nav");
    rail.id = "tl-rail";
    rail.setAttribute("aria-label", "Investigation progress");
    rail.innerHTML = [
      ["0.00", "01", "DISCOVER"],
      ["0.18", "02", "CONNECT"],
      ["0.38", "03", "EXTRACT"],
      ["0.58", "04", "VERIFY"],
      ["0.82", "05", "DECIDE"],
    ]
      .map(
        ([p, num, label]) =>
          `<button type="button" class="tl-rail-item" data-p="${p}"><span>${num}</span><em>${label}</em></button>`
      )
      .join("");
    DOC.body.appendChild(rail);
    rail.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-p]");
      if (!btn) return;
      const track = DOC.getElementById("tl-cinema-track");
      const root = scrollRoot();
      if (!track || !root) return;
      const p = parseFloat(btn.dataset.p || "0");
      const top = track.offsetTop + (track.offsetHeight - root.clientHeight) * p;
      root.scrollTo({ top, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    });
  }

  function syncRail() {
    const track = DOC.getElementById("tl-cinema-track");
    const rail = DOC.getElementById("tl-rail");
    if (!track || !rail) return;
    const root = scrollRoot();
    const rootRect = root.getBoundingClientRect();
    const rect = track.getBoundingClientRect();
    const total = track.offsetHeight - (root.clientHeight || innerHeight);
    const p = total <= 0 ? 0 : Math.min(1, Math.max(0, (rootRect.top - rect.top) / total));
    const items = [...rail.querySelectorAll(".tl-rail-item")];
    let active = items[0];
    items.forEach((btn) => {
      if (p >= parseFloat(btn.dataset.p || "0")) active = btn;
    });
    items.forEach((btn) => btn.classList.toggle("is-on", btn === active));
  }

  function pageVeil() {
    const page =
      (DOC.querySelector('div[data-testid="stRadio"] [aria-checked="true"] p') || {}).textContent || "";
    const prev = sessionStorage.getItem("tl-page");
    if (prev && prev !== page) {
      let overlay = DOC.getElementById("tl-page-veil");
      if (!overlay) {
        overlay = DOC.createElement("div");
        overlay.id = "tl-page-veil";
        DOC.body.appendChild(overlay);
      }
      overlay.classList.add("is-on");
      requestAnimationFrame(() => {
        overlay.classList.add("is-out");
        setTimeout(() => overlay.classList.remove("is-on", "is-out"), 700);
      });
    }
    if (page) sessionStorage.setItem("tl-page", page);
  }

  function watchPipeline() {
    const active = DOC.querySelector(".tl-pipeline.is-live .tl-step.is-on");
    if (!active || !WIN.__tlCinemaSetMode) return;
    const stage = active.getAttribute("data-stage");
    if (stage === "ingest") WIN.__tlCinemaSetMode("ingest");
    else if (stage === "preprocessing") WIN.__tlCinemaSetMode("extract");
    else if (stage === "grounding" || stage === "reasoning") WIN.__tlCinemaSetMode("graph");
    else if (stage === "platform") WIN.__tlCinemaSetMode("contradict");
    else if (stage === "fusing" || stage === "report") WIN.__tlCinemaSetMode("fuse");
  }

  function refresh() {
    ensureRail();
    bindMainScroll();
    syncRail();
    pageVeil();
    watchPipeline();
    WIN.__tlCinemaRefresh && WIN.__tlCinemaRefresh();
  }

  WIN.__tlMotionRefresh = refresh;

  addEventListener("scroll", syncRail, { passive: true });
  function bindMainScroll() {
    const root = scrollRoot();
    if (!root || root.__tlMotionScrollBound) return;
    root.__tlMotionScrollBound = true;
    root.addEventListener("scroll", syncRail, { passive: true });
  }
  const mo = new MutationObserver(() => {
    clearTimeout(WIN.__tlMoT);
    WIN.__tlMoT = setTimeout(refresh, 120);
  });
  mo.observe(DOC.body, { childList: true, subtree: true });

  // Cinematic payload is injected by Streamlit as #tl-cinema-src text; execute after Three loads.
  async function boot() {
    try {
      await loadScript("https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js", "tl-three");
    } catch (e) {
      console.warn("Three.js failed to load", e);
      return;
    }
    const src = DOC.getElementById("tl-cinema-src");
    if (src && !DOC.getElementById("tl-cinema-engine")) {
      const eng = DOC.createElement("script");
      eng.id = "tl-cinema-engine";
      eng.textContent = src.textContent;
      DOC.body.appendChild(eng);
    }
    refresh();
  }

  boot();
})();
