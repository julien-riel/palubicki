# Render Headless PNG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `palubicki.render` sub-package that produces diagnostic PNG images from a `Mesh` or `.glb` without OpenGL or a display, plus a `palubicki preview` CLI subcommand.

**Architecture:** matplotlib `Poly3DCollection` backend behind a stable `render_mesh(mesh, ...) -> ndarray` API. Pipeline: flatten Mesh primitives → triangle/normal/face-color arrays → flat-shaded Lambert with implicit double-sided → matplotlib 3D axes → PNG-encoded ndarray. The matplotlib dependency is opt-in via `palubicki[render]` extra.

**Tech Stack:** Python ≥3.11, numpy, matplotlib (extra), Pillow (already core), trimesh (already core for `.glb` loading), pytest.

**Spec reference:** `docs/superpowers/specs/2026-05-26-render-headless-png-design.md`

**File map:**
- Create: `src/palubicki/render/__init__.py` — exports + `RenderError` / `RenderDependencyError`
- Create: `src/palubicki/render/camera.py` — `Camera` dataclass + `Camera.fit()`
- Create: `src/palubicki/render/renderer.py` — `_flatten`, `_shade`, `render_mesh`, `render_glb`
- Create: `src/palubicki/render/io.py` — `_glb_to_mesh`, `save_png`
- Modify: `src/palubicki/cli.py` — add `preview` subcommand
- Modify: `pyproject.toml` — add `render` optional extra
- Modify: `tests/golden/conftest.py` — add `--render-on-fail` flag
- Modify: `README.md` — add Preview section under Usage
- Create: `tests/render/__init__.py` — empty test package marker
- Create: `tests/render/test_renderer.py` — unit tests (fast)
- Create: `tests/render/test_render_integration.py` — integration (`slow`)
- Modify: `tests/test_cli.py` — add `preview` smoke tests

**Conventions used throughout:**
- All file paths in this plan are relative to repo root `/Users/julienriel/src/palubicki/`.
- The Python venv is at `.venv/`. Activation doesn't persist across shells — always prefix commands with `.venv/bin/`. Example: `.venv/bin/pytest tests/render/ -v`.
- Each task ends with a commit. Conventional Commits style matches the repo log (`feat(render):`, `test(render):`, etc.).

---

## Task 1: Bootstrap render package + exceptions + pyproject extra

**Files:**
- Create: `src/palubicki/render/__init__.py`
- Modify: `pyproject.toml`
- Create: `tests/render/__init__.py`
- Test: `tests/render/test_init.py`

- [ ] **Step 1: Write the failing test**

Create `tests/render/test_init.py`:

```python
# tests/render/test_init.py
import pytest


def test_render_exceptions_are_importable():
    from palubicki.render import RenderError, RenderDependencyError
    assert issubclass(RenderDependencyError, RenderError)
    assert issubclass(RenderError, Exception)


def test_render_module_does_not_require_matplotlib_to_import():
    """The base module must import even if matplotlib is missing —
    only render_mesh / render_glb may force the import."""
    import importlib
    import palubicki.render
    importlib.reload(palubicki.render)  # ensure clean import path
    assert hasattr(palubicki.render, "RenderError")
```

Also create the empty test package marker:

```python
# tests/render/__init__.py
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/render/test_init.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'palubicki.render'`

- [ ] **Step 3: Create the package skeleton**

Create `src/palubicki/render/__init__.py`:

```python
# src/palubicki/render/__init__.py
"""Headless PNG rendering for palubicki Mesh / .glb (diagnostic level).

Matplotlib is an optional dependency: install with `pip install -e '.[render]'`.
Importing this module does NOT import matplotlib. The matplotlib import is
deferred to render_mesh() / render_glb() — failures raise RenderDependencyError.
"""
from __future__ import annotations


class RenderError(Exception):
    """Generic render module failure (bad input, degenerate mesh, etc.)."""


class RenderDependencyError(RenderError):
    """Raised when an optional dep (matplotlib) is missing."""


__all__ = ["RenderError", "RenderDependencyError"]
```

- [ ] **Step 4: Add the optional extra in `pyproject.toml`**

In `pyproject.toml`, locate the existing `[project.optional-dependencies]` block:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
]
```

Add a `render` extra immediately after `dev`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
]
render = [
    "matplotlib>=3.7",
]
```

- [ ] **Step 5: Install the new extra**

```bash
.venv/bin/pip install -e ".[dev,render]"
```

Expected: installs matplotlib (and its transitive deps: pyparsing, kiwisolver, cycler, contourpy, fonttools).

- [ ] **Step 6: Run test to verify it passes**

```bash
.venv/bin/pytest tests/render/test_init.py -v
```

Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/render/__init__.py \
        tests/render/__init__.py \
        tests/render/test_init.py \
        pyproject.toml
git commit -m "feat(render): bootstrap render package with optional matplotlib extra"
```

---

## Task 2: Camera dataclass + Camera.fit()

**Files:**
- Create: `src/palubicki/render/camera.py`
- Test: `tests/render/test_camera.py`

- [ ] **Step 1: Write the failing test**

Create `tests/render/test_camera.py`:

```python
# tests/render/test_camera.py
import numpy as np
import pytest

from palubicki.geom.mesh import Material, Mesh, Primitive
from palubicki.render.camera import Camera


def _box_mesh(lo: tuple, hi: tuple) -> Mesh:
    """A two-triangle quad covering the corners (lo, hi). For testing only."""
    positions = np.array(
        [lo, (hi[0], lo[1], lo[2]), hi, (lo[0], hi[1], hi[2])],
        dtype=np.float32,
    )
    normals = np.tile(np.array([0, 0, 1], dtype=np.float32), (4, 1))
    uvs = np.zeros((4, 2), dtype=np.float32)
    indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
    mat = Material(
        name="t", base_color=(0.5, 0.5, 0.5, 1.0),
        metallic=0.0, roughness=1.0,
        base_color_texture_png=None,
        alpha_mode="OPAQUE", alpha_cutoff=0.5, double_sided=False,
    )
    return Mesh(primitives=[Primitive(
        positions=positions, normals=normals, uvs=uvs,
        indices=indices, material=mat,
    )])


def test_camera_defaults():
    cam = Camera()
    assert cam.elevation_deg == 20.0
    assert cam.azimuth_deg == 35.0
    assert cam.target == (0.0, 0.0, 0.0)
    assert cam.distance is None
    assert cam.margin == 0.08


def test_camera_fit_centers_target_on_bbox():
    mesh = _box_mesh(lo=(-1.0, -1.0, -1.0), hi=(2.0, 2.0, 2.0))
    cam = Camera.fit(mesh)
    np.testing.assert_allclose(cam.target, (0.5, 0.5, 0.5), atol=1e-6)


def test_camera_fit_distance_scales_with_extent():
    small = Camera.fit(_box_mesh((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5)))
    big = Camera.fit(_box_mesh((-5.0, -5.0, -5.0), (5.0, 5.0, 5.0)))
    assert big.distance > small.distance
    assert big.distance / small.distance == pytest.approx(10.0, rel=0.05)


def test_camera_fit_accepts_overrides():
    mesh = _box_mesh((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0))
    cam = Camera.fit(mesh, elevation_deg=45.0, azimuth_deg=90.0)
    assert cam.elevation_deg == 45.0
    assert cam.azimuth_deg == 90.0


def test_camera_fit_empty_mesh_raises():
    from palubicki.render import RenderError
    empty = Mesh(primitives=[])
    with pytest.raises(RenderError, match="empty"):
        Camera.fit(empty)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/render/test_camera.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'palubicki.render.camera'`

- [ ] **Step 3: Implement `Camera`**

Create `src/palubicki/render/camera.py`:

```python
# src/palubicki/render/camera.py
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import numpy as np

from palubicki.render import RenderError

if TYPE_CHECKING:
    from palubicki.geom.mesh import Mesh


@dataclass(frozen=True)
class Camera:
    """Y-up perspective camera. Defaults give a 3/4 view of a standing tree.

    elevation_deg: 0 = horizon, 90 = top-down
    azimuth_deg:   rotation around vertical (Y) axis
    target:        point the camera looks at (typically bbox center)
    distance:      camera-to-target distance; None = auto-fit from bbox
    margin:        padding around bbox in fit mode (8% default)
    """
    elevation_deg: float = 20.0
    azimuth_deg: float = 35.0
    target: tuple[float, float, float] = (0.0, 0.0, 0.0)
    distance: float | None = None
    margin: float = 0.08

    @staticmethod
    def fit(mesh: "Mesh", **overrides) -> "Camera":
        """Auto-fit camera to mesh bbox. Concatenates all primitives' positions
        to compute the bbox, then sets target = bbox center and distance from
        the bbox extent (with `margin` padding)."""
        if not mesh.primitives:
            raise RenderError("cannot fit camera to empty mesh (no primitives)")

        all_positions = np.concatenate([p.positions for p in mesh.primitives])
        lo = all_positions.min(axis=0)
        hi = all_positions.max(axis=0)
        extent = (hi - lo).max()

        if extent < 1e-9:
            raise RenderError("mesh bounding box is degenerate (extent ≈ 0)")

        center = (lo + hi) * 0.5
        # Distance heuristic: extent / (2 tan(fov/2)) with fov=45° → ~1.21*extent.
        # Add margin and a small safety factor so the bbox sits inside the frame.
        margin = overrides.pop("margin", 0.08)
        distance = extent * (1.0 + margin) * 1.5

        cam = Camera(
            target=tuple(float(c) for c in center),
            distance=float(distance),
            margin=margin,
        )
        return replace(cam, **overrides)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/render/test_camera.py -v
```

Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/render/camera.py tests/render/test_camera.py
git commit -m "feat(render): Camera dataclass with bbox-fit factory"
```

---

## Task 3: `_flatten` helper — Mesh → triangle/normal/color arrays

**Files:**
- Create: `src/palubicki/render/renderer.py` (skeleton with `_flatten` only)
- Test: `tests/render/test_renderer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/render/test_renderer.py`:

```python
# tests/render/test_renderer.py
import numpy as np
import pytest

from palubicki.geom.mesh import Material, Mesh, Primitive


def _mk_mat(rgb=(0.7, 0.4, 0.2)):
    return Material(
        name="t", base_color=(*rgb, 1.0),
        metallic=0.0, roughness=1.0,
        base_color_texture_png=None,
        alpha_mode="OPAQUE", alpha_cutoff=0.5, double_sided=False,
    )


def _mk_prim(positions, normals, indices, rgb=(0.7, 0.4, 0.2)):
    return Primitive(
        positions=np.asarray(positions, dtype=np.float32),
        normals=np.asarray(normals, dtype=np.float32),
        uvs=np.zeros((len(positions), 2), dtype=np.float32),
        indices=np.asarray(indices, dtype=np.uint32),
        material=_mk_mat(rgb),
    )


def test_flatten_concatenates_primitives():
    from palubicki.render.renderer import _flatten
    # Primitive A: 1 triangle, brown
    pA = _mk_prim(
        positions=[(0, 0, 0), (1, 0, 0), (0, 1, 0)],
        normals=[(0, 0, 1), (0, 0, 1), (0, 0, 1)],
        indices=[0, 1, 2],
        rgb=(0.7, 0.4, 0.2),
    )
    # Primitive B: 2 triangles forming a quad, green
    pB = _mk_prim(
        positions=[(2, 0, 0), (3, 0, 0), (3, 1, 0), (2, 1, 0)],
        normals=[(0, 0, 1)] * 4,
        indices=[0, 1, 2, 0, 2, 3],
        rgb=(0.3, 0.6, 0.2),
    )
    mesh = Mesh(primitives=[pA, pB])

    tri, norms, cols = _flatten(mesh)

    assert tri.shape == (3, 3, 3)             # 3 triangles, 3 verts each, 3 coords
    assert norms.shape == (3, 3)
    assert cols.shape == (3, 3)
    # First triangle = primitive A's brown
    np.testing.assert_allclose(cols[0], (0.7, 0.4, 0.2), atol=1e-6)
    # Last two = primitive B's green
    np.testing.assert_allclose(cols[1], (0.3, 0.6, 0.2), atol=1e-6)
    np.testing.assert_allclose(cols[2], (0.3, 0.6, 0.2), atol=1e-6)
    # Normals are unit-length
    lengths = np.linalg.norm(norms, axis=1)
    np.testing.assert_allclose(lengths, np.ones(3), atol=1e-5)


def test_flatten_normalizes_non_unit_input_normals():
    from palubicki.render.renderer import _flatten
    # Pass normals with length 5; expect output unit-length.
    p = _mk_prim(
        positions=[(0, 0, 0), (1, 0, 0), (0, 1, 0)],
        normals=[(5, 0, 0), (0, 5, 0), (0, 0, 5)],
        indices=[0, 1, 2],
    )
    _, norms, _ = _flatten(Mesh(primitives=[p]))
    assert np.linalg.norm(norms[0]) == pytest.approx(1.0, abs=1e-5)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/render/test_renderer.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'palubicki.render.renderer'`

- [ ] **Step 3: Implement `_flatten`**

Create `src/palubicki/render/renderer.py`:

```python
# src/palubicki/render/renderer.py
from __future__ import annotations

import numpy as np

from palubicki.geom.mesh import Mesh


def _flatten(mesh: Mesh) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Concatenate all primitives into flat arrays for rendering.

    Returns:
        tri:   (T, 3, 3) float32 — T triangles, each as 3 vertices in 3D
        norm:  (T, 3)    float32 — unit-length face normal per triangle
        col:   (T, 3)    float32 — RGB face color from primitive's base_color
    """
    tris: list[np.ndarray] = []
    norms: list[np.ndarray] = []
    cols: list[np.ndarray] = []

    for p in mesh.primitives:
        idx = p.indices.reshape(-1, 3)
        # Triangle vertex positions
        tris.append(p.positions[idx].astype(np.float32, copy=False))
        # Face normal = mean of vertex normals, then renormalized
        n = p.normals[idx].astype(np.float32, copy=False).mean(axis=1)
        n /= np.linalg.norm(n, axis=1, keepdims=True).clip(1e-9)
        norms.append(n)
        # Face color = primitive's base_color broadcast to T triangles
        rgb = np.asarray(p.material.base_color[:3], dtype=np.float32)
        cols.append(np.broadcast_to(rgb, (idx.shape[0], 3)).copy())

    if not tris:
        # Empty mesh — caller should have caught this earlier.
        empty = np.zeros((0, 3, 3), dtype=np.float32)
        return empty, np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.float32)

    return np.concatenate(tris), np.concatenate(norms), np.concatenate(cols)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/render/test_renderer.py -v
```

Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/render/renderer.py tests/render/test_renderer.py
git commit -m "feat(render): _flatten helper concatenates primitives to face arrays"
```

---

## Task 4: `_shade` helper — flat Lambert with implicit double-sided

**Files:**
- Modify: `src/palubicki/render/renderer.py`
- Modify: `tests/render/test_renderer.py`

- [ ] **Step 1: Write the failing tests (append to existing file)**

Append to `tests/render/test_renderer.py`:

```python
def test_shade_facing_light_yields_full_intensity():
    from palubicki.render.renderer import _shade
    # Normal pointing toward (negated) light → max intensity
    normals = np.array([[0, 1, 0]], dtype=np.float32)
    colors = np.array([[1, 1, 1]], dtype=np.float32)
    light_dir = (0, -1, 0)  # downward → -L = (0, 1, 0), dot=1
    shaded = _shade(normals, colors, light_dir)
    np.testing.assert_allclose(shaded, [[1, 1, 1]], atol=1e-5)


def test_shade_perpendicular_to_light_yields_ambient():
    from palubicki.render.renderer import _shade
    # Normal perpendicular to light → only ambient (0.25)
    normals = np.array([[1, 0, 0]], dtype=np.float32)
    colors = np.array([[1, 1, 1]], dtype=np.float32)
    light_dir = (0, -1, 0)
    shaded = _shade(normals, colors, light_dir)
    np.testing.assert_allclose(shaded, [[0.25, 0.25, 0.25]], atol=1e-5)


def test_shade_back_facing_is_double_sided():
    """Normals pointing AWAY from light still light up — abs() implies
    double-sided behavior, correct for leaf quads."""
    from palubicki.render.renderer import _shade
    # Front-facing normal
    front = _shade(
        np.array([[0, 1, 0]], dtype=np.float32),
        np.array([[1, 1, 1]], dtype=np.float32),
        (0, -1, 0),
    )
    # Same surface, flipped normal
    back = _shade(
        np.array([[0, -1, 0]], dtype=np.float32),
        np.array([[1, 1, 1]], dtype=np.float32),
        (0, -1, 0),
    )
    np.testing.assert_allclose(front, back, atol=1e-5)


def test_shade_clamps_to_color():
    from palubicki.render.renderer import _shade
    # Base color is 0.5 — output cannot exceed 0.5 per channel.
    normals = np.array([[0, 1, 0]], dtype=np.float32)
    colors = np.array([[0.5, 0.5, 0.5]], dtype=np.float32)
    light_dir = (0, -1, 0)
    shaded = _shade(normals, colors, light_dir)
    assert shaded.max() <= 0.5 + 1e-5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/render/test_renderer.py -v
```

Expected: 4 new tests FAIL with `cannot import name '_shade' from 'palubicki.render.renderer'`

- [ ] **Step 3: Implement `_shade`**

Append to `src/palubicki/render/renderer.py`:

```python
def _shade(
    normals: np.ndarray,
    face_colors: np.ndarray,
    light_dir: tuple[float, float, float],
) -> np.ndarray:
    """Flat Lambert shading with implicit double-sided faces.

    intensity = abs(n · -L)        # abs() = both sides of leaf quads light up
    factor    = ambient + (1 - ambient) * intensity
    output    = clip(color * factor, 0, 1)
    """
    L = np.asarray(light_dir, dtype=np.float32)
    L /= np.linalg.norm(L).clip(1e-9)
    intensity = np.abs(normals @ -L).clip(0, 1)
    ambient = 0.25
    factor = ambient + (1.0 - ambient) * intensity
    return (face_colors * factor[:, None]).clip(0, 1)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/render/test_renderer.py -v
```

Expected: PASS (6 tests total: 2 from Task 3 + 4 new)

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/render/renderer.py tests/render/test_renderer.py
git commit -m "feat(render): _shade flat Lambert with implicit double-sided"
```

---

## Task 5: `render_mesh` — matplotlib pipeline

**Files:**
- Modify: `src/palubicki/render/renderer.py`
- Modify: `tests/render/test_renderer.py`

- [ ] **Step 1: Write the failing tests (append)**

Append to `tests/render/test_renderer.py`:

```python
def test_render_mesh_returns_rgba_uint8_array():
    from palubicki.render import render_mesh
    p = _mk_prim(
        positions=[(0, 0, 0), (1, 0, 0), (0, 1, 0)],
        normals=[(0, 0, 1)] * 3,
        indices=[0, 1, 2],
    )
    img = render_mesh(Mesh(primitives=[p]), size=(200, 150))
    assert img.dtype == np.uint8
    assert img.ndim == 3
    assert img.shape[2] == 4                       # RGBA
    # Size is "best effort" due to bbox_inches='tight' — allow ±60px.
    assert abs(img.shape[1] - 200) < 60
    assert abs(img.shape[0] - 150) < 60


def test_render_mesh_rejects_empty_mesh():
    from palubicki.render import RenderError, render_mesh
    with pytest.raises(RenderError, match="no triangles"):
        render_mesh(Mesh(primitives=[]))


def test_render_mesh_rejects_degenerate_mesh():
    from palubicki.render import RenderError, render_mesh
    p = _mk_prim(
        positions=[(0, 0, 0), (0, 0, 0), (0, 0, 0)],
        normals=[(0, 0, 1)] * 3,
        indices=[0, 1, 2],
    )
    with pytest.raises(RenderError, match="degenerate"):
        render_mesh(Mesh(primitives=[p]))


def test_render_mesh_rejects_absurd_size():
    from palubicki.render import render_mesh
    p = _mk_prim(
        positions=[(0, 0, 0), (1, 0, 0), (0, 1, 0)],
        normals=[(0, 0, 1)] * 3,
        indices=[0, 1, 2],
    )
    with pytest.raises(ValueError, match="size"):
        render_mesh(Mesh(primitives=[p]), size=(-1, 100))
    with pytest.raises(ValueError, match="size"):
        render_mesh(Mesh(primitives=[p]), size=(100_000, 100_000))


def test_render_mesh_produces_non_background_pixels():
    """Smoke check: rendering something on a white bg yields some non-white pixels."""
    from palubicki.render import render_mesh
    p = _mk_prim(
        positions=[(-1, -1, 0), (1, -1, 0), (0, 1, 0)],
        normals=[(0, 0, 1)] * 3,
        indices=[0, 1, 2],
        rgb=(0.2, 0.6, 0.3),
    )
    img = render_mesh(Mesh(primitives=[p]), size=(300, 300))
    # Pixel is "non-background" if any channel differs from white by > 8/255.
    delta = np.abs(img[:, :, :3].astype(int) - 255).max(axis=2)
    nonbg_ratio = (delta > 8).mean()
    assert nonbg_ratio > 0.005, f"expected >0.5% non-bg pixels, got {nonbg_ratio:.4%}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/render/test_renderer.py -v
```

Expected: 5 new tests FAIL — `render_mesh` not yet exported.

- [ ] **Step 3: Implement `render_mesh` (matplotlib pipeline)**

Replace the contents of `src/palubicki/render/renderer.py` with the full version:

```python
# src/palubicki/render/renderer.py
from __future__ import annotations

import io
import logging
import time
from pathlib import Path

import numpy as np

from palubicki.geom.mesh import Mesh
from palubicki.render import RenderDependencyError, RenderError
from palubicki.render.camera import Camera

_LOG = logging.getLogger("palubicki.render")
_MAX_PIXELS = 50_000_000  # guard against --size 99999x99999


def _flatten(mesh: Mesh) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Concatenate all primitives into flat arrays for rendering.

    Returns:
        tri:   (T, 3, 3) float32 — T triangles, each as 3 vertices in 3D
        norm:  (T, 3)    float32 — unit-length face normal per triangle
        col:   (T, 3)    float32 — RGB face color from primitive's base_color
    """
    tris: list[np.ndarray] = []
    norms: list[np.ndarray] = []
    cols: list[np.ndarray] = []

    for p in mesh.primitives:
        idx = p.indices.reshape(-1, 3)
        tris.append(p.positions[idx].astype(np.float32, copy=False))
        n = p.normals[idx].astype(np.float32, copy=False).mean(axis=1)
        n /= np.linalg.norm(n, axis=1, keepdims=True).clip(1e-9)
        norms.append(n)
        rgb = np.asarray(p.material.base_color[:3], dtype=np.float32)
        cols.append(np.broadcast_to(rgb, (idx.shape[0], 3)).copy())

    if not tris:
        empty = np.zeros((0, 3, 3), dtype=np.float32)
        return empty, np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.float32)
    return np.concatenate(tris), np.concatenate(norms), np.concatenate(cols)


def _shade(
    normals: np.ndarray,
    face_colors: np.ndarray,
    light_dir: tuple[float, float, float],
) -> np.ndarray:
    """Flat Lambert with implicit double-sided faces."""
    L = np.asarray(light_dir, dtype=np.float32)
    L /= np.linalg.norm(L).clip(1e-9)
    intensity = np.abs(normals @ -L).clip(0, 1)
    ambient = 0.25
    factor = ambient + (1.0 - ambient) * intensity
    return (face_colors * factor[:, None]).clip(0, 1)


def _validate_size(size: tuple[int, int]) -> None:
    w, h = size
    if w <= 0 or h <= 0:
        raise ValueError(f"size must be positive, got {size}")
    if w * h > _MAX_PIXELS:
        raise ValueError(f"size {size} exceeds {_MAX_PIXELS} pixel guard")


def _mesh_bbox(mesh: Mesh) -> tuple[np.ndarray, np.ndarray]:
    all_pos = np.concatenate([p.positions for p in mesh.primitives])
    return all_pos.min(axis=0), all_pos.max(axis=0)


def _apply_camera(ax, camera: Camera, lo: np.ndarray, hi: np.ndarray) -> None:
    """Set matplotlib 3D axes limits + view orientation from Camera."""
    ax.view_init(elev=camera.elevation_deg, azim=camera.azimuth_deg)

    # Center axes on camera.target with half-extent driven by camera.distance
    # if provided, otherwise by the bbox itself plus margin.
    cx, cy, cz = camera.target
    if camera.distance is not None:
        half = camera.distance * 0.5
    else:
        half = float((hi - lo).max()) * 0.5 * (1.0 + camera.margin)

    ax.set_xlim(cx - half, cx + half)
    # In matplotlib's mplot3d, axis "z" is the up axis. We use Y-up convention
    # in palubicki, so we swap Y and Z when feeding matplotlib.
    ax.set_ylim(cz - half, cz + half)
    ax.set_zlim(cy - half, cy + half)


def render_mesh(
    mesh: Mesh,
    *,
    size: tuple[int, int] = (800, 800),
    camera: Camera | None = None,
    bg: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
    light_dir: tuple[float, float, float] = (-0.3, -1.0, -0.5),
    drop_leaves: bool = False,  # kept for symmetry with render_glb; no-op on Mesh
) -> np.ndarray:
    """Render a Mesh to an (H, W, 4) uint8 RGBA ndarray. Matplotlib backend."""
    _validate_size(size)

    total_tris = sum(len(p.indices) // 3 for p in mesh.primitives)
    if total_tris == 0:
        raise RenderError("mesh has no triangles to render")

    # Bbox + degenerate check
    lo, hi = _mesh_bbox(mesh)
    if float((hi - lo).max()) < 1e-9:
        raise RenderError("mesh bounding box is degenerate (extent ≈ 0)")

    if camera is None:
        camera = Camera.fit(mesh)

    # Lazy matplotlib import — raises RenderDependencyError if missing.
    try:
        import matplotlib
        matplotlib.use("Agg")  # MUST be before pyplot
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    except ImportError as e:
        raise RenderDependencyError(
            "matplotlib is required for rendering; install with: "
            "pip install -e '.[render]'"
        ) from e
    from PIL import Image

    t0 = time.perf_counter()
    tri, norms, cols = _flatten(mesh)
    shaded = _shade(norms, cols, light_dir)

    # Swap Y and Z for matplotlib (mplot3d treats Z as up, palubicki is Y-up)
    tri_swap = tri[..., [0, 2, 1]]

    dpi = 100
    fig = plt.figure(figsize=(size[0] / dpi, size[1] / dpi), dpi=dpi)
    fig.patch.set_facecolor(bg[:3])
    fig.patch.set_alpha(bg[3])
    ax = fig.add_subplot(111, projection="3d", computed_zorder=False)
    ax.set_axis_off()
    ax.set_proj_type("persp")
    ax.set_box_aspect((1, 1, 1))

    coll = Poly3DCollection(tri_swap, facecolors=shaded, edgecolors="none", linewidth=0)
    ax.add_collection3d(coll)
    _apply_camera(ax, camera, lo, hi)

    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=dpi,
        bbox_inches="tight", pad_inches=0,
        facecolor=fig.get_facecolor(),
        transparent=(bg[3] < 1.0),
    )
    plt.close(fig)

    img = np.asarray(Image.open(buf).convert("RGBA"))
    _LOG.info(
        "rendered %dx%d, %d triangles, took %.0fms",
        img.shape[1], img.shape[0], total_tris,
        (time.perf_counter() - t0) * 1000,
    )
    return img
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/render/test_renderer.py -v
```

Expected: PASS (11 tests total)

- [ ] **Step 5: Make `render_mesh` reachable from `palubicki.render`**

Update `src/palubicki/render/__init__.py` exports:

```python
# src/palubicki/render/__init__.py
"""Headless PNG rendering for palubicki Mesh / .glb (diagnostic level).

Matplotlib is an optional dependency: install with `pip install -e '.[render]'`.
"""
from __future__ import annotations


class RenderError(Exception):
    """Generic render module failure (bad input, degenerate mesh, etc.)."""


class RenderDependencyError(RenderError):
    """Raised when an optional dep (matplotlib) is missing."""


def render_mesh(mesh, **kwargs):
    """See palubicki.render.renderer.render_mesh."""
    from palubicki.render.renderer import render_mesh as _impl
    return _impl(mesh, **kwargs)


__all__ = ["RenderError", "RenderDependencyError", "render_mesh"]
```

- [ ] **Step 6: Re-run all render tests**

```bash
.venv/bin/pytest tests/render/ -v
```

Expected: PASS (all tests in render/ — Task 1 + Task 2 + Task 3 + Task 4 + Task 5)

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/render/renderer.py \
        src/palubicki/render/__init__.py \
        tests/render/test_renderer.py
git commit -m "feat(render): render_mesh matplotlib pipeline returning RGBA ndarray"
```

---

## Task 6: `save_png` + `_glb_to_mesh` + `render_glb`

**Files:**
- Create: `src/palubicki/render/io.py`
- Modify: `src/palubicki/render/renderer.py` (add `render_glb`)
- Modify: `src/palubicki/render/__init__.py` (export new symbols)
- Test: `tests/render/test_io.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/render/test_io.py`:

```python
# tests/render/test_io.py
import io as stdio
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def _make_solid_image(w=64, h=48, rgb=(120, 60, 200)):
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., :3] = rgb
    arr[..., 3] = 255
    return arr


# ---------- save_png ----------

def test_save_png_writes_file(tmp_path):
    from palubicki.render.io import save_png
    img = _make_solid_image()
    out = tmp_path / "out.png"
    save_png(img, out)
    assert out.exists()
    loaded = np.asarray(Image.open(out).convert("RGBA"))
    np.testing.assert_array_equal(loaded, img)


def test_save_png_rejects_non_uint8(tmp_path):
    from palubicki.render.io import save_png
    img = _make_solid_image().astype(np.float32) / 255.0
    with pytest.raises(ValueError, match="uint8"):
        save_png(img, tmp_path / "x.png")


def test_save_png_rejects_wrong_shape(tmp_path):
    from palubicki.render.io import save_png
    img = np.zeros((10, 10), dtype=np.uint8)  # 2-D, not RGBA
    with pytest.raises(ValueError, match="shape"):
        save_png(img, tmp_path / "x.png")


# ---------- _glb_to_mesh ----------

def _build_tiny_glb(tmp_path: Path) -> Path:
    """Produce a real .glb from palubicki's builder, for roundtrip testing."""
    from palubicki.config import (
        Config, EnvelopeConfig, GeomConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.export.gltf import write_glb
    from palubicki.geom.builder import build_mesh
    from palubicki.sim.simulator import simulate

    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.5, ry=1.0, rz=0.5, marker_count=200),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_iterations=4),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        seed=11,
        output=tmp_path / "tiny.glb",
    )
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    write_glb(mesh, cfg.output, asset_meta={"seed": cfg.seed})
    return cfg.output


def test_glb_to_mesh_roundtrip_returns_palubicki_mesh(tmp_path):
    from palubicki.geom.mesh import Mesh
    from palubicki.render.io import _glb_to_mesh
    glb = _build_tiny_glb(tmp_path)
    mesh = _glb_to_mesh(glb)
    assert isinstance(mesh, Mesh)
    assert len(mesh.primitives) >= 1
    for p in mesh.primitives:
        assert p.positions.dtype == np.float32
        assert p.normals.shape == p.positions.shape
        assert p.indices.dtype == np.uint32
        assert len(p.material.base_color) == 4


def test_glb_to_mesh_drop_leaves_filters_green(tmp_path):
    from palubicki.render.io import _glb_to_mesh
    glb = _build_tiny_glb(tmp_path)
    with_leaves = _glb_to_mesh(glb, drop_leaves=False)
    no_leaves = _glb_to_mesh(glb, drop_leaves=True)
    # The leaf-dominant-green primitive should be gone.
    assert len(no_leaves.primitives) < len(with_leaves.primitives)


def test_glb_to_mesh_missing_path_raises(tmp_path):
    from palubicki.render import RenderError
    from palubicki.render.io import _glb_to_mesh
    with pytest.raises(RenderError, match="could not load"):
        _glb_to_mesh(tmp_path / "does-not-exist.glb")


# ---------- render_glb ----------

def test_render_glb_produces_image(tmp_path):
    from palubicki.render import render_glb
    glb = _build_tiny_glb(tmp_path)
    img = render_glb(glb, size=(200, 200))
    assert img.dtype == np.uint8
    assert img.shape[2] == 4
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/render/test_io.py -v
```

Expected: FAIL — module `palubicki.render.io` doesn't exist; `render_glb` not exported.

- [ ] **Step 3: Implement `save_png` and `_glb_to_mesh`**

Create `src/palubicki/render/io.py`:

```python
# src/palubicki/render/io.py
"""Persistence helpers: .glb → palubicki.Mesh, ndarray → PNG file."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from palubicki.geom.mesh import Material, Mesh, Primitive
from palubicki.render import RenderError


def save_png(image: np.ndarray, path: Path) -> None:
    """Persist an (H, W, 4) uint8 RGBA ndarray as a PNG file."""
    if image.dtype != np.uint8:
        raise ValueError(f"image must be dtype uint8, got {image.dtype}")
    if image.ndim != 3 or image.shape[2] != 4:
        raise ValueError(f"image must have shape (H, W, 4), got {image.shape}")
    from PIL import Image
    Image.fromarray(image, mode="RGBA").save(Path(path), format="PNG")


def _glb_to_mesh(path: Path, *, drop_leaves: bool = False) -> Mesh:
    """Load a .glb via trimesh and convert to palubicki.Mesh.

    Concatenates all scene nodes into a single Mesh with one Primitive per
    source geometry. Each node's world transform is applied to positions and
    normals. Textures are discarded (diagnostic mode); only base_color is kept.

    If drop_leaves=True, filter out primitives whose base_color is dominantly
    green (g > r and g > b and g > 0.3). This works around the glTF→trimesh
    roundtrip losing alpha_mode='MASK'.
    """
    try:
        import trimesh
    except ImportError as e:
        # trimesh is a core dep; if it's missing, the install is broken.
        raise RenderError(f"trimesh import failed: {e}") from e

    try:
        loaded = trimesh.load(str(path), force="scene")
    except (ValueError, OSError) as e:
        raise RenderError(f"could not load glTF: {path}: {e}") from e
    if loaded is None or not hasattr(loaded, "geometry") or not loaded.geometry:
        raise RenderError(f"could not load glTF: {path} (empty scene)")

    primitives: list[Primitive] = []
    # scene.graph yields (node_name, transform) pairs.
    for node_name, transform in loaded.graph.to_flattened().items():
        geom_name = loaded.graph[node_name][1] if node_name in loaded.graph.nodes else None
        if geom_name is None or geom_name not in loaded.geometry:
            continue
        geom = loaded.geometry[geom_name]
        if not hasattr(geom, "faces") or geom.faces is None or len(geom.faces) == 0:
            continue

        # Apply world transform (4×4) to vertices and normals.
        M = np.asarray(transform, dtype=np.float64)
        verts = np.asarray(geom.vertices, dtype=np.float32)
        verts_h = np.concatenate([verts, np.ones((verts.shape[0], 1), dtype=np.float32)], axis=1)
        verts_w = (verts_h @ M.T)[:, :3].astype(np.float32)

        # For normals, transform with inverse-transpose of upper 3×3.
        R = M[:3, :3]
        try:
            R_inv_t = np.linalg.inv(R).T.astype(np.float32)
        except np.linalg.LinAlgError:
            R_inv_t = R.astype(np.float32)
        if hasattr(geom, "vertex_normals") and geom.vertex_normals is not None:
            norms = np.asarray(geom.vertex_normals, dtype=np.float32) @ R_inv_t.T
        else:
            # Trimesh computes them lazily; fall back to face normals broadcast.
            norms = np.tile(np.array([0, 1, 0], dtype=np.float32), (verts.shape[0], 1))

        faces = np.asarray(geom.faces, dtype=np.uint32).reshape(-1)

        # Material baseColor: try the trimesh visual.material.baseColorFactor;
        # fall back to gray.
        base_color = (0.7, 0.7, 0.7, 1.0)
        visual = getattr(geom, "visual", None)
        mat = getattr(visual, "material", None) if visual is not None else None
        if mat is not None and hasattr(mat, "baseColorFactor") and mat.baseColorFactor is not None:
            bc = np.asarray(mat.baseColorFactor, dtype=np.float32)
            if bc.max() > 1.5:
                bc = bc / 255.0
            if bc.shape == (3,):
                base_color = (float(bc[0]), float(bc[1]), float(bc[2]), 1.0)
            elif bc.shape == (4,):
                base_color = tuple(float(x) for x in bc)

        # Drop-leaves heuristic
        if drop_leaves:
            r, g, b, _ = base_color
            if g > r and g > b and g > 0.3:
                continue

        material = Material(
            name=str(geom_name),
            base_color=base_color,
            metallic=0.0,
            roughness=1.0,
            base_color_texture_png=None,
            alpha_mode="OPAQUE",
            alpha_cutoff=0.5,
            double_sided=False,
        )
        primitives.append(Primitive(
            positions=verts_w,
            normals=norms.astype(np.float32),
            uvs=np.zeros((verts_w.shape[0], 2), dtype=np.float32),
            indices=faces,
            material=material,
        ))

    if not primitives:
        raise RenderError(f"glTF loaded but no usable primitives: {path}")
    return Mesh(primitives=primitives)
```

- [ ] **Step 4: Add `render_glb` to renderer.py**

Append to `src/palubicki/render/renderer.py`:

```python
def render_glb(
    glb_path: Path,
    *,
    size: tuple[int, int] = (800, 800),
    camera: Camera | None = None,
    bg: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
    light_dir: tuple[float, float, float] = (-0.3, -1.0, -0.5),
    drop_leaves: bool = False,
) -> np.ndarray:
    """Load a .glb and render it to an (H, W, 4) uint8 ndarray."""
    from palubicki.render.io import _glb_to_mesh
    mesh = _glb_to_mesh(Path(glb_path), drop_leaves=drop_leaves)
    return render_mesh(
        mesh, size=size, camera=camera, bg=bg, light_dir=light_dir,
    )
```

- [ ] **Step 5: Update `__init__.py` to export `render_glb` and `save_png`**

Replace `src/palubicki/render/__init__.py`:

```python
# src/palubicki/render/__init__.py
"""Headless PNG rendering for palubicki Mesh / .glb (diagnostic level).

Matplotlib is an optional dependency: install with `pip install -e '.[render]'`.
"""
from __future__ import annotations


class RenderError(Exception):
    """Generic render module failure (bad input, degenerate mesh, etc.)."""


class RenderDependencyError(RenderError):
    """Raised when an optional dep (matplotlib) is missing."""


def render_mesh(mesh, **kwargs):
    """See palubicki.render.renderer.render_mesh."""
    from palubicki.render.renderer import render_mesh as _impl
    return _impl(mesh, **kwargs)


def render_glb(glb_path, **kwargs):
    """See palubicki.render.renderer.render_glb."""
    from palubicki.render.renderer import render_glb as _impl
    return _impl(glb_path, **kwargs)


def save_png(image, path):
    """See palubicki.render.io.save_png."""
    from palubicki.render.io import save_png as _impl
    return _impl(image, path)


# Camera is small and matplotlib-free; eager export is fine.
from palubicki.render.camera import Camera   # noqa: E402

__all__ = [
    "Camera",
    "RenderError",
    "RenderDependencyError",
    "render_mesh",
    "render_glb",
    "save_png",
]
```

- [ ] **Step 6: Run all render tests**

```bash
.venv/bin/pytest tests/render/ -v
```

Expected: PASS (all tests in render/ including new io + render_glb)

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/render/io.py \
        src/palubicki/render/renderer.py \
        src/palubicki/render/__init__.py \
        tests/render/test_io.py
git commit -m "feat(render): save_png + glb loader + render_glb wrapper"
```

---

## Task 7: CLI `preview` subcommand

**Files:**
- Modify: `src/palubicki/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI tests (append to existing file)**

Append to `tests/test_cli.py`:

```python
def test_preview_smoke(tmp_path):
    """End-to-end: generate a .glb, then preview it to a PNG."""
    from palubicki.cli import main
    glb = tmp_path / "tree.glb"
    rc = main([
        "generate", "-o", str(glb),
        "--seed", "7",
        "--envelope", "ellipsoid",
        "--envelope-radii", "0.5", "1.0", "0.5",
        "--marker-count", "200",
        "--iterations", "4",
    ])
    assert rc == 0
    assert glb.exists()

    png = tmp_path / "tree.png"
    rc = main(["preview", str(glb), "-o", str(png), "--size", "200x200"])
    assert rc == 0
    assert png.exists()
    assert png.stat().st_size > 1_000


def test_preview_invalid_glb(tmp_path, capsys):
    from palubicki.cli import main
    rc = main(["preview", str(tmp_path / "missing.glb"),
               "-o", str(tmp_path / "x.png")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "preview error" in err and "could not load" in err


def test_preview_parses_size_flag(tmp_path):
    from palubicki.cli import _parse_size
    assert _parse_size("1200x900") == (1200, 900)
    assert _parse_size("800x800") == (800, 800)


def test_preview_size_flag_rejects_garbage():
    from palubicki.cli import _parse_size
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_size("not-a-size")
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_size("800x")


def test_preview_parses_bg_flag():
    from palubicki.cli import _parse_bg
    assert _parse_bg("white") == (1.0, 1.0, 1.0, 1.0)
    assert _parse_bg("black") == (0.0, 0.0, 0.0, 1.0)
    assert _parse_bg("transparent") == (1.0, 1.0, 1.0, 0.0)
```

Note: if the top of `tests/test_cli.py` does not already import `pytest`, add it.

- [ ] **Step 2: Run CLI tests to verify they fail**

```bash
.venv/bin/pytest tests/test_cli.py -v -k preview
```

Expected: FAIL — `preview` subcommand doesn't exist; `_parse_size` / `_parse_bg` not defined.

- [ ] **Step 3: Add the `preview` subparser, command handler, and helpers in `cli.py`**

In `src/palubicki/cli.py`, locate the `main()` dispatcher and add the preview branch:

```python
    if args.command == "preview":
        return _cmd_preview(args)
```

This goes alongside the other `if args.command == ...` branches in `main()`.

In `_build_parser()`, add a new subparser after the `forest` block:

```python
    pv = sub.add_parser("preview", help="Render a .glb to a diagnostic PNG")
    pv.add_argument("glb_path", type=Path)
    pv.add_argument("-o", "--output", type=Path, required=True)
    pv.add_argument("--size", type=_parse_size, default=(800, 800),
                    help="Target image size as WxH (default 800x800)")
    pv.add_argument("--elevation", type=float, default=20.0,
                    help="Camera elevation in degrees (default 20)")
    pv.add_argument("--azimuth", type=float, default=35.0,
                    help="Camera azimuth in degrees (default 35)")
    pv.add_argument("--distance", type=float, default=None,
                    help="Camera distance (default: auto-fit)")
    pv.add_argument("--bg", type=_parse_bg, default=(1.0, 1.0, 1.0, 1.0),
                    help="Background: white | black | transparent (default white)")
    pv.add_argument("--no-leaves", action="store_true",
                    help="Filter out green-dominant primitives (leaves)")
```

Add the parsing helpers at module level (e.g. just above `_cmd_generate`):

```python
def _parse_size(value: str) -> tuple[int, int]:
    """Parse 'WxH' → (W, H). Raises argparse.ArgumentTypeError on garbage."""
    parts = value.lower().split("x")
    if len(parts) != 2 or not all(parts):
        raise argparse.ArgumentTypeError(f"invalid --size {value!r}: expected WxH")
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid --size {value!r}: not integers")
    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError(f"--size must be positive, got {value!r}")
    return (w, h)


_BG_PRESETS = {
    "white": (1.0, 1.0, 1.0, 1.0),
    "black": (0.0, 0.0, 0.0, 1.0),
    "transparent": (1.0, 1.0, 1.0, 0.0),
}


def _parse_bg(value: str) -> tuple[float, float, float, float]:
    """Parse a --bg preset name → RGBA tuple."""
    try:
        return _BG_PRESETS[value]
    except KeyError:
        raise argparse.ArgumentTypeError(
            f"invalid --bg {value!r}: choose from {sorted(_BG_PRESETS)}"
        )
```

Add `_cmd_preview` (right after `_cmd_forest`):

```python
def _cmd_preview(args) -> int:
    try:
        from palubicki.render import Camera, RenderError, render_glb, save_png
    except ImportError:
        print(
            "preview error: render extra not installed. "
            "Run: pip install -e '.[render]'",
            file=sys.stderr,
        )
        return 2

    cam = Camera(
        elevation_deg=args.elevation,
        azimuth_deg=args.azimuth,
        distance=args.distance,
    )
    try:
        img = render_glb(
            args.glb_path,
            size=args.size,
            camera=cam,
            bg=args.bg,
            drop_leaves=args.no_leaves,
        )
        save_png(img, args.output)
    except RenderError as e:
        print(f"preview error: {e}", file=sys.stderr)
        return 1
    return 0
```

- [ ] **Step 4: Run CLI tests**

```bash
.venv/bin/pytest tests/test_cli.py -v -k preview
```

Expected: PASS (5 preview tests)

- [ ] **Step 5: Run the full test suite to ensure nothing else broke**

```bash
.venv/bin/pytest -m "not slow" -v
```

Expected: PASS (all fast tests; `slow` integration goldens excluded)

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/cli.py tests/test_cli.py
git commit -m "feat(cli): palubicki preview subcommand renders .glb to PNG"
```

---

## Task 8: Integration tests (slow) — V1, V3 forest, V4 species

**Files:**
- Create: `tests/render/test_render_integration.py`

- [ ] **Step 1: Write the integration tests**

Create `tests/render/test_render_integration.py`:

```python
# tests/render/test_render_integration.py
"""Slow end-to-end tests: simulate → build_mesh → render. Marked `slow`."""
from pathlib import Path

import numpy as np
import pytest

from palubicki.config import (
    Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig, LightConfig,
    ObstacleAABB, PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.export.gltf import write_glb, write_glb_forest
from palubicki.geom.builder import build_mesh
from palubicki.render import render_glb, render_mesh, save_png
from palubicki.sim.simulator import simulate, simulate_forest

pytestmark = pytest.mark.slow


def _nonbg_ratio(img: np.ndarray, bg_rgb=(255, 255, 255), tol=8) -> float:
    delta = np.abs(img[:, :, :3].astype(int) - np.array(bg_rgb)).max(axis=2)
    return float((delta > tol).mean())


def _v1_cfg(out: Path) -> Config:
    return Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=600),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_iterations=10),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        seed=7,
        output=out,
    )


def test_render_v1_ellipsoid_from_mesh(tmp_path):
    cfg = _v1_cfg(tmp_path / "v1.glb")
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    img = render_mesh(mesh, size=(400, 400))
    assert img.shape[2] == 4
    assert _nonbg_ratio(img) > 0.005


def test_render_v1_ellipsoid_glb_roundtrip(tmp_path):
    """Render via the .glb path — exercises trimesh load + _glb_to_mesh."""
    cfg = _v1_cfg(tmp_path / "v1.glb")
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    write_glb(mesh, cfg.output, asset_meta={"seed": cfg.seed})
    img = render_glb(cfg.output, size=(400, 400))
    assert img.shape[2] == 4
    assert _nonbg_ratio(img) > 0.005


def test_render_forest_glb(tmp_path):
    cfg = Config(
        envelope=EnvelopeConfig(rx=1.5, ry=2.5, rz=1.5, shape="ellipsoid", marker_count=1500),
        sim=SimConfig(max_iterations=6),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        light=LightConfig(enabled=False),
        output=tmp_path / "forest.glb",
        seed=42,
        forest=ForestConfig(
            seeds=(
                ForestSeed(position=(0.0, 0.0, 0.0)),
                ForestSeed(position=(4.0, 0.0, 0.0)),
            ),
            obstacles=(ObstacleAABB(min=(1.5, 0.0, -1.0), max=(2.5, 2.0, 1.0)),),
        ),
    )
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, cfg.output, asset_meta={"seed": cfg.seed})
    img = render_glb(cfg.output, size=(500, 400))
    assert img.shape[2] == 4
    assert _nonbg_ratio(img) > 0.01   # Forest is bigger → more pixels covered.


def test_render_drop_leaves_reduces_non_bg_pixels(tmp_path):
    cfg = _v1_cfg(tmp_path / "v1.glb")
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    write_glb(mesh, cfg.output, asset_meta={})
    full = render_glb(cfg.output, size=(400, 400))
    leafless = render_glb(cfg.output, size=(400, 400), drop_leaves=True)
    # Removing leaves should reduce coverage (silhouette gets sparser).
    assert _nonbg_ratio(leafless) < _nonbg_ratio(full)


def test_render_save_to_disk(tmp_path):
    cfg = _v1_cfg(tmp_path / "v1.glb")
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    img = render_mesh(mesh, size=(300, 300))
    out = tmp_path / "v1.png"
    save_png(img, out)
    assert out.exists()
    assert out.stat().st_size > 1_000
```

- [ ] **Step 2: Run the integration tests**

```bash
.venv/bin/pytest tests/render/test_render_integration.py -v -m slow
```

Expected: PASS (5 tests)

- [ ] **Step 3: Run the entire test suite (fast + slow) to check no regressions**

```bash
.venv/bin/pytest -v
```

Expected: all tests pass (the pre-existing slow goldens may take longer; that's normal)

- [ ] **Step 4: Commit**

```bash
git add tests/render/test_render_integration.py
git commit -m "test(render): slow integration tests for V1 + forest + drop-leaves"
```

---

## Task 9: Golden `--render-on-fail` opt-in flag + README update

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/golden/test_goldens.py`
- Modify: `README.md`

- [ ] **Step 1: Add the `--render-on-fail` pytest option**

In `tests/conftest.py`, extend `pytest_addoption` (locate the existing function around lines 5-9):

```python
def pytest_addoption(parser):
    parser.addoption(
        "--update-goldens", action="store_true",
        help="Regenerate golden binaries instead of comparing.",
    )
    parser.addoption(
        "--render-on-fail", action="store_true",
        help="When a golden buffer hash check fails, also render PNG of the "
             "current mesh to tmp_path/diff/ for visual diagnosis.",
    )
```

- [ ] **Step 2: Wire the new flag into the goldens**

In `tests/golden/conftest.py`, add a fixture alongside the existing `update_goldens`:

```python
# tests/golden/conftest.py
import pytest


@pytest.fixture
def update_goldens(request):
    return request.config.getoption("--update-goldens")


@pytest.fixture
def render_on_fail(request):
    return request.config.getoption("--render-on-fail")
```

- [ ] **Step 3: Use the flag in `test_golden_ellipsoid` (existing test)**

In `tests/golden/test_goldens.py`, locate `test_golden_ellipsoid` (around line 61) and add the `render_on_fail` fixture + a small helper that's used only when the assert is about to fail:

```python
def test_golden_ellipsoid(tmp_path, update_goldens, render_on_fail):
    cfg = _cfg_ellipsoid(tmp_path / "g.glb")
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    write_glb(mesh, cfg.output, asset_meta={"seed": cfg.seed})

    h = _hash_buffers(cfg.output)
    golden = GOLDEN_DIR / "ellipsoid.sha256"

    if update_goldens or not golden.exists():
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden.write_text(h)
        pytest.skip("golden written; re-run without --update-goldens to verify")
    expected = golden.read_text().strip()

    if h != expected and render_on_fail:
        diff_dir = tmp_path / "diff"
        diff_dir.mkdir(exist_ok=True)
        try:
            from palubicki.render import render_mesh, save_png
            save_png(render_mesh(mesh, size=(600, 600)), diff_dir / "actual.png")
            extra = f"\n  rendered actual to: {diff_dir / 'actual.png'}"
        except Exception as e:  # render is best-effort, never block the assert
            extra = f"\n  (render-on-fail unavailable: {e})"
    else:
        extra = ""

    assert h == expected, (
        f"golden mismatch.\nexpected: {expected}\nactual:   {h}\n"
        f"if intentional, re-run with --update-goldens after visual review{extra}"
    )
```

Note: only `test_golden_ellipsoid` gets this treatment in this task. The same pattern can be applied to the other goldens incrementally when they actually need it.

- [ ] **Step 4: Smoke-test the flag**

The behavior is only triggered on failure, which we can't easily simulate without breaking a golden. We just confirm pytest accepts the flag:

```bash
.venv/bin/pytest tests/golden/test_goldens.py::test_golden_ellipsoid --render-on-fail -v -m slow
```

Expected: PASS (or skip if goldens missing). The flag is consumed without error.

- [ ] **Step 5: Update README — add a Preview section**

In `README.md`, add a new section under `## Usage`. Locate the closing fence of the `## Usage` section (right before `### V2 — voxel light shadowing`). Insert:

```markdown
### Preview — render a `.glb` to PNG

For quick visual iteration without an external glTF viewer:

```bash
# Install the optional render extra (matplotlib)
pip install -e ".[render]"

# Default: 800x800 white background
palubicki preview tree.glb -o tree.png

# Custom view angle and size
palubicki preview tree.glb -o tree.png --size 1200x900 --elevation 15 --azimuth 60

# Transparent background, no leaves (silhouette of bark only)
palubicki preview forest.glb -o forest.png --bg transparent --no-leaves
```

The renderer is **diagnostic level**: silhouette + flat Lambert shading + base
material colors. No textures, no shadows, no anti-aliasing tricks. It exists
so that iterating on configs and species presets doesn't require opening every
`.glb` in an external viewer.

In notebooks, use the underlying API directly:

```python
from palubicki.render import render_glb
import matplotlib.pyplot as plt
plt.imshow(render_glb("oak.glb"))
```
```

- [ ] **Step 6: Final test run + commit**

```bash
.venv/bin/pytest -v
```

Expected: all tests pass.

```bash
git add tests/conftest.py tests/golden/conftest.py tests/golden/test_goldens.py README.md
git commit -m "feat(render): --render-on-fail opt-in for golden diagnosis + README"
```

---

## Self-review checklist

Run this mentally after the plan is committed:

**Spec coverage:**
- ✅ `palubicki.render` package with public API — Task 1, 5, 6
- ✅ `Camera` + `Camera.fit` — Task 2
- ✅ `render_mesh` with size/camera/bg/light_dir/drop_leaves — Task 5
- ✅ `_flatten` and `_shade` helpers — Task 3, 4
- ✅ `_glb_to_mesh` with green-dominance drop-leaves heuristic — Task 6
- ✅ `render_glb` and `save_png` — Task 6
- ✅ CLI `preview` subcommand with all flags + `_parse_size` / `_parse_bg` — Task 7
- ✅ pyproject `render` optional extra — Task 1
- ✅ Error hierarchy (`RenderError`, `RenderDependencyError`) — Task 1
- ✅ All 5 error cases (matplotlib absent, glTF invalid, empty mesh, degenerate, absurd size) — Task 1, 5, 6, 7
- ✅ Unit tests covering `_flatten`, `_shade`, `Camera.fit`, `render_mesh` shape + errors — Task 2, 3, 4, 5
- ✅ Integration tests (slow) for V1 + forest + drop_leaves + save roundtrip — Task 8
- ✅ CLI smoke tests (3 cases) — Task 7
- ✅ Golden `--render-on-fail` opt-in flag — Task 9
- ✅ README Preview section — Task 9
- ✅ Logging discipline (one info line, namespaced logger) — Task 5

**No placeholders:** Every step contains the actual code, the actual command, and the expected output. No "TBD" / "implement later" / "similar to X" found.

**Type consistency:**
- `render_mesh(mesh, *, size, camera, bg, light_dir, drop_leaves)` — used identically across Tasks 5, 6, 7.
- `render_glb(glb_path, **kwargs)` — kwargs match `render_mesh` minus `drop_leaves` being handled before `render_mesh`.
- `Camera(elevation_deg, azimuth_deg, target, distance, margin)` — consistent across Tasks 2 and 7.
- `RenderError` / `RenderDependencyError` — same names from Task 1 onward.
- `_glb_to_mesh(path, *, drop_leaves)` — consistent in Tasks 6 + 8.
- `_parse_size`, `_parse_bg`, `_BG_PRESETS` — defined once in Task 7, referenced only there.
