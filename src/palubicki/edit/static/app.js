// palubicki edit frontend — single-file app
// Uses globals: THREE (from three.min.js), THREE.GLTFLoader, THREE.OrbitControls.

const state = {
  schema: null,        // { sections: [...], top_level: [...], species: [...] }
  values: {},          // { envelope: { rx: 3.0, ... }, sim: {...}, ..., seed: 7 }
  lastGlbBytes: null,  // ArrayBuffer of the most recent generation
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
      const preset = await fetchJSON(`/api/species/${name}`, { method: "POST" });
      // Merge preset over current values (preset keys override).
      mergeInto(state.values, preset);
      // Re-render to reflect new values.
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

  viewer = { scene, camera, renderer, controls, treeRoot };

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

init();
