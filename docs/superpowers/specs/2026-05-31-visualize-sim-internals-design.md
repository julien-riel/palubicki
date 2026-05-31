# Design — Visualize simulation internals (markers, envelope, buds, shed) with per-iteration playback

**Issue:** #29 · **Branch:** `issue-29-visualize-simulation-internals-markers` · **PR:** #54
**Date:** 2026-05-31

## Goal

The web editor (`src/palubicki/edit/`) is a black box: tweak parameters, hit generate,
see the final `.glb`. You can't see *why* the tree grew that way — where the markers
were, which buds were active vs dormant, which got shed, how the envelope constrained
things. This adds a read-only debug visualization layer to the editor so the
space-colonization model's intermediate state becomes inspectable, with a timeline to
replay growth iteration by iteration.

Primarily a development/debugging tool (would directly help diagnose bugs like #24 and
validate #25); secondarily a "how does this actually work" teaching view.

## Settled decisions (brainstorm)

| Decision | Choice |
|---|---|
| Server flow | **(A) Capture-on-generate + cache.** One sim run when the debug toggle is on; timeline cached on `app.state`; `/api/debug` serves it. No independent re-run (no drift, single sim cost). |
| Capture granularity | **Every iteration, no stride.** Delta-encoding keeps the dominant cost (markers) flat. Add a stride only if a long sim proves painful. |
| Marker count | **Reuse the configured count.** No separate debug knob — the overlay must explain the *actual* tree on screen (markers drive growth; a different count = a different tree). |
| Layer scope (this PR) | markers (alive/dead) · envelope (wireframe) · buds (colored by state) · **shed highlight** · timeline slider · play/pause · per-layer toggles. |
| Deferred | bud quality color-ramp · attraction-direction arrows · light-grid voxels · obstacles wireframe · RESERVE/DEAD bud states · per-tree filtering · streaming transport · disk export. |
| Forest scope | Capture at **forest level**: marker positions once (shared competition substrate); buds + shed **flattened across all trees**, no per-tree id in the schema. |

## Architecture & data flow

**Capture is observational; the sim core stays untouched.** `_iteration_step` has a
bit-exact backward-compat contract (single tree + no obstacles must evolve identically).
The collector never mutates sim state and never changes call order — it only reads and
diffs.

```
/api/generate (debug toggle ON)
   └─ simulate_forest(cfg, collector=DebugCollector())   # collector=None by default → zero cost
        ├─ build_forest                → collector.capture_static(forest)   # envelope + marker positions, ONCE
        └─ for each iteration:
             _iteration_step(...)       # unchanged
             collector.capture_frame(forest, t)           # diffs alive-mask & internode set vs previous frame
   └─ build_mesh(forest.trees[0]) → GLB                   # as today
   └─ app.state.last_debug = collector.timeline()         # cache
/api/debug (GET)  →  returns app.state.last_debug  (or 404 if none)
```

Deliberate choices:

- **Diff-based deltas, computed in the collector.** `markers_killed` = indices where the
  alive-mask flipped True→False since last frame; `shed` = internode endpoints present
  last frame but gone this frame. So `kill_near` and `shed_low_quality` need **no
  changes** — capture cannot perturb the deterministic evolution.
- **No cache key / hashing.** Single-user localhost editor; the client calls generate
  then debug in sequence, so `app.state.last_debug` (most recent capture) is sufficient.
  Per-cfg hashing would be YAGNI.
- **Gating via collector param.** The server creates the collector only when the request
  carries `debug: true`; `collector=None` is the default, so a normal generate pays
  nothing. (No `Config` flag — the param already gates cost and there is no headless
  consumer in scope.)

**Known nuance:** the editor's GLB is built from `trees[0]` only (existing behavior),
while the overlay captures all trees. Identical in the single-tree case the editor
normally drives; in forest mode the overlay is a superset. Not expanding mesh scope here.

## Capture module & wire schema

New module `src/palubicki/sim/debug_capture.py` — one class, single responsibility
(accumulate + delta-encode), testable without a server or browser.

```python
class DebugCollector:
    def capture_static(self, forest, cfg): ...   # envelope + marker positions; snapshot alive-mask & internode set
    def capture_frame(self, forest, t):  ...      # diff vs previous snapshot, append one frame
    def timeline(self) -> dict:          ...      # the JSON-ready payload below
```

Inter-frame state: `_prev_alive` (bool array) and `_prev_iods` (dict of internode
`id()` → endpoint pair), so each `capture_frame` is a cheap diff.

`/api/debug` returns this verbatim (positions once, deltas per frame):

```jsonc
{
  "envelope": { "shape": "half_ellipsoid", "center": [x,y,z], "radii": [rx,ry,rz] },
  "markers":  { "positions": [[x,y,z], ...] },          // static, sent once
  "frames": [
    {
      "t": 1.0,                                          // clock years
      "markers_killed": [12, 88, 130],                   // indices into markers.positions, NEW this frame
      "buds": [ { "p":[x,y,z], "dir":[x,y,z], "state":"ACTIVE" } ],  // flattened across trees
      "shed": [ [[x,y,z],[x,y,z]], ... ]                 // internode endpoint pairs culled this frame
    }
  ]
}
```

Notes:
- **Buds** come from each tree's `active_buds` → states **ACTIVE / DORMANT** (the live
  set). RESERVE buds live on `node.dormant_reserve_buds`; DEAD buds are already dropped
  from `active_buds`. MVP shows the active/dormant set; RESERVE/DEAD is a documented
  deferred enrichment, not faked.
- **Envelope** read from `forest.per_tree_cfgs[0].envelope` (the displayed tree's region).
- The static marker list is the full as-sampled cloud; "alive" at frame *i* = "not in any
  `markers_killed` set up to and including *i*."
- Floats rounded (≈4 decimals) to keep payload lean — cosmetic only.

## Frontend (`app.js` + `index.html`)

Debug layer slots in as a self-contained group, reasoned about / removable independently.

- **`debugRoot` group** with four children added to the scene next to the GLB:
  - `markers` — one `THREE.Points` (positions uploaded once); per-frame recolor a
    vertex-color buffer (alive = pale green, dead = dark/red) from the cumulative killed
    set up to the current frame. No geometry rebuild on scrub.
  - `envelope` — a `THREE.Mesh` wireframe sized from `shape`/`radii`
    (sphere/ellipsoid/half-ellipsoid/cone → matching geometry).
  - `buds` — a `THREE.Points` rebuilt per frame, vertex-colored by state (ACTIVE /
    DORMANT distinct colors).
  - `shed` — a `THREE.LineSegments`, cumulative shed segments up to the current frame
    (persist as you scrub forward).
- **Capture toggle:** a checkbox in the controls. When checked, `/api/generate` sends
  `debug: true`; on success the client then `GET /api/debug` and builds the layers.
  Unchecked → behaves exactly as today (no debug fetch).
- **Timeline slider:** a range input `[0 … frames.length-1]` + a readout (`t=…yr`,
  alive/dead counts, bud count). `setFrame(i)`:
  - markers → recolor by cumulative killed set ≤ i (precomputed prefix → O(Δ) per step)
  - buds → rebuild from `frames[i].buds`
  - shed → cumulative segments ≤ i
  - envelope → static
- **Play/pause** button steps the slider on a timer (animate the growth).
- **Per-layer visibility toggles:** four checkboxes (markers / envelope / buds / shed)
  flipping each `Object3D.visible`.
- **Scrub cost:** precompute the cumulative killed-prefix once after fetch, so each
  `setFrame` is O(buds + Δmarkers), not O(all markers).

## Testing & verification

**Python (collector — the real logic):**
- Unit tests: build a tiny forest, run a few iterations with a collector, assert —
  - `capture_static` records all marker positions once + envelope shape/radii/center;
  - `markers_killed` across frames is a **partition** of the markers that actually died
    (no index repeated; union = total killed), checked against `forest.markers` alive-mask;
  - `shed` segments match internodes removed that step;
  - `buds` per frame match each tree's `active_buds` (count + states).
- **Backward-compat guard:** one test asserts a capture-enabled run yields the same final
  tree hash as a `collector=None` run — the collector doesn't perturb evolution. (Existing
  species goldens already lock the no-collector path.)

**Server:**
- `POST /api/generate` with `debug: true` → 200 GLB **and** `app.state.last_debug`
  populated; `GET /api/debug` → timeline JSON with expected top-level keys.
- `POST /api/generate` without the flag → `app.state.last_debug` stays `None`;
  `GET /api/debug` → 404.

**Frontend:** no JS test harness in the repo → manual verification via `palubicki edit`
(see acceptance checklist).

## Acceptance criteria (from #29)

- [ ] `palubicki edit` with the debug toggle on overlays markers, envelope, and buds on the tree.
- [ ] A timeline control scrubs through iterations and overlays update (markers die, buds change state); play/pause animates.
- [ ] Each layer toggles independently; debug capture is off by default and adds no measurable cost to a normal generate.
- [ ] The exported `.glb` is unchanged (no debug geometry leaks into output).

## Out of scope (this PR)

Bud quality ramp · attraction arrows · light-grid voxels · obstacles wireframe ·
RESERVE/DEAD bud states · per-tree filtering · object picking/inspection · streaming
transport · disk export of the timeline · headless/preview PNG overlays · full-forest GLB
in the editor.

## Docs to update at finish (per `/work`)

- `docs/roadmap.md` — move #29 from "À faire" to "Fait" (with PR #54); re-check ordering.
- `docs/botany/simulator-gap-analysis.md` — this is observability tooling (no botanical
  concept touched), so likely **no edit needed**; confirm explicitly at finish.
