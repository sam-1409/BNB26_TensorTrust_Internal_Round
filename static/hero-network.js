(() => {
  const canvas = document.getElementById("field");
  const svg = document.getElementById("net");
  const stage = document.getElementById("stage");
  if (!canvas || !svg) return;

  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const mobile = matchMedia("(max-width: 720px)").matches;
  const ctx = canvas.getContext("2d", { alpha: true });
  const dpr = Math.min(devicePixelRatio || 1, 2);

  const NODES = [
    { id: "image", label: "IMAGE", x: 0.16, y: 0.22, t: 1.0 },
    { id: "claim", label: "CLAIM", x: 0.50, y: 0.48, t: 2.4 },
    { id: "audio", label: "AUDIO", x: 0.16, y: 0.72, t: 3.4 },
    { id: "document", label: "DOCUMENT", x: 0.82, y: 0.24, t: 4.3 },
    { id: "event", label: "EVENT", x: 0.50, y: 0.86, t: 5.3 },
  ];
  const EDGES = [
    { from: "image", to: "claim", label: "SUPPORTS", t: 2.9, kind: "support" },
    { from: "audio", to: "claim", label: "MATCHES", t: 3.9, kind: "support" },
    { from: "document", to: "claim", label: "CONTRADICTS", t: 4.9, kind: "contradict" },
    { from: "claim", to: "event", label: "LINKED", t: 5.7, kind: "link" },
  ];

  let w = 0, h = 0, start = performance.now();
  let mx = 0.5, my = 0.5;
  let particles = [];
  let streams = [];
  let burst = [];
  let pulse = 0;
  let cloudPhase = 0;

  function resize() {
    const rect = stage.getBoundingClientRect();
    w = Math.max(320, rect.width);
    h = Math.max(280, rect.height);
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  }

  function nodePos(n) {
    const px = (mx - 0.5) * 14;
    const py = (my - 0.5) * 10;
    return { x: n.x * w + px, y: n.y * h + py };
  }

  function spawnField() {
    const count = reduce ? 12 : mobile ? 55 : 110;
    particles = [];
    for (let i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        r: 0.5 + Math.random() * 1.8,
        a: 0.05 + Math.random() * 0.25,
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        life: Math.random(),
      });
    }
  }

  function launchStream(toNode, delay) {
    const n = NODES.find((x) => x.id === toNode);
    if (!n) return;
    const p = nodePos(n);
    const origin = {
      x: Math.random() > 0.5 ? -20 : w + 20,
      y: Math.random() * h,
    };
    streams.push({
      x: origin.x,
      y: origin.y,
      tx: p.x,
      ty: p.y,
      t0: delay,
      done: false,
      trail: [],
    });
  }

  function particleBurst(x, y, kind) {
    const n = reduce ? 6 : 18;
    for (let i = 0; i < n; i++) {
      const ang = (Math.PI * 2 * i) / n + Math.random() * 0.4;
      const sp = 0.6 + Math.random() * 1.8;
      burst.push({
        x, y,
        vx: Math.cos(ang) * sp,
        vy: Math.sin(ang) * sp,
        life: 1,
        a: 0.7,
        green: kind !== "contradict",
        warn: kind === "contradict",
      });
    }
  }

  /* Build SVG nodes/edges once; animate via attributes */
  function buildSvg() {
    const ns = "http://www.w3.org/2000/svg";
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    const defs = document.createElementNS(ns, "defs");
    defs.innerHTML = `
      <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="2.2" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
      <radialGradient id="core" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stop-color="rgba(61,220,151,0.28)"/>
        <stop offset="100%" stop-color="rgba(61,220,151,0)"/>
      </radialGradient>
    `;
    svg.appendChild(defs);

    const core = document.createElementNS(ns, "circle");
    core.setAttribute("id", "core-glow");
    core.setAttribute("fill", "url(#core)");
    core.setAttribute("opacity", "0");
    svg.appendChild(core);

    EDGES.forEach((e, i) => {
      const path = document.createElementNS(ns, "path");
      path.setAttribute("id", `e-${i}`);
      path.setAttribute("class", `edge edge-${e.kind}`);
      path.setAttribute("fill", "none");
      path.setAttribute("stroke-width", e.kind === "contradict" ? "1.6" : "1.25");
      path.setAttribute("stroke-dasharray", "7 10");
      path.setAttribute("opacity", "0");
      path.style.filter = "url(#glow)";
      svg.appendChild(path);

      const label = document.createElementNS(ns, "text");
      label.setAttribute("id", `el-${i}`);
      label.setAttribute("class", `rel rel-${e.kind}`);
      label.setAttribute("opacity", "0");
      label.textContent = e.label;
      svg.appendChild(label);

      const bead = document.createElementNS(ns, "circle");
      bead.setAttribute("id", `eb-${i}`);
      bead.setAttribute("r", "2.4");
      bead.setAttribute("class", `bead bead-${e.kind}`);
      bead.setAttribute("opacity", "0");
      svg.appendChild(bead);
    });

    NODES.forEach((n) => {
      const g = document.createElementNS(ns, "g");
      g.setAttribute("id", `n-${n.id}`);
      g.setAttribute("opacity", "0");
      g.style.transformOrigin = "center";
      const rect = document.createElementNS(ns, "rect");
      rect.setAttribute("width", n.id === "claim" ? "108" : "96");
      rect.setAttribute("height", n.id === "claim" ? "40" : "34");
      rect.setAttribute("rx", "18");
      rect.setAttribute("class", "node");
      const text = document.createElementNS(ns, "text");
      text.setAttribute("class", "label");
      text.setAttribute("text-anchor", "middle");
      text.textContent = n.label;
      g.appendChild(rect);
      g.appendChild(text);
      svg.appendChild(g);
    });
  }

  function curve(a, b) {
    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const ox = -dy * 0.12;
    const oy = dx * 0.12;
    return `M${a.x} ${a.y} Q${mx + ox} ${my + oy} ${b.x} ${b.y}`;
  }

  function pointOnQuad(a, b, t) {
    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const ox = -dy * 0.12;
    const oy = dx * 0.12;
    const cx = mx + ox;
    const cy = my + oy;
    const u = 1 - t;
    return {
      x: u * u * a.x + 2 * u * t * cx + t * t * b.x,
      y: u * u * a.y + 2 * u * t * cy + t * t * b.y,
    };
  }

  const appeared = {};
  const edgeOn = {};

  function syncSvg(elapsed) {
    const core = document.getElementById("core-glow");
    const claim = nodePos(NODES.find((n) => n.id === "claim"));
    if (core) {
      core.setAttribute("cx", claim.x);
      core.setAttribute("cy", claim.y);
      core.setAttribute("r", 90 + Math.sin(elapsed * 0.8) * 8);
      core.setAttribute("opacity", elapsed > 2.4 ? String(0.55 + Math.sin(elapsed) * 0.08) : "0");
    }

    NODES.forEach((n) => {
      const g = document.getElementById(`n-${n.id}`);
      if (!g) return;
      const p = nodePos(n);
      const rw = n.id === "claim" ? 108 : 96;
      const rh = n.id === "claim" ? 40 : 34;
      const rect = g.querySelector("rect");
      const text = g.querySelector("text");
      rect.setAttribute("x", p.x - rw / 2);
      rect.setAttribute("y", p.y - rh / 2);
      text.setAttribute("x", p.x);
      text.setAttribute("y", p.y + 4);
      const on = elapsed >= n.t || reduce;
      if (on && !appeared[n.id]) {
        appeared[n.id] = true;
        particleBurst(p.x, p.y, "support");
        launchStream(n.id, 0);
      }
      let op = 0;
      if (reduce) op = 1;
      else if (elapsed >= n.t) op = Math.min(1, (elapsed - n.t) / 0.45);
      g.setAttribute("opacity", String(op));
      const breathe = on ? 1 + Math.sin(elapsed * 1.4 + n.x * 4) * 0.015 : 1;
      g.style.transform = `scale(${breathe})`;
    });

    EDGES.forEach((e, i) => {
      const a = nodePos(NODES.find((n) => n.id === e.from));
      const b = nodePos(NODES.find((n) => n.id === e.to));
      const path = document.getElementById(`e-${i}`);
      const label = document.getElementById(`el-${i}`);
      const bead = document.getElementById(`eb-${i}`);
      if (!path) return;
      path.setAttribute("d", curve(a, b));
      const on = elapsed >= e.t || reduce;
      if (on && !edgeOn[i]) {
        edgeOn[i] = true;
        if (e.kind === "contradict") particleBurst(b.x, b.y, "contradict");
      }
      let op = 0;
      if (reduce) op = 0.85;
      else if (elapsed >= e.t) op = Math.min(0.9, (elapsed - e.t) / 0.5);
      path.setAttribute("opacity", String(op));
      path.style.strokeDashoffset = String(-((elapsed * 28) % 140));

      const mid = pointOnQuad(a, b, 0.5);
      label.setAttribute("x", mid.x);
      label.setAttribute("y", mid.y - 8);
      label.setAttribute("opacity", String(op));

      const bt = ((elapsed * 0.22) + i * 0.2) % 1;
      const bp = pointOnQuad(a, b, bt);
      bead.setAttribute("cx", bp.x);
      bead.setAttribute("cy", bp.y);
      bead.setAttribute("opacity", String(op > 0.2 ? 0.95 : 0));
    });

    /* Cloud morph: after graph settles, soft pulse */
    if (elapsed > 6.2) {
      pulse = 0.5 + Math.sin(elapsed * 0.9) * 0.5;
      cloudPhase = (elapsed - 6.2) * 0.15;
    }
  }

  function drawCloud(elapsed) {
    if (reduce || elapsed < 0.4) return;
    const claim = nodePos(NODES.find((n) => n.id === "claim"));
    const density = mobile ? 40 : 70;
    const reveal = Math.min(1, elapsed / 6);
    for (let i = 0; i < density; i++) {
      const ang = (i / density) * Math.PI * 2 + cloudPhase;
      const rad = (38 + (i % 7) * 7) * (0.55 + reveal * 0.45);
      const wobble = Math.sin(elapsed * 1.2 + i) * 4;
      const x = claim.x + Math.cos(ang) * (rad + wobble);
      const y = claim.y + Math.sin(ang) * (rad * 0.72 + wobble * 0.5);
      const a = 0.04 + (i % 5) * 0.02 * pulse;
      ctx.beginPath();
      ctx.fillStyle = `rgba(61,220,151,${a})`;
      ctx.arc(x, y, 1.1 + (i % 3) * 0.4, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function drawParticles(dt) {
    ctx.clearRect(0, 0, w, h);
    drawCloud(dt);

    for (const p of particles) {
      p.x += p.vx;
      p.y += p.vy;
      p.life += 0.002;
      if (p.x < -10) p.x = w + 10;
      if (p.x > w + 10) p.x = -10;
      if (p.y < -10) p.y = h + 10;
      if (p.y > h + 10) p.y = -10;
      const dx = p.x - mx * w;
      const dy = p.y - my * h;
      const dist = Math.sqrt(dx * dx + dy * dy) + 1;
      if (dist < 90) {
        p.x += (dx / dist) * 0.4;
        p.y += (dy / dist) * 0.4;
      }
      ctx.beginPath();
      ctx.fillStyle = `rgba(61,220,151,${p.a})`;
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }

    streams = streams.filter((s) => {
      if (s.done) return false;
      const dx = s.tx - s.x;
      const dy = s.ty - s.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      s.x += (dx / dist) * 4.2;
      s.y += (dy / dist) * 4.2;
      s.trail.push({ x: s.x, y: s.y, a: 0.55 });
      if (s.trail.length > 14) s.trail.shift();
      s.trail.forEach((t, i) => {
        ctx.beginPath();
        ctx.fillStyle = `rgba(61,220,151,${(i / s.trail.length) * t.a})`;
        ctx.arc(t.x, t.y, 1.6, 0, Math.PI * 2);
        ctx.fill();
      });
      if (dist < 6) {
        s.done = true;
        return false;
      }
      return true;
    });

    burst = burst.filter((b) => {
      b.x += b.vx;
      b.y += b.vy;
      b.vx *= 0.96;
      b.vy *= 0.96;
      b.life -= 0.025;
      if (b.life <= 0) return false;
      ctx.beginPath();
      ctx.fillStyle = b.warn
        ? `rgba(226,91,74,${b.life * 0.7})`
        : `rgba(61,220,151,${b.life * 0.7})`;
      ctx.arc(b.x, b.y, 1.8, 0, Math.PI * 2);
      ctx.fill();
      return true;
    });

    /* Opening particle seed */
    if (dt < 1.1) {
      const x = w * 0.18 + dt * 40;
      const y = h * 0.2 + Math.sin(dt * 4) * 8;
      ctx.beginPath();
      ctx.fillStyle = `rgba(61,220,151,${0.2 + dt * 0.5})`;
      ctx.shadowColor = "#3ddc97";
      ctx.shadowBlur = 12;
      ctx.arc(x, y, 2.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  }

  let hoverId = null;
  function hitTest(x, y) {
    for (const n of NODES) {
      const p = nodePos(n);
      if (Math.abs(x - p.x) < 56 && Math.abs(y - p.y) < 24) return n.id;
    }
    return null;
  }

  function applyHover() {
    NODES.forEach((n) => {
      const g = document.getElementById(`n-${n.id}`);
      if (!g) return;
      if (!hoverId) {
        g.classList.remove("is-dim", "is-hot");
        return;
      }
      const connected = EDGES.some(
        (e) =>
          (e.from === hoverId && e.to === n.id) ||
          (e.to === hoverId && e.from === n.id) ||
          n.id === hoverId
      );
      g.classList.toggle("is-hot", n.id === hoverId);
      g.classList.toggle("is-dim", !connected);
    });
    EDGES.forEach((e, i) => {
      const path = document.getElementById(`e-${i}`);
      if (!path) return;
      const hot = hoverId && (e.from === hoverId || e.to === hoverId);
      path.classList.toggle("is-hot", !!hot);
      path.classList.toggle("is-dim", !!(hoverId && !hot));
    });
  }

  stage.addEventListener("pointermove", (e) => {
    const r = stage.getBoundingClientRect();
    mx = (e.clientX - r.left) / r.width;
    my = (e.clientY - r.top) / r.height;
    hoverId = hitTest(e.clientX - r.left, e.clientY - r.top);
    applyHover();
  });
  stage.addEventListener("pointerleave", () => {
    hoverId = null;
    applyHover();
  });

  function frame(now) {
    const elapsed = reduce ? 10 : (now - start) / 1000;
    drawParticles(elapsed);
    syncSvg(elapsed);
    requestAnimationFrame(frame);
  }

  resize();
  spawnField();
  buildSvg();
  addEventListener("resize", () => {
    resize();
    spawnField();
  });
  if (reduce) {
    syncSvg(10);
    drawParticles(10);
  } else {
    requestAnimationFrame(frame);
  }
})();
