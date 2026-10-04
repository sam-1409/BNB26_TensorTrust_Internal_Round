(() => {
  const canvas = document.getElementById("sig");
  const stage = document.getElementById("stage");
  if (!canvas || !stage) return;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ctx = canvas.getContext("2d", { alpha: true });
  const dpr = Math.min(devicePixelRatio || 1, 2);
  let w = 0, h = 0, t0 = performance.now();

  const streams = [
    { label: "IMAGE", color: "61,220,151", angle: -2.4 },
    { label: "AUDIO", color: "61,220,151", angle: -0.7 },
    { label: "DOCUMENT", color: "61,220,151", angle: 0.5 },
    { label: "TEXT", color: "245,248,246", angle: 2.1 },
  ];

  function resize() {
    const r = stage.getBoundingClientRect();
    w = Math.max(300, r.width);
    h = Math.max(260, r.height);
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function draw(now) {
    const t = (now - t0) / 1000;
    ctx.clearRect(0, 0, w, h);
    const cx = w * 0.5;
    const cy = h * 0.52;
    const converge = Math.min(1, Math.max(0, (t - 0.4) / 2.2));

    // soft core
    const g = ctx.createRadialGradient(cx, cy, 4, cx, cy, 90);
    g.addColorStop(0, `rgba(61,220,151,${0.2 + converge * 0.2})`);
    g.addColorStop(1, "rgba(61,220,151,0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(cx, cy, 90, 0, Math.PI * 2);
    ctx.fill();

    streams.forEach((s, i) => {
      const dist = (1 - converge) * (110 + i * 18) + 28;
      const ang = s.angle + Math.sin(t * 0.6 + i) * 0.05;
      const x = cx + Math.cos(ang) * dist;
      const y = cy + Math.sin(ang) * dist * 0.75;

      // particle stream
      for (let p = 0; p < 18; p++) {
        const u = p / 18;
        const px = x + (cx - x) * u + Math.sin(t * 2 + p) * 2;
        const py = y + (cy - y) * u + Math.cos(t * 1.6 + p) * 2;
        ctx.beginPath();
        ctx.fillStyle = `rgba(${s.color},${0.08 + u * 0.35})`;
        ctx.arc(px, py, 1.2 + u, 0, Math.PI * 2);
        ctx.fill();
      }

      // node chip
      ctx.fillStyle = "rgba(16,22,20,0.92)";
      ctx.strokeStyle = `rgba(${s.color},0.7)`;
      ctx.lineWidth = 1;
      roundRect(x - 42, y - 14, 84, 28, 14);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#f4f7f5";
      ctx.font = "700 10px Plus Jakarta Sans, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(s.label, x, y);

      // relation after converge
      if (converge > 0.55) {
        const kind = i === 2 ? "CONTRADICTS" : i === 3 ? "LINKED" : "SUPPORTS";
        const col = i === 2 ? "226,91,74" : "61,220,151";
        ctx.beginPath();
        ctx.strokeStyle = `rgba(${col},${(converge - 0.55) * 1.5})`;
        ctx.setLineDash([5, 7]);
        ctx.lineDashOffset = -t * 24;
        ctx.moveTo(x, y);
        ctx.quadraticCurveTo((x + cx) / 2, (y + cy) / 2 - 20, cx, cy);
        ctx.stroke();
        ctx.setLineDash([]);
        if (converge > 0.75) {
          ctx.fillStyle = `rgba(${col},0.9)`;
          ctx.font = "700 8px Plus Jakarta Sans, sans-serif";
          ctx.fillText(kind, (x + cx) / 2, (y + cy) / 2 - 18);
        }
      }
    });

    // claim / verdict core
    const verdictT = Math.max(0, t - 3.2);
    const labels = ["CLAIM", "REASONING", "TRUST"];
    const label = labels[Math.min(labels.length - 1, Math.floor(verdictT / 1.1))] || "CLAIM";
    ctx.fillStyle = "rgba(16,22,20,0.95)";
    ctx.strokeStyle = "rgba(61,220,151,0.85)";
    roundRect(cx - 54, cy - 18, 108, 36, 18);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#3ddc97";
    ctx.font = "700 11px Plus Jakarta Sans, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, cx, cy);

    if (!reduce) requestAnimationFrame(draw);
  }

  function roundRect(x, y, rw, rh, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + rw, y, x + rw, y + rh, r);
    ctx.arcTo(x + rw, y + rh, x, y + rh, r);
    ctx.arcTo(x, y + rh, x, y, r);
    ctx.arcTo(x, y, x + rw, y, r);
    ctx.closePath();
  }

  resize();
  addEventListener("resize", resize);
  if (reduce) {
    t0 = performance.now() - 5000;
    draw(performance.now());
  } else {
    requestAnimationFrame(draw);
  }
})();
