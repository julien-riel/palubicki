# Petiole geometry for simple leaves — design (#5)

**Issue:** `geom/leaves.py: petiole geometry between bud site and blade` (#5)
**Branch:** `issue-5-petiole-attache-de-feuille-orientation`
**Date:** 2026-05-31

## Problem

Simple leaves anchor the blade directly at the bud-site node — there is no stalk
between the branch and the blade, so leaves read as "glued" to the stem. A real
petiole (a thin tapered stalk, a few mm wide, 10–50 % of blade length) removes
that artifact and is the anchor around which any future per-leaf orientation
control rotates the blade.

## Key finding: the machinery already half-exists

- `build_leaves_primitive` (`geom/leaves.py`) **already** routes simple leaves
  through `compound_layout("simple", …)`, which returns one identity leaflet at
  `(0,0)` and an empty rachis.
- `build_rachis_primitive` (`geom/compound_leaf.py`) **already** lifts petiole +
  rachis tubes per selected leaf — it just early-returns empty for
  `leaf_kind == "simple"`.
- `petiole_length_ratio` already exists in `GeomConfig` (default 0.4), consumed
  only on the compound path today.

So #5 is mostly *enabling existing machinery* for the simple path, plus taper,
droop, and a distinct material.

## Design

### 1. Core idea — unify onto the rachis/leaflet path

A simple leaf becomes a `CompoundLayout` with **one petiole segment + one blade
leaflet at the petiole tip**. Simple and compound leaves then share one
petiole/blade-anchor/lift path. `petiole_length == 0` → no segment, blade at the
node (needles / sessile leaves; byte-identical to today).

### 2. Layout — `compound_leaf.py::compound_layout`, simple branch

Today: `CompoundLayout(leaflets=[((0,0), 0.0, 1.0)], rachis_segments=[])`.

New, when `petiole_length > 0`:
- blade leaflet at `(0, petiole_length)` (instead of `(0,0)`),
- one petiole segment `((0,0) → (0, petiole_length))`.

`_lift_compound_leaf` already maps a leaflet at `v0` to
`origin = center + size·(u0·rot_axis_u + v0·leaf_up)`, so the blade rides up the
petiole with **no change to the lift code**.

### 3. Taper — `RachisSeg` + `_emit_cylinder`

`RachisSeg` grows from `(start_uv, end_uv, radius)` to
`(start_uv, end_uv, r0, r1)`; `_emit_cylinder` takes `radius0, radius1` and uses
`r0` on the bottom ring, `r1` on the top. **All existing layout builders
(`_pinnate`, `_palmate`, `_bipinnate`) pass `(radius, radius)`** so compound
(ash) geometry is unchanged byte-for-byte. The simple petiole tapers
`petiole_radius → petiole_radius · petiole_taper` (≈ 0.6).

### 4. Droop — `petiole_droop_deg`

Down is **−Y** (matches `sim/sag.py` default direction `(0, −1, 0)`). Droop
rotates the leaf's `leaf_up` axis toward −Y by `petiole_droop_deg` **before**
placing the petiole tip and blade — a **rigid** rotation, so the blade tilts
with the petiole ("the blade rotates around the petiole", per the issue) and
**blade area is preserved** (rotation-invariant → the leaf-area diagnostic is
unaffected).

To keep the petiole tube and the blade consistent, extract a shared helper
`leaf_basis(direction, azimuth, splay_rad, droop_rad) -> (rot_axis_u, leaf_up,
rot_axis_w)` used by both `_lift_compound_leaf` and `build_rachis_primitive`
(this also removes the basis math currently duplicated across the two).

Droop is a **fixed angle** for this PR (deterministic, in scope). Age-ramped
droop (à la epinasty's `1 − exp(−age/τ)`) is a later refinement.

### 5. Material — `petiole_color`

New `"petiole"` material built from `cfg.geom.petiole_color`, distinct from the
bark-colored `"rachis"` material. The simple-leaf petiole tube renders with it;
the compound rachis keeps `"rachis"` (unchanged).

### 6. Config + wiring

`GeomConfig` adds:
- `petiole_radius_ratio` (≈ 0.02, fraction of leaf size),
- `petiole_taper` (≈ 0.6, tip/base radius ratio),
- `petiole_sides` (default = existing rachis ring-side count),
- `petiole_droop_deg` (0.0),
- `petiole_color` (greenish default RGB).

`petiole_length_ratio` already exists and is reused.

`builder.py`:
- builds a `leaflet_specs` for simple leaves too (carrying `petiole_length` from
  `petiole_length_ratio`),
- calls `build_rachis_primitive` with the **petiole** material whenever
  `petiole_length_ratio > 0` (simple) or for compound leaves (rachis material),
- the `leaf_kind == "simple"` early-return in `build_rachis_primitive` is
  dropped; the existing "no rachis_segments → empty" guard covers needles
  (`petiole_length == 0`).

### 7. Species YAML

- oak / birch / maple: visible petioles (`petiole_length_ratio` ≈ 0.2–0.4).
- pine / fir: `petiole_length_ratio: 0` (no stalk — acceptance criterion).
- ash (compound, pinnate): unchanged.

## Invariants & testing (TDD)

- **Leaf-area parity** (`test_leaf_area_matches_geom_helper`) stays green: the
  petiole is its own primitive, and blade area is translation/rotation-invariant.
  Confirm the geom helper counts blade area only (not the petiole tube).
- **Unit tests:**
  - simple leaf with `petiole_length > 0` emits exactly one petiole segment of
    the expected length;
  - `petiole_length == 0` → zero segments + blade at the node (byte-identical to
    legacy output);
  - taper: bottom ring radius `r0`, top ring radius `r1 = r0 · taper`;
  - droop: the petiole tip / blade origin moves toward −Y as `petiole_droop_deg`
    increases.
- **Vertex-count bound:** total grows by `~petiole_sides × n_leaves` (acceptance
  criterion — no order-of-magnitude regression).
- **Goldens** regenerated (`pytest --update-goldens`): oak, birch, maple, pine,
  fir, ellipsoid. ash expected unchanged (verify).

## Acceptance criteria (from the issue)

- [ ] `generate --species oak` → visibly stalked leaves.
- [ ] `generate --species pine` → no visible stalks (`petiole_length_ratio = 0`).
- [ ] Vertex count grows by ≤ ~`petiole_sides × n_leaves`.
- [ ] Leaf goldens updated in the same PR.

## Out of scope

- Stipules (`simulator-gap-analysis.md` §2 marks SKIP).
- Per-leaf stochastic petiole-length variation.
- Sessile leaves as a distinct code path (covered by `length_ratio = 0`).
- Age-ramped droop.
