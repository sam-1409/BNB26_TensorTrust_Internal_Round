(() => {
  const WIN = window;
  const DOC = document;
  if (WIN.__tlCinemaBooted) {
    WIN.__tlCinemaRefresh && WIN.__tlCinemaRefresh();
    return;
  }
  WIN.__tlCinemaBooted = true;

  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const mobile = matchMedia("(max-width: 960px)").matches;
  const tablet = matchMedia("(max-width: 1200px)").matches;

  const COUNT = reduce ? 400 : mobile ? 1400 : tablet ? 2800 : 5200;
  const GREEN = new THREE.Color(0x3ddc97);
  const WARN = new THREE.Color(0xe25b4a);
  const AMBER = new THREE.Color(0xe2b657);
  const INK = new THREE.Color(0xf4f7f5);
  const MUTED = new THREE.Color(0x6f7a73);

  let renderer, scene, camera, points, positions, colors, velocities, targets, roles;
  let clock, raf = 0, scrollP = 0, targetP = 0;
  let scanMesh, artifactGroup, linkGroup, labelSprites = [];
  let ready = false;
  let mx = 0, my = 0;
  let storyPlaying = false;
  let storyStart = 0;
  let storyDuration = 10000;
  let storyFrom = 0.1;
  let storyTo = 0.99;
  let storyCaptions = [];

  function hash01(i) {
    const x = Math.sin(i * 127.1 + 311.7) * 43758.5453;
    return x - Math.floor(x);
  }

  const NODES = {
    image: { x: -2.35, y: 0.75, z: 0.2 },
    audio: { x: -2.2, y: -1.15, z: -0.3 },
    document: { x: 2.45, y: 0.95, z: 0.1 },
    video: { x: 2.3, y: -1.05, z: -0.2 },
    claim: { x: 0, y: 0.05, z: 0.6 },
    event: { x: 0.2, y: -1.75, z: 0.1 },
    person: { x: -0.9, y: 1.35, z: -0.4 },
    source: { x: 1.1, y: 1.4, z: -0.5 },
  };

  function ensureHost() {
    let host = DOC.getElementById("tl-universe");
    if (!host) {
      host = DOC.createElement("div");
      host.id = "tl-universe";
      host.setAttribute("aria-hidden", "true");
      DOC.body.appendChild(host);
    }
    let canvas = host.querySelector("canvas");
    if (!canvas) {
      canvas = DOC.createElement("canvas");
      host.appendChild(canvas);
    }
    return { host, canvas };
  }

  function makeLabel(text, color) {
    const c = DOC.createElement("canvas");
    c.width = 512;
    c.height = 128;
    const ctx = c.getContext("2d");
    ctx.clearRect(0, 0, 512, 128);
    ctx.font = "700 42px Plus Jakarta Sans, sans-serif";
    ctx.fillStyle = color || "#f4f7f5";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.shadowColor = "rgba(0,0,0,0.65)";
    ctx.shadowBlur = 12;
    ctx.fillText(text, 256, 64);
    const tex = new THREE.CanvasTexture(c);
    tex.needsUpdate = true;
    const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false });
    const spr = new THREE.Sprite(mat);
    spr.scale.set(1.6, 0.4, 1);
    spr.userData.text = text;
    return spr;
  }

  function init() {
    if (typeof THREE === "undefined") return;
    const { canvas } = ensureHost();
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, mobile ? 1.25 : 1.75));
    renderer.setClearColor(0x000000, 0);
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(42, 1, 0.1, 80);
    camera.position.set(0, 0.2, 8.5);
    clock = new THREE.Clock();

    const geo = new THREE.BufferGeometry();
    positions = new Float32Array(COUNT * 3);
    colors = new Float32Array(COUNT * 3);
    velocities = new Float32Array(COUNT * 3);
    targets = new Float32Array(COUNT * 3);
    roles = new Uint8Array(COUNT);

    for (let i = 0; i < COUNT; i++) {
      const i3 = i * 3;
      const r = Math.pow(Math.random(), 0.55) * 1.35;
      const th = Math.random() * Math.PI * 2;
      const ph = Math.acos(2 * Math.random() - 1);
      positions[i3] = r * Math.sin(ph) * Math.cos(th);
      positions[i3 + 1] = r * Math.sin(ph) * Math.sin(th) * 0.85;
      positions[i3 + 2] = r * Math.cos(ph);
      targets[i3] = positions[i3];
      targets[i3 + 1] = positions[i3 + 1];
      targets[i3 + 2] = positions[i3 + 2];
      velocities[i3] = (Math.random() - 0.5) * 0.01;
      velocities[i3 + 1] = (Math.random() - 0.5) * 0.01;
      velocities[i3 + 2] = (Math.random() - 0.5) * 0.01;
      const c = Math.random() > 0.18 ? GREEN : INK;
      const a = 0.35 + Math.random() * 0.65;
      colors[i3] = c.r * a;
      colors[i3 + 1] = c.g * a;
      colors[i3 + 2] = c.b * a;
      roles[i] = 0; // cloud
    }
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    const mat = new THREE.PointsMaterial({
      size: mobile ? 0.035 : 0.028,
      vertexColors: true,
      transparent: true,
      opacity: 0.92,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
    });
    points = new THREE.Points(geo, mat);
    scene.add(points);

    // volumetric-ish core glow
    const glowGeo = new THREE.SphereGeometry(1.55, 32, 32);
    const glowMat = new THREE.MeshBasicMaterial({
      color: 0x3ddc97,
      transparent: true,
      opacity: 0.045,
      depthWrite: false,
    });
    const glow = new THREE.Mesh(glowGeo, glowMat);
    glow.name = "coreGlow";
    scene.add(glow);

    // scan plane
    const scanGeo = new THREE.PlaneGeometry(3.2, 0.04);
    const scanMat = new THREE.MeshBasicMaterial({
      color: 0x3ddc97,
      transparent: true,
      opacity: 0,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    scanMesh = new THREE.Mesh(scanGeo, scanMat);
    scanMesh.position.set(0, 0, 1.2);
    scene.add(scanMesh);

    artifactGroup = new THREE.Group();
    scene.add(artifactGroup);
    linkGroup = new THREE.Group();
    scene.add(linkGroup);

    // soft ambient fill via large dark particles far away
    const fog = new THREE.FogExp2(0x050706, 0.035);
    scene.fog = fog;

    resize();
    ready = true;
    if (!reduce) raf = requestAnimationFrame(tick);
    else renderOnce(0.12);
  }

  function clearGroup(g) {
    while (g.children.length) {
      const ch = g.children.pop();
      if (ch.geometry) ch.geometry.dispose();
      if (ch.material) {
        if (ch.material.map) ch.material.map.dispose();
        ch.material.dispose();
      }
    }
  }

  function boxArtifact(w, h, d, color, opacity) {
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(w, h, d),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: opacity ?? 0.55,
        wireframe: false,
      })
    );
    const wire = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(w, h, d)),
      new THREE.LineBasicMaterial({ color: 0x3ddc97, transparent: true, opacity: 0.75 })
    );
    const g = new THREE.Group();
    g.add(mesh);
    g.add(wire);
    return g;
  }

  function waveformOrb() {
    const g = new THREE.Group();
    const core = new THREE.Mesh(
      new THREE.SphereGeometry(0.28, 24, 24),
      new THREE.MeshBasicMaterial({ color: 0x3ddc97, transparent: true, opacity: 0.25 })
    );
    g.add(core);
    for (let i = 0; i < 8; i++) {
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(0.22 + i * 0.05, 0.008, 8, 48),
        new THREE.MeshBasicMaterial({ color: 0x3ddc97, transparent: true, opacity: 0.35 - i * 0.03 })
      );
      ring.rotation.x = Math.PI / 2;
      ring.userData.spin = 0.4 + i * 0.1;
      g.add(ring);
    }
    return g;
  }

  function docSheets() {
    const g = new THREE.Group();
    for (let i = 0; i < 3; i++) {
      const sheet = boxArtifact(0.7, 0.9, 0.02, 0x101614, 0.7);
      sheet.position.set(i * 0.08, i * 0.05, i * 0.04);
      sheet.rotation.z = (i - 1) * 0.08;
      g.add(sheet);
    }
    return g;
  }

  function videoStrip() {
    const g = new THREE.Group();
    for (let i = 0; i < 5; i++) {
      const f = boxArtifact(0.42, 0.28, 0.02, 0x0c1210, 0.65);
      f.position.set((i - 2) * 0.32, Math.sin(i) * 0.05, 0);
      g.add(f);
    }
    return g;
  }

  function imagePlane() {
    return boxArtifact(1.1, 0.78, 0.04, 0x0c1210, 0.7);
  }

  function addLink(a, b, color, dash) {
    const pts = [];
    const mid = new THREE.Vector3().addVectors(a, b).multiplyScalar(0.5);
    mid.z += 0.4 + Math.random() * 0.3;
    mid.y += (Math.random() - 0.5) * 0.3;
    const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
    for (let i = 0; i <= 24; i++) pts.push(curve.getPoint(i / 24));
    const geo = new THREE.BufferGeometry().setFromPoints(pts);
    const mat = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: dash ? 0.35 : 0.7,
      blending: THREE.AdditiveBlending,
    });
    const line = new THREE.Line(geo, mat);
    line.userData.kind = dash ? "warn" : "ok";
    linkGroup.add(line);
    return line;
  }

  function setParticleTarget(i, x, y, z, role, color) {
    const i3 = i * 3;
    targets[i3] = x;
    targets[i3 + 1] = y;
    targets[i3 + 2] = z;
    roles[i] = role;
    if (color) {
      colors[i3] = color.r;
      colors[i3 + 1] = color.g;
      colors[i3 + 2] = color.b;
    }
  }

  function cloudFormation(t, radius, center) {
    const cx = center?.x || 0, cy = center?.y || 0, cz = center?.z || 0;
    for (let i = 0; i < COUNT; i++) {
      const seed = i * 0.618;
      const th = seed * Math.PI * 2 + t * 0.15;
      const ph = ((i * 1.7) % 100) / 100 * Math.PI;
      const r = radius * (0.35 + (i % 17) / 17 * 0.75);
      setParticleTarget(
        i,
        cx + r * Math.sin(ph) * Math.cos(th),
        cy + r * Math.sin(ph) * Math.sin(th) * 0.8,
        cz + r * Math.cos(ph) * 0.9,
        0,
        hash01(i) > 0.2 ? GREEN : INK
      );
    }
  }

  function scatterToNodes(nodeKeys, share) {
    const n = nodeKeys.length;
    const per = Math.floor(COUNT * share / n);
    let idx = 0;
    for (let k = 0; k < n; k++) {
      const node = NODES[nodeKeys[k]];
      for (let j = 0; j < per && idx < COUNT; j++, idx++) {
        const jitter = 0.18;
        setParticleTarget(
          idx,
          node.x + (hash01(idx) - 0.5) * jitter,
          node.y + (hash01(idx + 17) - 0.5) * jitter,
          node.z + (hash01(idx + 31) - 0.5) * jitter,
          1 + k,
          GREEN
        );
      }
    }
    for (; idx < COUNT; idx++) {
      const r = 2.8 + hash01(idx + 3) * 2.5;
      const th = hash01(idx + 9) * Math.PI * 2;
      setParticleTarget(
        idx,
        Math.cos(th) * r,
        (hash01(idx + 21) - 0.5) * 2.2,
        Math.sin(th) * r * 0.4,
        9,
        MUTED
      );
    }
  }

  function streamBetween(aKey, bKey, start, end, color) {
    const a = NODES[aKey], b = NODES[bKey];
    for (let i = start; i < end && i < COUNT; i++) {
      const u = (i - start) / Math.max(1, end - start);
      setParticleTarget(
        i,
        a.x + (b.x - a.x) * u + Math.sin(u * 12) * 0.05,
        a.y + (b.y - a.y) * u + Math.cos(u * 10) * 0.04,
        a.z + (b.z - a.z) * u + 0.15,
        5,
        color || GREEN
      );
    }
  }

  function rebuildArtifacts(mode, localT) {
    clearGroup(artifactGroup);
    clearGroup(linkGroup);
    labelSprites.forEach((s) => scene.remove(s));
    labelSprites = [];

    function place(obj, key, label, scale) {
      const n = NODES[key];
      obj.position.set(n.x, n.y, n.z);
      obj.scale.setScalar(scale || 1);
      obj.rotation.y = localT * 0.2;
      artifactGroup.add(obj);
      if (label) {
        const spr = makeLabel(label);
        spr.position.set(n.x, n.y + 0.55, n.z);
        spr.material.opacity = 0.9;
        scene.add(spr);
        labelSprites.push(spr);
      }
    }

    if (mode === "hero" || mode === "graph" || mode === "contradict" || mode === "verdict") {
      place(imagePlane(), "image", "IMAGE", 0.85);
      place(waveformOrb(), "audio", "AUDIO", 1);
      place(docSheets(), "document", "DOCUMENT", 0.75);
      place(boxArtifact(0.9, 0.42, 0.08, 0x101614, 0.75), "claim", "CLAIM", 1);
      place(boxArtifact(0.7, 0.32, 0.06, 0x101614, 0.6), "event", "EVENT", 1);
      addLink(new THREE.Vector3().copy(NODES.image), new THREE.Vector3().copy(NODES.claim), 0x3ddc97);
      addLink(new THREE.Vector3().copy(NODES.audio), new THREE.Vector3().copy(NODES.claim), 0x3ddc97);
      if (mode === "contradict" || mode === "verdict") {
        addLink(new THREE.Vector3().copy(NODES.document), new THREE.Vector3().copy(NODES.claim), 0xe25b4a, true);
      } else {
        addLink(new THREE.Vector3().copy(NODES.document), new THREE.Vector3().copy(NODES.claim), 0x3ddc97);
      }
      addLink(new THREE.Vector3().copy(NODES.claim), new THREE.Vector3().copy(NODES.event), 0x8f9a93);
    } else if (mode === "single") {
      place(imagePlane(), "claim", null, 1.6);
    } else if (mode === "shatter" || mode === "multi") {
      place(imagePlane(), "image", "IMAGE", 0.9);
      place(waveformOrb(), "audio", "AUDIO", 1);
      place(docSheets(), "document", "DOCUMENT", 0.8);
      if (mode === "multi") {
        place(videoStrip(), "video", "VIDEO", 0.9);
        place(boxArtifact(0.95, 0.4, 0.08, 0x101614, 0.8), "claim", "EVIDENCE", 1);
        addLink(new THREE.Vector3().copy(NODES.image), new THREE.Vector3().copy(NODES.claim), 0x3ddc97);
        addLink(new THREE.Vector3().copy(NODES.audio), new THREE.Vector3().copy(NODES.claim), 0x3ddc97);
        addLink(new THREE.Vector3().copy(NODES.document), new THREE.Vector3().copy(NODES.claim), 0x3ddc97);
        addLink(new THREE.Vector3().copy(NODES.video), new THREE.Vector3().copy(NODES.claim), 0x3ddc97);
      }
    } else if (mode === "adaptive1") {
      place(imagePlane(), "claim", "IMAGE", 1.3);
    } else if (mode === "adaptive2") {
      place(imagePlane(), "image", "IMAGE", 0.95);
      place(docSheets(), "document", "TEXT", 0.75);
      addLink(new THREE.Vector3().copy(NODES.image), new THREE.Vector3().copy(NODES.document), 0x3ddc97);
    } else if (mode === "adaptive3") {
      place(videoStrip(), "claim", "VIDEO", 1.1);
      place(imagePlane(), "image", "FRAMES", 0.55);
      place(waveformOrb(), "audio", "AUDIO", 0.7);
      place(docSheets(), "document", "TEXT", 0.55);
    } else if (mode === "scan") {
      place(imagePlane(), "claim", null, 1.7);
    } else if (mode === "coord") {
      place(imagePlane(), "image", "IMAGE", 0.7);
      place(waveformOrb(), "audio", "AUDIO", 0.8);
      place(docSheets(), "document", "DOCUMENT", 0.65);
      place(videoStrip(), "video", "VIDEO", 0.7);
      place(boxArtifact(0.55, 0.28, 0.05, 0x101614, 0.7), "person", "PERSON", 1);
      place(boxArtifact(0.55, 0.28, 0.05, 0x101614, 0.7), "event", "EVENT", 1);
      place(boxArtifact(0.7, 0.32, 0.06, 0x101614, 0.75), "claim", "CLAIM", 1);
      place(boxArtifact(0.55, 0.28, 0.05, 0x101614, 0.65), "source", "SOURCE", 1);
      ["image", "audio", "document", "video"].forEach((k) => {
        addLink(new THREE.Vector3().copy(NODES[k]), new THREE.Vector3().copy(NODES.person), 0xe2b657);
        addLink(new THREE.Vector3().copy(NODES[k]), new THREE.Vector3().copy(NODES.claim), 0xe2b657);
      });
      addLink(new THREE.Vector3().copy(NODES.person), new THREE.Vector3().copy(NODES.event), 0xe2b657);
      addLink(new THREE.Vector3().copy(NODES.event), new THREE.Vector3().copy(NODES.claim), 0xe25b4a, true);
    } else if (mode === "uncertain") {
      place(imagePlane(), "image", "IMAGE", 0.85);
      place(boxArtifact(0.85, 0.38, 0.07, 0x101614, 0.45), "claim", "CLAIM", 1);
      // missing nodes implied by empty space
    }
  }

  let lastMode = "";
  function applyScene(p, t) {
    // p = scroll 0..1
    let mode = "hero";
    let camZ = 8.5, camY = 0.2, camX = 0, lookY = 0;
    let glowOp = 0.045, scanOp = 0, scanY = 0;
    let massR = 1.35;

    if (p < 0.08) {
      mode = "hero";
      const lp = p / 0.08;
      cloudFormation(t, 1.2 + lp * 0.3, { x: 0, y: 0, z: 0 });
      // gradually stream some particles toward nodes
      if (lp > 0.25) streamBetween("image", "claim", 0, Math.floor(COUNT * 0.08 * lp), GREEN);
      if (lp > 0.45) streamBetween("audio", "claim", Math.floor(COUNT * 0.1), Math.floor(COUNT * 0.18), GREEN);
      if (lp > 0.65) streamBetween("document", "claim", Math.floor(COUNT * 0.2), Math.floor(COUNT * 0.28), WARN);
      camZ = 9.2 - lp * 1.2;
      camY = 0.35 - lp * 0.2;
    } else if (p < 0.18) {
      const lp = (p - 0.08) / 0.1;
      mode = lp < 0.35 ? "single" : lp < 0.7 ? "shatter" : "multi";
      if (lp < 0.35) {
        cloudFormation(t, 0.4 + lp, { x: 0, y: 0.1, z: 0 });
        // concentrate on center artifact
        for (let i = 0; i < COUNT * 0.45; i++) {
          setParticleTarget(
            i,
            (hash01(i) - 0.5) * 1.2,
            (hash01(i + 5) - 0.5) * 0.9,
            (hash01(i + 11) - 0.5) * 0.2,
            2,
            GREEN
          );
        }
      } else if (lp < 0.7) {
        // explode outward
        for (let i = 0; i < COUNT; i++) {
          const th = (i / COUNT) * Math.PI * 2;
          const r = 0.5 + (lp - 0.35) / 0.35 * (1.5 + (i % 9) * 0.12);
          setParticleTarget(
            i,
            Math.cos(th) * r,
            Math.sin(th) * r * 0.7,
            (hash01(i + 7) - 0.5) * 0.6,
            3,
            GREEN
          );
        }
      } else {
        scatterToNodes(["image", "audio", "document"], 0.55);
      }
      camZ = 8.0 - lp * 0.6;
      camX = Math.sin(lp * Math.PI) * 0.8;
    } else if (p < 0.28) {
      mode = "multi";
      const lp = (p - 0.18) / 0.1;
      scatterToNodes(["image", "audio", "document", "video", "claim"], 0.7);
      streamBetween("image", "claim", 0, Math.floor(COUNT * 0.1), GREEN);
      streamBetween("audio", "claim", Math.floor(COUNT * 0.1), Math.floor(COUNT * 0.2), GREEN);
      streamBetween("document", "claim", Math.floor(COUNT * 0.2), Math.floor(COUNT * 0.3), GREEN);
      streamBetween("video", "claim", Math.floor(COUNT * 0.3), Math.floor(COUNT * 0.4), GREEN);
      camZ = 7.6 - lp * 0.5;
      glowOp = 0.06 + lp * 0.04;
    } else if (p < 0.38) {
      const lp = (p - 0.28) / 0.1;
      mode = lp < 0.33 ? "adaptive1" : lp < 0.66 ? "adaptive2" : "adaptive3";
      if (mode === "adaptive1") cloudFormation(t, 0.9, NODES.claim);
      else if (mode === "adaptive2") scatterToNodes(["image", "document"], 0.5);
      else scatterToNodes(["image", "audio", "document", "claim"], 0.65);
      camZ = 7.4;
      camY = 0.1 + Math.sin(lp * Math.PI) * 0.3;
    } else if (p < 0.48) {
      mode = "scan";
      const lp = (p - 0.38) / 0.1;
      cloudFormation(t * 0.5, 0.55, NODES.claim);
      // particles peel off into signal bands
      const bands = [
        { y: 0.9, c: GREEN },
        { y: 0.45, c: INK },
        { y: 0.0, c: GREEN },
        { y: -0.45, c: AMBER },
        { y: -0.9, c: MUTED },
      ];
      const bandN = Math.floor(COUNT * 0.5);
      for (let i = 0; i < bandN; i++) {
        const b = bands[i % bands.length];
        const x = -1.4 + ((i / bandN) * 2.8);
        setParticleTarget(i, x, b.y + Math.sin(t + i) * 0.03, 0.8, 4, b.c);
      }
      scanOp = 0.85;
      scanY = -1.1 + lp * 2.2;
      camZ = 6.8;
      camY = 0.05;
    } else if (p < 0.58) {
      mode = "graph";
      scatterToNodes(["image", "audio", "document", "claim", "event"], 0.75);
      streamBetween("image", "claim", 0, Math.floor(COUNT * 0.12), GREEN);
      streamBetween("audio", "claim", Math.floor(COUNT * 0.12), Math.floor(COUNT * 0.24), GREEN);
      streamBetween("document", "claim", Math.floor(COUNT * 0.24), Math.floor(COUNT * 0.36), GREEN);
      streamBetween("claim", "event", Math.floor(COUNT * 0.36), Math.floor(COUNT * 0.48), MUTED);
      camZ = 7.2 - ((p - 0.48) / 0.1) * 0.9;
      glowOp = 0.08;
    } else if (p < 0.70) {
      mode = "contradict";
      const lp = (p - 0.58) / 0.12;
      scatterToNodes(["image", "audio", "document", "claim", "event"], 0.7);
      streamBetween("document", "claim", 0, Math.floor(COUNT * 0.2), WARN);
      // pulse: push claim particles outward
      const pulse = Math.sin(lp * Math.PI * 3) * (0.2 + lp * 0.4);
      for (let i = Math.floor(COUNT * 0.55); i < COUNT * 0.7; i++) {
        setParticleTarget(
          i,
          NODES.claim.x + (hash01(i) - 0.5) * (0.3 + pulse),
          NODES.claim.y + (hash01(i + 13) - 0.5) * (0.3 + pulse),
          NODES.claim.z + pulse * 0.5,
          6,
          WARN
        );
      }
      camZ = 6.5;
      camX = Math.sin(lp * Math.PI) * 0.5;
      glowOp = 0.03 + lp * 0.05;
    } else if (p < 0.82) {
      mode = "coord";
      const lp = (p - 0.70) / 0.12;
      scatterToNodes(["image", "audio", "document", "video", "person", "event", "claim", "source"], 0.8);
      // densify center cluster
      for (let i = 0; i < COUNT * 0.2; i++) {
        setParticleTarget(
          i,
          (hash01(i) - 0.5) * (0.8 - lp * 0.3),
          (hash01(i + 19) - 0.5) * (0.8 - lp * 0.3),
          (hash01(i + 29) - 0.5) * 0.4,
          7,
          AMBER
        );
      }
      camZ = 8.0 - lp * 1.2;
      glowOp = 0.05 + lp * 0.06;
    } else if (p < 0.92) {
      mode = "uncertain";
      const lp = (p - 0.82) / 0.1;
      // incomplete: only some particles reach nodes, rest drift to void
      scatterToNodes(["image", "claim"], 0.35);
      for (let i = Math.floor(COUNT * 0.4); i < COUNT; i++) {
        const voidSide = i % 2 === 0 ? 1 : -1;
        setParticleTarget(
          i,
          voidSide * (2.5 + hash01(i) * 2),
          (hash01(i + 41) - 0.5) * 3,
          -1 - hash01(i + 47) * 2,
          8,
          MUTED
        );
      }
      camZ = 7.5 + lp * 0.8;
      glowOp = 0.02;
    } else {
      mode = "verdict";
      const lp = (p - 0.92) / 0.08;
      // collapse to center then expand to emblem
      const r = Math.max(0.08, 1.6 * (1 - lp) + lp * 0.35);
      cloudFormation(t * 0.2, r, { x: 0, y: 0, z: 0 });
      if (lp > 0.55) {
        for (let i = 0; i < COUNT * 0.3; i++) {
          const th = (i / (COUNT * 0.3)) * Math.PI * 2;
          setParticleTarget(i, Math.cos(th) * 1.1, Math.sin(th) * 0.45, 0.2, 1, GREEN);
        }
      }
      camZ = 6.2 + lp * 1.5;
      glowOp = 0.04 + lp * 0.1;
      massR = r;
    }

    if (mode !== lastMode) {
      rebuildArtifacts(mode, t);
      lastMode = mode;
    } else {
      // gentle rotate artifacts
      artifactGroup.children.forEach((ch, i) => {
        ch.rotation.y = t * (0.15 + (i % 3) * 0.05);
        if (ch.children) {
          ch.children.forEach((sub) => {
            if (sub.userData && sub.userData.spin) sub.rotation.z = t * sub.userData.spin;
          });
        }
      });
    }

    // camera
    const parallaxX = mx * 0.35;
    const parallaxY = my * 0.2;
    camera.position.x += (camX + parallaxX - camera.position.x) * 0.06;
    camera.position.y += (camY + parallaxY - camera.position.y) * 0.06;
    camera.position.z += (camZ - camera.position.z) * 0.06;
    camera.lookAt(0, lookY, 0);

    const glow = scene.getObjectByName("coreGlow");
    if (glow) {
      glow.material.opacity = glowOp;
      glow.scale.setScalar(massR);
      glow.rotation.y = t * 0.12;
      glow.rotation.x = t * 0.05;
    }
    if (scanMesh) {
      scanMesh.material.opacity = scanOp;
      scanMesh.position.y = scanY;
      scanMesh.position.x = NODES.claim.x;
      scanMesh.visible = scanOp > 0.05;
    }

    // update caption overlays
    updateCaptions(p);

    points.geometry.attributes.color.needsUpdate = true;
  }

  function updateCaptions(p) {
    const caps = DOC.querySelectorAll("[data-tl-cap]");
    caps.forEach((el) => {
      const from = parseFloat(el.getAttribute("data-from") || "0");
      const to = parseFloat(el.getAttribute("data-to") || "1");
      const on = p >= from && p < to;
      el.classList.toggle("is-on", on);
    });
    const track = DOC.getElementById("tl-cinema-track");
    if (track) track.style.setProperty("--tl-p", p.toFixed(4));
  }

  function stepParticles() {
    const pos = points.geometry.attributes.position.array;
    const frame = (performance.now() * 0.06) | 0;
    for (let i = 0; i < COUNT; i++) {
      const i3 = i * 3;
      pos[i3] += (targets[i3] - pos[i3]) * 0.045 + velocities[i3];
      pos[i3 + 1] += (targets[i3 + 1] - pos[i3 + 1]) * 0.045 + velocities[i3 + 1];
      pos[i3 + 2] += (targets[i3 + 2] - pos[i3 + 2]) * 0.045 + velocities[i3 + 2];
      velocities[i3] *= 0.96;
      velocities[i3 + 1] *= 0.96;
      velocities[i3 + 2] *= 0.96;
      // micro turbulence
      velocities[i3] += (hash01(i + frame) - 0.5) * 0.0006;
      velocities[i3 + 1] += (hash01(i + 97 + frame) - 0.5) * 0.0006;
    }
    points.geometry.attributes.position.needsUpdate = true;
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

  function cinemaProgress() {
    const track = DOC.getElementById("tl-cinema-track");
    if (!track) return 0;
    // Home is hero-only — never scrub through storytelling scenes on scroll.
    if (track.getAttribute("data-tl-hero-only") === "1") return 0.045;
    const root = scrollRoot();
    const rootRect = root.getBoundingClientRect ? root.getBoundingClientRect() : { top: 0, height: innerHeight };
    const rect = track.getBoundingClientRect();
    const viewH = root.clientHeight || innerHeight;
    const total = track.offsetHeight - viewH;
    if (total <= 0) return 0;
    const scrolled = (rootRect.top || 0) - rect.top;
    return Math.min(1, Math.max(0, scrolled / total));
  }

  function ensureLiveCaption() {
    let el = DOC.getElementById("tl-live-caption");
    if (!el) {
      el = DOC.createElement("div");
      el.id = "tl-live-caption";
      el.className = "tl-live-stage tl-live-reveal is-active";
      el.innerHTML =
        '<div class="tl-kicker" id="tl-live-cap-kicker"></div>' +
        '<h2 class="tl-live-title" id="tl-live-cap-title"></h2>' +
        '<p class="tl-lead" id="tl-live-cap-lead"></p>';
      DOC.body.appendChild(el);
    }
    return el;
  }

  function setLiveCaption(kicker, title, lead) {
    const el = ensureLiveCaption();
    el.style.display = "block";
    const k = DOC.getElementById("tl-live-cap-kicker");
    const tEl = DOC.getElementById("tl-live-cap-title");
    const l = DOC.getElementById("tl-live-cap-lead");
    if (k) k.textContent = kicker || "";
    if (tEl) tEl.textContent = title || "";
    if (l) l.textContent = lead || "";
  }

  function hideLiveCaption() {
    const el = DOC.getElementById("tl-live-caption");
    if (el) el.style.display = "none";
  }

  function syncStoryCaption(p) {
    if (!storyCaptions.length) return;
    let cur = storyCaptions[0];
    for (let i = 0; i < storyCaptions.length; i++) {
      if (p >= storyCaptions[i].p) cur = storyCaptions[i];
    }
    if (cur) setLiveCaption(cur.kicker || "Evidence reconstruction", cur.title, cur.sub);
  }

  function easeInOut(u) {
    return u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
  }

  function tick() {
    if (!ready) return;
    const host = DOC.getElementById("tl-universe");
    const active = host && host.classList.contains("is-active");
    const view = DOC.documentElement.dataset.tlView || "home";
    if (active) {
      const t = clock.getElapsedTime();
      if (view === "home") {
        // Frame the whole evidence group to the right so the hero headline stays clear.
        // Nodes keep the same relative layout; only the parent scene is translated.
        scene.position.x = mobile ? 0 : tablet ? 1.2 : 2.05;
        scrollP = 0.045;
        targetP = 0.045;
        applyScene(0.045, t);
      } else if (view === "running") {
        scene.position.x = 0;
        if (storyPlaying) {
          const u = Math.min(1, (performance.now() - storyStart) / storyDuration);
          targetP = storyFrom + (storyTo - storyFrom) * easeInOut(u);
          if (u >= 1) storyPlaying = false;
        }
        const rate = reduce ? 1 : 0.055;
        scrollP += (targetP - scrollP) * rate;
        applyScene(scrollP, t);
        if (storyCaptions.length) syncStoryCaption(scrollP);
      }
      stepParticles();
      renderer.render(scene, camera);
    }
    raf = requestAnimationFrame(tick);
  }

  function renderOnce(p) {
    applyScene(p, 1);
    stepParticles();
    renderer.render(scene, camera);
  }

  function resize() {
    if (!renderer || !camera) return;
    const w = innerWidth;
    const h = innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }

  function refresh() {
    ensureHost();
    bindScroll();
    const track = DOC.getElementById("tl-cinema-track");
    const host = DOC.getElementById("tl-universe");
    const root = scrollRoot();
    const viewEl = DOC.getElementById("tl-view");
    const view = (viewEl && viewEl.dataset.view) || DOC.documentElement.dataset.tlView || (track ? "home" : "workbench");
    DOC.documentElement.dataset.tlView = view;

    let visible = false;
    if (view === "home" && track) {
      const r = track.getBoundingClientRect();
      const viewH = root.clientHeight || innerHeight;
      visible = r.bottom > 40 && r.top < viewH * 0.95;
    } else if (view === "running") {
      visible = true;
    } else {
      visible = false;
      storyPlaying = false;
      storyCaptions = [];
      hideLiveCaption();
      if (scene) scene.position.x = 0;
      DOC.querySelectorAll(".tl-cap").forEach((el) => {
        el.classList.remove("is-on");
        el.style.visibility = "hidden";
        el.style.opacity = "0";
      });
      const rail = DOC.getElementById("tl-rail");
      if (rail) rail.style.display = "none";
    }
    if (host) {
      host.classList.toggle("is-active", visible);
      host.classList.toggle("is-live", view === "running");
    }
    if (ready && visible) {
      if (view === "home") applyScene(0.045, clock ? clock.getElapsedTime() : 0);
    }
  }

  WIN.__tlCinemaRefresh = refresh;

  // pipeline / upload hooks for workbench
  WIN.__tlCinemaSetMode = function (name) {
    if (!ready) return;
    const host = DOC.getElementById("tl-universe");
    if (host) host.classList.add("is-active", "is-live");
    DOC.documentElement.dataset.tlView = "running";
    storyPlaying = false;
    storyCaptions = [];
    hideLiveCaption();
    const map = {
      ingest: 0.2,
      extract: 0.43,
      graph: 0.53,
      contradict: 0.64,
      fuse: 0.55,
    };
    const p = map[name] != null ? map[name] : 0.53;
    WIN.__tlCinemaSeek(p);
  };

  WIN.__tlCinemaSeek = function (p) {
    if (!ready) return;
    const host = DOC.getElementById("tl-universe");
    if (host) host.classList.add("is-active", "is-live");
    DOC.documentElement.dataset.tlView = "running";
    // Soft target only — tick lerps + applyScene every frame.
    storyPlaying = false;
    targetP = Math.min(1, Math.max(0, Number(p) || 0));
  };

  WIN.__tlCinemaPlayStory = function (opts) {
    if (!ready) return;
    const host = DOC.getElementById("tl-universe");
    if (host) host.classList.add("is-active", "is-live");
    DOC.documentElement.dataset.tlView = "running";
    if (WIN.__tlStoryTimer) clearTimeout(WIN.__tlStoryTimer);

    const captions = (opts && opts.captions) || [];
    storyCaptions = captions.map((c) => ({
      p: Number(c.p) || 0,
      title: c.title || "",
      sub: c.sub || "",
      kicker: c.kicker || "Evidence reconstruction",
    }));
    storyFrom = opts && opts.from != null ? Number(opts.from) : (storyCaptions[0] ? storyCaptions[0].p : 0.1);
    storyTo = opts && opts.to != null ? Number(opts.to) : 0.99;
    storyDuration = Math.max(1200, Number((opts && opts.duration) || 10000));
    storyStart = performance.now();
    storyPlaying = true;
    scrollP = storyFrom;
    targetP = storyFrom;
    if (storyCaptions.length) {
      const first = storyCaptions[0];
      setLiveCaption(first.kicker, first.title, first.sub);
    }
  };

  WIN.__tlCinemaHideCaption = hideLiveCaption;

  function bindScroll() {
    const root = scrollRoot();
    if (root.__tlCinemaScrollBound) return;
    root.__tlCinemaScrollBound = true;
    root.addEventListener(
      "scroll",
      () => {
        const host = DOC.getElementById("tl-universe");
        const track = DOC.getElementById("tl-cinema-track");
        if (!host || !track) return;
        const r = track.getBoundingClientRect();
        const viewH = root.clientHeight || innerHeight;
        const visible = r.bottom > 40 && r.top < viewH * 0.95;
        host.classList.toggle("is-active", visible);
      },
      { passive: true }
    );
  }

  addEventListener("resize", resize);
  addEventListener(
    "pointermove",
    (e) => {
      mx = (e.clientX / innerWidth - 0.5) * 2;
      my = (e.clientY / innerHeight - 0.5) * 2;
    },
    { passive: true }
  );

  const mo = new MutationObserver(() => {
    if (storyPlaying) return; // don't thrash WebGL mid-story
    clearTimeout(WIN.__tlCinemaMo);
    WIN.__tlCinemaMo = setTimeout(refresh, 180);
  });
  mo.observe(DOC.body, { childList: true, subtree: true });

  function bootWhenThree() {
    if (typeof THREE === "undefined") {
      setTimeout(bootWhenThree, 40);
      return;
    }
    init();
    refresh();
  }
  bootWhenThree();
})();
