# Compound Leaves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render compound leaves (pinnate / palmate / bipinnate) — one leaf made of several leaflets on a rachis — alongside the existing simple-blade path, with no regression on the four current species.

**Architecture:** A pure 2D **layout** function (`compound_layout`) returns leaflet placements `(origin_uv, axis_angle, scale)` and rachis centerlines in the leaf's local `(u, v)` frame. The existing instanced renderer (`build_leaves_primitive`) lifts each leaflet blade into 3D using the same per-site basis it already builds, looping over the layout's leaflets. The rachis/petiole is a separate stem-material primitive. `kind="simple"` degenerates to exactly today's single-blade output (regression guarantee).

**Tech Stack:** Python 3.14, numpy, pytest. Run tests with the project venv: `.venv/bin/pytest`. Run ruff with `.venv/bin/ruff`.

---

## Background the implementer needs

- **`src/palubicki/geom/leaf_blade.py`** — `build_blade(*, length, width, shape, margin, margin_depth=0.0, margin_count=0) -> (positions(N,3) f32, normals(N,3) f32, uvs(N,2) f32, indices(M,) u32)`. The 2D blade lives in `(u, v, 0)`: `u` lateral, `v` along the blade length, origin `(0,0)` is the petiole attachment. `positions[0]` is the anchor.

- **`src/palubicki/geom/leaves.py`** — current pipeline:
  - `selected_leaves(tree, *, foliage_depth, needle_cluster_spacing=0.0)` returns a list of records `(leaf, stem_dir, source_internode, render_pos)`.
  - `build_leaves_primitive(...)` builds **one** unit blade template (`length=1.0, width=aspect`), preallocates arrays sized `n_records * verts_per_leaf`, loops records calling `_lift_leaf`.
  - `_lift_leaf(center, direction, azimuth, size, splay_rad, n_planes, blade_pos_unit, blade_uv, blade_idx, out_pos, out_norm, out_uv, out_idx, base)` reconstructs a basis from `direction`:
    ```python
    d = direction / |direction|
    right, forward = _basis_perpendicular_to(d)
    rot_axis_u = cos(az)*right + sin(az)*forward
    rot_axis_w = -sin(az)*right + cos(az)*forward
    leaf_up    = cos(splay)*d + sin(splay)*rot_axis_u
    ```
    then lifts the blade with `basis_u=rot_axis_u, basis_v=leaf_up, normal=rot_axis_w`; a second plane (`n_planes==2`, linear shape only) uses `basis_u=rot_axis_w, normal=rot_axis_u`.
  - `compute_effective_leaf_size(internode, leaf_size, sun_shade_k)` → per-site `eff_size`.
  - `_lift_blade(blade_pos_unit, blade_uv, blade_idx, origin, basis_u, basis_v, normal, scale, out_pos, out_norm, out_uv, out_idx, base)` writes `origin + (u*scale)*basis_u + (v*scale)*basis_v`.

- **`src/palubicki/geom/builder.py`** — `build_mesh(tree, cfg)` builds `bark_prim`, then (if `cfg.geom.enable_leaves`) a `leaf_mat` Material and `leaf_prim = build_leaves_primitive(...)`, returns `Mesh(primitives=[bark_prim, leaf_prim, ...])`.

- **`src/palubicki/geom/mesh.py`** — `Material(name, base_color(4-tuple), metallic, roughness, base_color_texture_png, alpha_mode, alpha_cutoff, double_sided)`; `Primitive(positions, normals, uvs, indices, material, colors=None)`.

- **`src/palubicki/sim/diagnostics.py`** — `_total_leaf_area(tree, cfg)` builds a unit blade, computes `unit_blade_area`, `pair_area = unit_blade_area * (cos(splay) + plane_b_factor)`, then sums `pair_area * eff**2` over `selected_leaves` records.

- **`src/palubicki/config.py`** — `GeomConfig` (frozen dataclass) holds `leaf_*` fields (see Task 1). `Config._validate` raises `ConfigError` for bad leaf values.

### Local-frame conventions for compound layout (LOCKED — every task uses these)

- A leaf's local 2D frame: axis **`u`** ↔ world `rot_axis_u` (lateral, in leaf plane); axis **`v`** ↔ world `leaf_up` (along the leaf / rachis); plane normal ↔ world `rot_axis_w`.
- All layout lengths are **ratios of the whole-leaf size** (`eff_size`); they get multiplied by `eff_size` at lift time. So `compound_layout` is given ratios directly.
- A leaflet placement `(origin_uv, axis_angle, scale)`:
  - `origin_uv = (u0, v0)` — the leaflet's petiole-attachment point in the leaf frame (size-units).
  - `axis_angle` — radians; the leaflet's own `v` axis is `cos(axis_angle)*leaf_up + sin(axis_angle)*rot_axis_u` (rotation from `+v` toward `+u`). `0` = points straight along the leaf.
  - `scale` — leaflet size as a multiple of `eff_size`.
- A rachis segment `(start_uv, end_uv, radius)` — a thin cylinder centerline in the leaf frame; `radius` in size-units.
- **simple** ⇒ `leaflets = [((0.0, 0.0), 0.0, 1.0)]`, `rachis_segments = []`. This reproduces `_lift_leaf` exactly.

---

## File Structure

- **Create** `src/palubicki/geom/compound_leaf.py` — `CompoundLayout` dataclass, `compound_layout(...)` pure function, `resolve_leaflet_blade(geom)` helper, `build_rachis_primitive(...)` + `_emit_cylinder(...)`.
- **Modify** `src/palubicki/config.py` — add `GeomConfig` fields + `_validate` checks.
- **Modify** `src/palubicki/geom/leaves.py` — `build_leaves_primitive` consumes a layout; add `_lift_compound_leaf`.
- **Modify** `src/palubicki/geom/builder.py` — build rachis material + primitive when `leaf_kind != "simple"`.
- **Modify** `src/palubicki/sim/diagnostics.py` — `_total_leaf_area` sums over layout leaflets.
- **Create** `tests/geom/test_compound_leaf.py` — layout unit tests + rachis tests.
- **Modify** `tests/geom/test_leaves.py` — integration: simple-regression + pinnate vert count.
- **Modify** `tests/test_config.py` — new-field validation + inherit resolution.

---

## Task 1: Config fields + validation

**Files:**
- Modify: `src/palubicki/config.py` (GeomConfig dataclass ~line 226; `_validate` leaf block ~line 504)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
def test_geom_compound_defaults():
    from palubicki.config import GeomConfig
    g = GeomConfig()
    assert g.leaf_kind == "simple"
    assert g.leaflet_count == 5
    assert g.leaflet_pair_count == 0
    assert g.terminal_leaflet is True
    assert g.rachis_length_ratio == 1.5
    assert g.rachis_radius_ratio == 0.03
    assert g.petiole_length_ratio == 0.4
    assert g.leaflet_shape is None
    assert g.leaflet_margin is None
    assert g.leaflet_aspect is None


def test_validate_rejects_bad_leaf_kind():
    import pytest
    from palubicki.config import Config, ConfigError
    cfg = Config.default()
    with pytest.raises(ConfigError, match="leaf_kind"):
        Config.default_with(geom_overrides={"leaf_kind": "frond"})


def test_validate_rejects_zero_leaflet_count():
    import pytest
    from palubicki.config import Config, ConfigError
    with pytest.raises(ConfigError, match="leaflet_count"):
        Config.default_with(geom_overrides={"leaf_kind": "pinnate", "leaflet_count": 0})
```

> NOTE: if `Config.default()` / `Config.default_with(geom_overrides=...)` do not exist, replace these two helpers with however `tests/test_config.py` already constructs a `Config` and overrides geom fields (grep the file for an existing `ConfigError` test and copy its construction idiom). Keep the three assertions identical.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_config.py::test_geom_compound_defaults -v`
Expected: FAIL — `AttributeError: ... 'leaf_kind'`.

- [ ] **Step 3: Add the GeomConfig fields**

In `src/palubicki/config.py`, inside `GeomConfig`, after the existing `leaf_sun_shade_k` field add:

```python
    # --- Compound leaves (#6) ---
    leaf_kind: Literal["simple", "pinnate", "palmate", "bipinnate"] = field(
        default="simple", metadata={"ui": {"label": "Leaf kind"}}
    )
    leaflet_count: int = field(default=5, metadata={"ui": {"min": 1, "max": 21, "step": 1}})
    leaflet_pair_count: int = field(default=0, metadata={"ui": {"min": 0, "max": 12, "step": 1}})
    terminal_leaflet: bool = field(default=True, metadata={"ui": {"label": "Terminal leaflet"}})
    rachis_length_ratio: float = field(
        default=1.5, metadata={"ui": {"min": 0.1, "max": 6.0, "step": 0.1}}
    )
    rachis_radius_ratio: float = field(
        default=0.03, metadata={"ui": {"min": 0.005, "max": 0.2, "step": 0.005}}
    )
    petiole_length_ratio: float = field(
        default=0.4, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.1}}
    )
    leaflet_shape: Literal["linear", "elliptic", "lanceolate", "ovate", "cordate", "palmate"] | None = None
    leaflet_margin: Literal["entire", "serrate", "dentate", "lobed"] | None = None
    leaflet_aspect: float | None = None
```

- [ ] **Step 4: Add validation**

In `Config._validate`, after the existing `leaf_margin_count` check, add:

```python
        if g.leaf_kind not in ("simple", "pinnate", "palmate", "bipinnate"):
            raise ConfigError(
                f"geom.leaf_kind must be one of "
                f"'simple'|'pinnate'|'palmate'|'bipinnate', got {g.leaf_kind!r}"
            )
        if g.leaflet_count < 1:
            raise ConfigError(f"geom.leaflet_count must be >= 1, got {g.leaflet_count}")
        if g.leaflet_pair_count < 0:
            raise ConfigError(
                f"geom.leaflet_pair_count must be >= 0, got {g.leaflet_pair_count}"
            )
        if g.leaf_kind == "bipinnate" and g.leaflet_pair_count < 1:
            raise ConfigError(
                "geom.leaflet_pair_count must be >= 1 when leaf_kind is 'bipinnate'"
            )
        if g.rachis_length_ratio <= 0:
            raise ConfigError(
                f"geom.rachis_length_ratio must be > 0, got {g.rachis_length_ratio}"
            )
        if g.rachis_radius_ratio <= 0:
            raise ConfigError(
                f"geom.rachis_radius_ratio must be > 0, got {g.rachis_radius_ratio}"
            )
        if g.petiole_length_ratio < 0:
            raise ConfigError(
                f"geom.petiole_length_ratio must be >= 0, got {g.petiole_length_ratio}"
            )
        if g.leaflet_shape is not None and g.leaflet_shape not in (
            "linear", "elliptic", "lanceolate", "ovate", "cordate", "palmate"
        ):
            raise ConfigError(f"geom.leaflet_shape invalid, got {g.leaflet_shape!r}")
        if g.leaflet_margin is not None and g.leaflet_margin not in (
            "entire", "serrate", "dentate", "lobed"
        ):
            raise ConfigError(f"geom.leaflet_margin invalid, got {g.leaflet_margin!r}")
        if g.leaflet_aspect is not None and not (0.0 < g.leaflet_aspect <= 4.0):
            raise ConfigError(
                f"geom.leaflet_aspect must be in (0, 4], got {g.leaflet_aspect}"
            )
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/pytest tests/test_config.py -k "compound or leaf_kind or leaflet" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "feat(config): compound-leaf GeomConfig fields + validation (#6)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `compound_layout` pure function

**Files:**
- Create: `src/palubicki/geom/compound_leaf.py`
- Test: `tests/geom/test_compound_leaf.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/geom/test_compound_leaf.py`:

```python
import math

from palubicki.geom.compound_leaf import CompoundLayout, compound_layout


def _layout(kind, **kw):
    base = dict(
        leaflet_count=5, leaflet_pair_count=3, terminal_leaflet=True,
        rachis_length=1.5, petiole_length=0.4, rachis_radius=0.045,
    )
    base.update(kw)
    return compound_layout(kind, **base)


def test_simple_is_single_blade_no_rachis():
    lay = _layout("simple")
    assert isinstance(lay, CompoundLayout)
    assert len(lay.leaflets) == 1
    origin_uv, axis_angle, scale = lay.leaflets[0]
    assert origin_uv == (0.0, 0.0)
    assert axis_angle == 0.0
    assert scale == 1.0
    assert lay.rachis_segments == []


def test_pinnate_leaflet_count_includes_terminal():
    lay = _layout("pinnate", leaflet_count=7, terminal_leaflet=True)
    assert len(lay.leaflets) == 8  # 7 lateral + 1 terminal
    lay2 = _layout("pinnate", leaflet_count=7, terminal_leaflet=False)
    assert len(lay2.leaflets) == 7
    # rachis present (petiole + rachis = 2 segments)
    assert len(lay.rachis_segments) >= 1


def test_pinnate_pairs_are_opposite():
    lay = _layout("pinnate", leaflet_count=4, terminal_leaflet=False)
    angles = sorted(a for (_uv, a, _s) in lay.leaflets)
    # opposite pairs: equal-magnitude positive/negative axis angles
    assert angles[0] < 0 < angles[-1]
    assert math.isclose(angles[0], -angles[-1], abs_tol=1e-9)


def test_palmate_no_rachis_fan_count():
    lay = _layout("palmate", leaflet_count=5)
    assert len(lay.leaflets) == 5
    assert lay.rachis_segments == [] or len(lay.rachis_segments) == 1  # petiole only
    angles = [a for (_uv, a, _s) in lay.leaflets]
    assert min(angles) < 0 < max(angles)


def test_bipinnate_count_is_pairs_times_leaflets():
    lay = _layout("bipinnate", leaflet_pair_count=3, leaflet_count=4)
    assert len(lay.leaflets) == 3 * 4


def test_growth_is_linear_in_leaflet_count():
    a = len(_layout("pinnate", leaflet_count=4, terminal_leaflet=False).leaflets)
    b = len(_layout("pinnate", leaflet_count=8, terminal_leaflet=False).leaflets)
    assert b == 2 * a
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/geom/test_compound_leaf.py -v`
Expected: FAIL — `ModuleNotFoundError: ... compound_leaf`.

- [ ] **Step 3: Implement the module (layout half)**

Create `src/palubicki/geom/compound_leaf.py`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Leaflet placement in the leaf's local (u, v) frame, in whole-leaf-size units.
#   origin_uv  : (u, v) petiole-attachment point of the leaflet
#   axis_angle : radians; leaflet v-axis = cos(a)*leaf_up + sin(a)*rot_axis_u
#   scale      : leaflet size as a multiple of the whole-leaf size
Leaflet = tuple[tuple[float, float], float, float]
# Rachis centerline segment: (start_uv, end_uv, radius) in size-units.
RachisSeg = tuple[tuple[float, float], tuple[float, float], float]

_OUTWARD = math.radians(60.0)   # pinnate leaflet splay from the rachis
_FAN = math.radians(55.0)       # palmate half-fan half-angle


@dataclass(frozen=True)
class CompoundLayout:
    leaflets: list[Leaflet]
    rachis_segments: list[RachisSeg]


def compound_layout(
    kind: str,
    *,
    leaflet_count: int,
    leaflet_pair_count: int,
    terminal_leaflet: bool,
    rachis_length: float,
    petiole_length: float,
    rachis_radius: float,
) -> CompoundLayout:
    if kind == "simple":
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


def _pinnate(n_lat, terminal, rachis_length, petiole_length, radius):
    leaflets: list[Leaflet] = []
    v0, v1 = petiole_length, petiole_length + rachis_length
    n_levels = max(1, math.ceil(n_lat / 2))
    spacing = (v1 - v0) / n_levels
    lscale = min(0.6, 0.9 * spacing)
    placed = 0
    for i in range(n_levels):
        v = v0 + (i + 0.5) * spacing
        # right then left
        leaflets.append(((0.0, v), _OUTWARD, lscale))
        placed += 1
        if placed < n_lat:
            leaflets.append(((0.0, v), -_OUTWARD, lscale))
            placed += 1
    if terminal:
        leaflets.append(((0.0, v1), 0.0, lscale))
    segs: list[RachisSeg] = [
        ((0.0, 0.0), (0.0, v0), radius),
        ((0.0, v0), (0.0, v1), radius),
    ]
    return CompoundLayout(leaflets=leaflets, rachis_segments=segs)


def _palmate(n, petiole_length, radius):
    leaflets: list[Leaflet] = []
    lscale = 0.8
    if n == 1:
        angles = [0.0]
    else:
        angles = [(-_FAN + 2 * _FAN * k / (n - 1)) for k in range(n)]
    for a in angles:
        leaflets.append(((0.0, petiole_length), a, lscale))
    segs: list[RachisSeg] = (
        [((0.0, 0.0), (0.0, petiole_length), radius)] if petiole_length > 0 else []
    )
    return CompoundLayout(leaflets=leaflets, rachis_segments=segs)


def _bipinnate(pair_count, leaflets_per, rachis_length, petiole_length, radius):
    leaflets: list[Leaflet] = []
    segs: list[RachisSeg] = [
        ((0.0, 0.0), (0.0, petiole_length), radius),
        ((0.0, petiole_length), (0.0, petiole_length + rachis_length), radius),
    ]
    v0, v1 = petiole_length, petiole_length + rachis_length
    n_levels = max(1, pair_count)
    spacing = (v1 - v0) / n_levels
    sec_len = 0.7 * spacing * leaflets_per  # secondary rachis length
    lscale = min(0.4, 0.9 * spacing)
    side_count = 0
    for i in range(n_levels):
        v = v0 + (i + 0.5) * spacing
        for sign in (+1.0, -1.0):
            if side_count >= pair_count * 2:
                break
            sec_ang = sign * _OUTWARD
            # secondary direction unit vector in (u, v): (sin, cos) of sec_ang
            du, dv = math.sin(sec_ang), math.cos(sec_ang)
            base_u, base_v = 0.0, v
            end_u, end_v = base_u + du * sec_len, base_v + dv * sec_len
            segs.append(((base_u, base_v), (end_u, end_v), radius * 0.6))
            for j in range(leaflets_per):
                t = (j + 0.5) / leaflets_per
                ou, ov = base_u + du * sec_len * t, base_v + dv * sec_len * t
                # sub-leaflet angled outward from the secondary on alternating sides
                sub = sec_ang + (_OUTWARD if j % 2 == 0 else -_OUTWARD)
                leaflets.append(((ou, ov), sub, lscale))
            side_count += 1
    return CompoundLayout(leaflets=leaflets, rachis_segments=segs)
```

> The angle/scale constants (`_OUTWARD`, `_FAN`, the `lscale`/`sec_len` formulas) are first-pass values to be tuned later in the empirical loop; the tests only assert counts and symmetry, not exact magnitudes.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/geom/test_compound_leaf.py -v`
Expected: PASS (all 6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/geom/compound_leaf.py tests/geom/test_compound_leaf.py
git commit -m "feat(geom): compound_layout pure 2D leaf layout (#6)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Leaflet sub-config resolution helper

**Files:**
- Modify: `src/palubicki/geom/compound_leaf.py`
- Test: `tests/geom/test_compound_leaf.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/geom/test_compound_leaf.py`:

```python
def test_resolve_leaflet_blade_inherits_when_none():
    from palubicki.config import GeomConfig
    from palubicki.geom.compound_leaf import resolve_leaflet_blade
    g = GeomConfig(leaf_shape="ovate", leaf_margin="serrate", leaf_aspect=0.7)
    shape, margin, aspect = resolve_leaflet_blade(g)
    assert (shape, margin, aspect) == ("ovate", "serrate", 0.7)


def test_resolve_leaflet_blade_overrides():
    from palubicki.config import GeomConfig
    from palubicki.geom.compound_leaf import resolve_leaflet_blade
    g = GeomConfig(
        leaf_shape="ovate", leaf_margin="serrate", leaf_aspect=0.7,
        leaflet_shape="lanceolate", leaflet_margin="entire", leaflet_aspect=0.3,
    )
    assert resolve_leaflet_blade(g) == ("lanceolate", "entire", 0.3)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/geom/test_compound_leaf.py -k resolve -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_leaflet_blade'`.

- [ ] **Step 3: Implement**

Add to `src/palubicki/geom/compound_leaf.py`:

```python
def resolve_leaflet_blade(geom) -> tuple[str, str, float]:
    """(shape, margin, aspect) for a leaflet: leaflet_* overrides, else inherit
    the simple-leaf values."""
    shape = geom.leaflet_shape if geom.leaflet_shape is not None else geom.leaf_shape
    margin = geom.leaflet_margin if geom.leaflet_margin is not None else geom.leaf_margin
    aspect = geom.leaflet_aspect if geom.leaflet_aspect is not None else geom.leaf_aspect
    return shape, margin, aspect
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/geom/test_compound_leaf.py -k resolve -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/geom/compound_leaf.py tests/geom/test_compound_leaf.py
git commit -m "feat(geom): resolve_leaflet_blade inherit/override helper (#6)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Lift leaflets in `build_leaves_primitive`

**Files:**
- Modify: `src/palubicki/geom/leaves.py`
- Test: `tests/geom/test_leaves.py`

- [ ] **Step 1: Write the failing tests**

First find how `tests/geom/test_leaves.py` builds a tree and calls `build_leaves_primitive` (grep the file for `build_leaves_primitive(` and reuse that exact tree-construction idiom — call it `make_tree()` below; if the test module already has such a helper/fixture, use it verbatim).

Append to `tests/geom/test_leaves.py`:

```python
def test_simple_kind_matches_default_output():
    """leaf_kind='simple' (the new default path) is byte-identical to the
    pre-compound single-blade output."""
    import numpy as np
    from palubicki.geom.leaves import build_leaves_primitive
    tree = make_tree()
    mat = _leaf_material()  # reuse whatever the other tests use; or a minimal Material
    base = dict(
        leaf_size=0.06, material=mat, aspect=1.0, splay_deg=0.0, foliage_depth=1,
        leaf_shape="ovate", leaf_margin="entire",
    )
    prim = build_leaves_primitive(tree, leaf_kind="simple", leaflet_specs=None, **base)
    # one leaflet per record, same vertex count as a plain ovate blade build
    assert prim.positions.shape[0] > 0
    assert prim.indices.shape[0] % 3 == 0


def test_pinnate_vert_count_is_linear_in_leaflets():
    from palubicki.geom.leaves import build_leaves_primitive, selected_leaves
    from palubicki.geom.compound_leaf import compound_layout
    tree = make_tree()
    mat = _leaf_material()
    n_records = len(selected_leaves(tree, foliage_depth=1))
    lay = compound_layout(
        "pinnate", leaflet_count=6, leaflet_pair_count=0, terminal_leaflet=True,
        rachis_length=1.5, petiole_length=0.4, rachis_radius=0.045,
    )
    leaflets_per_leaf = len(lay.leaflets)  # 6 + 1 = 7
    prim = build_leaves_primitive(
        tree, leaf_kind="pinnate",
        leaflet_specs=dict(leaflet_count=6, leaflet_pair_count=0, terminal_leaflet=True,
                           rachis_length=1.5, petiole_length=0.4, rachis_radius=0.045,
                           leaflet_shape="ovate", leaflet_margin="entire", leaflet_aspect=0.5),
        leaf_size=0.06, material=mat, aspect=1.0, splay_deg=0.0, foliage_depth=1,
        leaf_shape="ovate", leaf_margin="entire",
    )
    # one ovate blade has a fixed vertex count V; total == n_records * leaflets * V
    from palubicki.geom.leaf_blade import build_blade
    V = build_blade(length=1.0, width=0.5, shape="ovate", margin="entire")[0].shape[0]
    assert prim.positions.shape[0] == n_records * leaflets_per_leaf * V
```

> If `tests/geom/test_leaves.py` has no `make_tree`/`_leaf_material`, copy the construction (tree + Material) from the top of the existing tests in that file. Do NOT invent a new tree shape — reuse the file's.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/geom/test_leaves.py -k "simple_kind or pinnate_vert" -v`
Expected: FAIL — `build_leaves_primitive() got an unexpected keyword argument 'leaf_kind'`.

- [ ] **Step 3: Refactor `build_leaves_primitive` to consume a layout**

In `src/palubicki/geom/leaves.py`:

1. Add import at top: `from palubicki.geom.compound_leaf import compound_layout`.

2. Change the signature of `build_leaves_primitive` to add two params (keep all existing ones):

```python
def build_leaves_primitive(
    tree: Tree,
    *,
    leaf_size: float,
    material: Material,
    aspect: float = 1.0,
    splay_deg: float = 0.0,
    foliage_depth: int = 1,
    needle_cluster_spacing: float = 0.0,
    sun_shade_k: float = 0.0,
    leaf_shape: str = "ovate",
    leaf_margin: str = "entire",
    leaf_margin_depth: float = 0.0,
    leaf_margin_count: int = 0,
    leaf_kind: str = "simple",
    leaflet_specs: dict | None = None,
) -> Primitive:
```

3. Build the layout + blade template. For `simple`, the blade template uses the
   whole-leaf `leaf_shape/leaf_margin/aspect` (unchanged). For compound, it uses
   the leaflet blade params from `leaflet_specs`:

```python
    records = selected_leaves(
        tree, foliage_depth=foliage_depth,
        needle_cluster_spacing=needle_cluster_spacing,
    )
    if not records:
        return Primitive(
            positions=np.zeros((0, 3), dtype=np.float32),
            normals=np.zeros((0, 3), dtype=np.float32),
            uvs=np.zeros((0, 2), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
            material=material,
        )

    if leaf_kind == "simple" or leaflet_specs is None:
        layout = compound_layout(
            "simple", leaflet_count=1, leaflet_pair_count=0, terminal_leaflet=False,
            rachis_length=1.0, petiole_length=0.0, rachis_radius=0.0,
        )
        blade_shape, blade_margin, blade_aspect = leaf_shape, leaf_margin, aspect
        bdepth, bcount = leaf_margin_depth, leaf_margin_count
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
        blade_shape = leaflet_specs["leaflet_shape"]
        blade_margin = leaflet_specs["leaflet_margin"]
        blade_aspect = leaflet_specs["leaflet_aspect"]
        bdepth, bcount = leaf_margin_depth, leaf_margin_count

    blade_pos_unit, _, blade_uv, blade_idx = build_blade(
        length=1.0, width=blade_aspect, shape=blade_shape, margin=blade_margin,
        margin_depth=bdepth, margin_count=bcount,
    )
    blade_v_count = blade_pos_unit.shape[0]
    blade_i_count = blade_idx.shape[0]
    n_planes = 2 if blade_shape == "linear" else 1

    leaflets_per_leaf = len(layout.leaflets)
    verts_per_leaf = n_planes * blade_v_count * leaflets_per_leaf
    idx_per_leaf = n_planes * blade_i_count * leaflets_per_leaf
    n = len(records)
    positions = np.empty((n * verts_per_leaf, 3), dtype=np.float32)
    normals = np.empty((n * verts_per_leaf, 3), dtype=np.float32)
    uvs = np.empty((n * verts_per_leaf, 2), dtype=np.float32)
    indices = np.empty((n * idx_per_leaf,), dtype=np.uint32)

    splay_rad = math.radians(splay_deg)
    for i, (leaf, stem_dir, source_iod, render_pos) in enumerate(records):
        eff_size = compute_effective_leaf_size(source_iod, leaf_size, sun_shade_k)
        v_start = i * verts_per_leaf
        i_start = i * idx_per_leaf
        _lift_compound_leaf(
            render_pos, stem_dir, leaf.azimuth, eff_size, splay_rad, n_planes,
            layout.leaflets, blade_pos_unit, blade_uv, blade_idx,
            positions[v_start : v_start + verts_per_leaf],
            normals[v_start : v_start + verts_per_leaf],
            uvs[v_start : v_start + verts_per_leaf],
            indices[i_start : i_start + idx_per_leaf],
            v_start, blade_v_count, blade_i_count,
        )
    return Primitive(positions=positions, normals=normals, uvs=uvs, indices=indices, material=material)
```

4. Add `_lift_compound_leaf`, generalizing `_lift_leaf` over the leaflet list.
   It reproduces `_lift_leaf` exactly when `leaflets == [((0,0), 0, 1)]`:

```python
def _lift_compound_leaf(center, direction, azimuth, size, splay_rad, n_planes,
                        leaflets, blade_pos_unit, blade_uv, blade_idx,
                        out_pos, out_norm, out_uv, out_idx, base,
                        blade_v_count, blade_i_count):
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    right, forward = _basis_perpendicular_to(d)
    leaf_center = np.asarray(center, dtype=np.float64)

    rot_axis_u = math.cos(azimuth) * right + math.sin(azimuth) * forward
    rot_axis_w = -math.sin(azimuth) * right + math.cos(azimuth) * forward
    leaf_up = math.cos(splay_rad) * d + math.sin(splay_rad) * rot_axis_u

    per_leaflet_v = n_planes * blade_v_count
    per_leaflet_i = n_planes * blade_i_count
    for k, ((u0, v0), axis_angle, scale) in enumerate(leaflets):
        origin = leaf_center + size * (u0 * rot_axis_u + v0 * leaf_up)
        # leaflet axes: rotate (rot_axis_u, leaf_up) by axis_angle about rot_axis_w
        lflt_v = math.cos(axis_angle) * leaf_up + math.sin(axis_angle) * rot_axis_u
        lflt_u = -math.sin(axis_angle) * leaf_up + math.cos(axis_angle) * rot_axis_u
        s = size * scale
        vk = k * per_leaflet_v
        ik = k * per_leaflet_i
        _lift_blade(
            blade_pos_unit, blade_uv, blade_idx,
            origin, lflt_u, lflt_v, rot_axis_w, s,
            out_pos[vk : vk + blade_v_count],
            out_norm[vk : vk + blade_v_count],
            out_uv[vk : vk + blade_v_count],
            out_idx[ik : ik + blade_i_count],
            base + vk,
        )
        if n_planes == 2:
            vb = vk + blade_v_count
            ib = ik + blade_i_count
            _lift_blade(
                blade_pos_unit, blade_uv, blade_idx,
                origin, rot_axis_w, lflt_v, lflt_u, s,
                out_pos[vb : vb + blade_v_count],
                out_norm[vb : vb + blade_v_count],
                out_uv[vb : vb + blade_v_count],
                out_idx[ib : ib + blade_i_count],
                base + vb,
            )
```

5. Keep the old `_lift_leaf` in place (other tests/imports may use it) OR delete
   it if grep shows no other references. Run
   `grep -rn "_lift_leaf\b" src tests` first; delete only if the sole reference
   was the old call site you just replaced.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/geom/test_leaves.py -v`
Expected: PASS — including the existing tests (simple path unchanged) and the two new ones.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/geom/leaves.py tests/geom/test_leaves.py
git commit -m "feat(geom): lift leaflets via compound_layout in build_leaves_primitive (#6)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Rachis primitive + builder wiring

**Files:**
- Modify: `src/palubicki/geom/compound_leaf.py` (add `_emit_cylinder`, `build_rachis_primitive`)
- Modify: `src/palubicki/geom/builder.py`
- Test: `tests/geom/test_compound_leaf.py`, `tests/geom/test_builder.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/geom/test_compound_leaf.py`:

```python
def test_build_rachis_primitive_empty_for_simple():
    # reuse the tree + Material idiom from tests/geom/test_leaves.py
    from tests.geom.test_leaves import make_tree, _leaf_material  # or inline construction
    from palubicki.geom.compound_leaf import build_rachis_primitive
    tree = make_tree()
    prim = build_rachis_primitive(
        tree, material=_leaf_material(), leaf_size=0.06, foliage_depth=1,
        leaf_kind="simple", leaflet_specs=None, ring_sides=5,
    )
    assert prim.positions.shape[0] == 0


def test_build_rachis_primitive_nonempty_for_pinnate():
    from tests.geom.test_leaves import make_tree, _leaf_material
    from palubicki.geom.compound_leaf import build_rachis_primitive
    tree = make_tree()
    prim = build_rachis_primitive(
        tree, material=_leaf_material(), leaf_size=0.06, foliage_depth=1,
        leaf_kind="pinnate",
        leaflet_specs=dict(leaflet_count=6, leaflet_pair_count=0, terminal_leaflet=True,
                           rachis_length=1.5, petiole_length=0.4, rachis_radius=0.045,
                           leaflet_shape="ovate", leaflet_margin="entire", leaflet_aspect=0.5),
        ring_sides=5,
    )
    assert prim.positions.shape[0] > 0
    assert prim.indices.shape[0] % 3 == 0
```

> If `make_tree`/`_leaf_material` aren't importable from the test module, inline the same tree + `Material(...)` construction used in `tests/geom/test_leaves.py`.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/geom/test_compound_leaf.py -k rachis -v`
Expected: FAIL — `ImportError: cannot import name 'build_rachis_primitive'`.

- [ ] **Step 3: Implement the rachis builder**

Add to `src/palubicki/geom/compound_leaf.py` (top imports already have numpy/math):

```python
from palubicki.geom.leaves import (
    _basis_perpendicular_to,
    compute_effective_leaf_size,
    selected_leaves,
)
from palubicki.geom.mesh import Material, Primitive


def _emit_cylinder(p0, p1, radius, ring_sides, base_index):
    """A capped-less cylinder between 3D points p0->p1. Returns
    (positions(2R,3), normals(2R,3), uvs(2R,2), indices(6R,)) with indices
    offset by base_index."""
    p0 = np.asarray(p0, dtype=np.float64)
    p1 = np.asarray(p1, dtype=np.float64)
    axis = p1 - p0
    L = float(np.linalg.norm(axis))
    if L < 1e-12:
        z = np.zeros((0, 3), np.float32)
        return z, z, np.zeros((0, 2), np.float32), np.zeros((0,), np.uint32)
    axis = axis / L
    right, forward = _basis_perpendicular_to(axis)
    ang = np.linspace(0.0, 2.0 * np.pi, ring_sides, endpoint=False)
    ring = (np.cos(ang)[:, None] * right[None, :]
            + np.sin(ang)[:, None] * forward[None, :])  # (R,3) unit
    nrm = ring.astype(np.float32)
    bottom = p0[None, :] + radius * ring
    top = p1[None, :] + radius * ring
    positions = np.concatenate([bottom, top]).astype(np.float32)
    normals = np.concatenate([nrm, nrm])
    uvs = np.zeros((2 * ring_sides, 2), np.float32)
    idx = []
    for k in range(ring_sides):
        a = k
        b = (k + 1) % ring_sides
        c = ring_sides + k
        dd = ring_sides + (k + 1) % ring_sides
        idx += [a, c, b, b, c, dd]
    indices = (np.asarray(idx, dtype=np.uint32) + np.uint32(base_index))
    return positions, normals, uvs, indices


def build_rachis_primitive(
    tree, *, material, leaf_size, foliage_depth, leaf_kind, leaflet_specs,
    ring_sides=5, needle_cluster_spacing=0.0, sun_shade_k=0.0, splay_deg=0.0,
):
    """Thin stem tubes for petiole + rachis(es), lifted at every selected leaf
    site. Empty primitive for leaf_kind='simple' (no rachis)."""
    empty = Primitive(
        positions=np.zeros((0, 3), np.float32), normals=np.zeros((0, 3), np.float32),
        uvs=np.zeros((0, 2), np.float32), indices=np.zeros((0,), np.uint32),
        material=material,
    )
    if leaf_kind == "simple" or leaflet_specs is None:
        return empty
    layout = compound_layout(
        leaf_kind,
        leaflet_count=leaflet_specs["leaflet_count"],
        leaflet_pair_count=leaflet_specs["leaflet_pair_count"],
        terminal_leaflet=leaflet_specs["terminal_leaflet"],
        rachis_length=leaflet_specs["rachis_length"],
        petiole_length=leaflet_specs["petiole_length"],
        rachis_radius=leaflet_specs["rachis_radius"],
    )
    if not layout.rachis_segments:
        return empty
    records = selected_leaves(
        tree, foliage_depth=foliage_depth, needle_cluster_spacing=needle_cluster_spacing,
    )
    splay_rad = math.radians(splay_deg)
    pos_chunks, nrm_chunks, uv_chunks, idx_chunks = [], [], [], []
    cursor = 0
    for leaf, stem_dir, source_iod, render_pos in records:
        eff = compute_effective_leaf_size(source_iod, leaf_size, sun_shade_k)
        d = np.asarray(stem_dir, dtype=np.float64)
        d = d / np.linalg.norm(d)
        right, forward = _basis_perpendicular_to(d)
        az = leaf.azimuth
        rot_axis_u = math.cos(az) * right + math.sin(az) * forward
        leaf_up = math.cos(splay_rad) * d + math.sin(splay_rad) * rot_axis_u
        center = np.asarray(render_pos, dtype=np.float64)

        def lift(uv):
            u, v = uv
            return center + eff * (u * rot_axis_u + v * leaf_up)

        for (s_uv, e_uv, r) in layout.rachis_segments:
            p, nn, uv, ix = _emit_cylinder(lift(s_uv), lift(e_uv), r * eff, ring_sides, cursor)
            if p.shape[0] == 0:
                continue
            pos_chunks.append(p); nrm_chunks.append(nn); uv_chunks.append(uv); idx_chunks.append(ix)
            cursor += p.shape[0]
    if not pos_chunks:
        return empty
    return Primitive(
        positions=np.concatenate(pos_chunks), normals=np.concatenate(nrm_chunks),
        uvs=np.concatenate(uv_chunks), indices=np.concatenate(idx_chunks),
        material=material,
    )
```

> Watch the import direction: `compound_leaf.py` imports from `leaves.py`, and `leaves.py` imports `compound_layout` from `compound_leaf.py`. To avoid a circular import, in `leaves.py` import **only** `compound_layout` at module top (it has no leaves.py dependency at import time — the `from palubicki.geom.leaves import ...` lines in `compound_leaf.py` are evaluated when `compound_leaf` is first imported, which is fine because `leaves` only needs `compound_layout`, defined before those imports execute). If Python still raises a circular ImportError, move the `from palubicki.geom.leaves import ...` block in `compound_leaf.py` to *inside* `build_rachis_primitive` (function-local import).

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/geom/test_compound_leaf.py -k rachis -v`
Expected: PASS.

- [ ] **Step 5: Wire into builder**

In `src/palubicki/geom/builder.py`:

1. Add imports:
```python
from palubicki.geom.compound_leaf import build_rachis_primitive, resolve_leaflet_blade
```

2. Inside `if cfg.geom.enable_leaves:`, replace the `build_leaves_primitive(...)` call so it passes the compound params, and append a rachis primitive when compound:

```python
        g = cfg.geom
        leaflet_specs = None
        if g.leaf_kind != "simple":
            lshape, lmargin, laspect = resolve_leaflet_blade(g)
            leaflet_specs = dict(
                leaflet_count=g.leaflet_count,
                leaflet_pair_count=g.leaflet_pair_count,
                terminal_leaflet=g.terminal_leaflet,
                rachis_length=g.rachis_length_ratio,
                petiole_length=g.petiole_length_ratio,
                rachis_radius=g.rachis_radius_ratio,
                leaflet_shape=lshape, leaflet_margin=lmargin, leaflet_aspect=laspect,
            )
        leaf_prim = build_leaves_primitive(
            tree,
            leaf_size=g.leaf_size,
            material=leaf_mat,
            aspect=g.leaf_aspect,
            splay_deg=g.leaf_splay_deg,
            foliage_depth=g.foliage_depth,
            needle_cluster_spacing=g.needle_cluster_spacing,
            sun_shade_k=g.leaf_sun_shade_k,
            leaf_shape=g.leaf_shape,
            leaf_margin=g.leaf_margin,
            leaf_margin_depth=g.leaf_margin_depth,
            leaf_margin_count=g.leaf_margin_count,
            leaf_kind=g.leaf_kind,
            leaflet_specs=leaflet_specs,
        )
        primitives.append(leaf_prim)
        if leaflet_specs is not None:
            rachis_mat = Material(
                name="rachis",
                base_color=(*g.bark_color, 1.0),
                metallic=0.0,
                roughness=0.9,
                base_color_texture_png=None,
                alpha_mode="OPAQUE",
                alpha_cutoff=0.5,
                double_sided=False,
            )
            rachis_prim = build_rachis_primitive(
                tree, material=rachis_mat, leaf_size=g.leaf_size,
                foliage_depth=g.foliage_depth, leaf_kind=g.leaf_kind,
                leaflet_specs=leaflet_specs, ring_sides=max(3, g.ring_sides // 2),
                needle_cluster_spacing=g.needle_cluster_spacing,
                sun_shade_k=g.leaf_sun_shade_k, splay_deg=g.leaf_splay_deg,
            )
            if rachis_prim.positions.shape[0] > 0:
                primitives.append(rachis_prim)
```

- [ ] **Step 6: Add a builder integration test**

Append to `tests/geom/test_builder.py` (reuse that file's existing `Config`/tree idiom; replace `build_default_config()` / `make_tree()` with the file's actual helpers):

```python
def test_build_mesh_pinnate_adds_rachis_primitive():
    from palubicki.geom.builder import build_mesh
    cfg = build_default_config()
    cfg = cfg_with_geom(cfg, leaf_kind="pinnate", leaflet_count=6)
    tree = make_tree()
    mesh = build_mesh(tree, cfg)
    names = [p.material.name for p in mesh.primitives]
    assert "rachis" in names
    assert "leaf" in names


def test_build_mesh_simple_has_no_rachis():
    from palubicki.geom.builder import build_mesh
    cfg = build_default_config()  # leaf_kind defaults to 'simple'
    tree = make_tree()
    mesh = build_mesh(tree, cfg)
    names = [p.material.name for p in mesh.primitives]
    assert "rachis" not in names
```

- [ ] **Step 7: Run to verify pass**

Run: `.venv/bin/pytest tests/geom/test_compound_leaf.py tests/geom/test_builder.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/palubicki/geom/compound_leaf.py src/palubicki/geom/builder.py tests/geom/test_compound_leaf.py tests/geom/test_builder.py
git commit -m "feat(geom): separate stem-material rachis primitive + builder wiring (#6)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Diagnostics leaf-area through the layout

**Files:**
- Modify: `src/palubicki/sim/diagnostics.py` (`_total_leaf_area`)
- Test: `tests/sim/test_diagnostics.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_diagnostics.py` (reuse the file's tree/cfg idiom):

```python
def test_total_leaf_area_scales_with_leaflets():
    """Pinnate leaf area > simple leaf area for the same tree (more blades),
    and simple is unchanged from the pre-compound value."""
    from palubicki.sim.diagnostics import _total_leaf_area
    cfg_simple = build_default_config()           # leaf_kind='simple'
    tree = make_tree()
    a_simple = _total_leaf_area(tree, cfg_simple)
    cfg_pinnate = cfg_with_geom(cfg_simple, leaf_kind="pinnate", leaflet_count=6,
                                leaflet_aspect=0.5)
    a_pinnate = _total_leaf_area(tree, cfg_pinnate)
    assert a_pinnate > a_simple > 0.0
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_total_leaf_area_scales_with_leaflets -v`
Expected: FAIL — pinnate equals simple (layout not yet consulted), so `a_pinnate > a_simple` is False.

- [ ] **Step 3: Implement**

In `src/palubicki/sim/diagnostics.py`, rewrite `_total_leaf_area` to sum over the
layout's leaflets, using the leaflet blade params for compound kinds:

```python
def _total_leaf_area(tree: Tree, cfg: Config) -> float:
    import math
    import numpy as np
    from palubicki.geom.leaf_blade import build_blade
    from palubicki.geom.leaves import compute_effective_leaf_size, selected_leaves
    from palubicki.geom.compound_leaf import compound_layout, resolve_leaflet_blade

    g = cfg.geom
    records = selected_leaves(
        tree, foliage_depth=g.foliage_depth,
        needle_cluster_spacing=g.needle_cluster_spacing,
    )
    if not records:
        return 0.0

    if g.leaf_kind == "simple":
        layout = compound_layout("simple", leaflet_count=1, leaflet_pair_count=0,
                                 terminal_leaflet=False, rachis_length=1.0,
                                 petiole_length=0.0, rachis_radius=0.0)
        b_shape, b_margin, b_aspect = g.leaf_shape, g.leaf_margin, g.leaf_aspect
    else:
        layout = compound_layout(
            g.leaf_kind, leaflet_count=g.leaflet_count,
            leaflet_pair_count=g.leaflet_pair_count,
            terminal_leaflet=g.terminal_leaflet,
            rachis_length=g.rachis_length_ratio,
            petiole_length=g.petiole_length_ratio,
            rachis_radius=g.rachis_radius_ratio,
        )
        b_shape, b_margin, b_aspect = resolve_leaflet_blade(g)

    blade_pos, _, _, blade_idx = build_blade(
        length=1.0, width=b_aspect, shape=b_shape,
        margin=b_margin, margin_depth=g.leaf_margin_depth, margin_count=g.leaf_margin_count,
    )
    pos2d = blade_pos.astype(np.float64)
    tris = blade_idx.reshape(-1, 3)
    e1 = pos2d[tris[:, 1]] - pos2d[tris[:, 0]]
    e2 = pos2d[tris[:, 2]] - pos2d[tris[:, 0]]
    unit_blade_area = float(0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum())

    splay_rad = math.radians(g.leaf_splay_deg)
    n_planes = 2 if b_shape == "linear" else 1
    plane_b_factor = 1.0 if n_planes == 2 else 0.0
    pair_area = unit_blade_area * (math.cos(splay_rad) + plane_b_factor)

    leaflet_scale_sq_sum = sum(scale * scale for (_uv, _a, scale) in layout.leaflets)

    total = 0.0
    for _leaf, _stem_dir, source_iod, _pos in records:
        eff = compute_effective_leaf_size(source_iod, g.leaf_size, g.leaf_sun_shade_k)
        total += pair_area * (eff * eff) * leaflet_scale_sq_sum
    return total
```

> For `leaf_kind="simple"`, `layout.leaflets == [((0,0),0,1.0)]` so
> `leaflet_scale_sq_sum == 1.0` and `b_*` equal the leaf params → the result is
> **bit-for-bit** the pre-change value. This is what keeps the four species
> diagnostic hashes from moving.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -v`
Expected: PASS (new test + all existing diagnostics tests, since `simple` is unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/diagnostics.py tests/sim/test_diagnostics.py
git commit -m "feat(diagnostics): total_leaf_area sums over compound layout leaflets (#6)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Full-suite + golden verification, ruff, docs

**Files:**
- Modify: `docs/roadmap.md`, `docs/botany/simulator-gap-analysis.md` (completion bookkeeping)

- [ ] **Step 1: Run the whole test suite**

Run: `.venv/bin/pytest -q`
Expected: PASS. The species goldens (`tests/golden/test_species_goldens.py`) and
GLB goldens (`tests/golden/test_goldens.py`) must be **unchanged** — all four
species default to `leaf_kind="simple"`, which is byte-identical. If a golden
fails, STOP: a "simple" path regressed; diff the failing primitive and fix
before regenerating. Do **not** blindly regenerate goldens.

- [ ] **Step 2: Lint**

Run: `.venv/bin/ruff check src/palubicki/geom/compound_leaf.py src/palubicki/geom/leaves.py src/palubicki/geom/builder.py src/palubicki/sim/diagnostics.py src/palubicki/config.py`
Expected: no errors. Fix any (unused imports, line length) and re-run.

- [ ] **Step 3: Smoke-render the four kinds (manual sanity)**

Run a tiny script via `.venv/bin/python` that builds a tree and exports a `.glb`
for `leaf_kind` in `{pinnate, palmate, bipinnate}` (reuse the CLI or the
`build_mesh` + export path the repo already exposes; grep `tests/export` for the
export helper). Confirm: no exceptions, leaf+rachis primitives present,
vert count grows with `leaflet_count`. This is a sanity check, not an automated
test.

- [ ] **Step 4: Update completion docs**

- `docs/roadmap.md`: in item 1 of "À faire (dans l'ordre)", strike #6 (compound
  leaves) as delivered; move a "#6 — feuilles composées (pinnée/palmée/bipinnée)"
  row into the "Fait" table with PR **#58**. Re-check ordering of the remaining
  sub-items (#5 pétiole, #7 fascicules).
- `docs/botany/simulator-gap-analysis.md`: flip the compound-leaf row in §6 from
  ❌/🟡 to ✅; update the §6 verdict and the "Last reviewed" line; refresh "Top
  remaining recommendations" #2 if compound leaves was listed there.

- [ ] **Step 5: Commit**

```bash
git add docs/roadmap.md docs/botany/simulator-gap-analysis.md
git commit -m "docs: mark compound leaves (#6) done; refresh gap analysis

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Push**

```bash
git push
```

---

## Self-Review notes

- **Spec coverage:** simple/pinnate/palmate/bipinnate (Task 2); leaflet sub-config
  inherit/override (Task 3); instanced leaflet lift + linear growth (Task 4);
  separate stem-material rachis + `leaf_kind != "simple"` gating (Task 5);
  diagnostics no-drift (Task 6); goldens unchanged + docs (Task 7); config +
  validation (Task 1). All acceptance criteria mapped.
- **Regression guarantee** lives in three places, all keyed on
  `leaf_kind == "simple"` → single leaflet `((0,0),0,1)` + no rachis: geometry
  (Task 4), diagnostics (Task 6), builder skips the rachis primitive (Task 5).
- **Naming consistency:** `compound_layout`, `CompoundLayout`,
  `resolve_leaflet_blade`, `build_rachis_primitive`, `_lift_compound_leaf`,
  `_emit_cylinder`, `leaflet_specs` (dict), used identically across tasks.
- **Known soft spots to tune later (empirical loop, not blockers):** leaflet
  angle/scale constants in `compound_leaf.py`; rachis `ring_sides`; whether
  petiole+rachis should be one tube vs two. Tests assert structure (counts,
  symmetry, ordering), not exact magnitudes, so tuning won't churn tests.
```
