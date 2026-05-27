// palubicki edit frontend — single-file app
// Uses globals: THREE (from three.min.js), THREE.GLTFLoader, THREE.OrbitControls.

const state = {
  schema: null,        // { sections: [...], top_level: [...], species: [...] }
  values: {},          // { envelope: { rx: 3.0, ... }, sim: {...}, ..., seed: 7 }
  lastGlbBytes: null,  // ArrayBuffer of the most recent generation
};

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

async function regenerate() {
  // Stub — implemented in next task
  console.log("regenerate clicked", state.values);
}

function initViewer() {
  // Stub — implemented in next task
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
