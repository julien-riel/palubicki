// palubicki edit frontend — single-file app
// Uses globals: THREE (from three.min.js), THREE.GLTFLoader, THREE.OrbitControls.

const state = {
  schema: null,        // { sections: [...], top_level: [...], species: [...] }
  values: {},          // { envelope: { rx: 3.0, ... }, sim: {...}, ..., seed: 7 }
  lastGlbBytes: null,  // ArrayBuffer of the most recent generation
  debug: {
    enabled: false,    // capture toggle state
    timeline: null,    // { envelope, markers, frames } from /api/debug
    frame: 0,          // current timeline index
    killedPrefix: [],  // killedPrefix[i] = Set of marker indices dead by frame i
    playing: false,
    timer: null,
  },
};

let viewer = null; // { scene, camera, renderer, controls, treeRoot }

async function init() {
  try {
    state.schema = await fetchJSON("/api/schema");
    state.values = await fetchJSON("/api/initial");
  } catch (err) {
    showFatal("Échec d'initialisation : " + err.message);
    return;
  }
  renderSidebar();
  renderSpecies();
  attachActions();
  initViewer();
  // Initial generation
  await regenerate();
}

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try { const j = await r.json(); if (j.error) msg = j.error; } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
}

function renderSidebar() {
  const root = document.getElementById("sections-root");
  root.innerHTML = "";
  for (const sec of state.schema.sections) {
    const div = document.createElement("div");
    div.className = "section expanded";
    div.innerHTML = `<div class="section-header">${sec.label}</div><div class="section-body"></div>`;
    div.querySelector(".section-header").addEventListener("click", () => {
      div.classList.toggle("expanded");
    });
    const body = div.querySelector(".section-body");
    for (const field of sec.fields) {
      body.appendChild(renderField(sec.name, field));
    }
    root.appendChild(div);
  }
  const top = document.getElementById("top-level-root");
  top.innerHTML = "";
  for (const field of state.schema.top_level) {
    top.appendChild(renderField(null, field));
  }
}

function renderField(sectionName, field) {
  const row = document.createElement("div");
  row.className = "field-row";
  const label = document.createElement("label");
  label.textContent = field.label || field.name;
  row.appendChild(label);
  const value = (sectionName ? state.values[sectionName]?.[field.name] : state.values[field.name]);
  const setter = (v) => {
    if (sectionName) {
      state.values[sectionName] = state.values[sectionName] || {};
      state.values[sectionName][field.name] = v;
    } else {
      state.values[field.name] = v;
    }
  };
  if (field.type === "enum") {
    const sel = document.createElement("select");
    for (const choice of field.choices) {
      const opt = document.createElement("option");
      opt.value = choice; opt.textContent = choice;
      if (choice === value) opt.selected = true;
      sel.appendChild(opt);
    }
    sel.addEventListener("change", () => setter(sel.value));
    row.appendChild(sel);
  } else if (field.type === "bool") {
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = !!value;
    cb.addEventListener("change", () => setter(cb.checked));
    row.appendChild(cb);
    row.appendChild(document.createElement("span"));
  } else if (field.type === "int" || field.type === "float") {
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = field.min; slider.max = field.max; slider.step = field.step;
    slider.value = value;
    const num = document.createElement("input");
    num.type = "number";
    num.min = field.min; num.max = field.max; num.step = field.step;
    num.value = value;
    const parse = field.type === "int" ? (v) => parseInt(v, 10) : (v) => parseFloat(v);
    slider.addEventListener("input", () => { num.value = slider.value; setter(parse(slider.value)); });
    num.addEventListener("input", () => { slider.value = num.value; setter(parse(num.value)); });
    row.appendChild(slider);
    row.appendChild(num);
  } else {
    // unknown / vec3 — skip with a placeholder
    const span = document.createElement("span");
    span.textContent = "(not editable)";
    row.appendChild(span);
    row.appendChild(document.createElement("span"));
  }
  return row;
}

function renderSpecies() {
  const sel = document.getElementById("species-select");
  for (const s of state.schema.species) {
    const opt = document.createElement("option");
    opt.value = s; opt.textContent = s;
    sel.appendChild(opt);
  }
  sel.addEventListener("change", async () => {
    const name = sel.value;
    if (!name) return;
    try {
      // Backend returns defaults + preset already merged — match CLI semantics
      // (`palubicki generate --species X` starts from defaults, not from the prior preset).
      const merged = await fetchJSON(`/api/species/${name}`, { method: "POST" });
      state.values = merged;
      renderSidebar();
    } catch (err) {
      showToast("Preset error: " + err.message);
    }
  });
}

function mergeInto(target, source) {
  for (const k of Object.keys(source)) {
    if (source[k] && typeof source[k] === "object" && !Array.isArray(source[k])) {
      target[k] = target[k] || {};
      mergeInto(target[k], source[k]);
    } else {
      target[k] = source[k];
    }
  }
}

function attachActions() {
  document.getElementById("regenerate-btn").addEventListener("click", regenerate);
  document.getElementById("export-glb-btn").addEventListener("click", exportGlb);
  document.getElementById("export-yaml-btn").addEventListener("click", exportYaml);
  document.getElementById("toggle-leaves-btn").addEventListener("click", toggleLeaves);
  document.getElementById("toggle-wireframe-btn").addEventListener("click", toggleWireframe);

  const debugToggle = document.getElementById("debug-capture-toggle");
  debugToggle.addEventListener("change", () => {
    state.debug.enabled = debugToggle.checked;
    document.getElementById("debug-panel").classList.toggle("hidden", !debugToggle.checked);
    if (debugToggle.checked) regenerate();
    else clearDebugLayers();
  });
  document.getElementById("timeline-slider").addEventListener("input", (e) => {
    stopPlay();
    setFrame(parseInt(e.target.value, 10));
  });
  document.getElementById("timeline-play-btn").addEventListener("click", togglePlay);
  for (const [id, name] of [
    ["layer-markers-toggle", "markers"], ["layer-envelope-toggle", "envelope"],
    ["layer-buds-toggle", "buds"], ["layer-shed-toggle", "shed"],
  ]) {
    document.getElementById(id).addEventListener("change", (e) => {
      if (viewer.debugLayers[name]) viewer.debugLayers[name].visible = e.target.checked;
    });
  }
}

function exportGlb() {
  if (!state.lastGlbBytes) return;
  const blob = new Blob([state.lastGlbBytes], { type: "model/gltf-binary" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "tree.glb";
  a.click();
  URL.revokeObjectURL(url);
}

async function exportYaml() {
  try {
    const r = await fetch("/api/save-yaml", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.values),
    });
    if (!r.ok) {
      let msg = `HTTP ${r.status}`;
      try { const j = await r.json(); if (j.error) msg = j.error; } catch (_) {}
      throw new Error(msg);
    }
    const text = await r.text();
    const blob = new Blob([text], { type: "application/x-yaml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "tree.yaml";
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    showToast("YAML export failed: " + err.message);
  }
}

let leavesHidden = false;
function toggleLeaves() {
  leavesHidden = !leavesHidden;
  viewer.treeRoot.traverse((obj) => {
    if (obj.isMesh && obj.material) {
      const matName = (obj.material.name || "").toLowerCase();
      if (matName.includes("leaf")) obj.visible = !leavesHidden;
    }
  });
}

let wireframe = false;
function toggleWireframe() {
  wireframe = !wireframe;
  viewer.treeRoot.traverse((obj) => {
    if (obj.isMesh && obj.material) {
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
      for (const m of mats) m.wireframe = wireframe;
    }
  });
}

function initViewer() {
  const canvas = document.getElementById("viewer-canvas");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  resizeRenderer(renderer);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xe8e8e8);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1.0));
  const dir = new THREE.DirectionalLight(0xffffff, 0.6);
  dir.position.set(5, 10, 7);
  scene.add(dir);

  const camera = new THREE.PerspectiveCamera(45, canvas.clientWidth / canvas.clientHeight, 0.1, 1000);
  camera.position.set(8, 6, 10);

  const controls = new THREE.OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.1;

  const treeRoot = new THREE.Group();
  scene.add(treeRoot);

  const debugRoot = new THREE.Group();
  scene.add(debugRoot);

  viewer = { scene, camera, renderer, controls, treeRoot, debugRoot, debugLayers: {} };

  window.addEventListener("resize", () => {
    resizeRenderer(renderer);
    camera.aspect = canvas.clientWidth / canvas.clientHeight;
    camera.updateProjectionMatrix();
  });

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();
}

function resizeRenderer(renderer) {
  const canvas = renderer.domElement;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== w || canvas.height !== h) {
    renderer.setSize(w, h, false);
  }
}

async function regenerate() {
  const btn = document.getElementById("regenerate-btn");
  const spinner = document.getElementById("spinner");
  btn.disabled = true;
  spinner.classList.remove("hidden");
  try {
    const r = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.values),
    });
    if (!r.ok) {
      let msg = `HTTP ${r.status}`;
      try { const j = await r.json(); if (j.error) msg = j.error; } catch (_) {}
      throw new Error(msg);
    }
    const buf = await r.arrayBuffer();
    state.lastGlbBytes = buf;
    document.getElementById("export-glb-btn").disabled = false;
    await replaceTree(buf);
    if (state.debug.enabled) {
      await fetchDebugTimeline();
    }
  } catch (err) {
    showToast("Generation failed: " + err.message);
  } finally {
    btn.disabled = false;
    spinner.classList.add("hidden");
  }
}

function replaceTree(arrayBuffer) {
  return new Promise((resolve, reject) => {
    const loader = new THREE.GLTFLoader();
    loader.parse(arrayBuffer, "", (gltf) => {
      disposeChildren(viewer.treeRoot);
      viewer.treeRoot.add(gltf.scene);
      fitCameraToObject(viewer.camera, viewer.controls, gltf.scene);
      resolve();
    }, (err) => {
      reject(new Error("GLTFLoader: " + (err.message || err)));
    });
  });
}

function disposeChildren(group) {
  while (group.children.length) {
    const child = group.children[0];
    group.remove(child);
    child.traverse?.((obj) => {
      if (obj.geometry) obj.geometry.dispose();
      if (obj.material) {
        const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
        for (const m of mats) {
          if (m.map) m.map.dispose();
          m.dispose();
        }
      }
    });
  }
}

function fitCameraToObject(camera, controls, object) {
  const box = new THREE.Box3().setFromObject(object);
  if (box.isEmpty()) return;
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const fov = camera.fov * (Math.PI / 180);
  const dist = (maxDim / 2) / Math.tan(fov / 2) * 1.5;
  const dir = new THREE.Vector3(1, 0.6, 1).normalize();
  camera.position.copy(center).addScaledVector(dir, dist);
  camera.lookAt(center);
  controls.target.copy(center);
  controls.update();
}

function showToast(msg) {
  const c = document.getElementById("toast-container");
  const t = document.createElement("div");
  t.className = "toast"; t.textContent = msg;
  t.addEventListener("click", () => t.remove());
  c.appendChild(t);
  setTimeout(() => t.remove(), 5000);
}

function showFatal(msg) {
  document.body.innerHTML = `<div style="padding:32px;color:#ff5b5b;font-family:sans-serif">${msg}</div>`;
}

// ---- Debug overlay (#29) ----

async function fetchDebugTimeline() {
  try {
    const tl = await fetchJSON("/api/debug");
    state.debug.timeline = tl;
    state.debug.killedPrefix = buildKilledPrefix(tl.frames);
    buildDebugLayers(tl);
    const slider = document.getElementById("timeline-slider");
    slider.max = Math.max(0, tl.frames.length - 1);
    slider.value = slider.max;
    setFrame(tl.frames.length - 1);
  } catch (err) {
    showToast("Debug fetch failed: " + err.message);
  }
}

// killedPrefix[i] = Set of all marker indices dead by frame i (cumulative union).
function buildKilledPrefix(frames) {
  const prefix = [];
  const acc = new Set();
  for (const f of frames) {
    for (const idx of f.markers_killed) acc.add(idx);
    prefix.push(new Set(acc));
  }
  return prefix;
}

function clearDebugLayers() {
  stopPlay();
  disposeChildren(viewer.debugRoot);
  viewer.debugLayers = {};
}

function buildDebugLayers(tl) {
  clearDebugLayers();

  // Markers — one Points cloud, positions uploaded once, recolored per frame.
  const mPos = new Float32Array(tl.markers.positions.length * 3);
  tl.markers.positions.forEach((p, i) => { mPos[i*3]=p[0]; mPos[i*3+1]=p[1]; mPos[i*3+2]=p[2]; });
  const mGeo = new THREE.BufferGeometry();
  mGeo.setAttribute("position", new THREE.BufferAttribute(mPos, 3));
  mGeo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(mPos.length), 3));
  const markers = new THREE.Points(mGeo,
    new THREE.PointsMaterial({ size: 0.04, vertexColors: true }));
  viewer.debugLayers.markers = markers;
  viewer.debugRoot.add(markers);

  // Envelope — wireframe sized from shape/radii/center.
  const envelope = buildEnvelopeMesh(tl.envelope);
  viewer.debugLayers.envelope = envelope;
  viewer.debugRoot.add(envelope);

  // Buds — Points cloud rebuilt per frame.
  const buds = new THREE.Points(new THREE.BufferGeometry(),
    new THREE.PointsMaterial({ size: 0.08, vertexColors: true }));
  viewer.debugLayers.buds = buds;
  viewer.debugRoot.add(buds);

  // Shed — line segments, cumulative up to the current frame.
  const shed = new THREE.LineSegments(new THREE.BufferGeometry(),
    new THREE.LineBasicMaterial({ color: 0xff4040 }));
  viewer.debugLayers.shed = shed;
  viewer.debugRoot.add(shed);

  // Honor current checkbox states.
  for (const [id, name] of [
    ["layer-markers-toggle", "markers"], ["layer-envelope-toggle", "envelope"],
    ["layer-buds-toggle", "buds"], ["layer-shed-toggle", "shed"],
  ]) {
    viewer.debugLayers[name].visible = document.getElementById(id).checked;
  }
}

function buildEnvelopeMesh(env) {
  const [rx, ry, rz] = env.radii;
  let geo;
  if (env.shape === "cone") {
    geo = new THREE.ConeGeometry(1, 1, 24, 1, true);
    geo.translate(0, 0.5, 0);                 // apex at y=1, base at y=0
    geo.scale(rx, ry, rz);
  } else {
    geo = new THREE.SphereGeometry(1, 24, 16); // sphere/ellipsoid/half_ellipsoid
    geo.scale(rx, ry, rz);
  }
  const mesh = new THREE.Mesh(geo,
    new THREE.MeshBasicMaterial({ color: 0x3399ff, wireframe: true, transparent: true, opacity: 0.4 }));
  mesh.position.set(env.center[0], env.center[1], env.center[2]);
  return mesh;
}

function setFrame(i) {
  const tl = state.debug.timeline;
  if (!tl || !tl.frames.length) return;
  i = Math.max(0, Math.min(i, tl.frames.length - 1));
  state.debug.frame = i;
  document.getElementById("timeline-slider").value = i;
  const frame = tl.frames[i];
  const dead = state.debug.killedPrefix[i] || new Set();

  // Markers: recolor by cumulative killed set (alive = green, dead = dark red).
  const colors = viewer.debugLayers.markers.geometry.getAttribute("color");
  for (let k = 0; k < tl.markers.positions.length; k++) {
    if (dead.has(k)) { colors.setXYZ(k, 0.45, 0.08, 0.08); }
    else { colors.setXYZ(k, 0.45, 0.85, 0.45); }
  }
  colors.needsUpdate = true;

  // Buds: rebuild positions + colors from this frame.
  const bp = new Float32Array(frame.buds.length * 3);
  const bc = new Float32Array(frame.buds.length * 3);
  frame.buds.forEach((b, j) => {
    bp[j*3]=b.p[0]; bp[j*3+1]=b.p[1]; bp[j*3+2]=b.p[2];
    const c = b.state === "ACTIVE" ? [1.0, 0.85, 0.1] : [0.5, 0.5, 0.55]; // dormant = grey
    bc[j*3]=c[0]; bc[j*3+1]=c[1]; bc[j*3+2]=c[2];
  });
  const bGeo = viewer.debugLayers.buds.geometry;
  bGeo.setAttribute("position", new THREE.BufferAttribute(bp, 3));
  bGeo.setAttribute("color", new THREE.BufferAttribute(bc, 3));

  // Shed: cumulative segments up to and including frame i.
  const segs = [];
  for (let f = 0; f <= i; f++) {
    for (const s of tl.frames[f].shed) { segs.push(...s[0], ...s[1]); }
  }
  const sGeo = viewer.debugLayers.shed.geometry;
  sGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(segs), 3));

  // Readout: time, alive/dead counts, bud count.
  const aliveCount = tl.markers.positions.length - dead.size;
  document.getElementById("timeline-readout").textContent =
    `t=${frame.t}yr  ·  markers ${aliveCount}↑/${dead.size}†  ·  buds ${frame.buds.length}`;
}

function togglePlay() {
  if (state.debug.playing) { stopPlay(); return; }
  const tl = state.debug.timeline;
  if (!tl || !tl.frames.length) return;
  state.debug.playing = true;
  document.getElementById("timeline-play-btn").textContent = "⏸";
  if (state.debug.frame >= tl.frames.length - 1) setFrame(0);
  state.debug.timer = setInterval(() => {
    if (state.debug.frame >= tl.frames.length - 1) { stopPlay(); return; }
    setFrame(state.debug.frame + 1);
  }, 250);
}

function stopPlay() {
  state.debug.playing = false;
  if (state.debug.timer) { clearInterval(state.debug.timer); state.debug.timer = null; }
  const btn = document.getElementById("timeline-play-btn");
  if (btn) btn.textContent = "▶";
}

init();
