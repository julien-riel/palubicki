# Compound leaves (pinnate, palmate, bipinnate) — design

Issue: #6 · Branch: `issue-6-compound-leaves-pinnate-palmate` · PR: #58

## Goal

A single leaf made of several leaflets arranged on a central rachis: **pinnate**
(leaflets along a rachis — ash, walnut, rose), **palmate** (leaflets radiating
from one point — horse chestnut, lupine), **bipinnate** (the rachis is itself
branched — mimosa, acacia). Without this, a large swath of broadleaf species
cannot be visibly distinguished from simple-leaved species. Mechanism only — no
new species presets (separate follow-up).

## Architecture — reconcile the issue's API with the instanced pipeline

The issue proposes `build_compound_leaf(...) -> Primitive` per leaf. That fights
the current design: `build_leaves_primitive` builds **one** unit blade template
and instances it across every selected leaf into preallocated arrays (linear,
fast). We keep that pattern and add a thin **layout** layer instead.

New module **`src/palubicki/geom/compound_leaf.py`** exposing a pure,
mesh-free layout function:

```python
def compound_layout(
    kind: str,                 # "simple" | "pinnate" | "palmate" | "bipinnate"
    leaflet_count: int,
    leaflet_pair_count: int,   # bipinnate: secondary-rachis pairs
    terminal_leaflet: bool,
    rachis_length: float,
    petiole_length: float,
    rachis_radius: float,
) -> CompoundLayout
```

`CompoundLayout` carries, in the leaf's **local 2D frame** (`v` = leaf axis along
the lifted stem direction, `u` = lateral):

- `leaflets`: list of `(origin_uv, axis_angle, scale)` — where each leaflet blade
  is seated, its rotation within the leaf plane, and its size relative to the
  whole-leaf size.
- `rachis_segments`: list of `(start_uv, end_uv, radius)` — petiole + rachis
  (+ sub-rachises for bipinnate) as centerlines for the stem tubes.

This is the unit of testability: a pure function with no numpy meshing, so
placement counts and linear growth are asserted directly.

`kind="simple"` → exactly one leaflet at the base (`origin_uv=(0,0)`,
`axis_angle=0`, `scale=1`) and **zero** rachis segments → byte-identical to the
current single-blade path. This is the regression guarantee for the 4 existing
species (all simple-leaved).

## Layouts

- **pinnate**: petiole (axis `0 → petiole_length`) + rachis
  (`→ +rachis_length`). `leaflet_count` leaflets in **opposite pairs** at even
  `v` intervals along the rachis, each angled outward ±~60° via a short
  petiolule; optional terminal leaflet at the tip (imparipinnate when
  `terminal_leaflet`). Basal→terminal size taper deferred (nice-to-have).
- **palmate**: petiole only, no rachis. `leaflet_count` leaflets radiating from
  the petiole tip in an even half-fan (~30–45° apart).
- **bipinnate**: petiole + primary rachis + `leaflet_pair_count` secondary
  rachises (paired along the primary), each a small pinnate of `leaflet_count`
  leaflets. One level of recursion (per issue).

## Geometry assembly & the separate rachis primitive

- `build_leaves_primitive` computes the layout **once** (uniform `leaf_kind` per
  tree → constant `leaflets_per_leaf`), preallocates
  `n_records × leaflets_per_leaf × blade_v_count`, and a new
  `_lift_compound_leaf` seats each leaflet using the existing base-site basis
  (`rot_axis_u`, `leaf_up`, `rot_axis_w`) plus the leaflet's local `origin_uv` /
  `axis_angle` / `scale`. Linear in leaflet count.
- The **rachis/petiole** is a **second primitive** with a new **stem material**.
  `build_rachis_primitive(tree, layout, ...)` (in `compound_leaf.py`) emits thin
  tubes (reusing `tubes._emit_chain_tube`) along each rachis centerline, lifted
  into 3D at each leaf site. `builder.build_mesh` constructs a `rachis_mat`
  (bark color, `OPAQUE`, name `"rachis"`) and appends the primitive **only when
  `leaf_kind != "simple"`** — so simple-leaf species get no new primitive and
  goldens stay frozen.

## Config additions (`GeomConfig`)

```
leaf_kind: "simple"|"pinnate"|"palmate"|"bipinnate" = "simple"
leaflet_count: int = 5
leaflet_pair_count: int = 0            # bipinnate secondary-rachis pairs
terminal_leaflet: bool = True
rachis_length_ratio: float = 1.5       # × leaf_size (whole-leaf length)
rachis_radius_ratio: float = 0.03      # × rachis_length
petiole_length_ratio: float = 0.4      # × leaf_size
leaflet_shape:  Literal[...] | None = None   # None -> inherit leaf_shape
leaflet_margin: Literal[...] | None = None   # None -> inherit leaf_margin
leaflet_aspect: float | None = None          # None -> inherit leaf_aspect
```

`_validate` adds checks mirroring the existing leaf validators (enum membership,
counts ≥ 0/≥ 1 where required, ratios > 0). Leaflet-sub-config inheritance
resolves at build time: `None` means copy the simple-leaf value. No species
presets touched.

## Diagnostics (the #36 drift trap)

`sim/diagnostics._total_leaf_area` must mirror the `.glb`. It is routed through
the **same `compound_layout`** so per-site area =
`Σ_leaflets pair_area × (eff · scale)²`. For `simple` this reduces to today's
exact value (the 4 species diagnostic hashes do not move). Guarded by extending
`test_leaf_area_matches_geom_helper`.

## Testing

- `tests/geom/test_compound_leaf.py`: layout counts (pinnate = N + terminal;
  palmate = N; bipinnate = pairs × N), linear-growth assertion, `simple` == 1
  leaflet / 0 rachis segments.
- `tests/geom/test_leaves.py`: integration — pinnate tree leaf-primitive vert
  count == records × leaflets × blade_verts; rachis primitive non-empty;
  `simple` output vert-for-vert equal to the current output.
- `tests/test_config.py`: validation for new fields + inherit-on-`None`
  resolution.
- Full golden suite: confirm the 4 species goldens + GLB goldens are unchanged.

## Acceptance criteria (from the issue)

- [ ] `kind="simple"` produces the same geometry as before (no regression).
- [ ] `kind="pinnate"` with `leaflet_count=7` produces a recognizable
  ash/walnut-style compound leaf.
- [ ] `kind="palmate"` with `leaflet_count=5` produces a horse-chestnut fan.
- [ ] `kind="bipinnate"` produces a recognizable mimosa-style doubly-divided leaf.
- [ ] Total geometry grows roughly linearly with `leaflet_count`.
- [ ] Existing four species presets render unchanged.

## Out of scope

Tripinnate; stochastic/asymmetric leaflet sizing; alternate (non-paired) leaflet
phyllotaxy; per-leaflet senescence; new species presets (ash/walnut/etc.).
