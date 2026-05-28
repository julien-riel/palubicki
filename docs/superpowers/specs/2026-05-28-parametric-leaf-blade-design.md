# Parametric Leaf Blade — Design

**Issue:** [#4](https://github.com/julien-riel/palubicki/issues/4) — `geom/leaves.py: parametric blade with shape + margin function (replace cross-quads)`
**PR:** [#17](https://github.com/julien-riel/palubicki/pull/17)
**Date:** 2026-05-28
**Status:** Design approved, ready for implementation plan

## Goal

Replace the current flat-rectangle leaf mesh with a parametric blade outline (triangulated polygon) that expresses real-world leaf silhouettes — lanceolate, ovate, elliptic, cordate, linear, palmate — and serrated / dentate / lobed margins. Today every species shares the same rectangle UV-mapped to a texture, which collapses leaf identity into texture alpha. Gap analysis (`docs/botany/simulator-gap-analysis.md` §6) flags this as the **highest leaf-realism payoff for the dollar**.

## Decisions made during brainstorming

1. **Lobed shapes are in MVP**, not deferred. Acceptance criteria require oak (pinnatifid) and maple (palmate) to look botanically correct. Without lobed, two of the four target species don't change visibly from rectangles — defeating the headline goal.
2. **Palmate is its own shape**; lobing on convex shapes lives in `margin`. Final enum: `shape ∈ {linear, elliptic, lanceolate, ovate, cordate, palmate}`, `margin ∈ {entire, serrate, dentate, lobed}`. Oak = `ovate + lobed`; maple = `palmate + entire`. Margin and shape are orthogonal.
3. **Fan-from-interior-anchor triangulation.** Every shape is star-shaped from a natural anchor; one triangulator handles all of them. ~30 lines vs. ~80 for general earcut.
4. **Tooth vertex-pair insertion for margins.** Walk the smooth boundary; for each tooth, insert one inside-valley vertex and one outside-peak vertex between adjacent samples. Crisper than radius modulation, cheaper than 3-vertex tooth replacement.
5. **Per-shape outline functions + shared margin/triangulate/lift pipeline** (Approach A). Each shape gets its own `_outline_<name>()` returning `(boundary, anchor)`; downstream layers are shared.

## Architecture

```
src/palubicki/geom/leaf_blade.py     (NEW)
  build_blade(L, W, shape, margin, margin_depth, margin_count) -> (pos, norm, uv, idx)
    │
    ├─ _outline_<shape>(L, W) -> (boundary_2d, anchor_2d)
    │     {linear, elliptic, lanceolate, ovate, cordate, palmate}
    ├─ _apply_margin(boundary, margin, depth, count) -> boundary'
    │     {entire (no-op), serrate, dentate, lobed}
    ├─ _triangulate_fan(boundary, anchor) -> (positions_2d, indices)
    └─ _to_3d_blade_template(positions_2d, indices) -> BladeTemplate
          BladeTemplate is a dataclass cached and reused per cluster lift
```

`geom/leaves.py` is modified, not replaced. `_emit_leaf_cluster` calls `build_blade` once per primitive (cached at the call-site), then `_lift_blade(...)` writes each cluster member's two perpendicular planes. `_add_quad` is deleted.

## 2D coordinate convention (blade-local)

- Origin `(0, 0)` = petiole attachment point (where the leaf meets the twig).
- `+v` = blade-length direction (out from the twig).
- `+u` = lateral direction (perpendicular to `+v`, in the blade plane).
- Bounding box: `u ∈ [-W/2, +W/2]`, `v ∈ [0, L]`. Exception: cordate and palmate may extend slightly into `v < 0` for back-lobes/notches.
- UVs: `tex_u = (u + W/2) / W`, `tex_v = v / L`. Matches the existing rectangle convention so existing leaf textures align.

## Per-shape outlines

Each `_outline_<shape>(L, W)` returns `(boundary_uv: (N, 2) np.float64 array, anchor_uv: (2,) np.float64 array)`. Boundary is CCW, anchor is interior. Boundary does *not* close (no duplicate first vertex); the triangulator wraps around.

| Shape | Outline | Anchor | Default base N |
|---|---|---|---|
| **linear** | Rectangle: `(-W/2, 0), (W/2, 0), (W/2, L), (-W/2, L)`. | `(0, L/2)` | 4 |
| **elliptic** | Half-ellipse symmetric about `u=0`; max width at `v=L/2`. Right side: `u(v) = (W/2) · sin(π v/L)`. Left side mirrored. | `(0, L/2)` | 16 |
| **lanceolate** | Max width shifted toward base: `u(v) = (W/2) · sin(π v/L)^0.7`, scaled by a `(1 - v/L)^0.3` taper to keep tip narrow. | `(0, L/3)` | 16 |
| **ovate** | Broader-at-base: `u(v) = (W/2) · sin(π v/L)^1.3`, with width peak biased toward `v ≈ L/3`. | `(0, L/3)` | 16 |
| **cordate** | Ovate base with a basal notch: outline dips to `v = -L/8` between two back-lobes that curl back lateral to the petiole. | `(0, L/3)` | 20 |
| **palmate** | 5 radial lobes from center `c = (0, 0.4·L)`. Lobe `k ∈ {-2, -1, 0, 1, 2}` has angle `θ_k = π/2 + k · (π/3)` measured from `c`; tip distance `R = 0.5·max(L, W)`; inter-lobe valley at `0.3·R`. | `(0, 0.4·L)` | 20 |

The `^0.7` / `^1.3` exponents and the inter-lobe ratios are starting parameters; final values are eyeballed against the visual goldens during implementation.

## Margin algorithm

`_apply_margin(boundary, margin, margin_depth, margin_count)` modifies the smooth boundary by inserting two extra vertices per tooth between adjacent boundary samples.

**Per tooth** (one of `margin_count` evenly distributed positions along the eligible arc):
1. Locate the arc-length midpoint `P` between the two source boundary samples.
2. Compute the inward normal `n_in` and outward tangent `tan` at `P`.
3. Insert in order:
   - **Valley** at `P + n_in · (depth · w_local)` — pulled inward.
   - **Peak** at `P − n_in · (depth · w_local) + tan · (half_period)` — pushed outward, offset along the tangent.
4. `w_local` is the local blade half-width at that `v` (for symmetric shapes) or a constant fraction of `R` (palmate). `half_period` is the spacing between adjacent teeth on the source boundary.

**Per-margin tuning:**

| Margin | Peak offset along tangent | Valley pull factor | Notes |
|---|---|---|---|
| `entire` | — | — | No-op; returns boundary unchanged. |
| `serrate` | `+0.5 · half_period` (forward) | `1.0` | Sawteeth point apex-ward (cherry-leaf look). |
| `dentate` | `0.0` (symmetric) | `0.5` | Symmetric triangular teeth, gentler valleys. |
| `lobed` | `0.0` | `1.0`, larger `depth` (0.25–0.4), lower `count` (3–8) | Pinnatifid lobes when applied to `shape=ovate`. |

**Eligible arc:**
- Symmetric shapes (linear/elliptic/lanceolate/ovate): the full perimeter *except* the base segment crossing the petiole (small `v < 0.05·L` arc near the origin).
- Cordate: full perimeter except the petiole/notch arc.
- Palmate: each lobe's outer arc independently.

**Vertex cost per margin:** `+2 · margin_count` boundary vertices, regardless of margin type.

## Triangulation

`_triangulate_fan(boundary, anchor)`:
1. `positions = concat([anchor, boundary])` — anchor is vertex 0; boundary occupies `1..N`.
2. For `i = 0..N-1`: emit triangle `(0, 1+i, 1+((i+1) % N))`.

Total: `N+1` vertices, `N` triangles (`3N` indices). Star-shape (every boundary vertex visible from the anchor) is guaranteed by the per-shape outline functions and is asserted in unit tests.

## Lifting 2D into 3D

`_lift_blade(blade_2d, origin, basis_u, basis_v, normal, out_pos, out_norm, out_uv, out_idx, base)`:
- For each 2D vertex `(u, v)`: `position_3d = origin + u · basis_u + v · basis_v`.
- Normals: constant `normal` for all blade verts (single-sided plane; the cross-blade pairing provides the other side).
- UVs: pass through from `blade_2d` unchanged.
- Indices: add `base` offset to each.

In `_emit_leaf_cluster`, for each cluster member `k` and each of the two perpendicular planes:
- `origin = leaf_center` (the foliage site, with optional small `d`-offset for visual lift; no longer the 0.3·size offset of today)
- `basis_v = leaf_up = cos(splay)·d + sin(splay)·rot_axis_u`
- `basis_u = rot_axis_u` (plane A) or `rot_axis_w` (plane B)
- `normal = rot_axis_w` (plane A) or `rot_axis_u` (plane B)

The cluster + cross-blade structure is unchanged; only the per-plane geometry changes from quad to triangulated blade.

## Vertex budget per (shape, margin)

| Shape | Margin | Base N | + tooth verts | Per face | Per cluster member (×2 faces) | Multiplier vs. today (8/face) |
|---|---|---|---|---|---|---|
| linear | entire | 4 | 0 | 5 | 10 | 0.6× |
| ovate | entire | 16 | 0 | 17 | 34 | 2.1× |
| ovate | lobed (oak, count=7) | 12 | +14 | 27 | 54 | 3.4× |
| ovate | serrate (birch, count=12) | 12 | +24 | 37 | 74 | 4.6× |
| palmate | entire (maple) | 24 | 0 | 25 | 50 | 3.1× |
| cordate | entire | 20 | 0 | 21 | 42 | 2.6× |

All under the 64/face hard cap. Birch worst case is 4.6× per cluster member — over the "~2× total" aspirational target but within practical limits. `margin_count` is the per-species knob if perf forces a dial-back.

## Config schema

Four new fields on `GeomConfig` (`src/palubicki/config.py`):

```python
leaf_shape: Literal["linear", "elliptic", "lanceolate", "ovate", "cordate", "palmate"] = field(
    default="ovate", metadata={"ui": {"label": "Leaf shape"}}
)
leaf_margin: Literal["entire", "serrate", "dentate", "lobed"] = field(
    default="entire", metadata={"ui": {"label": "Leaf margin"}}
)
leaf_margin_depth: float = field(
    default=0.0, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.05}}
)
leaf_margin_count: int = field(
    default=0, metadata={"ui": {"min": 0, "max": 30, "step": 1}}
)
```

Validation in `Config.__post_init__` (matches existing `phyllotaxy.mode` and `bud_break_bias.mode` patterns):
- Reject unknown `leaf_shape` / `leaf_margin` with `ConfigError`.
- Reject `leaf_margin_depth < 0` or `> 1`.
- Reject `leaf_margin_count < 0`.
- No warning for `margin != "entire" && margin_count == 0` — `_apply_margin` returns the unchanged boundary, behaving as `entire`; user can see this in the rendered output.

## Species presets

| Species | leaf_shape | leaf_margin | margin_depth | margin_count | leaf_size | leaf_aspect | Rationale |
|---|---|---|---|---|---|---|---|
| **oak** | `ovate` | `lobed` | `0.35` | `7` | `0.14` | `0.7` | Pinnatifid: deeper lobes, fewer of them. Aspect reduced from 1.0 → 0.7 so the lobed silhouette reads as oak, not elm. |
| **birch** | `ovate` | `serrate` | `0.08` | `12` | `0.05` | `0.7` | Shallow forward-pointing teeth. Existing aspect 0.7 preserved. |
| **maple** | `palmate` | `entire` | `0.0` | `0` | `0.12` | `1.0` | 5-lobed canonical maple silhouette. Width=length for proper star shape. |
| **pine** | `linear` | `entire` | `0.0` | `0` | `0.06` | `0.025` | Identical visual to today (needle = thin rectangle). |
| **fir** | `linear` | `entire` | `0.0` | `0` | `0.05` | `0.025` | Identical visual to today. |

Default `GeomConfig` (no preset): `ovate + entire`. Sensible-looking generic leaf, smallest jump from current rectangle baseline.

## Tests

### New: `tests/geom/test_leaf_blade.py`

2D unit tests, no Tree/Material/Internode setup:

- `test_outline_<shape>_bounding_box` (×6) — outline fits within nominal `[-W/2, W/2] × [-L/8, L]`.
- `test_outline_<shape>_ccw` (×6) — signed area > 0.
- `test_outline_<shape>_anchor_inside` (×6) — ray-casting check.
- `test_outline_<shape>_star_from_anchor` (×6) — every boundary vertex has line-of-sight to anchor (segment-segment intersection check).
- `test_margin_entire_is_noop` — `_apply_margin(b, "entire", ...)` returns `b` unchanged.
- `test_margin_serrate_adds_2N_verts` — `len(out) − len(in) == 2 · margin_count`.
- `test_margin_lobed_increases_boundary_variance` — radial-distance variance grows.
- `test_margin_serrate_teeth_point_forward` — peak verts have higher mean `v` than valley verts.
- `test_triangulate_fan_covers_polygon` — sum of triangle areas == polygon signed area (±1e-9).
- `test_triangulate_fan_indices_in_bounds` — `indices.max() < positions.shape[0]`.
- `test_build_blade_returns_consistent_arrays` — positions / normals / uvs same length; indices in bounds; index count divisible by 3.
- `test_build_blade_vert_count_under_64` — for each `(shape, margin)` default pair, per-face verts ≤ 64.
- `test_build_blade_unknown_shape_raises` — `ValueError`.
- `test_build_blade_unknown_margin_raises` — `ValueError`.

### Visual reference images: `tests/geom/visual/`

Matplotlib PNG renders for human review, one per `(shape, margin)` combo. Per the issue's "manual eyeball + saved reference image is fine":
- A standalone script `scripts/regen_leaf_visuals.py` calls `_outline_<shape>` + `_apply_margin` and writes a PNG via `matplotlib.pyplot.fill` to `tests/geom/visual/`.
- PNGs are committed and reviewed during PR.
- **No automated pixel diff** — too fragile across matplotlib versions, and 2D unit tests (CCW, star-shape, vert counts, tooth direction) already cover correctness. The PNGs exist for "does this actually look like an oak leaf?"
- Rerun the script on intentional changes; commit the new PNGs alongside.

### Modified: `tests/geom/test_leaves.py`

Default `leaf_shape=ovate`, base N=16, anchor +1 → 17 verts/face, 16 tris/face. Each cluster member emits two perpendicular faces (cross-blade), so per cluster member = 34 verts, 96 indices.

- `test_one_bud_eight_vertices_twelve_indices` → renamed `test_one_bud_default_shape_vert_count`; expected `(34, 3)` positions and `(96,)` indices (cluster_count=1, two faces of 17 verts and 48 indices each).
- `test_three_buds_yields_24_vertices` → renamed `test_three_buds_yields_3x_default_blade_verts`; expected `(102, 3)` positions and `(288,)` indices.
- `test_indices_within_bounds` — unchanged.
- `test_leaf_size_*` sun/shade tests — unchanged (still exercise `compute_effective_leaf_size`).
- `test_leaves_follow_sag_offset_at_apex` — unchanged.

### Modified: `tests/geom/test_leaf_cluster.py`, `tests/geom/test_leaf_texture.py`

Mechanical vert-count updates to whichever assertions assume 8/face. Both files small; full review during implementation plan.

### Modified: `tests/test_config_leaf_cluster.py`

Extend coverage to the 4 new YAML keys:
- Valid `leaf_shape` / `leaf_margin` values accepted.
- Unknown values rejected with `ConfigError`.
- Defaults applied when keys are absent.
- `leaf_margin_depth` range check.

## Error handling

`build_blade` validates upfront, raises `ValueError` with a precise message — no silent fallbacks (matches the project's PoC-no-back-compat preference):

- Unknown `shape` → `ValueError("unknown leaf shape: <name>; expected one of [...]")`.
- Unknown `margin` → similar.
- `length ≤ 0` or `width ≤ 0` → `ValueError`.
- `margin_depth < 0` or `> 1` → `ValueError`.
- `margin_count < 0` → `ValueError`.
- `margin != "entire"` with `margin_count == 0` → no error; `_apply_margin` returns the boundary unchanged. The config-level check covers obvious misconfig.

Config-level errors raise `ConfigError`.

## Artifact updates in this PR

- **GLB regeneration:** `out/oak.glb`, `out/birch.glb`, `out/maple.glb`, `out/pine.glb` regenerated and committed. Add `out/fir.glb` for parity with the other species (no .glb committed today; the species YAML exists).
- **Gap analysis doc** (`docs/botany/simulator-gap-analysis.md` §6): mark row "Blade with parametric length, width, shape" `✅ ⬆ Implemented`; update §6 verdict; bump "Last reviewed" date.

## Out of scope

- **Compound leaves** (pinnate/palmate/bipinnate) — separate issue, builds on this one.
- **Petiole geometry** — separate issue (#5 in the roadmap), depends on this design's blade-local coordinate convention.
- **Per-leaf state** (age, color trajectory) — gated behind Phase 1 (time/phenology axis).
- **Geometric venation, ridges, blade curvature** (cup, wave) — defer.
- **Procedural venation as normal map** — listed in issue as "Nice to have"; defer.
- **`tip_shape` parameter** (acute/obtuse/acuminate) — defer; bakeable into outline tuning if needed later.
- **Fascicles** for needle clusters — separate issue.

## Acceptance criteria (verbatim from issue)

- [ ] `build_blade(...)` returns geometry that visually matches each named shape (manual eyeball + saved reference image is fine).
- [ ] All four species presets render with their botanically correct shape + margin.
- [ ] Mesh vert count per leaf is bounded (≤ ~64 per face) — perf regression is acceptable up to ~2× total leaf vertex count.
- [ ] All four `palubicki generate --species X` smoke tests still produce valid `.glb`.
- [ ] Existing leaf-related goldens are updated and reviewed in the same PR (the old rectangle goldens are obsolete; this is a PoC, no back-compat).
