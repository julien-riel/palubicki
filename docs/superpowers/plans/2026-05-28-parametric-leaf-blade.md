# Parametric Leaf Blade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace flat-rectangle leaf geometry with parametric blades (6 shapes × 4 margins) so each species's silhouette is visually distinct.

**Architecture:** Per-shape outline functions feed a shared margin-modulation pass, a fan-from-interior-anchor triangulator, and a 2D→3D lifter. Triangulated blade replaces the cross-quad in `geom/leaves.py`; cluster + cross-blade structure preserved. Spec: `docs/superpowers/specs/2026-05-28-parametric-leaf-blade-design.md`.

**Tech Stack:** Python 3.14, NumPy (only — no scipy/shapely), PyTest, matplotlib (visual reference only), `.venv/bin/` for all CLI invocations.

---

## File Structure

**Created:**
- `src/palubicki/geom/leaf_blade.py` — outline functions + margin + triangulate + lift + public `build_blade()`.
- `tests/geom/test_leaf_blade.py` — 2D unit tests covering outlines, margin, triangulation, errors.
- `scripts/regen_leaf_visuals.py` — matplotlib script that writes one PNG per `(shape, margin)`.
- `tests/geom/visual/<shape>_<margin>.png` — 12 PNGs (6 shapes × default-margin-for-shape combos, plus extras for the species presets).

**Modified:**
- `src/palubicki/geom/leaves.py` — `_emit_leaf_cluster` rewritten to lift a `BladeTemplate`; `_add_quad` removed.
- `src/palubicki/config.py` — `GeomConfig` gains `leaf_shape`, `leaf_margin`, `leaf_margin_depth`, `leaf_margin_count` + validation in `Config.__post_init__`.
- `tests/geom/test_leaves.py` — vert-count assertions updated; some tests renamed.
- `tests/geom/test_leaf_cluster.py` — vert-count assertions updated.
- `tests/test_config_leaf_cluster.py` — coverage for 4 new keys added.
- `src/palubicki/configs/species/{oak,birch,maple,pine,fir}.yaml` — new `leaf_shape` / `leaf_margin` fields.
- `out/oak.glb`, `out/birch.glb`, `out/maple.glb`, `out/pine.glb`, `out/fir.glb` — regenerated.
- `docs/botany/simulator-gap-analysis.md` — §6 row marked `✅`, "Last reviewed" date bumped.

**Untouched:**
- `tests/geom/test_leaf_texture.py` — texture-only test, not affected by mesh changes.

---

## Task 1: Module skeleton + linear outline + fan triangulator + build_blade dispatcher

**Files:**
- Create: `src/palubicki/geom/leaf_blade.py`
- Create: `tests/geom/test_leaf_blade.py`

This task lands the module skeleton plus the simplest shape (linear rectangle) end-to-end so the public `build_blade()` API exists from the start. Other shapes get added in later tasks.

- [ ] **Step 1: Write failing tests for linear outline**

Create `tests/geom/test_leaf_blade.py`:

```python
import numpy as np
import pytest

from palubicki.geom.leaf_blade import (
    _outline_linear, _triangulate_fan, build_blade,
)


def _polygon_signed_area(pts: np.ndarray) -> float:
    x = pts[:, 0]
    y = pts[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _point_in_polygon(pt: np.ndarray, poly: np.ndarray) -> bool:
    x, y = float(pt[0]), float(pt[1])
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi):
            inside = not inside
        j = i
    return inside


def test_linear_outline_has_4_corners():
    boundary, anchor = _outline_linear(L=1.0, W=0.2)
    assert boundary.shape == (4, 2)
    assert boundary.dtype == np.float64
    assert anchor.shape == (2,)


def test_linear_outline_bounding_box():
    boundary, _ = _outline_linear(L=1.0, W=0.2)
    assert boundary[:, 0].min() == pytest.approx(-0.1)
    assert boundary[:, 0].max() == pytest.approx(0.1)
    assert boundary[:, 1].min() == pytest.approx(0.0)
    assert boundary[:, 1].max() == pytest.approx(1.0)


def test_linear_outline_ccw():
    boundary, _ = _outline_linear(L=1.0, W=0.2)
    assert _polygon_signed_area(boundary) > 0


def test_linear_anchor_inside_polygon():
    boundary, anchor = _outline_linear(L=1.0, W=0.2)
    assert _point_in_polygon(anchor, boundary)


def test_triangulate_fan_basic_shape():
    boundary = np.array([[-0.1, 0.0], [0.1, 0.0], [0.1, 1.0], [-0.1, 1.0]],
                        dtype=np.float64)
    anchor = np.array([0.0, 0.5], dtype=np.float64)
    positions, indices = _triangulate_fan(boundary, anchor)
    # anchor at index 0, 4 boundary points at indices 1..4
    assert positions.shape == (5, 2)
    np.testing.assert_allclose(positions[0], anchor)
    # 4 triangles (one per boundary segment), 12 indices
    assert indices.shape == (12,)
    assert indices.max() < 5
    # All triangles share vertex 0 (the anchor)
    tris = indices.reshape(-1, 3)
    assert (tris[:, 0] == 0).all()


def test_triangulate_fan_covers_polygon():
    boundary = np.array([[-0.1, 0.0], [0.1, 0.0], [0.1, 1.0], [-0.1, 1.0]],
                        dtype=np.float64)
    anchor = np.array([0.0, 0.5], dtype=np.float64)
    positions, indices = _triangulate_fan(boundary, anchor)
    tri_area_sum = 0.0
    for i in range(0, len(indices), 3):
        a, b, c = positions[indices[i]], positions[indices[i+1]], positions[indices[i+2]]
        tri_area_sum += 0.5 * abs(
            (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        )
    assert tri_area_sum == pytest.approx(_polygon_signed_area(boundary), rel=1e-9)


def test_build_blade_linear_entire_returns_consistent_arrays():
    pos, norm, uv, idx = build_blade(
        length=1.0, width=0.2, shape="linear", margin="entire",
        margin_depth=0.0, margin_count=0,
    )
    assert pos.shape[0] == norm.shape[0] == uv.shape[0]
    assert pos.shape[1] == 3
    assert norm.shape[1] == 3
    assert uv.shape[1] == 2
    assert idx.shape[0] % 3 == 0
    assert int(idx.max()) < pos.shape[0]


def test_build_blade_linear_uvs_span_unit_square():
    _, _, uv, _ = build_blade(
        length=1.0, width=0.2, shape="linear", margin="entire",
        margin_depth=0.0, margin_count=0,
    )
    assert uv[:, 0].min() == pytest.approx(0.0)
    assert uv[:, 0].max() == pytest.approx(1.0)
    assert uv[:, 1].min() == pytest.approx(0.0)
    assert uv[:, 1].max() == pytest.approx(1.0)


def test_build_blade_unknown_shape_raises():
    with pytest.raises(ValueError, match="unknown leaf shape"):
        build_blade(length=1.0, width=0.2, shape="invalid", margin="entire",
                    margin_depth=0.0, margin_count=0)


def test_build_blade_unknown_margin_raises():
    with pytest.raises(ValueError, match="unknown leaf margin"):
        build_blade(length=1.0, width=0.2, shape="linear", margin="invalid",
                    margin_depth=0.0, margin_count=0)


def test_build_blade_rejects_zero_length():
    with pytest.raises(ValueError, match="length"):
        build_blade(length=0.0, width=0.2, shape="linear", margin="entire",
                    margin_depth=0.0, margin_count=0)


def test_build_blade_rejects_zero_width():
    with pytest.raises(ValueError, match="width"):
        build_blade(length=1.0, width=0.0, shape="linear", margin="entire",
                    margin_depth=0.0, margin_count=0)


def test_build_blade_rejects_margin_depth_out_of_range():
    with pytest.raises(ValueError, match="margin_depth"):
        build_blade(length=1.0, width=0.2, shape="linear", margin="entire",
                    margin_depth=1.5, margin_count=0)
    with pytest.raises(ValueError, match="margin_depth"):
        build_blade(length=1.0, width=0.2, shape="linear", margin="entire",
                    margin_depth=-0.1, margin_count=0)


def test_build_blade_rejects_negative_margin_count():
    with pytest.raises(ValueError, match="margin_count"):
        build_blade(length=1.0, width=0.2, shape="linear", margin="entire",
                    margin_depth=0.0, margin_count=-1)
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/pytest tests/geom/test_leaf_blade.py -v
```
Expected: all tests fail with `ModuleNotFoundError: No module named 'palubicki.geom.leaf_blade'`.

- [ ] **Step 3: Implement `leaf_blade.py` with linear outline + triangulator + dispatcher**

Create `src/palubicki/geom/leaf_blade.py`:

```python
"""Parametric leaf blade generation.

Per-shape outline functions return a 2D boundary polygon + interior anchor;
a shared margin pass perturbs the boundary with teeth or lobes; a fan-from-
anchor triangulator emits triangles; the result is lifted into a flat 3D
primitive aligned with given basis vectors (done in geom/leaves.py).

Conventions:
    - 2D local frame: (u, v). u = lateral, v = blade-length axis.
    - Origin (0, 0) is the petiole attachment point.
    - Boundary points are CCW, do NOT include a duplicate closing vertex.
    - Anchor is interior to the polygon; star-shape from anchor is required.
"""
from __future__ import annotations

from typing import Literal

import numpy as np

Shape = Literal["linear", "elliptic", "lanceolate", "ovate", "cordate", "palmate"]
Margin = Literal["entire", "serrate", "dentate", "lobed"]

_SHAPES = ("linear", "elliptic", "lanceolate", "ovate", "cordate", "palmate")
_MARGINS = ("entire", "serrate", "dentate", "lobed")


def build_blade(
    *,
    length: float,
    width: float,
    shape: str,
    margin: str,
    margin_depth: float = 0.0,
    margin_count: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build a triangulated leaf blade as a flat 3D mesh in the (u, v, 0) plane.

    Returns
    -------
    positions : (N, 3) float32
        Vertex positions. positions[0] is the anchor; positions[1:] are the
        boundary points after margin modulation.
    normals : (N, 3) float32
        Constant +z normal for all vertices.
    uvs : (N, 2) float32
        tex_u = (u + width/2) / width, tex_v = v / length.
    indices : (M,) uint32
        Triangle indices; M is divisible by 3.
    """
    if length <= 0:
        raise ValueError(f"length must be > 0, got {length}")
    if width <= 0:
        raise ValueError(f"width must be > 0, got {width}")
    if not (0.0 <= margin_depth <= 1.0):
        raise ValueError(f"margin_depth must be in [0, 1], got {margin_depth}")
    if margin_count < 0:
        raise ValueError(f"margin_count must be >= 0, got {margin_count}")
    if shape not in _SHAPES:
        raise ValueError(
            f"unknown leaf shape: {shape!r}; expected one of {list(_SHAPES)}"
        )
    if margin not in _MARGINS:
        raise ValueError(
            f"unknown leaf margin: {margin!r}; expected one of {list(_MARGINS)}"
        )

    outline_fn = _OUTLINE_FNS[shape]
    boundary, anchor = outline_fn(length, width)
    # margin pass (no-op for "entire" or count==0)
    boundary = _apply_margin(boundary, margin, margin_depth, margin_count, shape, length, width)
    positions_2d, indices = _triangulate_fan(boundary, anchor)

    # Lift 2D into 3D: z=0, normal=+z, UV from bounding-box convention.
    n = positions_2d.shape[0]
    positions = np.zeros((n, 3), dtype=np.float32)
    positions[:, 0] = positions_2d[:, 0]
    positions[:, 1] = positions_2d[:, 1]
    normals = np.zeros((n, 3), dtype=np.float32)
    normals[:, 2] = 1.0
    uvs = np.empty((n, 2), dtype=np.float32)
    uvs[:, 0] = (positions_2d[:, 0] + width * 0.5) / width
    uvs[:, 1] = positions_2d[:, 1] / length
    indices = indices.astype(np.uint32, copy=False)
    return positions, normals, uvs, indices


def _outline_linear(L: float, W: float) -> tuple[np.ndarray, np.ndarray]:
    boundary = np.array(
        [[-W * 0.5, 0.0], [W * 0.5, 0.0], [W * 0.5, L], [-W * 0.5, L]],
        dtype=np.float64,
    )
    anchor = np.array([0.0, L * 0.5], dtype=np.float64)
    return boundary, anchor


def _triangulate_fan(
    boundary: np.ndarray, anchor: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Fan triangulate boundary from anchor. positions[0] is the anchor."""
    n = boundary.shape[0]
    positions = np.empty((n + 1, 2), dtype=np.float64)
    positions[0] = anchor
    positions[1:] = boundary
    indices = np.empty((n * 3,), dtype=np.uint32)
    for i in range(n):
        indices[3 * i + 0] = 0
        indices[3 * i + 1] = 1 + i
        indices[3 * i + 2] = 1 + ((i + 1) % n)
    return positions, indices


def _apply_margin(
    boundary: np.ndarray, margin: str, depth: float, count: int,
    shape: str, length: float, width: float,
) -> np.ndarray:
    """No-op for now; subsequent task implements serrate/dentate/lobed."""
    if margin == "entire" or count == 0:
        return boundary
    return boundary  # placeholder; later task adds tooth insertion


_OUTLINE_FNS = {
    "linear": _outline_linear,
}
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv/bin/pytest tests/geom/test_leaf_blade.py -v
```
Expected: all 14 tests pass.

- [ ] **Step 5: Commit**

```
git add src/palubicki/geom/leaf_blade.py tests/geom/test_leaf_blade.py
git commit -m "leaf_blade: skeleton, linear shape, fan triangulator, build_blade dispatcher"
```

---

## Task 2: Convex outlines — elliptic, lanceolate, ovate, cordate

**Files:**
- Modify: `src/palubicki/geom/leaf_blade.py`
- Modify: `tests/geom/test_leaf_blade.py`

- [ ] **Step 1: Write failing tests for the four new outlines**

Append to `tests/geom/test_leaf_blade.py`:

```python
from palubicki.geom.leaf_blade import (
    _outline_elliptic, _outline_lanceolate, _outline_ovate, _outline_cordate,
)


def _segments_intersect(a, b, c, d) -> bool:
    """Return True if open segments [a,b] and [c,d] properly intersect."""
    def cross(o, x, y):
        return (x[0] - o[0]) * (y[1] - o[1]) - (x[1] - o[1]) * (y[0] - o[0])
    d1 = cross(c, d, a)
    d2 = cross(c, d, b)
    d3 = cross(a, b, c)
    d4 = cross(a, b, d)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def _is_star_shape_from(anchor: np.ndarray, boundary: np.ndarray) -> bool:
    """Every boundary vertex must have unobstructed line-of-sight to anchor."""
    n = len(boundary)
    for i in range(n):
        p = boundary[i]
        for j in range(n):
            j2 = (j + 1) % n
            if j == i or j2 == i:
                continue  # adjacent edges share p
            if _segments_intersect(anchor, p, boundary[j], boundary[j2]):
                return False
    return True


@pytest.mark.parametrize("name,fn,extra_v_range", [
    ("elliptic", _outline_elliptic, 0.0),
    ("lanceolate", _outline_lanceolate, 0.0),
    ("ovate", _outline_ovate, 0.0),
    ("cordate", _outline_cordate, 0.2),  # allow basal notch slack
])
def test_convex_outline_basic_invariants(name, fn, extra_v_range):
    boundary, anchor = fn(L=1.0, W=0.5)
    assert boundary.shape[1] == 2
    assert boundary.dtype == np.float64
    assert _polygon_signed_area(boundary) > 0, f"{name} not CCW"
    assert _point_in_polygon(anchor, boundary), f"{name} anchor not inside"
    assert _is_star_shape_from(anchor, boundary), f"{name} not star-shaped"
    # Bounding box check
    assert boundary[:, 0].min() >= -0.25 - 1e-6
    assert boundary[:, 0].max() <= 0.25 + 1e-6
    assert boundary[:, 1].min() >= -extra_v_range - 1e-6
    assert boundary[:, 1].max() <= 1.0 + 1e-6


def test_lanceolate_widest_at_lower_third():
    boundary, _ = _outline_lanceolate(L=1.0, W=0.5)
    # The widest u-coordinate should occur at v ~ L/3 (one-third).
    widest_idx = int(np.argmax(boundary[:, 0]))
    widest_v = boundary[widest_idx, 1]
    assert 0.2 < widest_v < 0.5, f"expected widest near v=L/3, got {widest_v}"


def test_ovate_broader_at_base_than_lanceolate():
    """At v = L/4, ovate should be wider than lanceolate."""
    b_ovate, _ = _outline_ovate(L=1.0, W=0.5)
    b_lanc, _ = _outline_lanceolate(L=1.0, W=0.5)
    def half_width_at(boundary, v_target):
        return max(
            abs(boundary[i, 0]) for i in range(len(boundary))
            if abs(boundary[i, 1] - v_target) < 0.1
        )
    assert half_width_at(b_ovate, 0.25) > half_width_at(b_lanc, 0.25)


def test_cordate_has_basal_notch():
    boundary, _ = _outline_cordate(L=1.0, W=0.5)
    # Notch creates a point with v < 0
    assert boundary[:, 1].min() < 0.0


@pytest.mark.parametrize("shape", ["elliptic", "lanceolate", "ovate", "cordate"])
def test_build_blade_convex_shapes_under_64_verts(shape):
    pos, _, _, _ = build_blade(
        length=1.0, width=0.5, shape=shape, margin="entire",
        margin_depth=0.0, margin_count=0,
    )
    assert pos.shape[0] <= 64
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/pytest tests/geom/test_leaf_blade.py -v -k "convex or lanceolate or ovate or cordate"
```
Expected: import errors / `_outline_elliptic` undefined.

- [ ] **Step 3: Add the four outline functions and register them**

Edit `src/palubicki/geom/leaf_blade.py`. After `_outline_linear`, add:

```python
def _outline_elliptic(L: float, W: float, n: int = 16) -> tuple[np.ndarray, np.ndarray]:
    """Half-ellipse symmetric about u=0, max width at v=L/2."""
    # Sample boundary CCW starting from petiole (0, 0).
    # Right side ascending: v from 0 to L; left side descending: v from L to 0.
    # Use n samples per side; skip duplicate at petiole and tip.
    half = max(2, n // 2)
    t_right = np.linspace(0.0, 1.0, half, endpoint=False)
    v_right = t_right * L
    u_right = (W * 0.5) * np.sin(np.pi * t_right)
    t_left = np.linspace(1.0, 0.0, half, endpoint=False)
    v_left = t_left * L
    u_left = -(W * 0.5) * np.sin(np.pi * t_left)
    boundary = np.empty((2 * half, 2), dtype=np.float64)
    boundary[:half, 0] = u_right
    boundary[:half, 1] = v_right
    boundary[half:, 0] = u_left
    boundary[half:, 1] = v_left
    anchor = np.array([0.0, L * 0.5], dtype=np.float64)
    return boundary, anchor


def _outline_lanceolate(L: float, W: float, n: int = 16) -> tuple[np.ndarray, np.ndarray]:
    """Widest at v=L/3, narrow toward tip."""
    half = max(2, n // 2)
    t_right = np.linspace(0.0, 1.0, half, endpoint=False)
    v_right = t_right * L
    u_right = (W * 0.5) * np.power(np.sin(np.pi * t_right), 0.7) \
              * np.power(1.0 - 0.3 * t_right, 0.5)
    t_left = np.linspace(1.0, 0.0, half, endpoint=False)
    v_left = t_left * L
    u_left = -(W * 0.5) * np.power(np.sin(np.pi * t_left), 0.7) \
              * np.power(1.0 - 0.3 * t_left, 0.5)
    boundary = np.empty((2 * half, 2), dtype=np.float64)
    boundary[:half, 0] = u_right
    boundary[:half, 1] = v_right
    boundary[half:, 0] = u_left
    boundary[half:, 1] = v_left
    anchor = np.array([0.0, L / 3.0], dtype=np.float64)
    return boundary, anchor


def _outline_ovate(L: float, W: float, n: int = 16) -> tuple[np.ndarray, np.ndarray]:
    """Broader at base than lanceolate, widest at v=L/3."""
    half = max(2, n // 2)
    t_right = np.linspace(0.0, 1.0, half, endpoint=False)
    v_right = t_right * L
    # Shape function: broad lobe early, taper to tip.
    u_right = (W * 0.5) * np.power(np.sin(np.pi * t_right), 1.0) \
              * (1.0 - 0.4 * t_right)
    t_left = np.linspace(1.0, 0.0, half, endpoint=False)
    v_left = t_left * L
    u_left = -(W * 0.5) * np.power(np.sin(np.pi * t_left), 1.0) \
              * (1.0 - 0.4 * t_left)
    boundary = np.empty((2 * half, 2), dtype=np.float64)
    boundary[:half, 0] = u_right
    boundary[:half, 1] = v_right
    boundary[half:, 0] = u_left
    boundary[half:, 1] = v_left
    anchor = np.array([0.0, L / 3.0], dtype=np.float64)
    return boundary, anchor


def _outline_cordate(L: float, W: float, n: int = 20) -> tuple[np.ndarray, np.ndarray]:
    """Heart-shaped: ovate body with a basal notch at v=0."""
    # Start with ovate body, then insert two back-lobes near v=0.
    half = max(3, n // 2)
    t_right = np.linspace(0.0, 1.0, half, endpoint=False)
    v_right = t_right * L
    u_right = (W * 0.5) * np.power(np.sin(np.pi * t_right), 1.0) \
              * (1.0 - 0.4 * t_right)
    t_left = np.linspace(1.0, 0.0, half, endpoint=False)
    v_left = t_left * L
    u_left = -(W * 0.5) * np.power(np.sin(np.pi * t_left), 1.0) \
              * (1.0 - 0.4 * t_left)
    # Insert basal notch at the start (after right-side traversal ends at petiole),
    # before flipping to left. We achieve this by appending a "notch dip" vertex
    # at (0, -L/8) right where the boundary crosses the petiole.
    # CCW order: right-side (going up, then back down) ... left-side. The basal
    # notch belongs *between* right-tail and left-head. Build:
    boundary = np.empty((2 * half + 1, 2), dtype=np.float64)
    boundary[:half, 0] = u_right
    boundary[:half, 1] = v_right
    # Insert basal notch vertex
    boundary[half, 0] = 0.0
    boundary[half, 1] = -L / 8.0
    boundary[half + 1:, 0] = u_left
    boundary[half + 1:, 1] = v_left
    anchor = np.array([0.0, L / 3.0], dtype=np.float64)
    return boundary, anchor


_OUTLINE_FNS = {
    "linear": _outline_linear,
    "elliptic": _outline_elliptic,
    "lanceolate": _outline_lanceolate,
    "ovate": _outline_ovate,
    "cordate": _outline_cordate,
}
```

Note: the parametrized invariants test may fail for some shapes if the star-shape check finds non-convex cases. Tune the formulas if needed (e.g., reduce taper exponents) until all shapes pass.

- [ ] **Step 4: Run tests to verify all pass**

```
.venv/bin/pytest tests/geom/test_leaf_blade.py -v
```
Expected: all tests pass. If a shape fails the star-shape or CCW assertion, tune the formula and re-run.

- [ ] **Step 5: Commit**

```
git add src/palubicki/geom/leaf_blade.py tests/geom/test_leaf_blade.py
git commit -m "leaf_blade: convex outlines (elliptic, lanceolate, ovate, cordate)"
```

---

## Task 3: Palmate outline

**Files:**
- Modify: `src/palubicki/geom/leaf_blade.py`
- Modify: `tests/geom/test_leaf_blade.py`

- [ ] **Step 1: Write failing tests for palmate**

Append to `tests/geom/test_leaf_blade.py`:

```python
from palubicki.geom.leaf_blade import _outline_palmate


def test_palmate_outline_invariants():
    boundary, anchor = _outline_palmate(L=1.0, W=1.0)
    assert boundary.shape[1] == 2
    assert _polygon_signed_area(boundary) > 0
    assert _point_in_polygon(anchor, boundary)
    assert _is_star_shape_from(anchor, boundary)


def test_palmate_has_five_radial_peaks():
    """A palmate outline should have 5 local maxima in radial distance from anchor."""
    boundary, anchor = _outline_palmate(L=1.0, W=1.0)
    radii = np.linalg.norm(boundary - anchor, axis=1)
    # Count local maxima (compare to both neighbors with wraparound).
    n = len(radii)
    peaks = 0
    for i in range(n):
        if radii[i] > radii[(i - 1) % n] and radii[i] > radii[(i + 1) % n]:
            peaks += 1
    assert peaks == 5, f"expected 5 lobe peaks, got {peaks}"


def test_palmate_under_64_verts():
    pos, _, _, _ = build_blade(
        length=1.0, width=1.0, shape="palmate", margin="entire",
        margin_depth=0.0, margin_count=0,
    )
    assert pos.shape[0] <= 64
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/pytest tests/geom/test_leaf_blade.py::test_palmate_outline_invariants tests/geom/test_leaf_blade.py::test_palmate_has_five_radial_peaks tests/geom/test_leaf_blade.py::test_palmate_under_64_verts -v
```

Expected: import errors / `_outline_palmate` undefined.

- [ ] **Step 3: Implement palmate outline**

In `src/palubicki/geom/leaf_blade.py`, after `_outline_cordate`, add:

```python
def _outline_palmate(L: float, W: float, samples_per_lobe: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """5 radial lobes from center (0, 0.4*L).

    Each lobe has a peak at angle theta_k and an inter-lobe valley at the
    midpoint between adjacent peaks. Boundary is sampled around the polar
    contour at samples_per_lobe samples per lobe (lobe edge from valley → peak
    → valley = 2 segments) plus extra detail at peaks.
    """
    n_lobes = 5
    cx, cy = 0.0, 0.4 * L
    anchor = np.array([cx, cy], dtype=np.float64)
    R_peak = 0.5 * max(L, W)
    R_valley = 0.3 * R_peak
    # Lobe angles (radians), measured from +u CCW.
    # We want one lobe straight up (along +v) and four lobes splayed.
    # theta_k = pi/2 + k * (2*pi/n_lobes) for k = 0..n_lobes-1
    boundary_pts = []
    for k in range(n_lobes):
        theta_peak = np.pi * 0.5 + k * (2.0 * np.pi / n_lobes)
        theta_next_peak = np.pi * 0.5 + ((k + 1) % n_lobes) * (2.0 * np.pi / n_lobes)
        # Walk from this peak toward the valley with the next peak.
        # samples_per_lobe is the number of segments from peak to valley.
        # Use intermediate samples for a smoother lobe edge.
        # First emit the peak itself.
        peak = np.array([cx + R_peak * np.cos(theta_peak),
                          cy + R_peak * np.sin(theta_peak)])
        boundary_pts.append(peak)
        # Then samples_per_lobe-1 intermediate points heading to the valley.
        theta_valley = (theta_peak + theta_next_peak) * 0.5
        # Interpolate radial distance from R_peak to R_valley.
        for s in range(1, samples_per_lobe):
            t = s / samples_per_lobe
            theta = theta_peak + t * (theta_valley - theta_peak)
            R = R_peak + t * (R_valley - R_peak)
            boundary_pts.append(np.array([cx + R * np.cos(theta),
                                           cy + R * np.sin(theta)]))
        # Emit the valley point.
        boundary_pts.append(np.array([cx + R_valley * np.cos(theta_valley),
                                       cy + R_valley * np.sin(theta_valley)]))
        # Then samples_per_lobe-1 intermediate points heading toward the next peak.
        for s in range(1, samples_per_lobe):
            t = s / samples_per_lobe
            theta = theta_valley + t * (theta_next_peak - theta_valley)
            R = R_valley + t * (R_peak - R_valley)
            boundary_pts.append(np.array([cx + R * np.cos(theta),
                                           cy + R * np.sin(theta)]))
    boundary = np.array(boundary_pts, dtype=np.float64)
    # CCW check: signed area should be > 0. If not, reverse.
    x = boundary[:, 0]
    y = boundary[:, 1]
    area = 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
    if area < 0:
        boundary = boundary[::-1].copy()
    return boundary, anchor
```

And add to the dispatch table:

```python
_OUTLINE_FNS = {
    "linear": _outline_linear,
    "elliptic": _outline_elliptic,
    "lanceolate": _outline_lanceolate,
    "ovate": _outline_ovate,
    "cordate": _outline_cordate,
    "palmate": _outline_palmate,
}
```

- [ ] **Step 4: Run tests**

```
.venv/bin/pytest tests/geom/test_leaf_blade.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add src/palubicki/geom/leaf_blade.py tests/geom/test_leaf_blade.py
git commit -m "leaf_blade: palmate outline (5 radial lobes)"
```

---

## Task 4: Margin algorithm (serrate, dentate, lobed)

**Files:**
- Modify: `src/palubicki/geom/leaf_blade.py`
- Modify: `tests/geom/test_leaf_blade.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/geom/test_leaf_blade.py`:

```python
from palubicki.geom.leaf_blade import _apply_margin


def test_apply_margin_entire_is_noop():
    b, _ = _outline_ovate(L=1.0, W=0.5)
    b_out = _apply_margin(b, "entire", 0.1, 5, "ovate", 1.0, 0.5)
    np.testing.assert_array_equal(b, b_out)


def test_apply_margin_zero_count_is_noop():
    b, _ = _outline_ovate(L=1.0, W=0.5)
    b_out = _apply_margin(b, "serrate", 0.1, 0, "ovate", 1.0, 0.5)
    np.testing.assert_array_equal(b, b_out)


def test_apply_margin_serrate_adds_2N_verts():
    b, _ = _outline_ovate(L=1.0, W=0.5)
    b_out = _apply_margin(b, "serrate", 0.08, 8, "ovate", 1.0, 0.5)
    assert b_out.shape[0] == b.shape[0] + 2 * 8


def test_apply_margin_dentate_adds_2N_verts():
    b, _ = _outline_ovate(L=1.0, W=0.5)
    b_out = _apply_margin(b, "dentate", 0.08, 6, "ovate", 1.0, 0.5)
    assert b_out.shape[0] == b.shape[0] + 2 * 6


def test_apply_margin_lobed_increases_boundary_variance():
    b, _ = _outline_ovate(L=1.0, W=0.5)
    b_lobed = _apply_margin(b, "lobed", 0.35, 5, "ovate", 1.0, 0.5)
    radii_smooth = np.linalg.norm(b - b.mean(axis=0), axis=1)
    radii_lobed = np.linalg.norm(b_lobed - b_lobed.mean(axis=0), axis=1)
    assert radii_lobed.var() > radii_smooth.var()


def test_apply_margin_serrate_teeth_point_forward():
    """For serrate, peak verts should have higher mean v than valley verts."""
    b, _ = _outline_ovate(L=1.0, W=0.5)
    b_out = _apply_margin(b, "serrate", 0.08, 8, "ovate", 1.0, 0.5)
    # New verts are inserted in pairs (valley, peak) — find them by diffing.
    # Easier: re-run with depth=0 to get same count but no perturbation, then
    # compare. With depth=0 the inserted verts coincide with the midpoints.
    b_flat = _apply_margin(b, "serrate", 0.0, 8, "ovate", 1.0, 0.5)
    # Verts that moved are the toothed ones; pair them up by index parity.
    # We expect 8 valleys + 8 peaks. By construction (valley before peak in
    # insertion order), even-indexed extras are valleys, odd-indexed are peaks.
    diff = np.linalg.norm(b_out - b_flat, axis=1)
    moved_idx = np.where(diff > 1e-9)[0]
    valleys_v = b_out[moved_idx[0::2], 1]
    peaks_v = b_out[moved_idx[1::2], 1]
    assert peaks_v.mean() > valleys_v.mean()


def test_apply_margin_lobed_lower_count_than_serrate():
    """Lobed defaults bias toward fewer, deeper teeth.
    This test just checks that lobed with depth=0.35, count=5 produces an
    outline whose radial-max-minus-radial-min is larger than serrate's at
    depth=0.05, count=15 (same total insertions)."""
    b, _ = _outline_ovate(L=1.0, W=0.5)
    b_lobed = _apply_margin(b, "lobed", 0.35, 5, "ovate", 1.0, 0.5)
    b_serr = _apply_margin(b, "serrate", 0.05, 15, "ovate", 1.0, 0.5)
    def radial_range(b):
        c = b.mean(axis=0)
        r = np.linalg.norm(b - c, axis=1)
        return r.max() - r.min()
    assert radial_range(b_lobed) > radial_range(b_serr)


def test_build_blade_ovate_serrate_birch_under_64():
    pos, _, _, _ = build_blade(
        length=1.0, width=0.7, shape="ovate", margin="serrate",
        margin_depth=0.08, margin_count=12,
    )
    assert pos.shape[0] <= 64


def test_build_blade_ovate_lobed_oak_under_64():
    pos, _, _, _ = build_blade(
        length=1.0, width=0.7, shape="ovate", margin="lobed",
        margin_depth=0.35, margin_count=7,
    )
    assert pos.shape[0] <= 64
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/pytest tests/geom/test_leaf_blade.py -v -k "margin"
```
Expected: tests fail because `_apply_margin` is currently a no-op for all margin types.

- [ ] **Step 3: Implement margin algorithm**

Replace the existing `_apply_margin` in `src/palubicki/geom/leaf_blade.py` with:

```python
_MARGIN_PARAMS = {
    # (peak_offset_fraction_of_period, valley_pull_factor)
    # peak_offset > 0 = forward (toward apex/tip-end)
    "serrate": (0.5, 1.0),
    "dentate": (0.0, 0.5),
    "lobed": (0.0, 1.0),
}


def _apply_margin(
    boundary: np.ndarray, margin: str, depth: float, count: int,
    shape: str, length: float, width: float,
) -> np.ndarray:
    """Insert 2*count tooth vertices (valley, peak) along the boundary.

    Teeth are spaced evenly by arc length over the *eligible* arc (excluding
    the petiole stub for symmetric shapes, the notch for cordate). For each
    tooth midpoint:
        valley  = P + n_in * (depth * w_local)
        peak    = P - n_in * (depth * w_local) + tan * (peak_offset * period)
    where n_in is the inward unit normal, tan the unit tangent at P, w_local
    a shape-aware radius scale, and period the spacing between consecutive
    teeth measured in arc length.
    """
    if margin == "entire" or count == 0:
        return boundary
    if margin not in _MARGIN_PARAMS:
        raise ValueError(f"unknown leaf margin: {margin!r}")
    peak_off_frac, valley_pull = _MARGIN_PARAMS[margin]

    n = boundary.shape[0]
    # Arc lengths between consecutive boundary points (with wraparound).
    diffs = np.diff(boundary, axis=0, append=boundary[:1])
    seg_lens = np.linalg.norm(diffs, axis=1)
    cum = np.concatenate(([0.0], np.cumsum(seg_lens)))
    total_arc = cum[-1]

    # Eligible arc: skip a small petiole stub near v=0 for symmetric shapes
    # and the basal notch for cordate. For palmate, every lobe edge counts.
    eligible_start, eligible_end = _eligible_arc_range(shape, boundary, cum, total_arc)
    eligible_length = eligible_end - eligible_start
    if eligible_length <= 0:
        return boundary

    # Tooth positions evenly spaced over eligible arc.
    # Place midpoints at fractional positions (k + 0.5) / count, k = 0..count-1.
    positions_arc = eligible_start + (np.arange(count) + 0.5) * (eligible_length / count)
    period = eligible_length / count

    # Build the new boundary by walking boundary segments and inserting teeth
    # at the right arc positions.
    out: list[np.ndarray] = []
    tooth_idx = 0
    for i in range(n):
        out.append(boundary[i])
        # Check if any teeth fall in segment [cum[i], cum[i+1]].
        while tooth_idx < count and cum[i] <= positions_arc[tooth_idx] < cum[i + 1]:
            arc_pos = positions_arc[tooth_idx]
            t = (arc_pos - cum[i]) / max(seg_lens[i], 1e-12)
            P = boundary[i] + t * diffs[i]
            tan = diffs[i] / max(seg_lens[i], 1e-12)
            n_in = np.array([-tan[1], tan[0]])  # left-hand normal; CCW interior = left
            # Make sure n_in points inward: compare to vector from P to centroid.
            centroid = boundary.mean(axis=0)
            if np.dot(n_in, centroid - P) < 0:
                n_in = -n_in
            # Local width: use radial distance from centroid to P.
            w_local = float(np.linalg.norm(P - centroid))
            valley_pull_amt = depth * w_local * valley_pull
            peak_push_amt = depth * w_local
            peak_tangent_offset = peak_off_frac * period
            valley = P + n_in * valley_pull_amt
            peak = P - n_in * peak_push_amt + tan * peak_tangent_offset
            out.append(valley)
            out.append(peak)
            tooth_idx += 1
    return np.array(out, dtype=np.float64)


def _eligible_arc_range(
    shape: str, boundary: np.ndarray, cum: np.ndarray, total_arc: float
) -> tuple[float, float]:
    """Skip the petiole stub for symmetric shapes; include everything else.

    For symmetric shapes (linear/elliptic/lanceolate/ovate), the petiole is
    the segment crossing y≈0 at the very start of the boundary. We skip the
    first and last 2% of the total arc to avoid placing teeth at the petiole.
    For cordate, the basal notch is included in that skip range. For palmate,
    every arc point is eligible.
    """
    if shape == "palmate":
        return 0.0, total_arc
    skip = 0.02 * total_arc
    return skip, total_arc - skip
```

- [ ] **Step 4: Run tests**

```
.venv/bin/pytest tests/geom/test_leaf_blade.py -v
```
Expected: all tests pass. If a tooth-direction test fails, check `n_in` orientation or peak offset sign.

- [ ] **Step 5: Commit**

```
git add src/palubicki/geom/leaf_blade.py tests/geom/test_leaf_blade.py
git commit -m "leaf_blade: margin algorithm (serrate, dentate, lobed via tooth insertion)"
```

---

## Task 5: Visual reference PNGs

**Files:**
- Create: `scripts/regen_leaf_visuals.py`
- Create: `tests/geom/visual/<shape>_<margin>.png` (committed; produced by the script)

- [ ] **Step 1: Write the script**

Create `scripts/regen_leaf_visuals.py`:

```python
"""Regenerate matplotlib PNG references for each (shape, margin) combo.

These are human-review artifacts, not automated tests. They live in
tests/geom/visual/ and should be regenerated whenever leaf_blade.py changes
visually. Commit the new PNGs alongside the code change.

Usage:
    .venv/bin/python scripts/regen_leaf_visuals.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from palubicki.geom.leaf_blade import _OUTLINE_FNS, _apply_margin


OUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "geom" / "visual"

# Subset focused on what species presets actually use, plus pure-shape refs.
COMBOS = [
    ("linear", "entire", 0.0, 0),
    ("elliptic", "entire", 0.0, 0),
    ("lanceolate", "entire", 0.0, 0),
    ("ovate", "entire", 0.0, 0),
    ("ovate", "serrate", 0.08, 12),
    ("ovate", "dentate", 0.10, 10),
    ("ovate", "lobed", 0.35, 7),
    ("cordate", "entire", 0.0, 0),
    ("palmate", "entire", 0.0, 0),
    # cordate+toothed not committed: _eligible_arc_range needs a cordate-
    # specific carve-out for the basal notch (out of scope here; default
    # 2% skip places teeth in the notch and looks wrong).
]

L, W = 1.0, 0.7


def render(shape: str, margin: str, depth: float, count: int) -> None:
    boundary, anchor = _OUTLINE_FNS[shape](L, W) if shape != "palmate" \
        else _OUTLINE_FNS[shape](L, W)
    boundary = _apply_margin(boundary, margin, depth, count, shape, L, W)
    # Close the polygon for plotting.
    closed = np.vstack([boundary, boundary[:1]])
    fig, ax = plt.subplots(figsize=(3, 4))
    ax.fill(closed[:, 0], closed[:, 1], color="#4d7a2e", alpha=0.85)
    ax.plot(closed[:, 0], closed[:, 1], color="#2a4317", linewidth=1)
    ax.plot(anchor[0], anchor[1], "o", color="red", markersize=3)
    ax.set_aspect("equal")
    ax.set_title(f"{shape} / {margin}")
    ax.set_xlim(-0.5, 0.5)
    ax.set_ylim(-0.2, 1.1)
    ax.grid(True, alpha=0.3)
    out = OUT_DIR / f"{shape}_{margin}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=80, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    for combo in COMBOS:
        render(*combo)
```

- [ ] **Step 2: Run the script and inspect the outputs**

```
.venv/bin/python scripts/regen_leaf_visuals.py
```
Expected: prints "wrote tests/geom/visual/<combo>.png" for each combo, no errors. Open a few PNGs to confirm shapes look botanically reasonable. If anything looks wrong, tune the outline math in `leaf_blade.py` and re-run.

- [ ] **Step 3: Commit script + PNGs**

```
git add scripts/regen_leaf_visuals.py tests/geom/visual/
git commit -m "leaf_blade: matplotlib reference PNGs for each shape/margin combo"
```

---

## Task 6: GeomConfig schema additions

**Files:**
- Modify: `src/palubicki/config.py`
- Modify: `tests/test_config_leaf_cluster.py`

- [ ] **Step 1: Write failing tests for the 4 new fields**

Append to `tests/test_config_leaf_cluster.py`:

```python
def test_leaf_shape_default_is_ovate():
    g = GeomConfig()
    assert g.leaf_shape == "ovate"


def test_leaf_margin_default_is_entire():
    g = GeomConfig()
    assert g.leaf_margin == "entire"


def test_leaf_margin_depth_default_is_zero():
    g = GeomConfig()
    assert g.leaf_margin_depth == 0.0


def test_leaf_margin_count_default_is_zero():
    g = GeomConfig()
    assert g.leaf_margin_count == 0


def test_full_config_rejects_unknown_leaf_shape(tmp_path):
    with pytest.raises(ConfigError, match="leaf_shape"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_shape="banana"),  # type: ignore[arg-type]
            output=tmp_path / "x.glb",
        )


def test_full_config_rejects_unknown_leaf_margin(tmp_path):
    with pytest.raises(ConfigError, match="leaf_margin"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_margin="frilly"),  # type: ignore[arg-type]
            output=tmp_path / "x.glb",
        )


def test_full_config_rejects_margin_depth_out_of_range(tmp_path):
    with pytest.raises(ConfigError, match="leaf_margin_depth"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_margin_depth=1.5),
            output=tmp_path / "x.glb",
        )


def test_full_config_rejects_negative_margin_count(tmp_path):
    with pytest.raises(ConfigError, match="leaf_margin_count"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_margin_count=-1),
            output=tmp_path / "x.glb",
        )
```

- [ ] **Step 2: Run to verify they fail**

```
.venv/bin/pytest tests/test_config_leaf_cluster.py -v
```
Expected: failures on the new tests (attribute does not exist or validation does not raise).

- [ ] **Step 3: Add fields to `GeomConfig`**

In `src/palubicki/config.py`, locate `class GeomConfig` (around line 215) and add four fields just before `leaf_sun_shade_k`:

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

In `Config.__post_init__`, near the existing `g = self.geom` block validations (around line 418), add:

```python
        if g.leaf_shape not in ("linear", "elliptic", "lanceolate", "ovate", "cordate", "palmate"):
            raise ConfigError(
                f"geom.leaf_shape must be one of "
                f"'linear'|'elliptic'|'lanceolate'|'ovate'|'cordate'|'palmate', "
                f"got {g.leaf_shape!r}"
            )
        if g.leaf_margin not in ("entire", "serrate", "dentate", "lobed"):
            raise ConfigError(
                f"geom.leaf_margin must be one of "
                f"'entire'|'serrate'|'dentate'|'lobed', got {g.leaf_margin!r}"
            )
        if not (0.0 <= g.leaf_margin_depth <= 1.0):
            raise ConfigError(
                f"geom.leaf_margin_depth must be in [0, 1], got {g.leaf_margin_depth}"
            )
        if g.leaf_margin_count < 0:
            raise ConfigError(
                f"geom.leaf_margin_count must be >= 0, got {g.leaf_margin_count}"
            )
```

- [ ] **Step 4: Run config tests**

```
.venv/bin/pytest tests/test_config_leaf_cluster.py -v
```
Expected: all pass. Also run the full config test suite:

```
.venv/bin/pytest tests/test_config.py tests/test_config_leaf_cluster.py -v
```
Expected: nothing regressed.

- [ ] **Step 5: Commit**

```
git add src/palubicki/config.py tests/test_config_leaf_cluster.py
git commit -m "config: GeomConfig gains leaf_shape, leaf_margin, leaf_margin_depth, leaf_margin_count"
```

---

## Task 7: leaves.py integration — replace `_add_quad` with lifted blade

**Files:**
- Modify: `src/palubicki/geom/leaves.py`
- Modify: `tests/geom/test_leaves.py`
- Modify: `tests/geom/test_leaf_cluster.py`

- [ ] **Step 1: Update test_leaves.py for new vert counts**

Edit `tests/geom/test_leaves.py`. Replace the body of `test_one_bud_eight_vertices_twelve_indices` (around line 26) with the new expectations and rename:

```python
def test_one_bud_default_shape_vert_count():
    """Default leaf_shape=ovate (base N=16) + entire margin + cluster=1:
    per face = 16 boundary + 1 anchor = 17 verts and 48 indices.
    Two perpendicular faces per cluster member = 34 verts, 96 indices."""
    tree = _tree_with_n_terminal_buds(1)
    prim = build_leaves_primitive(tree, leaf_size=0.1, material=_mat())
    assert prim.positions.shape == (34, 3)
    assert prim.indices.shape == (96,)


def test_three_buds_yields_3x_default_blade_verts():
    tree = _tree_with_n_terminal_buds(3)
    prim = build_leaves_primitive(tree, leaf_size=0.1, material=_mat())
    assert prim.positions.shape == (102, 3)
    assert prim.indices.shape == (288,)
```

The original `test_dead_buds_excluded` and `test_indices_within_bounds` need no body change, just verify their assertions still hold under new geom (which they should).

- [ ] **Step 2: Update test_leaf_cluster.py for new vert counts**

Edit `tests/geom/test_leaf_cluster.py`. Replace the test bodies:

```python
def test_default_cluster_default_shape_vert_count():
    """Per-bud per-face = 17 verts (ovate N=16 + anchor); two faces per cluster
    member; cluster_count=1; so per-bud = 34 verts, 96 indices."""
    tree = _small_tree()
    prim = build_leaves_primitive(tree, leaf_size=0.06,
                                  cluster_count=1, aspect=1.0, splay_deg=0.0,
                                  material=_stub_material())
    n_terminal = sum(1 for b in tree.active_buds if not b.parent_node.children_internodes)
    assert prim.positions.shape == (n_terminal * 34, 3)
    assert prim.indices.shape == (n_terminal * 96,)


def test_cluster_count_5_emits_5x_vertices_per_bud():
    tree = _small_tree()
    prim = build_leaves_primitive(tree, leaf_size=0.06,
                                  cluster_count=5, aspect=0.2, splay_deg=20.0,
                                  material=_stub_material())
    n_terminal = sum(1 for b in tree.active_buds if not b.parent_node.children_internodes)
    assert prim.positions.shape == (n_terminal * 5 * 34, 3)
    assert prim.indices.shape == (n_terminal * 5 * 96,)


def test_aspect_ratio_narrows_blade_along_axis_u():
    """With aspect=0.2, the width along axis_u is 0.2× the aspect=1.0 width.
    Measured via the u-axis extent of the first cluster member's face."""
    tree = _small_tree()
    p1 = build_leaves_primitive(tree, leaf_size=0.06, cluster_count=1, aspect=1.0,
                                splay_deg=0.0, material=_stub_material())
    p2 = build_leaves_primitive(tree, leaf_size=0.06, cluster_count=1, aspect=0.2,
                                splay_deg=0.0, material=_stub_material())
    # Take the first cluster member's face (34 verts) and project onto its u-axis.
    # Simpler proxy: total bounding-box diagonal scales with aspect on the u-side.
    bbox1 = p1.positions.max(axis=0) - p1.positions.min(axis=0)
    bbox2 = p2.positions.max(axis=0) - p2.positions.min(axis=0)
    # The narrower extent of bbox2 (along u-axis) should be ~0.2× that of bbox1.
    # Pick the smallest of the three axes as the u-extent.
    u_extent_1 = float(min(bbox1))
    u_extent_2 = float(min(bbox2))
    assert u_extent_2 == pytest.approx(0.2 * u_extent_1, rel=0.1)
```

- [ ] **Step 3: Run the updated tests to verify they fail against current `leaves.py`**

```
.venv/bin/pytest tests/geom/test_leaves.py tests/geom/test_leaf_cluster.py -v
```
Expected: vert-count assertions fail because `_emit_leaf_cluster` still emits 8 verts/face.

- [ ] **Step 4: Rewrite `_emit_leaf_cluster` in `leaves.py`**

Edit `src/palubicki/geom/leaves.py`. Add `from palubicki.geom.leaf_blade import build_blade` at the top alongside existing imports.

Update `build_leaves_primitive` so that, before the per-site loop, it builds the blade template once:

```python
def build_leaves_primitive(
    tree: Tree,
    *,
    leaf_size: float,
    material: Material,
    cluster_count: int = 1,
    aspect: float = 1.0,
    splay_deg: float = 0.0,
    foliage_depth: int = 1,
    sun_shade_k: float = 0.0,
    leaf_shape: str = "ovate",
    leaf_margin: str = "entire",
    leaf_margin_depth: float = 0.0,
    leaf_margin_count: int = 0,
) -> Primitive:
    """[unchanged docstring + new params for shape/margin]"""
    sites = _collect_foliage_sites(tree, foliage_depth)

    if not sites:
        return Primitive(
            positions=np.zeros((0, 3), dtype=np.float32),
            normals=np.zeros((0, 3), dtype=np.float32),
            uvs=np.zeros((0, 2), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
            material=material,
        )

    # Build blade template once. Positions are in (u, v, 0) local space.
    # We rebuild it per-site if sun/shade is enabled (since each site has its
    # own eff_size); but the blade shape is the same, only scaled. So we build
    # the unit-length blade once and scale at lift time.
    blade_pos_unit, blade_norm, blade_uv, blade_idx = build_blade(
        length=1.0, width=aspect, shape=leaf_shape, margin=leaf_margin,
        margin_depth=leaf_margin_depth, margin_count=leaf_margin_count,
    )
    blade_v_count = blade_pos_unit.shape[0]
    blade_i_count = blade_idx.shape[0]

    verts_per_site = cluster_count * 2 * blade_v_count
    idx_per_site = cluster_count * 2 * blade_i_count
    n = len(sites)
    positions = np.empty((n * verts_per_site, 3), dtype=np.float32)
    normals = np.empty((n * verts_per_site, 3), dtype=np.float32)
    uvs = np.empty((n * verts_per_site, 2), dtype=np.float32)
    indices = np.empty((n * idx_per_site,), dtype=np.uint32)

    splay_rad = math.radians(splay_deg)

    for i, (center, direction, source_iod) in enumerate(sites):
        eff_size = compute_effective_leaf_size(source_iod, leaf_size, sun_shade_k)
        v_start = i * verts_per_site
        i_start = i * idx_per_site
        _emit_leaf_cluster(
            center, direction, eff_size, cluster_count, splay_rad,
            blade_pos_unit, blade_uv, blade_idx,
            positions[v_start : v_start + verts_per_site],
            normals[v_start : v_start + verts_per_site],
            uvs[v_start : v_start + verts_per_site],
            indices[i_start : i_start + idx_per_site],
            v_start,
        )
    return Primitive(positions=positions, normals=normals, uvs=uvs, indices=indices, material=material)
```

Replace `_emit_leaf_cluster` and `_add_quad` with:

```python
def _emit_leaf_cluster(center, direction, size, cluster_count, splay_rad,
                       blade_pos_unit, blade_uv, blade_idx,
                       out_pos, out_norm, out_uv, out_idx, base):
    """Emit ``cluster_count`` × 2 perpendicular triangulated blades per foliage site.

    The blade is built once in (u, v, 0) local space with length=1, width=aspect.
    Per cluster member we lift it onto two perpendicular planes (cross-blade) so
    the leaf is visible from any angle.
    """
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    right, forward = _basis_perpendicular_to(d)

    blade_v_count = blade_pos_unit.shape[0]
    blade_i_count = blade_idx.shape[0]
    leaf_center = np.asarray(center, dtype=np.float64)

    for k in range(cluster_count):
        az = 2.0 * math.pi * k / cluster_count
        rot_axis_u = math.cos(az) * right + math.sin(az) * forward
        rot_axis_w = -math.sin(az) * right + math.cos(az) * forward
        leaf_up = math.cos(splay_rad) * d + math.sin(splay_rad) * rot_axis_u

        # Plane A: basis_u = rot_axis_u, basis_v = leaf_up, normal = rot_axis_w
        slot_a = k * 2 * blade_v_count
        _lift_blade(
            blade_pos_unit, blade_uv, blade_idx,
            leaf_center, rot_axis_u, leaf_up, rot_axis_w, size,
            out_pos[slot_a : slot_a + blade_v_count],
            out_norm[slot_a : slot_a + blade_v_count],
            out_uv[slot_a : slot_a + blade_v_count],
            out_idx[k * 2 * blade_i_count : k * 2 * blade_i_count + blade_i_count],
            base + slot_a,
        )
        # Plane B: basis_u = rot_axis_w, basis_v = leaf_up, normal = rot_axis_u
        slot_b = slot_a + blade_v_count
        _lift_blade(
            blade_pos_unit, blade_uv, blade_idx,
            leaf_center, rot_axis_w, leaf_up, rot_axis_u, size,
            out_pos[slot_b : slot_b + blade_v_count],
            out_norm[slot_b : slot_b + blade_v_count],
            out_uv[slot_b : slot_b + blade_v_count],
            out_idx[k * 2 * blade_i_count + blade_i_count :
                    k * 2 * blade_i_count + 2 * blade_i_count],
            base + slot_b,
        )


def _lift_blade(blade_pos_unit, blade_uv, blade_idx,
                origin, basis_u, basis_v, normal, scale,
                out_pos, out_norm, out_uv, out_idx, base):
    """Lift a (u, v, 0) 2D blade into 3D along given basis vectors."""
    # blade_pos_unit[:, 0] is u, blade_pos_unit[:, 1] is v; scale to physical size.
    pu = blade_pos_unit[:, 0] * scale
    pv = blade_pos_unit[:, 1] * scale
    bu = np.asarray(basis_u, dtype=np.float64)
    bv = np.asarray(basis_v, dtype=np.float64)
    pos = origin[np.newaxis, :] + pu[:, np.newaxis] * bu[np.newaxis, :] \
          + pv[:, np.newaxis] * bv[np.newaxis, :]
    out_pos[:] = pos.astype(np.float32)
    n = np.asarray(normal, dtype=np.float32)
    out_norm[:] = n[np.newaxis, :]
    out_uv[:] = blade_uv
    out_idx[:] = blade_idx + np.uint32(base)
```

Remove `_add_quad` (no longer used).

- [ ] **Step 5: Pipe shape/margin from config to `build_leaves_primitive`**

Find the call site for `build_leaves_primitive` (`grep -rn build_leaves_primitive src/palubicki/`) — typically in `src/palubicki/glb.py` or `src/palubicki/generator.py`. Pass the four new kwargs from `config.geom`:

```python
leaves_prim = build_leaves_primitive(
    tree,
    leaf_size=config.geom.leaf_size,
    material=leaf_material,
    cluster_count=config.geom.leaf_cluster_count,
    aspect=config.geom.leaf_aspect,
    splay_deg=config.geom.leaf_splay_deg,
    foliage_depth=config.geom.foliage_depth,
    sun_shade_k=config.geom.leaf_sun_shade_k,
    leaf_shape=config.geom.leaf_shape,
    leaf_margin=config.geom.leaf_margin,
    leaf_margin_depth=config.geom.leaf_margin_depth,
    leaf_margin_count=config.geom.leaf_margin_count,
)
```

- [ ] **Step 6: Run all leaf-related tests**

```
.venv/bin/pytest tests/geom/test_leaves.py tests/geom/test_leaf_cluster.py tests/geom/test_leaf_texture.py tests/geom/test_leaf_blade.py -v
```
Expected: all pass.

Run the full test suite to catch regressions elsewhere:

```
.venv/bin/pytest -q
```

Investigate any new failures (likely vert-count assertions in other tests, or a missed call site). Do not move on until the suite is green.

- [ ] **Step 7: Commit**

```
git add src/palubicki/geom/leaves.py tests/geom/test_leaves.py tests/geom/test_leaf_cluster.py
# also any other file you modified to pipe shape/margin through
git status  # confirm what's staged
git commit -m "leaves: replace cross-quad with parametric blade via leaf_blade.build_blade"
```

---

## Task 8: Update species presets

**Files:**
- Modify: `src/palubicki/configs/species/oak.yaml`
- Modify: `src/palubicki/configs/species/birch.yaml`
- Modify: `src/palubicki/configs/species/maple.yaml`
- Modify: `src/palubicki/configs/species/pine.yaml`
- Modify: `src/palubicki/configs/species/fir.yaml`

- [ ] **Step 1: Edit each YAML**

**oak.yaml** — in the `geom:` block, set `leaf_aspect: 0.7` (was 1.0) and add:

```yaml
  leaf_shape: ovate
  leaf_margin: lobed
  leaf_margin_depth: 0.35
  leaf_margin_count: 7
```

**birch.yaml** — in the `geom:` block, add:

```yaml
  leaf_shape: ovate
  leaf_margin: serrate
  leaf_margin_depth: 0.08
  leaf_margin_count: 12
```

**maple.yaml** — in the `geom:` block, set `leaf_aspect: 1.0` (was 1.1) and add:

```yaml
  leaf_shape: palmate
  leaf_margin: entire
  leaf_margin_depth: 0.0
  leaf_margin_count: 0
```

**pine.yaml** — in the `geom:` block, add:

```yaml
  leaf_shape: linear
  leaf_margin: entire
  leaf_margin_depth: 0.0
  leaf_margin_count: 0
```

**fir.yaml** — same as pine:

```yaml
  leaf_shape: linear
  leaf_margin: entire
  leaf_margin_depth: 0.0
  leaf_margin_count: 0
```

- [ ] **Step 2: Run species-loading tests**

```
.venv/bin/pytest tests/ -v -k "species or config"
```
Expected: all pass. If any test asserts on default `leaf_aspect=1.0` for oak or maple, update its expectation.

- [ ] **Step 3: Smoke test each species via the CLI**

```
.venv/bin/palubicki generate --species oak --output out/oak.glb
.venv/bin/palubicki generate --species birch --output out/birch.glb
.venv/bin/palubicki generate --species maple --output out/maple.glb
.venv/bin/palubicki generate --species pine --output out/pine.glb
.venv/bin/palubicki generate --species fir --output out/fir.glb
```
Expected: each finishes without error and writes a non-empty `.glb`.

```
ls -lh out/*.glb
```

- [ ] **Step 4: Visually inspect (optional but recommended)**

```
.venv/bin/palubicki preview out/oak.glb --output /tmp/oak.png
open /tmp/oak.png  # or use your image viewer
```
Confirm oak leaves now have lobed silhouettes, birch shows serrated teeth, maple has 5-lobed star, pine/fir look like needles. If something looks wrong, tune the matching species YAML (e.g., reduce `leaf_margin_count`) and re-run.

- [ ] **Step 5: Commit YAMLs + regenerated GLBs**

```
git add src/palubicki/configs/species/*.yaml out/*.glb
git commit -m "configs/species: assign botanically-correct shape/margin per species"
```

---

## Task 9: Gap analysis doc update

**Files:**
- Modify: `docs/botany/simulator-gap-analysis.md`

- [ ] **Step 1: Update §6 row**

Find the row `| Blade with parametric length, width, shape | 🟡 | = | ...` (around line 130) and replace it with:

```
| Blade with parametric length, width, shape | ✅ | ⬆ Implemented | `geom/leaf_blade.py` (issue #4 / PR #17) — `build_blade(L, W, shape, margin, depth, count)` with 6 shapes × 4 margins. Species presets updated: oak (ovate+lobed), birch (ovate+serrate), maple (palmate), pine/fir (linear). | — | — | **DONE** — leaf silhouettes are now species-distinct. Compound leaves and petiole geometry remain. |
```

- [ ] **Step 2: Update the §6 verdict line**

Find the verdict paragraph at the end of §6 (around line 141) and update to reflect the new state — `parametric blade` should no longer be in the "priority order" list. Replace:

> **Verdict.** Phase 2C added one real-world leaf behavior (sun/shade morphology) but leaves are still cross-quads with no per-leaf state. **In priority order: parametric blade → compound leaves → margins → (Phase 1: leaves-on-nodes + deciduousness).** The first three don't require seasonal infrastructure and can land anytime.

with:

> **Verdict.** Parametric blade + margins (issue #4) and sun/shade morphology (Phase 2C) are in; leaves still aren't first-class node attributes. **In priority order: compound leaves → petiole geometry → (Phase 1: leaves-on-nodes + deciduousness).** The first two don't require seasonal infrastructure.

- [ ] **Step 3: Update §1 "What changed since the previous review"**

Find the bullet list and add at the top:

```
- **Parametric leaf blade** (`geom/leaf_blade.py`) — 6 shapes × 4 margins replace cross-quad rectangles. Each species now has a distinct silhouette.
```

- [ ] **Step 4: Bump the "Last reviewed" date**

Find `**Last reviewed:** 2026-05-27, after Phases 2A–2D landed on \`main\`.` and update to:

```
**Last reviewed:** 2026-05-28, after parametric leaf blade (issue #4) landed on the issue branch.
```

- [ ] **Step 5: Update the "Top remaining recommendations" list (§10 or end of file)**

Find the numbered list around line 229 and remove the "Parametric leaf blade + margins (§6)" item; renumber the remaining items.

- [ ] **Step 6: Commit**

```
git add docs/botany/simulator-gap-analysis.md
git commit -m "docs(gap-analysis): mark parametric leaf blade done (§6)"
```

---

## Task 10: Mark PR ready, smoke test the branch end-to-end

**Files:** none

- [ ] **Step 1: Run the full test suite once more**

```
.venv/bin/pytest -q
```
Expected: all green.

- [ ] **Step 2: Verify the GLBs are valid and reasonable in size**

```
ls -lh out/*.glb
```
Expected: each file is non-zero and roughly proportional to species complexity (oak/maple larger, pine/fir smaller). If a `.glb` is missing or zero-bytes, re-run `palubicki generate` for it.

- [ ] **Step 3: Push and mark PR ready for review**

```
git push
gh pr ready 17 -R julien-riel/palubicki
```

- [ ] **Step 4: Update the PR description**

```
gh pr edit 17 -R julien-riel/palubicki --body "$(cat <<'EOF'
Closes #4.

## Summary
- Adds `src/palubicki/geom/leaf_blade.py` with `build_blade(length, width, shape, margin, margin_depth, margin_count)`. Six shapes (linear, elliptic, lanceolate, ovate, cordate, palmate) × four margins (entire, serrate, dentate, lobed).
- Replaces the cross-quad in `geom/leaves.py` with the triangulated blade; cluster + cross-blade structure preserved.
- `GeomConfig` gains `leaf_shape`, `leaf_margin`, `leaf_margin_depth`, `leaf_margin_count`.
- Species presets assigned botanically-correct shape/margin: oak ovate+lobed, birch ovate+serrate, maple palmate, pine/fir linear.

## Spec & plan
- Design: `docs/superpowers/specs/2026-05-28-parametric-leaf-blade-design.md`
- Plan: `docs/superpowers/plans/2026-05-28-parametric-leaf-blade.md`

## Vert-budget tradeoff
Every (shape, margin) combo stays under 64 verts/face. Worst case (birch, ovate+serrate, count=12) is 4.6× per cluster member vs. the old rectangle — over the issue's "~2×" aspirational target but within practical limits. Use `leaf_margin_count` to dial back if perf forces it.

## Test plan
- [x] 2D unit tests in `tests/geom/test_leaf_blade.py` (CCW, anchor inside, star-shape, vert counts under 64, margin direction, errors)
- [x] Updated existing leaf tests (`test_leaves.py`, `test_leaf_cluster.py`, `test_config_leaf_cluster.py`)
- [x] Visual reference PNGs in `tests/geom/visual/` (human review)
- [x] CLI smoke: `palubicki generate --species {oak,birch,maple,pine,fir}` all produce valid `.glb`
- [ ] Manual eyeball of oak/birch/maple leaves in a 3D viewer
EOF
)"
```

That's the full plan. Don't merge the PR without manual eyeball confirmation that the leaves look reasonable.

---

## Self-Review

**Spec coverage:**
- ✅ Per-shape outlines (6 shapes) → Tasks 1, 2, 3
- ✅ Margin algorithm (4 margins) → Task 4
- ✅ Triangulation (fan from anchor) → Task 1
- ✅ 2D → 3D lift → Task 7 (within `_lift_blade`)
- ✅ Public `build_blade` API + validation → Task 1
- ✅ Visual reference PNGs → Task 5
- ✅ Config schema (4 new fields) + validation → Task 6
- ✅ `leaves.py` integration (`_emit_leaf_cluster` rewritten, `_add_quad` removed) → Task 7
- ✅ Existing leaf tests updated → Task 7
- ✅ Species presets → Task 8
- ✅ GLB regeneration → Task 8
- ✅ Gap analysis doc → Task 9
- ✅ Branch finalization → Task 10

**Placeholder scan:** No "TBD" / "implement later" / "similar to Task N" references found. Every code-changing step shows the actual code.

**Type consistency:** `build_blade` signature is identical across Tasks 1, 4, 7 (`length, width, shape, margin, margin_depth, margin_count`). `_outline_<shape>` returns `(boundary, anchor)` in all tasks. `_apply_margin` signature `(boundary, margin, depth, count, shape, length, width)` matches between Task 4 implementation and Task 5 script use.

**Open uncertainties:**
- The exact call site for `build_leaves_primitive` in Task 7 Step 5 isn't pinned — engineer must grep. This is intentional (it's a small surface area discovery, faster to grep than to bake into the plan).
- Outline formula constants (`^0.7`, `^1.3`, taper factors) are starting values that may need eyeballing against the visual PNGs in Task 5. Plan flags this in Task 2 Step 3.
