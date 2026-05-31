# Petiole Geometry for Simple Leaves — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give simple leaves a rendered, tapered, optionally-drooping petiole stalk between the bud-site node and the blade base, by unifying simple leaves onto the existing compound-leaf rachis machinery.

**Architecture:** A simple leaf becomes a `CompoundLayout` with one petiole segment plus one blade leaflet placed at the petiole tip. Simple and compound leaves then share the same petiole/blade-anchor/lift path. Taper is added by giving each rachis segment a start/end radius; droop is a rigid rotation of the per-leaf basis toward gravity (−Y); the petiole renders as its own `"petiole"`-material tube. `petiole_length_ratio == 0` short-circuits to today's behavior (needles/sessile, byte-identical).

**Tech Stack:** Python 3, NumPy, dataclasses; pytest; ruff. Package under `src/palubicki/`. venv at `.venv/` (always invoke tools as `.venv/bin/<tool>`).

**Spec:** `docs/superpowers/specs/2026-05-31-petiole-geometry-design.md`

---

## Background facts (read once before starting)

- **Down is −Y.** `sim/sag.py` default gravity direction is `(0, −1, 0)`.
- **The blade is intentionally sheared by splay.** In `_lift_blade`, the simple
  identity leaflet uses `basis_u = rot_axis_u` and `basis_v = leaf_up`, and
  `leaf_up = cos(splay)·d + sin(splay)·rot_axis_u` is *not* orthogonal to
  `rot_axis_u`. The angle between them gives the rendered blade area a `cos(splay)`
  factor, which `sim/diagnostics.py::_total_leaf_area` reproduces analytically.
  **A rigid rotation of the whole basis preserves that angle → preserves area →
  keeps `test_leaf_area_matches_geom_helper` green.** Droop MUST therefore rotate
  `rot_axis_u`, `leaf_up`, AND `rot_axis_w` by the same rotation.
- **The leaf-area diagnostic counts blade leaflets only** (it reads
  `layout.leaflets`, never `rachis_segments`) and the parity test filters by
  `prim.material.name == "leaf"`. So a separate `"petiole"` material primitive is
  automatically excluded. The diagnostic needs **no changes**.
- **Golden incrementality:** Tasks 1–4 are behavior-preserving for the rendered
  `.glb` (compound radii pass `(r, r)`; simple `petiole_length` stays `0.0` until
  the builder is wired in Task 5). Goldens should stay green through Task 4.
  Tasks 5–6 intentionally change oak/birch/maple goldens; pine/fir stay
  byte-identical (their `petiole_length_ratio` is set to `0`).

## File Structure

- **Modify** `src/palubicki/geom/compound_leaf.py` — `RachisSeg` becomes a
  4-tuple `(start_uv, end_uv, r0, r1)`; `_emit_cylinder` interpolates radius;
  `compound_layout` simple branch emits a petiole segment + blade-at-tip;
  `build_rachis_primitive` unpacks the 4-tuple, uses the shared `leaf_basis`
  helper, and no longer early-returns for `leaf_kind == "simple"`.
- **Modify** `src/palubicki/geom/leaves.py` — new shared
  `leaf_basis(direction, azimuth, splay_rad, droop_rad)` helper (the single
  source of the per-leaf frame, with droop); `_lift_compound_leaf` and
  `build_leaves_primitive` gain a `droop_rad` / `petiole` path and call the helper.
- **Modify** `src/palubicki/config.py` — five new `GeomConfig` fields.
- **Modify** `src/palubicki/geom/builder.py` — build `leaflet_specs` for simple
  leaves too, add the `"petiole"` material, thread droop, call
  `build_rachis_primitive` for simple petioles.
- **Modify** species YAML under `src/palubicki/configs/species/` — pine/fir → 0;
  oak/birch/maple → visible petiole (+ droop/color).
- **Modify/Add tests** under `tests/geom/`, regenerate `tests/golden/data/*.sha256`.
- **Modify docs** `docs/roadmap.md`, `docs/botany/simulator-gap-analysis.md`.

---

## Task 1: Taper-capable cylinder + 4-tuple `RachisSeg`

Make rachis segments carry a start and end radius so the petiole can taper, while
keeping all current (constant-radius) callers byte-identical.

**Files:**
- Modify: `src/palubicki/geom/compound_leaf.py` (`RachisSeg` line 16,
  `_emit_cylinder` lines 132–167, `_pinnate`/`_palmate`/`_bipinnate` lines 51–120,
  `build_rachis_primitive` segment loop lines 224–234)
- Test: `tests/geom/test_compound_leaf.py`

- [ ] **Step 1: Write the failing test** for tapered + constant cylinders.

Add to `tests/geom/test_compound_leaf.py`:

```python
from palubicki.geom.compound_leaf import _emit_cylinder


def test_emit_cylinder_constant_radius_rings():
    p, _, _, idx = _emit_cylinder((0, 0, 0), (0, 1, 0), 0.5, 0.5, 4, 0)
    # 4 sides -> 8 ring vertices (bottom 0-3, top 4-7), 6*4 indices
    assert p.shape == (8, 3)
    assert idx.shape == (24,)
    bottom_r = [float(np.hypot(v[0], v[2])) for v in p[:4]]
    top_r = [float(np.hypot(v[0], v[2])) for v in p[4:]]
    assert all(abs(r - 0.5) < 1e-6 for r in bottom_r + top_r)


def test_emit_cylinder_tapers_from_r0_to_r1():
    p, _, _, _ = _emit_cylinder((0, 0, 0), (0, 1, 0), 0.5, 0.2, 4, 0)
    bottom_r = [float(np.hypot(v[0], v[2])) for v in p[:4]]
    top_r = [float(np.hypot(v[0], v[2])) for v in p[4:]]
    assert all(abs(r - 0.5) < 1e-6 for r in bottom_r)
    assert all(abs(r - 0.2) < 1e-6 for r in top_r)
```

- [ ] **Step 2: Run the test to verify it fails.**

Run: `.venv/bin/pytest tests/geom/test_compound_leaf.py::test_emit_cylinder_tapers_from_r0_to_r1 -v`
Expected: FAIL — `_emit_cylinder()` takes 5 positional args, not 6 (signature mismatch / TypeError).

- [ ] **Step 3: Update `RachisSeg`, `_emit_cylinder`, and the layout builders.**

In `src/palubicki/geom/compound_leaf.py`, change the type alias (line 15–16):

```python
# Rachis centerline segment: (start_uv, end_uv, r0, r1) in size-units; r0 is the
# radius at start_uv, r1 at end_uv (equal r0==r1 = constant-radius tube).
RachisSeg = tuple[tuple[float, float], tuple[float, float], float, float]
```

Replace `_emit_cylinder` (lines 132–167) with the tapered version:

```python
def _emit_cylinder(p0, p1, radius0, radius1, ring_sides, base_index):
    """A capped-less cylinder between 3D points p0->p1, radius0 at p0 and
    radius1 at p1 (radius0==radius1 = constant). Returns
    (positions(2R,3), normals(2R,3), uvs(2R,2), indices(6R,)) with indices
    offset by base_index."""
    # Function-local import to avoid a leaves<->compound_leaf import cycle.
    from palubicki.geom.leaves import _basis_perpendicular_to

    p0 = np.asarray(p0, dtype=np.float64)
    p1 = np.asarray(p1, dtype=np.float64)
    axis = p1 - p0
    length = float(np.linalg.norm(axis))
    if length < 1e-12:
        z = np.zeros((0, 3), np.float32)
        return z, z, np.zeros((0, 2), np.float32), np.zeros((0,), np.uint32)
    axis = axis / length
    right, forward = _basis_perpendicular_to(axis)
    ang = np.linspace(0.0, 2.0 * np.pi, ring_sides, endpoint=False)
    ring = (
        np.cos(ang)[:, None] * right[None, :]
        + np.sin(ang)[:, None] * forward[None, :]
    )  # (R, 3) unit
    nrm = ring.astype(np.float32)
    bottom = p0[None, :] + radius0 * ring
    top = p1[None, :] + radius1 * ring
    positions = np.concatenate([bottom, top]).astype(np.float32)
    normals = np.concatenate([nrm, nrm])
    uvs = np.zeros((2 * ring_sides, 2), np.float32)
    idx: list[int] = []
    for k in range(ring_sides):
        a = k
        b = (k + 1) % ring_sides
        c = ring_sides + k
        dd = ring_sides + (k + 1) % ring_sides
        idx += [a, c, b, b, c, dd]
    indices = np.asarray(idx, dtype=np.uint32) + np.uint32(base_index)
    return positions, normals, uvs, indices
```

In `_pinnate` (lines 68–71) replace the `segs` block:

```python
    segs: list[RachisSeg] = [
        ((0.0, 0.0), (0.0, v0), radius, radius),
        ((0.0, v0), (0.0, v1), radius, radius),
    ]
```

In `_palmate` (lines 84–86) replace the `segs` block:

```python
    segs: list[RachisSeg] = (
        [((0.0, 0.0), (0.0, petiole_length), radius, radius)]
        if petiole_length > 0 else []
    )
```

In `_bipinnate`, replace the initial `segs` (lines 92–95):

```python
    segs: list[RachisSeg] = [
        ((0.0, 0.0), (0.0, petiole_length), radius, radius),
        ((0.0, petiole_length), (0.0, petiole_length + rachis_length), radius, radius),
    ]
```

and the secondary-axis append (line 112):

```python
            segs.append(((base_u, base_v), (end_u, end_v), radius * 0.6, radius * 0.6))
```

In `build_rachis_primitive`, change the segment loop (lines 224–227):

```python
        for s_uv, e_uv, r0, r1 in layout.rachis_segments:
            p, nn, uv, ix = _emit_cylinder(
                lift(s_uv), lift(e_uv), r0 * eff, r1 * eff, ring_sides, cursor
            )
```

- [ ] **Step 4: Run the new + existing compound tests to verify they pass.**

Run: `.venv/bin/pytest tests/geom/test_compound_leaf.py -v`
Expected: PASS (new cylinder tests pass; existing layout tests unaffected — they assert segment *counts*, not tuple contents).

- [ ] **Step 5: Run the species goldens to confirm ash is unchanged.**

Run: `.venv/bin/pytest tests/golden/test_species_goldens.py -v`
Expected: PASS for all species (ash radii pass `(r, r)` → byte-identical GLB).

- [ ] **Step 6: Commit.**

```bash
git add src/palubicki/geom/compound_leaf.py tests/geom/test_compound_leaf.py
git commit -m "geom: taper-capable RachisSeg (start/end radius) (#5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Shared `leaf_basis` helper with droop

Extract the per-leaf frame computation (currently duplicated in
`_lift_compound_leaf` and `build_rachis_primitive`) into one helper that also
applies gravity droop as a rigid rotation. Behavior is byte-identical when
`droop_rad == 0`.

**Files:**
- Modify: `src/palubicki/geom/leaves.py` (add `leaf_basis`; refactor
  `_lift_compound_leaf` basis math, lines ~242–248)
- Modify: `src/palubicki/geom/compound_leaf.py` (`build_rachis_primitive` basis
  math, lines 213–217)
- Test: `tests/geom/test_leaves.py`

- [ ] **Step 1: Write the failing tests** for `leaf_basis`.

Add to `tests/geom/test_leaves.py`:

```python
from palubicki.geom.leaves import leaf_basis


def test_leaf_basis_no_droop_matches_inline_math():
    import math
    d = np.array([0.0, 1.0, 0.0])
    az, splay = 0.7, math.radians(30.0)
    u, up, w = leaf_basis(d, az, splay, 0.0)
    # orthonormal lateral/normal axes, unit leaf_up
    assert abs(np.linalg.norm(u) - 1.0) < 1e-9
    assert abs(np.linalg.norm(w) - 1.0) < 1e-9
    assert abs(np.linalg.norm(up) - 1.0) < 1e-9
    # splay tilts leaf_up off the stem by exactly splay (dot with d == cos splay)
    assert abs(float(np.dot(up, d)) - math.cos(splay)) < 1e-9


def test_leaf_basis_droop_rotates_toward_minus_y():
    import math
    # horizontal stem along +X, no splay -> leaf_up == +X
    d = np.array([1.0, 0.0, 0.0])
    _, up0, _ = leaf_basis(d, 0.0, 0.0, 0.0)
    assert abs(up0[0] - 1.0) < 1e-9
    # droop 90 deg -> leaf_up rotates to -Y
    _, up90, _ = leaf_basis(d, 0.0, 0.0, math.radians(90.0))
    assert up90[1] < -0.999


def test_leaf_basis_droop_is_rigid_preserves_splay_angle():
    import math
    d = np.array([0.0, 1.0, 0.0])
    az, splay, droop = 1.2, math.radians(35.0), math.radians(40.0)
    u0, up0, _ = leaf_basis(d, az, splay, 0.0)
    u1, up1, _ = leaf_basis(d, az, splay, droop)
    # the angle between lateral axis and leaf_up (the area-defining shear) is
    # invariant under the rigid droop rotation
    assert abs(float(np.dot(u0, up0)) - float(np.dot(u1, up1))) < 1e-9
```

- [ ] **Step 2: Run to verify failure.**

Run: `.venv/bin/pytest tests/geom/test_leaves.py::test_leaf_basis_droop_rotates_toward_minus_y -v`
Expected: FAIL — `cannot import name 'leaf_basis'`.

- [ ] **Step 3: Add `leaf_basis` and refactor the two call sites.**

In `src/palubicki/geom/leaves.py`, add near the top (after the imports, before
`build_leaves_primitive`), and define the module constant:

```python
_DOWN = np.array([0.0, -1.0, 0.0])


def leaf_basis(direction, azimuth, splay_rad, droop_rad=0.0):
    """The per-leaf orthogonal-ish frame: (rot_axis_u, leaf_up, rot_axis_w).

    rot_axis_u is the lateral (blade-width) axis at phyllotactic ``azimuth``;
    rot_axis_w is the blade normal; leaf_up is the petiole / blade-length axis,
    tilted off the stem by ``splay_rad``. ``droop_rad`` > 0 rigidly rotates all
    three axes toward gravity (-Y), so the petiole and blade bend down together
    while the rot_axis_u<->leaf_up angle (the cos(splay) blade-area shear) is
    preserved. droop_rad == 0 reproduces the legacy inline math exactly.
    """
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    right, forward = _basis_perpendicular_to(d)
    rot_axis_u = math.cos(azimuth) * right + math.sin(azimuth) * forward
    rot_axis_w = -math.sin(azimuth) * right + math.cos(azimuth) * forward
    leaf_up = math.cos(splay_rad) * d + math.sin(splay_rad) * rot_axis_u
    if droop_rad != 0.0:
        k = np.cross(leaf_up, _DOWN)
        kn = float(np.linalg.norm(k))
        if kn > 1e-9:
            k = k / kn
            c, s = math.cos(droop_rad), math.sin(droop_rad)

            def _rot(v):
                return v * c + np.cross(k, v) * s + k * float(np.dot(k, v)) * (1.0 - c)

            rot_axis_u = _rot(rot_axis_u)
            leaf_up = _rot(leaf_up)
            rot_axis_w = _rot(rot_axis_w)
    return rot_axis_u, leaf_up, rot_axis_w
```

In `_lift_compound_leaf` (`src/palubicki/geom/leaves.py`), add `droop_rad=0.0` to
the signature and replace the inline basis block. Change the signature line:

```python
def _lift_compound_leaf(center, direction, azimuth, size, splay_rad, n_planes,
                        leaflets, blade_pos_unit, blade_uv, blade_idx,
                        out_pos, out_norm, out_uv, out_idx, base, droop_rad=0.0):
```

and replace the block currently computing `d`, `right`, `forward`,
`rot_axis_u`, `rot_axis_w`, `leaf_up` (the lines from `d = np.asarray(direction…`
through `leaf_up = math.cos(splay_rad) * d + math.sin(splay_rad) * rot_axis_u`)
with:

```python
    rot_axis_u, leaf_up, rot_axis_w = leaf_basis(
        direction, azimuth, splay_rad, droop_rad
    )
    blade_v_count = blade_pos_unit.shape[0]
    blade_i_count = blade_idx.shape[0]
    leaf_center = np.asarray(center, dtype=np.float64)
```

(Keep everything from `per_leaflet_v = …` onward unchanged.)

In `build_rachis_primitive` (`src/palubicki/geom/compound_leaf.py`), add
`droop_deg=0.0` to the signature, import `leaf_basis`, and replace the inline
basis block. Change the signature:

```python
def build_rachis_primitive(
    tree, *, material, leaf_size, foliage_depth, leaf_kind, leaflet_specs,
    ring_sides=5, needle_cluster_spacing=0.0, sun_shade_k=0.0, splay_deg=0.0,
    droop_deg=0.0,
):
```

Update the function-local import to add `leaf_basis`:

```python
    from palubicki.geom.leaves import (
        compute_effective_leaf_size,
        leaf_basis,
        selected_leaves,
    )
```

and replace the per-leaf basis block (the lines from `d = np.asarray(stem_dir…`
through `leaf_up = math.cos(splay_rad) * d + math.sin(splay_rad) * rot_axis_u`)
with:

```python
    droop_rad = math.radians(droop_deg)
    pos_chunks, nrm_chunks, uv_chunks, idx_chunks = [], [], [], []
    cursor = 0
    for leaf, stem_dir, source_iod, render_pos in records:
        eff = compute_effective_leaf_size(source_iod, leaf_size, sun_shade_k)
        rot_axis_u, leaf_up, _ = leaf_basis(
            stem_dir, leaf.azimuth, splay_rad, droop_rad
        )
        center = np.asarray(render_pos, dtype=np.float64)
```

(The existing `splay_rad = math.radians(splay_deg)` line stays above the loop.
`_basis_perpendicular_to` is no longer used directly here; remove it from the
import only if nothing else references it in this function — leave the import for
`_emit_cylinder`'s function-local import, which is separate.)

- [ ] **Step 4: Run the helper tests and the leaf suite.**

Run: `.venv/bin/pytest tests/geom/test_leaves.py tests/geom/test_compound_leaf.py -v`
Expected: PASS.

- [ ] **Step 5: Run goldens to confirm no change (droop defaults to 0).**

Run: `.venv/bin/pytest tests/golden/ -v`
Expected: PASS (refactor is byte-identical at `droop_rad == 0`).

- [ ] **Step 6: Commit.**

```bash
git add src/palubicki/geom/leaves.py src/palubicki/geom/compound_leaf.py tests/geom/test_leaves.py
git commit -m "geom: shared leaf_basis helper with gravity droop (#5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Petiole segment in the simple layout

Teach `compound_layout`'s simple branch to emit a tapered petiole segment and
place the blade leaflet at the petiole tip when `petiole_length > 0`.

**Files:**
- Modify: `src/palubicki/geom/compound_leaf.py` (`compound_layout` signature +
  simple branch, lines 28–48)
- Test: `tests/geom/test_compound_leaf.py`

- [ ] **Step 1: Write the failing tests.**

Add to `tests/geom/test_compound_leaf.py`:

```python
def test_simple_layout_with_petiole_emits_segment_and_blade_at_tip():
    layout = compound_layout(
        "simple", leaflet_count=1, leaflet_pair_count=0,
        terminal_leaflet=False, rachis_length=0.0,
        petiole_length=0.3, rachis_radius=0.02, petiole_taper=0.6,
    )
    # one blade leaflet, anchored at the petiole tip (0, 0.3)
    assert layout.leaflets == [((0.0, 0.3), 0.0, 1.0)]
    # one tapered petiole segment from base to tip
    assert len(layout.rachis_segments) == 1
    s_uv, e_uv, r0, r1 = layout.rachis_segments[0]
    assert s_uv == (0.0, 0.0)
    assert e_uv == (0.0, 0.3)
    assert abs(r0 - 0.02) < 1e-12
    assert abs(r1 - 0.02 * 0.6) < 1e-12


def test_simple_layout_zero_petiole_is_legacy_identity():
    layout = compound_layout(
        "simple", leaflet_count=1, leaflet_pair_count=0,
        terminal_leaflet=False, rachis_length=0.0,
        petiole_length=0.0, rachis_radius=0.02, petiole_taper=0.6,
    )
    assert layout.leaflets == [((0.0, 0.0), 0.0, 1.0)]
    assert layout.rachis_segments == []
```

- [ ] **Step 2: Run to verify failure.**

Run: `.venv/bin/pytest tests/geom/test_compound_leaf.py::test_simple_layout_with_petiole_emits_segment_and_blade_at_tip -v`
Expected: FAIL — `compound_layout()` got an unexpected keyword `petiole_taper` (and the simple branch ignores `petiole_length`).

- [ ] **Step 3: Add `petiole_taper` and rewrite the simple branch.**

In `src/palubicki/geom/compound_leaf.py`, update `compound_layout` (lines 28–48).
Add the kwarg and rewrite the `simple` branch:

```python
def compound_layout(
    kind: str,
    *,
    leaflet_count: int,
    leaflet_pair_count: int,
    terminal_leaflet: bool,
    rachis_length: float,
    petiole_length: float,
    rachis_radius: float,
    petiole_taper: float = 1.0,
) -> CompoundLayout:
    if kind == "simple":
        if petiole_length > 0.0:
            r0 = rachis_radius
            r1 = rachis_radius * petiole_taper
            return CompoundLayout(
                leaflets=[((0.0, petiole_length), 0.0, 1.0)],
                rachis_segments=[((0.0, 0.0), (0.0, petiole_length), r0, r1)],
            )
        return CompoundLayout(leaflets=[((0.0, 0.0), 0.0, 1.0)], rachis_segments=[])
    if kind == "pinnate":
        return _pinnate(leaflet_count, terminal_leaflet, rachis_length,
                        petiole_length, rachis_radius)
    if kind == "palmate":
        return _palmate(leaflet_count, petiole_length, rachis_radius)
    if kind == "bipinnate":
        return _bipinnate(leaflet_pair_count, leaflet_count, rachis_length,
                          petiole_length, rachis_radius)
    raise ValueError(f"unknown compound leaf kind: {kind!r}")
```

- [ ] **Step 4: Run the compound tests.**

Run: `.venv/bin/pytest tests/geom/test_compound_leaf.py -v`
Expected: PASS (existing simple-identity test still passes — callers still pass
`petiole_length=0.0` until Task 5).

- [ ] **Step 5: Run goldens to confirm still green.**

Run: `.venv/bin/pytest tests/golden/ -v`
Expected: PASS (no caller sets `petiole_length>0` for simple yet).

- [ ] **Step 6: Commit.**

```bash
git add src/palubicki/geom/compound_leaf.py tests/geom/test_compound_leaf.py
git commit -m "geom: simple-leaf petiole segment + blade-at-tip in compound_layout (#5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Config fields

Add the five petiole `GeomConfig` fields. The YAML loader reads dataclass fields
dynamically, so adding them here makes them YAML-settable automatically.

**Files:**
- Modify: `src/palubicki/config.py` (after `petiole_length_ratio`, line 145)
- Test: `tests/test_config.py` (create if absent)

- [ ] **Step 1: Write the failing test.**

Add to `tests/test_config.py` (create the file if it does not exist, with the
import):

```python
from palubicki.config import Config, GeomConfig
from palubicki.config import _from_dict  # loader used for YAML dicts


def test_geom_config_has_petiole_defaults():
    g = GeomConfig()
    assert g.petiole_radius_ratio == 0.02
    assert g.petiole_taper == 0.6
    assert g.petiole_sides == 4
    assert g.petiole_droop_deg == 0.0
    assert g.petiole_color == (0.32, 0.42, 0.18)


def test_geom_config_petiole_fields_load_from_dict():
    g = _from_dict(GeomConfig, {
        "petiole_length_ratio": 0.25,
        "petiole_droop_deg": 15.0,
        "petiole_color": [0.3, 0.4, 0.2],
    })
    assert g.petiole_length_ratio == 0.25
    assert g.petiole_droop_deg == 15.0
    assert g.petiole_color == (0.3, 0.4, 0.2)
```

(If `_from_dict` is private/named differently, use the public species loader
instead — verify the exact name in `src/palubicki/config.py`; the agent report
shows `_from_dict` and `_coerce`.)

- [ ] **Step 2: Run to verify failure.**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'GeomConfig' object has no attribute 'petiole_radius_ratio'`.

- [ ] **Step 3: Add the fields.**

In `src/palubicki/config.py`, immediately after the `petiole_length_ratio` line
(line 145), insert:

```python
    petiole_radius_ratio: float = 0.02  # simple-leaf petiole base radius / leaf_size
    petiole_taper: float = 0.6          # petiole tip radius / base radius
    petiole_sides: int = 4              # petiole tube cross-section polygon sides
    petiole_droop_deg: float = 0.0      # rigid downward (-Y) bend of petiole+blade
    petiole_color: tuple[float, float, float] = (0.32, 0.42, 0.18)
```

- [ ] **Step 4: Run the config tests.**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "config: petiole geom fields (radius/taper/sides/droop/color) (#5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Wire the builder — render the simple-leaf petiole

Build `leaflet_specs` for simple leaves, thread droop into the blade lift, add the
`"petiole"` material, and emit the petiole tube via `build_rachis_primitive`.

**Files:**
- Modify: `src/palubicki/geom/builder.py` (leaf section, lines 43–117)
- Modify: `src/palubicki/geom/leaves.py` (`build_leaves_primitive` — add
  `droop_deg`, pass real `petiole_length` for simple)
- Modify: `src/palubicki/geom/compound_leaf.py` (`build_rachis_primitive` — drop
  the `leaf_kind == "simple"` early-return)
- Test: `tests/geom/test_leaves.py`, `tests/geom/test_builder_petiole.py` (new)

- [ ] **Step 1: Write the failing integration tests.**

Create `tests/geom/test_builder_petiole.py`:

```python
import numpy as np

from palubicki.config import Config
from palubicki.geom.builder import build_mesh
from palubicki.sim.tree import Internode, Leaf, LeafState, Node, Tree


def _small_leafy_tree():
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    child = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=root, child_node=child, diameter=0.02)
    root.children_internodes.append(iod)
    child.parent_internode = iod
    child.leaves.append(
        Leaf(parent_node=child, azimuth=0.0, birth_time=0.0, state=LeafState.ACTIVE)
    )
    return Tree(root=root)


def _materials(mesh):
    return {p.material.name for p in mesh.primitives}


def test_simple_petiole_emits_petiole_primitive():
    cfg = Config()
    cfg.geom.enable_leaves = True
    cfg.geom.leaf_kind = "simple"
    cfg.geom.foliage_depth = 1
    cfg.geom.petiole_length_ratio = 0.3
    mesh = build_mesh(_small_leafy_tree(), cfg)
    assert "petiole" in _materials(mesh)
    pet = next(p for p in mesh.primitives if p.material.name == "petiole")
    # one tapered tube: 2 * petiole_sides vertices
    assert pet.positions.shape[0] == 2 * cfg.geom.petiole_sides


def test_zero_petiole_emits_no_petiole_primitive():
    cfg = Config()
    cfg.geom.enable_leaves = True
    cfg.geom.leaf_kind = "simple"
    cfg.geom.foliage_depth = 1
    cfg.geom.petiole_length_ratio = 0.0
    mesh = build_mesh(_small_leafy_tree(), cfg)
    assert "petiole" not in _materials(mesh)
```

(Verify the `Internode`/`Node`/`Tree` constructor kwargs against
`src/palubicki/sim/tree.py` — match the existing helper style in
`tests/geom/test_leaves.py` exactly; adjust required args if the constructors
need more than shown.)

- [ ] **Step 2: Run to verify failure.**

Run: `.venv/bin/pytest tests/geom/test_builder_petiole.py -v`
Expected: FAIL — no `"petiole"` material primitive is produced (builder only
emits the rachis tube for compound leaves today).

- [ ] **Step 3: Add `droop_deg` + real petiole to `build_leaves_primitive`.**

In `src/palubicki/geom/leaves.py`, add `droop_deg: float = 0.0` to the
`build_leaves_primitive` signature (after `splay_deg`). Inside, where the simple
layout is built (the `if leaf_kind == "simple" or leaflet_specs is None:` branch),
pass the petiole values from `leaflet_specs` when present:

```python
    if leaf_kind == "simple" or leaflet_specs is None:
        pet_len = 0.0 if leaflet_specs is None else leaflet_specs.get("petiole_length", 0.0)
        pet_taper = 1.0 if leaflet_specs is None else leaflet_specs.get("petiole_taper", 1.0)
        pet_rad = 0.0 if leaflet_specs is None else leaflet_specs.get("rachis_radius", 0.0)
        layout = compound_layout(
            "simple", leaflet_count=1, leaflet_pair_count=0,
            terminal_leaflet=False, rachis_length=1.0,
            petiole_length=pet_len, rachis_radius=pet_rad, petiole_taper=pet_taper,
        )
    else:
        layout = compound_layout(
            leaf_kind,
            leaflet_count=leaflet_specs["leaflet_count"],
            leaflet_pair_count=leaflet_specs["leaflet_pair_count"],
            terminal_leaflet=leaflet_specs["terminal_leaflet"],
            rachis_length=leaflet_specs["rachis_length"],
            petiole_length=leaflet_specs["petiole_length"],
            rachis_radius=leaflet_specs["rachis_radius"],
        )
```

Then compute `droop_rad` and pass it into the `_lift_compound_leaf` call. Add
above the record loop:

```python
    splay_rad = math.radians(splay_deg)
    droop_rad = math.radians(droop_deg)
```

and add `droop_rad` as the final argument of the `_lift_compound_leaf(...)` call:

```python
        _lift_compound_leaf(
            render_pos, stem_dir, leaf.azimuth, eff_size, splay_rad, n_planes,
            leaflets, blade_pos_unit, blade_uv, blade_idx,
            positions[v_start : v_start + verts_per_leaf],
            normals[v_start : v_start + verts_per_leaf],
            uvs[v_start : v_start + verts_per_leaf],
            indices[i_start : i_start + idx_per_leaf],
            v_start, droop_rad,
        )
```

- [ ] **Step 4: Drop the `simple` early-return in `build_rachis_primitive`.**

In `src/palubicki/geom/compound_leaf.py`, change the guard (lines 190–191) from:

```python
    if leaf_kind == "simple" or leaflet_specs is None:
        return empty
```

to:

```python
    if leaflet_specs is None:
        return empty
```

(The existing `if not layout.rachis_segments: return empty` below already returns
empty when `petiole_length == 0`, covering needles. `compound_layout` is already
called with `leaf_kind`, which now handles `"simple"` with a petiole.)
Also pass `petiole_taper` into that `compound_layout` call by adding the kwarg
from `leaflet_specs`:

```python
    layout = compound_layout(
        leaf_kind,
        leaflet_count=leaflet_specs["leaflet_count"],
        leaflet_pair_count=leaflet_specs["leaflet_pair_count"],
        terminal_leaflet=leaflet_specs["terminal_leaflet"],
        rachis_length=leaflet_specs["rachis_length"],
        petiole_length=leaflet_specs["petiole_length"],
        rachis_radius=leaflet_specs["rachis_radius"],
        petiole_taper=leaflet_specs.get("petiole_taper", 1.0),
    )
```

- [ ] **Step 5: Wire `builder.py`.**

In `src/palubicki/geom/builder.py`, replace the leaf block (lines 43–117). Build
`leaflet_specs` for simple leaves too, thread droop, add the petiole material:

```python
    if cfg.geom.enable_leaves:
        g = cfg.geom
        leaf_mat = Material(
            name="leaf",
            base_color=(*g.leaf_color, 1.0),
            metallic=0.0,
            roughness=0.9,
            double_sided=True,
            alpha_mode="MASK",
            base_color_texture_png=_resolve_texture(g.leaf_texture),
        )
        if g.leaf_kind != "simple":
            leaflet_specs = {
                "leaflet_count": g.leaflet_count,
                "leaflet_pair_count": g.leaflet_pair_count,
                "terminal_leaflet": g.terminal_leaflet,
                "rachis_length": g.rachis_length_ratio * g.leaf_size,
                "petiole_length": g.petiole_length_ratio * g.leaf_size,
                "rachis_radius": g.rachis_radius_ratio * g.leaf_size,
                "petiole_taper": 1.0,
            }
        else:
            leaflet_specs = {
                "leaflet_count": 1,
                "leaflet_pair_count": 0,
                "terminal_leaflet": False,
                "rachis_length": 0.0,
                "petiole_length": g.petiole_length_ratio * g.leaf_size,
                "rachis_radius": g.petiole_radius_ratio * g.leaf_size,
                "petiole_taper": g.petiole_taper,
            }
        leaf_prim = build_leaves_primitive(
            tree,
            leaf_size=g.leaf_size,
            material=leaf_mat,
            aspect=g.leaf_aspect,
            splay_deg=g.leaf_splay_deg,
            droop_deg=g.petiole_droop_deg,
            foliage_depth=g.foliage_depth,
            needle_cluster_spacing=g.needle_cluster_spacing,
            sun_shade_k=g.sun_shade_k,
            leaf_shape=g.leaf_shape,
            leaf_margin=g.leaf_margin,
            leaf_margin_depth=g.leaf_margin_depth,
            leaf_margin_count=g.leaf_margin_count,
            leaf_kind=g.leaf_kind,
            leaflet_specs=(leaflet_specs if g.leaf_kind != "simple" else leaflet_specs),
        )
        primitives.append(leaf_prim)

        is_compound = g.leaf_kind != "simple"
        stem_mat = Material(
            name=("rachis" if is_compound else "petiole"),
            base_color=((*g.bark_color, 1.0) if is_compound else (*g.petiole_color, 1.0)),
            metallic=0.0,
            roughness=0.9,
            double_sided=False,
            alpha_mode="OPAQUE",
        )
        stem_prim = build_rachis_primitive(
            tree,
            material=stem_mat,
            leaf_size=g.leaf_size,
            foliage_depth=g.foliage_depth,
            leaf_kind=g.leaf_kind,
            leaflet_specs=leaflet_specs,
            ring_sides=(max(3, g.ring_sides // 2) if is_compound else max(3, g.petiole_sides)),
            needle_cluster_spacing=g.needle_cluster_spacing,
            sun_shade_k=g.sun_shade_k,
            splay_deg=g.leaf_splay_deg,
            droop_deg=g.petiole_droop_deg,
        )
        if stem_prim.positions.shape[0] > 0:
            primitives.append(stem_prim)

    return Mesh(primitives=primitives)
```

(Note: `build_leaves_primitive` ignores `leaflet_specs` for `simple` except for
the petiole fields it now reads, so passing the same dict is fine. Confirm
`resolve_leaflet_blade(g)` is still imported/used elsewhere; the prior block's
unused locals can be dropped.)

- [ ] **Step 6: Run the new tests + the leaf-area parity test.**

Run: `.venv/bin/pytest tests/geom/test_builder_petiole.py tests/sim/test_diagnostics_leaf_area.py -v`
Expected: PASS — petiole primitive present/absent as asserted, and leaf-area
parity holds (petiole excluded by material name; droop is area-preserving).

- [ ] **Step 7: Run the full suite (goldens will fail — expected).**

Run: `.venv/bin/pytest -q`
Expected: PASS except `tests/golden/test_species_goldens.py` for simple-leaf
species whose default `petiole_length_ratio` (0.4) now renders a petiole. That is
intentional and handled in Task 6.

- [ ] **Step 8: Commit.**

```bash
git add src/palubicki/geom/builder.py src/palubicki/geom/leaves.py src/palubicki/geom/compound_leaf.py tests/geom/test_builder_petiole.py
git commit -m "geom: render simple-leaf petiole tube (material, droop, taper) (#5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Species tuning + golden regeneration

Set needles to zero petiole (byte-identical) and give broadleaves visible,
slightly-drooping petioles, then regenerate the affected goldens.

**Files:**
- Modify: `src/palubicki/configs/species/pine.yaml`, `fir.yaml` (add
  `petiole_length_ratio: 0.0`)
- Modify: `src/palubicki/configs/species/oak.yaml`, `birch.yaml`, `maple.yaml`
  (petiole length + droop + color)
- Regenerate: `tests/golden/data/species_{oak,birch,maple}.sha256`
- Test: acceptance checks via CLI

- [ ] **Step 1: Set needles to zero petiole.**

Append to the `geom:` block of `src/palubicki/configs/species/pine.yaml` and
`src/palubicki/configs/species/fir.yaml`:

```yaml
  petiole_length_ratio: 0.0
```

- [ ] **Step 2: Confirm pine/fir goldens are byte-identical (no regen).**

Run: `.venv/bin/pytest "tests/golden/test_species_goldens.py::test_species_golden[pine]" "tests/golden/test_species_goldens.py::test_species_golden[fir]" -v`
Expected: PASS without `--update-goldens` (zero petiole + droop 0 → identical
geometry).

- [ ] **Step 3: Give broadleaves visible petioles.**

Append to the `geom:` block of `oak.yaml`, `birch.yaml`, and `maple.yaml`:

```yaml
  petiole_length_ratio: 0.25
  petiole_radius_ratio: 0.02
  petiole_taper: 0.6
  petiole_droop_deg: 12.0
  petiole_color: [0.32, 0.42, 0.18]
```

- [ ] **Step 4: Regenerate the broadleaf goldens.**

Run: `.venv/bin/pytest tests/golden/test_species_goldens.py --update-goldens`
Then verify they pass:
Run: `.venv/bin/pytest tests/golden/test_species_goldens.py -v`
Expected: PASS (oak/birch/maple updated; pine/fir/ash unchanged).

- [ ] **Step 5: Acceptance check — oak is stalked, pine is not.**

Run:
```bash
.venv/bin/palubicki generate --species oak --seed 0 --output /tmp/oak.glb
.venv/bin/palubicki generate --species pine --seed 0 --output /tmp/pine.glb
```
Then confirm the petiole primitive presence with a one-off check:
```bash
.venv/bin/python -c "
from palubicki.config import load_species_config
from palubicki.geom.builder import build_mesh
from palubicki.sim.runner import simulate_tree
for sp, want in [('oak', True), ('pine', False)]:
    cfg = load_species_config(sp)
    mesh = build_mesh(simulate_tree(cfg, seed=0), cfg)
    names = {p.material.name for p in mesh.primitives}
    has = 'petiole' in names
    print(sp, 'petiole=' + str(has))
    assert has == want, sp
print('acceptance OK')
"
```
Expected: `oak petiole=True`, `pine petiole=False`, `acceptance OK`.
(Verify the CLI flags/entry point against `src/palubicki/cli.py`; adjust
`--output`/subcommand names if they differ.)

- [ ] **Step 6: Commit.**

```bash
git add src/palubicki/configs/species/*.yaml tests/golden/data/species_*.sha256
git commit -m "species: visible petioles on broadleaves, zero on needles + goldens (#5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Lint, full verification, and docs

**Files:**
- Modify: `docs/roadmap.md`, `docs/botany/simulator-gap-analysis.md`

- [ ] **Step 1: Lint and format.**

Run: `.venv/bin/ruff check src tests && .venv/bin/ruff format src tests`
Expected: no errors; format makes no/﻿minimal changes. Re-stage any reformatted files.

- [ ] **Step 2: Full test suite.**

Run: `.venv/bin/pytest -q`
Expected: PASS (all green, including goldens and leaf-area parity).

- [ ] **Step 3: Vertex-count sanity (acceptance criterion).**

Run:
```bash
.venv/bin/python -c "
from palubicki.config import load_species_config
from palubicki.geom.builder import build_mesh
from palubicki.sim.runner import simulate_tree
cfg = load_species_config('oak')
mesh = build_mesh(simulate_tree(cfg, seed=0), cfg)
for p in mesh.primitives:
    print(p.material.name, p.positions.shape[0])
"
```
Expected: a `petiole` primitive with `~2 * petiole_sides * n_leaves` vertices —
no order-of-magnitude blow-up vs the `leaf` primitive.

- [ ] **Step 4: Update `docs/roadmap.md`.**

Move issue #5 out of item 1 of "À faire (dans l'ordre)" into the "Fait" table
with PR #60. If #7 (fascicules) is still pending, keep item 1 for #7 and note #5
delivered. Re-check the ordering of remaining items.

- [ ] **Step 5: Update `docs/botany/simulator-gap-analysis.md`.**

Flip the petiole row (§6 / "Top remaining recommendations" #8) from ❌/🟡 to ✅,
update the section verdict, and refresh the "Last reviewed" line and the "Top
remaining recommendations" list. (This ticket touches a botanical concept, so the
gap-analysis DOES need an edit.)

- [ ] **Step 6: Commit docs.**

```bash
git add docs/roadmap.md docs/botany/simulator-gap-analysis.md
git commit -m "docs: petiole geometry landed — roadmap + gap-analysis (#5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 7: Push.**

```bash
git push
```

---

## Self-review notes (author)

- **Spec coverage:** unify-on-rachis → Tasks 3+5; taper → Task 1; droop → Task 2;
  separate `petiole` material → Task 5; config fields → Task 4; species (needles=0,
  broadleaf petioles) → Task 6; leaf-area invariant → asserted in Task 5 Step 6;
  vertex-count bound → Task 7 Step 3; goldens → Task 6; docs → Task 7. All covered.
- **Type consistency:** `RachisSeg` is the 4-tuple `(start_uv, end_uv, r0, r1)`
  everywhere after Task 1; `_emit_cylinder(p0, p1, radius0, radius1, ring_sides,
  base_index)`; `compound_layout(..., petiole_taper=1.0)`; `leaf_basis(direction,
  azimuth, splay_rad, droop_rad=0.0) -> (rot_axis_u, leaf_up, rot_axis_w)`;
  `build_leaves_primitive(..., droop_deg=0.0, ...)`;
  `build_rachis_primitive(..., droop_deg=0.0)`. Consistent across tasks.
- **Verify-before-coding:** confirm exact `Internode`/`Node`/`Tree` constructor
  signatures (Task 5 test) and the CLI subcommand/flags (Task 6) against the
  current source — they are quoted from an exploration report, not re-read here.
```
