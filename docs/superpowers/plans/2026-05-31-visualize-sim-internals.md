# Sim-Internals Visualizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in debug overlay to the `palubicki edit` web editor that visualizes the space-colonization model's intermediate state — markers (alive/dead), envelope, buds (by state), and shed branches — with a per-iteration timeline the user can scrub and play.

**Architecture:** Capture is *observational*: a `DebugCollector` is threaded into `simulate_forest` and only reads/diffs forest state, never mutates it, so the deterministic evolution is untouched. When the editor's debug toggle is on, `/api/generate` runs one capture-enabled sim, builds the GLB as usual, and caches the timeline on `app.state.last_debug`; `/api/debug` serves it. The three.js frontend draws four overlay layers and a timeline slider.

**Tech Stack:** Python (NumPy, FastAPI, `fastapi.testclient`), three.js (vanilla globals, no build step), pytest.

**Spec:** `docs/superpowers/specs/2026-05-31-visualize-sim-internals-design.md`

---

## File structure

| File | Responsibility |
|---|---|
| `src/palubicki/sim/markers.py` (modify) | Add `positions` property + `alive_mask()` accessor so the collector can read marker state without touching privates. |
| `src/palubicki/sim/debug_capture.py` (create) | `DebugCollector` — accumulate static data once, diff per frame, emit JSON-ready timeline. The only new domain unit. |
| `src/palubicki/sim/simulator.py` (modify) | `simulate_forest(cfg, collector=None)` — call `capture_static` after `build_forest`, `capture_frame` once per executed iteration. |
| `src/palubicki/edit/server.py` (modify) | `/api/generate` reads a `debug` flag → runs capture path, caches timeline; new `/api/debug` GET returns it. |
| `src/palubicki/edit/static/index.html` (modify) | Debug controls: capture toggle, timeline slider + play/pause, per-layer checkboxes, frame readout. |
| `src/palubicki/edit/static/app.js` (modify) | Fetch `/api/debug`, build the four overlay layers, `setFrame(i)` scrub, play/pause loop, layer visibility. |
| `tests/sim/test_markers.py` (modify) | Cover the new accessors. |
| `tests/sim/test_debug_capture.py` (create) | Unit-test the collector against a tiny real forest. |
| `tests/sim/test_simulator.py` (modify) | Backward-compat guard: collector run == no-collector run. |
| `tests/edit/test_server.py` (modify) | `/api/generate` debug flag + cache + `/api/debug`; frontend symbol/DOM-id presence. |

---

## Task 1: MarkerCloud read accessors

**Files:**
- Modify: `src/palubicki/sim/markers.py`
- Test: `tests/sim/test_markers.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_markers.py`:

```python
def test_positions_property_returns_all_positions():
    import numpy as np
    from palubicki.sim.markers import MarkerCloud
    pts = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 2.0, 2.0]])
    cloud = MarkerCloud(pts)
    assert np.array_equal(cloud.positions, pts)


def test_alive_mask_reflects_kills_and_is_a_copy():
    import numpy as np
    from palubicki.sim.markers import MarkerCloud
    pts = np.array([[0.0, 0.0, 0.0], [10.0, 10.0, 10.0]])
    cloud = MarkerCloud(pts)
    mask = cloud.alive_mask()
    assert mask.tolist() == [True, True]
    # Mutating the returned mask must not affect the cloud (it is a copy).
    mask[0] = False
    assert cloud.alive_mask().tolist() == [True, True]
    # Killing near the first point flips only that entry.
    cloud.kill_near(np.array([[0.0, 0.0, 0.0]]), kill_radius=1.0)
    assert cloud.alive_mask().tolist() == [False, True]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/sim/test_markers.py::test_positions_property_returns_all_positions tests/sim/test_markers.py::test_alive_mask_reflects_kills_and_is_a_copy -v`
Expected: FAIL with `AttributeError: 'MarkerCloud' object has no attribute 'positions'` / `alive_mask`.

- [ ] **Step 3: Add the accessors**

In `src/palubicki/sim/markers.py`, after the `alive_count` property (around line 19), add:

```python
    @property
    def positions(self) -> np.ndarray:
        """All marker positions in original index space (alive or dead)."""
        return self._positions

    def alive_mask(self) -> np.ndarray:
        """Copy of the per-marker alive boolean mask (original index space)."""
        return self._alive.copy()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/sim/test_markers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/markers.py tests/sim/test_markers.py
git commit -m "sim/markers: add positions property + alive_mask() accessor for debug capture (#29)"
```

---

## Task 2: DebugCollector — static capture

**Files:**
- Create: `src/palubicki/sim/debug_capture.py`
- Test: `tests/sim/test_debug_capture.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_debug_capture.py`:

```python
import numpy as np

from palubicki.config import load_config
from palubicki.sim.debug_capture import DebugCollector
from palubicki.sim.forest import build_forest


def _tiny_cfg(tmp_path):
    return load_config(
        yaml_path=None,
        cli_overrides={
            "envelope.shape": "ellipsoid",
            "envelope.rx": 1.0,
            "envelope.ry": 2.0,
            "envelope.rz": 1.0,
            "envelope.marker_count": 150,
            "sim.max_simulation_years": 4,
            "seed": 1,
        },
        output=tmp_path / "tree.glb",
    )


def test_capture_static_records_envelope_and_all_marker_positions(tmp_path):
    cfg = _tiny_cfg(tmp_path)
    forest = build_forest(cfg)
    c = DebugCollector()
    c.capture_static(forest, cfg)
    tl = c.timeline()
    assert tl["envelope"]["shape"] == "ellipsoid"
    assert tl["envelope"]["radii"] == [1.0, 2.0, 1.0]
    assert len(tl["envelope"]["center"]) == 3
    # Every marker position is present exactly once, sent statically.
    assert len(tl["markers"]["positions"]) == len(forest.markers.positions)
    assert tl["frames"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/sim/test_debug_capture.py::test_capture_static_records_envelope_and_all_marker_positions -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'palubicki.sim.debug_capture'`.

- [ ] **Step 3: Create the collector with static capture only**

Create `src/palubicki/sim/debug_capture.py`:

```python
# src/palubicki/sim/debug_capture.py
"""Observational debug capture for the editor's sim-internals visualizer (#29).

The collector only READS forest state and diffs it between frames — it never
mutates the sim, so threading it through ``simulate_forest`` cannot perturb the
deterministic evolution (the bit-exact backward-compat contract holds)."""
from __future__ import annotations

import numpy as np

_NDIGITS = 4


def _round_vec(v) -> list[float]:
    """Round a 3-vector to plain rounded floats for a lean JSON payload."""
    return [round(float(x), _NDIGITS) for x in v]


class DebugCollector:
    def __init__(self) -> None:
        self._envelope: dict | None = None
        self._marker_positions: np.ndarray | None = None
        self._prev_alive: np.ndarray | None = None
        self._prev_iods: dict[int, tuple[list, list]] | None = None
        self._frames: list[dict] = []

    def capture_static(self, forest, cfg) -> None:
        env = forest.per_tree_cfgs[0].envelope
        self._envelope = {
            "shape": env.shape,
            "center": [float(x) for x in env.center],
            "radii": [float(env.rx), float(env.ry), float(env.rz)],
        }
        self._marker_positions = np.asarray(forest.markers.positions, dtype=float)
        self._prev_alive = forest.markers.alive_mask()
        self._prev_iods = self._current_iods(forest)

    @staticmethod
    def _current_iods(forest) -> dict[int, tuple[list, list]]:
        """Map id(internode) -> (rounded parent endpoint, rounded child endpoint)
        across all trees. Endpoints are rounded copies, so later in-place position
        edits (sag/elongation) cannot corrupt a remembered shed segment."""
        out: dict[int, tuple[list, list]] = {}
        for tree in forest.trees:
            for iod in tree.all_internodes:
                out[id(iod)] = (
                    _round_vec(iod.parent_node.position),
                    _round_vec(iod.child_node.position),
                )
        return out

    def timeline(self) -> dict:
        positions = (
            [_round_vec(p) for p in self._marker_positions]
            if self._marker_positions is not None else []
        )
        return {
            "envelope": self._envelope,
            "markers": {"positions": positions},
            "frames": self._frames,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/sim/test_debug_capture.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/debug_capture.py tests/sim/test_debug_capture.py
git commit -m "sim: DebugCollector static capture (envelope + marker positions) (#29)"
```

---

## Task 3: DebugCollector — per-frame capture (markers killed, buds, shed)

**Files:**
- Modify: `src/palubicki/sim/debug_capture.py`
- Test: `tests/sim/test_debug_capture.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_debug_capture.py`:

```python
def test_frames_capture_killed_buds_and_shed(tmp_path):
    cfg = _tiny_cfg(tmp_path)
    forest = build_forest(cfg)
    c = DebugCollector()
    c.capture_static(forest, cfg)
    # Kill three markers, then capture a frame: killed indices are exactly those.
    killed_pts = forest.markers.positions[[5, 6, 7]]
    forest.markers.kill_near(killed_pts, kill_radius=0.001)
    c.capture_frame(forest, t=1.0)
    frame = c.timeline()["frames"][0]
    assert frame["t"] == 1.0
    assert set(frame["markers_killed"]) == {5, 6, 7}
    # Buds come from each tree's active_buds, flattened, with a string state.
    n_active = sum(len(tr.active_buds) for tr in forest.trees)
    assert len(frame["buds"]) == n_active
    if frame["buds"]:
        assert frame["buds"][0]["state"] in ("ACTIVE", "DORMANT", "RESERVE", "DEAD")
        assert len(frame["buds"][0]["p"]) == 3
        assert len(frame["buds"][0]["dir"]) == 3
    # No internodes removed yet → no shed.
    assert frame["shed"] == []


def test_markers_killed_is_a_partition_across_frames(tmp_path):
    cfg = _tiny_cfg(tmp_path)
    forest = build_forest(cfg)
    c = DebugCollector()
    c.capture_static(forest, cfg)
    # Frame 1: kill markers {0,1}. Frame 2: kill markers {1,2} (1 already dead).
    c_before = forest.markers.alive_mask()
    forest.markers.kill_near(forest.markers.positions[[0, 1]], kill_radius=0.001)
    c.capture_frame(forest, t=1.0)
    forest.markers.kill_near(forest.markers.positions[[1, 2]], kill_radius=0.001)
    c.capture_frame(forest, t=2.0)
    frames = c.timeline()["frames"]
    f1 = set(frames[0]["markers_killed"])
    f2 = set(frames[1]["markers_killed"])
    assert f1 == {0, 1}
    # Frame 2 only reports the NEWLY dead marker (2), not the already-dead 1.
    assert f2 == {2}
    assert f1.isdisjoint(f2)
    assert c_before.all()  # sanity: started all-alive


def test_shed_reports_removed_internode_endpoints(tmp_path):
    cfg = _tiny_cfg(tmp_path)
    forest = build_forest(cfg)
    c = DebugCollector()
    c.capture_static(forest, cfg)
    # Synthesize an internode, capture a baseline frame, then remove it.
    from palubicki.sim.tree import Internode, Node
    tree = forest.trees[0]
    n0, n1 = Node(position=np.array([0.0, 0.0, 0.0])), Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=n0, child_node=n1, length=1.0, is_main_axis=True)
    tree.all_internodes.append(iod)
    c.capture_frame(forest, t=1.0)               # iod present this frame
    tree.all_internodes.remove(iod)
    c.capture_frame(forest, t=2.0)               # iod gone → shed
    frame2 = c.timeline()["frames"][1]
    assert [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]] in frame2["shed"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/sim/test_debug_capture.py -k frames_or_partition_or_shed -v` (or run the file)
Run: `.venv/bin/pytest tests/sim/test_debug_capture.py -v`
Expected: FAIL with `AttributeError: 'DebugCollector' object has no attribute 'capture_frame'`.

- [ ] **Step 3: Add `capture_frame`**

In `src/palubicki/sim/debug_capture.py`, add this method to `DebugCollector` (after `capture_static`):

```python
    def capture_frame(self, forest, t: float) -> None:
        # Markers: report only those that flipped alive->dead since the last frame.
        alive = forest.markers.alive_mask()
        newly_killed = np.flatnonzero(self._prev_alive & ~alive)
        self._prev_alive = alive

        # Shed: internodes present last frame but gone now (shed_low_quality
        # removes them from tree.all_internodes). Use the previously remembered
        # rounded endpoints so the segment is the branch as it was when culled.
        cur_iods = self._current_iods(forest)
        shed = [
            [p0, p1]
            for iid, (p0, p1) in self._prev_iods.items()
            if iid not in cur_iods
        ]
        self._prev_iods = cur_iods

        # Buds: the live set (ACTIVE / DORMANT), flattened across trees.
        buds = [
            {
                "p": _round_vec(b.position),
                "dir": _round_vec(b.direction),
                "state": b.state.name,
            }
            for tree in forest.trees
            for b in tree.active_buds
        ]

        self._frames.append({
            "t": round(float(t), _NDIGITS),
            "markers_killed": [int(i) for i in newly_killed],
            "buds": buds,
            "shed": shed,
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/sim/test_debug_capture.py -v`
Expected: PASS (all five tests).

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/debug_capture.py tests/sim/test_debug_capture.py
git commit -m "sim: DebugCollector per-frame capture (killed/buds/shed deltas) (#29)"
```

---

## Task 4: Thread the collector into `simulate_forest`

**Files:**
- Modify: `src/palubicki/sim/simulator.py:50-89`
- Test: `tests/sim/test_simulator.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_simulator.py` (add imports at top of the new test as shown):

```python
def _position_signature(forest):
    """Order-independent structural signature of a forest's node positions."""
    import numpy as np
    sig = []
    for ti, tree in enumerate(forest.trees):
        stack = [tree.root]
        while stack:
            node = stack.pop()
            sig.append((ti, tuple(np.round(node.position, 6).tolist())))
            for iod in node.children_internodes:
                stack.append(iod.child_node)
    return sorted(sig)


def test_collector_does_not_perturb_evolution(tmp_path):
    from palubicki.config import load_config
    from palubicki.sim.debug_capture import DebugCollector
    from palubicki.sim.simulator import simulate_forest
    overrides = {
        "envelope.shape": "ellipsoid", "envelope.rx": 1.0, "envelope.ry": 2.0,
        "envelope.rz": 1.0, "envelope.marker_count": 200,
        "sim.max_simulation_years": 5, "seed": 3,
    }
    cfg = load_config(yaml_path=None, cli_overrides=overrides, output=tmp_path / "a.glb")
    plain = simulate_forest(cfg)
    cfg2 = load_config(yaml_path=None, cli_overrides=overrides, output=tmp_path / "b.glb")
    captured = simulate_forest(cfg2, collector=DebugCollector())
    assert _position_signature(plain) == _position_signature(captured)


def test_collector_captures_one_frame_per_executed_iteration(tmp_path):
    from palubicki.config import load_config
    from palubicki.sim.debug_capture import DebugCollector
    from palubicki.sim.simulator import simulate_forest
    cfg = load_config(
        yaml_path=None,
        cli_overrides={"envelope.marker_count": 200, "sim.max_simulation_years": 5, "seed": 3},
        output=tmp_path / "c.glb",
    )
    c = DebugCollector()
    simulate_forest(cfg, collector=c)
    tl = c.timeline()
    assert len(tl["frames"]) >= 1
    # Frame times are non-decreasing.
    times = [f["t"] for f in tl["frames"]]
    assert times == sorted(times)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/sim/test_simulator.py::test_collector_does_not_perturb_evolution tests/sim/test_simulator.py::test_collector_captures_one_frame_per_executed_iteration -v`
Expected: FAIL with `TypeError: simulate_forest() got an unexpected keyword argument 'collector'`.

- [ ] **Step 3: Add the `collector` param and capture hooks**

In `src/palubicki/sim/simulator.py`, change the `simulate_forest` signature and body. Replace lines 50-73 (from `def simulate_forest` through the `if no_new_streak >= 2: break`) with:

```python
def simulate_forest(cfg: Config, collector=None) -> Forest:
    forest = build_forest(cfg)
    if collector is not None:
        collector.capture_static(forest, cfg)
    if cfg.light.enabled:
        _init_light_grid(forest, cfg)
    no_new_streak = 0
    t0 = time.time()
    state = _SimState()
    clock = Clock(dt=cfg.sim.dt_years)
    for iteration in range(cfg.sim.num_iterations):
        clock.t = iteration * cfg.sim.dt_years
        if not any(t.active_buds for t in forest.trees):
            break
        if not clock.in_window(*cfg.sim.annual_growth_period):
            # Dormant season: age existing structure, emit nothing. Does NOT
            # count toward the no-growth early-stop (that is for saturation).
            _apply_temporal_dynamics(forest, cfg, clock.t)
            if collector is not None:
                collector.capture_frame(forest, clock.t)
            continue
        nodes_created = _iteration_step(forest, cfg, iteration, clock.t, state, t0)
        if collector is not None:
            collector.capture_frame(forest, clock.t)
        if nodes_created == 0:
            no_new_streak += 1
        else:
            no_new_streak = 0
        if no_new_streak >= 2:
            break
```

(The `# --- Phase 2D finalization ---` block and everything after it stays unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_simulator.py -v`
Expected: PASS, including the two new tests. The backward-compat guard proves the collector is purely observational.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/simulator.py tests/sim/test_simulator.py
git commit -m "sim: thread optional DebugCollector through simulate_forest (#29)"
```

---

## Task 5: Server — `/api/generate` debug flag + `/api/debug` endpoint

**Files:**
- Modify: `src/palubicki/edit/server.py`
- Test: `tests/edit/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/edit/test_server.py`:

```python
def test_debug_endpoint_404_before_any_capture(client):
    r = client.get("/api/debug")
    assert r.status_code == 404
    assert "error" in r.json()


def test_generate_without_debug_flag_leaves_no_capture(client):
    r = client.post("/api/generate", json=_tiny_config_dict())
    assert r.status_code == 200
    # No debug flag → cost-free path, nothing cached.
    r2 = client.get("/api/debug")
    assert r2.status_code == 404


def test_generate_with_debug_flag_populates_timeline(client):
    payload = _tiny_config_dict()
    payload["debug"] = True
    r = client.post("/api/generate", json=payload)
    assert r.status_code == 200
    assert r.headers["content-type"] == "model/gltf-binary"
    assert r.content[:4] == b"glTF"
    # The debug flag must NOT leak into config parsing (still a valid GLB above).
    r2 = client.get("/api/debug")
    assert r2.status_code == 200
    tl = r2.json()
    assert set(tl.keys()) == {"envelope", "markers", "frames"}
    assert "positions" in tl["markers"]
    assert isinstance(tl["frames"], list) and len(tl["frames"]) >= 1
    frame = tl["frames"][0]
    assert set(frame.keys()) == {"t", "markers_killed", "buds", "shed"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/edit/test_server.py::test_debug_endpoint_404_before_any_capture tests/edit/test_server.py::test_generate_with_debug_flag_populates_timeline -v`
Expected: FAIL — `/api/debug` returns 404 *route not found* (no such route) for the first; the third errors because there is no `/api/debug` route returning the timeline.

- [ ] **Step 3: Wire the debug path into the server**

In `src/palubicki/edit/server.py`:

(a) Add the import near the existing sim import (line 19):

```python
from palubicki.sim.simulator import simulate, simulate_forest
from palubicki.sim.debug_capture import DebugCollector
```

(b) In `create_app`, after `app.state.initial_config = initial_config` (line 26), add:

```python
    app.state.last_debug = None
```

(c) Replace the body of `post_generate` (lines 50-78) with:

```python
    async def post_generate(request: Request):
        payload = await request.json()
        debug = bool(payload.pop("debug", False))
        try:
            cfg = load_config(
                yaml_path=None,
                cli_overrides=config_dict_to_overrides(payload),
                output=Path("tree.glb"),
            )
        except ConfigError as e:
            logger.warning("generate: config error: %s", e)
            return JSONResponse(status_code=400, content={"error": str(e)})
        t0 = time.perf_counter()
        collector = DebugCollector() if debug else None
        try:
            if collector is not None:
                forest = await asyncio.to_thread(simulate_forest, cfg, collector)
                tree = forest.trees[0]
            else:
                tree = await asyncio.to_thread(simulate, cfg)
            mesh = build_mesh(tree, cfg)
            data = write_glb_to_bytes(mesh, asset_meta={"seed": cfg.seed})
        except ExportError as e:
            logger.warning("generate: export error: %s", e)
            return JSONResponse(status_code=400, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.exception("generate: unexpected error")
            return JSONResponse(
                status_code=500,
                content={"error": f"{type(e).__name__}: {e}"},
            )
        app.state.last_debug = collector.timeline() if collector is not None else None
        n_tris = sum(p.indices.shape[0] // 3 for p in mesh.primitives)
        logger.info("generate: %.2fs, %d triangles, %d bytes, debug=%s",
                    time.perf_counter() - t0, n_tris, len(data), debug)
        return Response(content=data, media_type="model/gltf-binary")
```

(d) Add the new route right after `post_generate` (before `post_save_yaml`):

```python
    @app.get("/api/debug")
    def get_debug():
        timeline = app.state.last_debug
        if timeline is None:
            return JSONResponse(
                status_code=404,
                content={"error": "no debug capture available — generate with debug enabled first"},
            )
        return JSONResponse(content=timeline)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/edit/test_server.py -v`
Expected: PASS, including the three new tests and all existing ones (the `simulate` import line still exports `simulate`).

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/edit/server.py tests/edit/test_server.py
git commit -m "edit/server: /api/generate debug flag + cached /api/debug timeline (#29)"
```

---

## Task 6: Frontend — debug controls in `index.html`

**Files:**
- Modify: `src/palubicki/edit/static/index.html`
- Test: `tests/edit/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/edit/test_server.py`:

```python
def test_index_html_has_debug_controls(client):
    text = client.get("/").text
    for el_id in (
        "debug-capture-toggle", "debug-panel", "timeline-slider",
        "timeline-play-btn", "timeline-readout",
        "layer-markers-toggle", "layer-envelope-toggle",
        "layer-buds-toggle", "layer-shed-toggle",
    ):
        assert f'id="{el_id}"' in text, f"missing debug control id: {el_id}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/edit/test_server.py::test_index_html_has_debug_controls -v`
Expected: FAIL with `missing debug control id: debug-capture-toggle`.

- [ ] **Step 3: Add the controls**

In `src/palubicki/edit/static/index.html`, replace the `viewer-overlay` div (lines 32-36) with:

```html
      <div class="viewer-overlay">
        <button id="toggle-leaves-btn" type="button">Toggle leaves</button>
        <button id="toggle-wireframe-btn" type="button">Wireframe</button>
        <label class="debug-toggle">
          <input id="debug-capture-toggle" type="checkbox" /> Capture debug
        </label>
        <span id="spinner" class="spinner hidden">…</span>
      </div>
      <div id="debug-panel" class="debug-panel hidden">
        <div class="debug-layers">
          <label><input id="layer-markers-toggle" type="checkbox" checked /> Markers</label>
          <label><input id="layer-envelope-toggle" type="checkbox" checked /> Envelope</label>
          <label><input id="layer-buds-toggle" type="checkbox" checked /> Buds</label>
          <label><input id="layer-shed-toggle" type="checkbox" checked /> Shed</label>
        </div>
        <div class="debug-timeline">
          <button id="timeline-play-btn" type="button">▶</button>
          <input id="timeline-slider" type="range" min="0" max="0" step="1" value="0" />
          <span id="timeline-readout">—</span>
        </div>
      </div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/edit/test_server.py::test_index_html_has_debug_controls -v`
Expected: PASS.

- [ ] **Step 5: Add minimal styling**

Append to `src/palubicki/edit/static/style.css`:

```css
.debug-toggle { font-size: 12px; color: #333; display: inline-flex; align-items: center; gap: 4px; }
.debug-panel { position: absolute; left: 8px; bottom: 8px; right: 8px; background: rgba(255,255,255,0.9);
  border: 1px solid #ccc; border-radius: 6px; padding: 8px; font-size: 12px; }
.debug-panel.hidden { display: none; }
.debug-layers { display: flex; gap: 12px; margin-bottom: 6px; }
.debug-layers label { display: inline-flex; align-items: center; gap: 4px; }
.debug-timeline { display: flex; align-items: center; gap: 8px; }
.debug-timeline #timeline-slider { flex: 1; }
#timeline-readout { font-variant-numeric: tabular-nums; min-width: 160px; }
```

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/edit/static/index.html src/palubicki/edit/static/style.css tests/edit/test_server.py
git commit -m "edit/static: debug panel markup (toggle, timeline, layer checkboxes) (#29)"
```

---

## Task 7: Frontend — overlay layers, scrub, play/pause in `app.js`

**Files:**
- Modify: `src/palubicki/edit/static/app.js`
- Test: `tests/edit/test_server.py`

This task is the largest. It is split into wiring (Step 3) and the layer/scrub logic (Step 4); commit once at the end.

- [ ] **Step 1: Write the failing test**

Append to `tests/edit/test_server.py`:

```python
def test_app_js_has_debug_overlay_logic(client):
    body = client.get("/static/app.js").text
    for sym in (
        "fetchDebugTimeline", "buildDebugLayers", "setFrame",
        "togglePlay", "debug-capture-toggle", "timeline-slider",
        "THREE.Points", "BufferGeometry",
    ):
        assert sym in body, f"missing app.js debug symbol: {sym}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/edit/test_server.py::test_app_js_has_debug_overlay_logic -v`
Expected: FAIL with `missing app.js debug symbol: fetchDebugTimeline`.

- [ ] **Step 3: Wire capture toggle + generate → debug fetch**

In `src/palubicki/edit/static/app.js`:

(a) Extend the `state` object (lines 4-8) to hold debug state:

```javascript
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
```

(b) In `attachActions` (lines 149-155), add the debug control handlers:

```javascript
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
```

(c) In `initViewer` (after `const treeRoot = ...; scene.add(treeRoot);`, line 234), add a debug root group:

```javascript
  const debugRoot = new THREE.Group();
  scene.add(debugRoot);

  viewer = { scene, camera, renderer, controls, treeRoot, debugRoot, debugLayers: {} };
```

Delete the old `viewer = { scene, camera, renderer, controls, treeRoot };` line (line 236) — it is replaced above.

(d) In `regenerate`, after `await replaceTree(buf);` (line 279), add:

```javascript
    if (state.debug.enabled) {
      await fetchDebugTimeline();
    }
```

- [ ] **Step 4: Add the debug overlay functions**

Append to `src/palubicki/edit/static/app.js` (before the final `init();` call on line 347):

```javascript
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/edit/test_server.py -v`
Expected: PASS (the new `test_app_js_has_debug_overlay_logic` plus all existing app.js/server tests).

- [ ] **Step 6: Manual smoke test (record result in the PR, not a test)**

Run: `.venv/bin/palubicki edit` then open the printed URL. Check the capture toggle off by default; enable it → tree regenerates, markers/envelope/buds appear; slide the timeline (markers turn red as they die, buds move/change colour); press ▶ to animate; toggle each layer checkbox; export `.glb` and confirm it still loads (no overlay geometry in it).

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/edit/static/app.js tests/edit/test_server.py
git commit -m "edit/static: three.js debug overlay layers + timeline scrub/play (#29)"
```

---

## Task 8: Full test sweep + lint

**Files:** none (verification only)

- [ ] **Step 1: Run the focused suites**

Run: `.venv/bin/pytest tests/sim/test_markers.py tests/sim/test_debug_capture.py tests/sim/test_simulator.py tests/edit/test_server.py -v`
Expected: PASS.

- [ ] **Step 2: Run the full suite (excluding slow goldens if desired)**

Run: `.venv/bin/pytest -q -m "not slow"`
Expected: PASS. If any golden hash drifted, investigate — the collector path must not change evolution; a drift means Task 4 perturbed something.

- [ ] **Step 3: Lint**

Run: `.venv/bin/ruff check src/palubicki/sim/debug_capture.py src/palubicki/sim/simulator.py src/palubicki/sim/markers.py src/palubicki/edit/server.py`
Expected: no errors. Fix any reported.

- [ ] **Step 4: Commit (only if lint required fixes)**

```bash
git add -A
git commit -m "chore: lint fixes for #29 debug visualizer"
```

---

## Task 9: Docs update (finish the ticket)

**Files:**
- Modify: `docs/roadmap.md`
- Possibly modify: `docs/botany/simulator-gap-analysis.md`

- [ ] **Step 1: Move #29 to "Fait" in `docs/roadmap.md`**

In `docs/roadmap.md`, remove item **1. #29 — visualiseur des internes de sim** from the "À faire (dans l'ordre)" list, renumber the remaining items, and add a row to the "Fait" table:

```markdown
| #29 | Visualiseur des internes de sim : overlay debug (marqueurs vivants/morts, envelope, bourgeons par état, branches élaguées) + timeline scrub/play dans l'éditeur. Capture opt-in (collecteur observationnel branché dans `simulate_forest`, zéro coût par défaut), servie via `/api/debug` ; le `.glb` exporté est inchangé. | #54 |
```

- [ ] **Step 2: Assess `docs/botany/simulator-gap-analysis.md`**

This ticket is observability tooling — no botanical concept changed. Per `/work`, state this explicitly rather than editing silently. Add nothing to the gap-analysis unless a row genuinely changes; if you confirm none does, note in the PR description: "gap-analysis unchanged — #29 is observability tooling, no botanical concept touched."

- [ ] **Step 3: Commit**

```bash
git add docs/roadmap.md
git commit -m "docs: move #29 to Fait (sim-internals visualizer) (#54)"
```

---

## Self-review notes

- **Spec coverage:** static capture (T2) · per-frame killed/buds/shed deltas (T3) · collector threaded with zero default cost (T4) · capture-on-generate + cache + `/api/debug` (T5) · four overlay layers + envelope shapes + timeline + play/pause + per-layer toggles (T6, T7) · backward-compat guard (T4) · server flag/cache tests (T5) · manual frontend verification (T7) · docs (T9). All spec sections map to a task.
- **Deferred items stay deferred:** no quality ramp, attraction arrows, light voxels, obstacles, RESERVE/DEAD reconstruction, per-tree ids, streaming, or disk export appear in any task.
- **Type/name consistency:** `DebugCollector.capture_static/capture_frame/timeline`; `_current_iods`; `_round_vec`; `MarkerCloud.positions`/`alive_mask`; `simulate_forest(cfg, collector=None)`; server `app.state.last_debug`; frontend `fetchDebugTimeline`/`buildDebugLayers`/`buildKilledPrefix`/`clearDebugLayers`/`setFrame`/`togglePlay`/`stopPlay` and `viewer.debugLayers.{markers,envelope,buds,shed}` — used consistently across tasks.
- **Known nuance carried from spec:** the editor GLB is `trees[0]` only while the overlay captures all trees — identical in the single-tree case the editor drives; documented, not "fixed" here.
