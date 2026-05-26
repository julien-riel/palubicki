# V4 Species Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three species presets (oak, pine, birch) to palubicki via a packaged YAML loader, procedural PIL textures, and a parametric leaf cluster — no simulation engine changes, V1/V2/V3 goldens stay bit-exact.

**Architecture:** Spec at `docs/superpowers/specs/2026-05-26-v4-species-presets-design.md`. Twelve incremental tasks ordered bottom-up: config additions → texture generators → preset loader → CLI integration → goldens. Each task lands a self-contained, committable slice.

**Tech Stack:** Python 3.11+, `dataclass`-based config, PIL/Pillow for procedural textures, PyYAML, `importlib.resources` for packaged data, pytest + golden hashes.

**Environment note:** This project uses `.venv/` at the repo root. Bash sessions do **not** persist `source .venv/bin/activate` between calls — always prefix Python commands with `.venv/bin/` (e.g. `.venv/bin/pytest`).

---

## Task 1: Add `bark_texture` field to GeomConfig and route it to the bark Material

**Files:**
- Modify: `src/palubicki/config.py:59-68` (GeomConfig), `src/palubicki/config.py:162-170` (validation)
- Modify: `src/palubicki/geom/builder.py:14-46` (builder uses bark_texture)
- Test: `tests/geom/test_builder_bark_texture.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/geom/test_builder_bark_texture.py`:

```python
from pathlib import Path

import numpy as np

from palubicki.config import (
    Config, EnvelopeConfig, GeomConfig, LightConfig, PhyllotaxyConfig,
    SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.geom.builder import build_mesh
from palubicki.sim.simulator import simulate


def _cfg(out: Path, bark_texture: Path | None) -> Config:
    return Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.5, ry=1.0, rz=0.5, marker_count=200),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_iterations=4),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(bark_texture=bark_texture),
        seed=1,
        output=out,
    )


def test_bark_material_has_no_texture_by_default(tmp_path):
    cfg = _cfg(tmp_path / "x.glb", bark_texture=None)
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    bark = mesh.primitives[0].material
    assert bark.base_color_texture_png is None


def test_bark_material_loads_supplied_png(tmp_path):
    from PIL import Image
    png_path = tmp_path / "bark.png"
    Image.new("RGB", (8, 8), (200, 150, 100)).save(png_path)

    cfg = _cfg(tmp_path / "x.glb", bark_texture=png_path)
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    bark = mesh.primitives[0].material
    assert bark.base_color_texture_png is not None
    assert bark.base_color_texture_png == png_path.read_bytes()
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/geom/test_builder_bark_texture.py -v
```

Expected: FAIL — `GeomConfig` has no `bark_texture` argument.

- [ ] **Step 3: Add field to GeomConfig**

In `src/palubicki/config.py`, modify the `GeomConfig` dataclass (around lines 59-68):

```python
@dataclass(frozen=True)
class GeomConfig:
    ring_sides: int = 8
    r_tip: float = 0.005
    pipe_exponent: float = 2.49
    leaf_size: float = 0.06
    leaf_texture: Path | None = None
    bark_color: tuple[float, float, float] = (0.35, 0.22, 0.12)
    bark_texture: Path | None = None
    enable_leaves: bool = True
```

- [ ] **Step 4: Route `bark_texture` through `build_mesh`**

In `src/palubicki/geom/builder.py`, replace the body of `build_mesh` to load and pass the bark texture (mirroring the leaf texture logic):

```python
def build_mesh(tree: Tree, cfg: Config) -> Mesh:
    compute_radii(tree, r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent)

    bark_png = _load_bark_texture(cfg.geom.bark_texture)
    bark_mat = Material(
        name="bark",
        base_color=(*cfg.geom.bark_color, 1.0),
        metallic=0.0,
        roughness=0.9,
        base_color_texture_png=bark_png,
        alpha_mode="OPAQUE",
        alpha_cutoff=0.5,
        double_sided=False,
    )
    bark_prim = build_bark_primitive(tree, ring_sides=cfg.geom.ring_sides, material=bark_mat)
    primitives = [bark_prim]

    if cfg.geom.enable_leaves:
        png = _load_leaf_texture(cfg.geom.leaf_texture)
        leaf_mat = Material(
            name="leaf",
            base_color=(0.4, 0.6, 0.2, 1.0),
            metallic=0.0,
            roughness=0.85,
            base_color_texture_png=png,
            alpha_mode="MASK",
            alpha_cutoff=0.5,
            double_sided=True,
        )
        leaf_prim = build_leaves_primitive(tree, leaf_size=cfg.geom.leaf_size, material=leaf_mat)
        primitives.append(leaf_prim)

    return Mesh(primitives=primitives)


def _load_bark_texture(path: Path | None) -> bytes | None:
    if path is None:
        return None
    return Path(path).read_bytes()


def _load_leaf_texture(path: Path | None) -> bytes:
    if path is None:
        return default_leaf_png()
    return Path(path).read_bytes()
```

- [ ] **Step 5: Run tests to verify**

```bash
.venv/bin/pytest tests/geom/test_builder_bark_texture.py -v
.venv/bin/pytest -m "not slow" -x
```

Expected: New tests PASS. All existing non-slow tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/config.py src/palubicki/geom/builder.py tests/geom/test_builder_bark_texture.py
git commit -m "feat(geom): GeomConfig.bark_texture (PNG path → bark Material)"
```

---

## Task 2: Add parametric leaf cluster parameters to GeomConfig

**Files:**
- Modify: `src/palubicki/config.py` (GeomConfig + validation)
- Test: `tests/test_config.py` (extend) or new `tests/test_config_leaf_cluster.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_leaf_cluster.py`:

```python
import pytest

from palubicki.config import ConfigError, GeomConfig


def test_leaf_cluster_defaults_are_v1_compat():
    g = GeomConfig()
    assert g.leaf_cluster_count == 1
    assert g.leaf_aspect == 1.0
    assert g.leaf_splay_deg == 0.0


def test_leaf_cluster_count_zero_invalid_at_config_validation():
    """GeomConfig itself is permissive (no __post_init__); validation lives in Config.
    We exercise it via a full Config construction in the next test."""
    g = GeomConfig(leaf_cluster_count=0)
    assert g.leaf_cluster_count == 0  # accepted at the dataclass level


def test_full_config_rejects_zero_cluster_count(tmp_path):
    from palubicki.config import (
        Config, EnvelopeConfig, LightConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    with pytest.raises(ConfigError, match="leaf_cluster_count"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_cluster_count=0),
            output=tmp_path / "x.glb",
        )


def test_full_config_rejects_aspect_out_of_range(tmp_path):
    from palubicki.config import (
        Config, EnvelopeConfig, LightConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    with pytest.raises(ConfigError, match="leaf_aspect"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_aspect=5.0),
            output=tmp_path / "x.glb",
        )


def test_full_config_rejects_splay_out_of_range(tmp_path):
    from palubicki.config import (
        Config, EnvelopeConfig, LightConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    with pytest.raises(ConfigError, match="leaf_splay_deg"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_splay_deg=120.0),
            output=tmp_path / "x.glb",
        )
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/test_config_leaf_cluster.py -v
```

Expected: FAIL — `GeomConfig` does not accept `leaf_cluster_count`.

- [ ] **Step 3: Extend GeomConfig**

In `src/palubicki/config.py`, modify `GeomConfig`:

```python
@dataclass(frozen=True)
class GeomConfig:
    ring_sides: int = 8
    r_tip: float = 0.005
    pipe_exponent: float = 2.49
    leaf_size: float = 0.06
    leaf_texture: Path | None = None
    bark_color: tuple[float, float, float] = (0.35, 0.22, 0.12)
    bark_texture: Path | None = None
    leaf_cluster_count: int = 1
    leaf_aspect: float = 1.0
    leaf_splay_deg: float = 0.0
    enable_leaves: bool = True
```

- [ ] **Step 4: Extend Config.__post_init__ validation**

In `src/palubicki/config.py`, inside `Config.__post_init__`, locate the `g = self.geom` block (around line 162) and append:

```python
        if g.leaf_cluster_count < 1:
            raise ConfigError(f"geom.leaf_cluster_count must be >= 1, got {g.leaf_cluster_count}")
        if not (0.0 < g.leaf_aspect <= 4.0):
            raise ConfigError(f"geom.leaf_aspect must be in (0, 4], got {g.leaf_aspect}")
        if not (0.0 <= g.leaf_splay_deg <= 90.0):
            raise ConfigError(f"geom.leaf_splay_deg must be in [0, 90], got {g.leaf_splay_deg}")
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/test_config_leaf_cluster.py -v
.venv/bin/pytest -m "not slow" -x
```

Expected: PASS. All existing non-slow tests still PASS (defaults are unchanged for V1/V2/V3 callers).

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/config.py tests/test_config_leaf_cluster.py
git commit -m "feat(config): GeomConfig leaf_cluster_count/aspect/splay_deg + validation"
```

---

## Task 3: Refactor `_emit_cross_quad` into `_emit_leaf_cluster` (bit-exact default)

**Files:**
- Modify: `src/palubicki/geom/leaves.py` (replace _emit_cross_quad with parametric cluster)
- Test: `tests/geom/test_leaf_cluster.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/geom/test_leaf_cluster.py`:

```python
import math
from pathlib import Path

import numpy as np

from palubicki.config import (
    Config, EnvelopeConfig, GeomConfig, LightConfig, PhyllotaxyConfig,
    SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.geom.leaves import build_leaves_primitive
from palubicki.geom.mesh import Material
from palubicki.sim.simulator import simulate


def _stub_material() -> Material:
    return Material(
        name="leaf", base_color=(0.4, 0.6, 0.2, 1.0),
        metallic=0.0, roughness=0.85, base_color_texture_png=None,
        alpha_mode="MASK", alpha_cutoff=0.5, double_sided=True,
    )


def _small_tree():
    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.5, ry=1.0, rz=0.5, marker_count=150),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_iterations=4),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        seed=1, output=Path("/tmp/unused.glb"),
    )
    return simulate(cfg)


def test_default_cluster_matches_old_cross_quad_vertex_count():
    tree = _small_tree()
    prim = build_leaves_primitive(tree, leaf_size=0.06,
                                  cluster_count=1, aspect=1.0, splay_deg=0.0,
                                  material=_stub_material())
    n_terminal = sum(1 for b in tree.active_buds if not b.parent_node.children_internodes)
    assert prim.positions.shape == (n_terminal * 8, 3)
    assert prim.indices.shape == (n_terminal * 12,)


def test_cluster_count_5_emits_5x_vertices_per_bud():
    tree = _small_tree()
    prim = build_leaves_primitive(tree, leaf_size=0.06,
                                  cluster_count=5, aspect=0.2, splay_deg=20.0,
                                  material=_stub_material())
    n_terminal = sum(1 for b in tree.active_buds if not b.parent_node.children_internodes)
    assert prim.positions.shape == (n_terminal * 5 * 8, 3)
    assert prim.indices.shape == (n_terminal * 5 * 12,)


def test_aspect_ratio_narrows_quads_along_axis_u():
    """With aspect=0.2 and the same leaf_size, the cross-quad's u-axis half-extent
    is 0.2× the value used with aspect=1.0."""
    tree = _small_tree()
    p1 = build_leaves_primitive(tree, leaf_size=0.06, cluster_count=1, aspect=1.0,
                                splay_deg=0.0, material=_stub_material())
    p2 = build_leaves_primitive(tree, leaf_size=0.06, cluster_count=1, aspect=0.2,
                                splay_deg=0.0, material=_stub_material())
    # First quad (vertices 0..3) for the first terminal bud
    diag1 = np.linalg.norm(p1.positions[1] - p1.positions[0])  # width along axis_u
    diag2 = np.linalg.norm(p2.positions[1] - p2.positions[0])
    assert diag2 == pytest.approx(0.2 * diag1, rel=1e-5)


import pytest
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/geom/test_leaf_cluster.py -v
```

Expected: FAIL — `build_leaves_primitive` does not accept `cluster_count`/`aspect`/`splay_deg`.

- [ ] **Step 3: Replace `_emit_cross_quad` with `_emit_leaf_cluster` and extend signature**

In `src/palubicki/geom/leaves.py`, replace the entire file content:

```python
from __future__ import annotations

import math

import numpy as np

from palubicki.geom.mesh import Material, Primitive
from palubicki.sim.tree import BudState, Tree


def build_leaves_primitive(
    tree: Tree,
    *,
    leaf_size: float,
    material: Material,
    cluster_count: int = 1,
    aspect: float = 1.0,
    splay_deg: float = 0.0,
) -> Primitive:
    """Per surviving terminal bud, emit `cluster_count` cross-quads (8 verts each)
    azimuthally spread around the growth direction and tilted outward by splay_deg."""
    surviving = [b for b in tree.active_buds if b.state != BudState.DEAD and _is_terminal(b)]

    if not surviving:
        return Primitive(
            positions=np.zeros((0, 3), dtype=np.float32),
            normals=np.zeros((0, 3), dtype=np.float32),
            uvs=np.zeros((0, 2), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
            material=material,
        )

    verts_per_bud = cluster_count * 8
    idx_per_bud = cluster_count * 12
    n = len(surviving)
    positions = np.empty((n * verts_per_bud, 3), dtype=np.float32)
    normals = np.empty((n * verts_per_bud, 3), dtype=np.float32)
    uvs = np.empty((n * verts_per_bud, 2), dtype=np.float32)
    indices = np.empty((n * idx_per_bud,), dtype=np.uint32)

    splay_rad = math.radians(splay_deg)

    for i, bud in enumerate(surviving):
        v_start = i * verts_per_bud
        i_start = i * idx_per_bud
        _emit_leaf_cluster(
            bud.position, bud.direction, leaf_size, cluster_count, aspect, splay_rad,
            positions[v_start : v_start + verts_per_bud],
            normals[v_start : v_start + verts_per_bud],
            uvs[v_start : v_start + verts_per_bud],
            indices[i_start : i_start + idx_per_bud],
            v_start,
        )
    return Primitive(positions=positions, normals=normals, uvs=uvs, indices=indices, material=material)


def _is_terminal(bud) -> bool:
    return len(bud.parent_node.children_internodes) == 0


def _emit_leaf_cluster(center, direction, size, cluster_count, aspect, splay_rad,
                      out_pos, out_norm, out_uv, out_idx, base):
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    right, forward = _basis_perpendicular_to(d)

    half_u = size * 0.5 * aspect
    half_v = size * 0.5
    petiole_offset = d * (size * 0.3)
    leaf_center = np.asarray(center, dtype=np.float64) + petiole_offset

    for k in range(cluster_count):
        az = 2.0 * math.pi * k / cluster_count
        # Rotate (right, forward) around d by az; then tilt the cluster axis outward by splay_rad.
        rot_axis_u = math.cos(az) * right + math.sin(az) * forward
        rot_axis_w = -math.sin(az) * right + math.cos(az) * forward  # in-plane perpendicular
        # leaf_up tilts from d toward rot_axis_u by splay_rad
        leaf_up = math.cos(splay_rad) * d + math.sin(splay_rad) * rot_axis_u

        v_off = k * 8
        i_off = k * 12
        cluster_base = base + v_off
        # Quad A: (rot_axis_u, leaf_up) plane; normal = rot_axis_w
        _add_quad(leaf_center, rot_axis_u, leaf_up, half_u, half_v, rot_axis_w,
                  out_pos, out_norm, out_uv, out_idx, cluster_base, v_off, slot=0, idx_base=i_off)
        # Quad B: (rot_axis_w, leaf_up) plane; normal = rot_axis_u
        _add_quad(leaf_center, rot_axis_w, leaf_up, half_u, half_v, rot_axis_u,
                  out_pos, out_norm, out_uv, out_idx, cluster_base, v_off, slot=4, idx_base=i_off)


def _basis_perpendicular_to(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    canonical = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    right = canonical - np.dot(canonical, d) * d
    right = right / np.linalg.norm(right)
    forward = np.cross(d, right)
    return right, forward


def _add_quad(center, axis_u, axis_v, half_u, half_v, normal,
              out_pos, out_norm, out_uv, out_idx, base, v_off, slot, idx_base):
    pos_slot = v_off + slot
    out_pos[pos_slot + 0] = (center - axis_u * half_u).astype(np.float32)
    out_pos[pos_slot + 1] = (center + axis_u * half_u).astype(np.float32)
    out_pos[pos_slot + 2] = (center + axis_u * half_u + axis_v * 2 * half_v).astype(np.float32)
    out_pos[pos_slot + 3] = (center - axis_u * half_u + axis_v * 2 * half_v).astype(np.float32)
    n = np.asarray(normal, dtype=np.float32)
    for j in range(4):
        out_norm[pos_slot + j] = n
    out_uv[pos_slot + 0] = (0.0, 0.0)
    out_uv[pos_slot + 1] = (1.0, 0.0)
    out_uv[pos_slot + 2] = (1.0, 1.0)
    out_uv[pos_slot + 3] = (0.0, 1.0)
    idx_slot = idx_base + (slot // 4) * 6
    a = base + slot + 0; b = base + slot + 1
    c = base + slot + 2; d = base + slot + 3
    out_idx[idx_slot + 0] = a; out_idx[idx_slot + 1] = b; out_idx[idx_slot + 2] = c
    out_idx[idx_slot + 3] = a; out_idx[idx_slot + 4] = c; out_idx[idx_slot + 5] = d
```

- [ ] **Step 4: Update the builder caller to pass the new params**

In `src/palubicki/geom/builder.py`, change the leaves call to forward the cluster params:

```python
        leaf_prim = build_leaves_primitive(
            tree,
            leaf_size=cfg.geom.leaf_size,
            material=leaf_mat,
            cluster_count=cfg.geom.leaf_cluster_count,
            aspect=cfg.geom.leaf_aspect,
            splay_deg=cfg.geom.leaf_splay_deg,
        )
```

- [ ] **Step 5: Run tests including V1/V2/V3 goldens**

```bash
.venv/bin/pytest tests/geom/test_leaf_cluster.py -v
.venv/bin/pytest -m "not slow" -x
.venv/bin/pytest -m slow tests/golden/ -v
```

Expected: New tests PASS. Non-slow tests PASS. **Goldens PASS unchanged** (defaults `cluster=1, aspect=1.0, splay=0` reproduce the prior cross-quad geometry bit-exact, since the same `_add_quad` math is reused).

If a golden fails, **STOP** and investigate before continuing. The likely cause is the `half_u` vs `half_v` change — verify with `aspect=1.0` that `half_u == half_v == size * 0.5`, matching the old code.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/geom/leaves.py src/palubicki/geom/builder.py tests/geom/test_leaf_cluster.py
git commit -m "feat(geom): parametric leaf cluster (cluster_count + aspect + splay)"
```

---

## Task 4: Rename `_leaf_texture.py` → `_textures.py`

**Files:**
- Move: `src/palubicki/geom/_leaf_texture.py` → `src/palubicki/geom/_textures.py`
- Modify: `src/palubicki/geom/builder.py:6` (update import)

- [ ] **Step 1: Move the file**

```bash
git mv src/palubicki/geom/_leaf_texture.py src/palubicki/geom/_textures.py
```

- [ ] **Step 2: Update import in builder.py**

In `src/palubicki/geom/builder.py`, change line 6:

```python
from palubicki.geom._textures import default_leaf_png
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/pytest -m "not slow" -x
```

Expected: PASS (rename + import update only).

- [ ] **Step 4: Commit**

```bash
git add src/palubicki/geom/_textures.py src/palubicki/geom/_leaf_texture.py src/palubicki/geom/builder.py
git commit -m "refactor(geom): rename _leaf_texture.py to _textures.py"
```

---

## Task 5: Add six procedural texture generators + `_PROC_TEXTURES` registry

**Files:**
- Modify: `src/palubicki/geom/_textures.py` (add 6 generators + registry)
- Test: `tests/geom/test_textures.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/geom/test_textures.py`:

```python
import io

import pytest
from PIL import Image

from palubicki.geom._textures import (
    _PROC_TEXTURES,
    birch_bark_png, birch_leaf_png,
    default_leaf_png,
    oak_bark_png, oak_leaf_png,
    pine_bark_png, pine_needle_png,
)


BARK_GENS = [oak_bark_png, pine_bark_png, birch_bark_png]
LEAF_GENS = [oak_leaf_png, pine_needle_png, birch_leaf_png]


@pytest.mark.parametrize("gen", BARK_GENS)
def test_bark_png_produces_valid_image(gen):
    png = gen(256)
    assert len(png) > 100
    img = Image.open(io.BytesIO(png))
    assert img.size == (256, 256)
    assert img.mode in {"RGB", "RGBA"}


@pytest.mark.parametrize("gen", LEAF_GENS)
def test_leaf_png_is_rgba_with_alpha(gen):
    png = gen(128)
    img = Image.open(io.BytesIO(png))
    assert img.size == (128, 128)
    assert img.mode == "RGBA"
    # Verify alpha actually varies (mask cutout, not opaque rectangle)
    alpha = img.split()[-1]
    extrema = alpha.getextrema()
    assert extrema[0] == 0, "leaf should have transparent regions outside the silhouette"
    assert extrema[1] == 255, "leaf should have fully opaque pixels inside the silhouette"


@pytest.mark.parametrize("gen", BARK_GENS + LEAF_GENS + [default_leaf_png])
def test_texture_is_deterministic(gen):
    a = gen(64)
    b = gen(64)
    assert a == b


def test_proc_textures_registry_has_six_entries():
    assert set(_PROC_TEXTURES) == {
        "oak_bark", "pine_bark", "birch_bark",
        "oak_leaf", "pine_needle", "birch_leaf",
    }


def test_proc_textures_callable_returns_bytes():
    for name, gen in _PROC_TEXTURES.items():
        png = gen()
        assert isinstance(png, bytes) and len(png) > 100, f"generator {name} broken"
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/geom/test_textures.py -v
```

Expected: FAIL — names don't exist yet.

- [ ] **Step 3: Implement the generators**

Append to `src/palubicki/geom/_textures.py` (after the existing `default_leaf_png`):

```python
import math
import random

import numpy as np


def _seeded_rng(label: str) -> random.Random:
    """Deterministic Random keyed by texture label — guarantees reproducibility."""
    return random.Random(hash(label) & 0xFFFFFFFF)


# ---------- BARK ----------

def oak_bark_png(size: int = 256) -> bytes:
    """Gris-brun fissuré vertical, sillons larges. Tileable horizontalement."""
    img = Image.new("RGB", (size, size), (95, 70, 50))
    draw = ImageDraw.Draw(img)
    rng = _seeded_rng("oak_bark")
    # Coarse noise via overlapping ellipses (cheap)
    for _ in range(120):
        x = rng.randint(0, size)
        y = rng.randint(0, size)
        r = rng.randint(8, 28)
        shade = rng.randint(60, 110)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(shade, int(shade * 0.75), int(shade * 0.5)))
    # Vertical fissures with sinusoidal jitter, drawn twice (x and x+size) so tile wraps
    for _ in range(14):
        x0 = rng.randint(0, size)
        amp = rng.uniform(2.0, 6.0)
        phase = rng.uniform(0, math.tau)
        for tile_dx in (0, size):
            pts = []
            for y in range(0, size + 1, 4):
                x = x0 + tile_dx + amp * math.sin(phase + y * 0.05)
                pts.append((x, y))
            draw.line(pts, fill=(35, 25, 18), width=rng.randint(2, 4))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def pine_bark_png(size: int = 256) -> bytes:
    """Plaques ocre/rouge irrégulières. Tileable."""
    img = Image.new("RGB", (size, size), (120, 70, 45))
    draw = ImageDraw.Draw(img)
    rng = _seeded_rng("pine_bark")
    # Plaques: irregular polygons
    for _ in range(40):
        cx = rng.randint(0, size)
        cy = rng.randint(0, size)
        n_verts = rng.randint(5, 8)
        radius = rng.randint(15, 35)
        pts = []
        for i in range(n_verts):
            angle = 2 * math.pi * i / n_verts + rng.uniform(-0.3, 0.3)
            r = radius * rng.uniform(0.7, 1.2)
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        shade_r = rng.randint(80, 170)
        shade_g = rng.randint(40, 80)
        shade_b = rng.randint(25, 55)
        draw.polygon(pts, fill=(shade_r, shade_g, shade_b), outline=(40, 20, 12))
        # Wrap-around copy for horizontal tile
        if cx < radius:
            pts2 = [(p[0] + size, p[1]) for p in pts]
            draw.polygon(pts2, fill=(shade_r, shade_g, shade_b), outline=(40, 20, 12))
        elif cx > size - radius:
            pts2 = [(p[0] - size, p[1]) for p in pts]
            draw.polygon(pts2, fill=(shade_r, shade_g, shade_b), outline=(40, 20, 12))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def birch_bark_png(size: int = 256) -> bytes:
    """Blanc cassé + stries horizontales noires + 'yeux' ovales. Tileable."""
    img = Image.new("RGB", (size, size), (235, 230, 220))
    draw = ImageDraw.Draw(img)
    rng = _seeded_rng("birch_bark")
    # Horizontal streaks (already tile horizontally by construction)
    for _ in range(8):
        y = rng.randint(0, size - 1)
        h = rng.randint(2, 8)
        shade = rng.randint(20, 60)
        draw.rectangle((0, y, size, y + h), fill=(shade, shade, shade))
    # 'Eye' ovals
    for _ in range(12):
        cx = rng.randint(0, size)
        cy = rng.randint(0, size)
        w = rng.randint(6, 18)
        h = rng.randint(2, 6)
        draw.ellipse((cx - w, cy - h, cx + w, cy + h), fill=(20, 18, 15))
        if cx - w < 0:
            draw.ellipse((cx - w + size, cy - h, cx + w + size, cy + h), fill=(20, 18, 15))
        elif cx + w > size:
            draw.ellipse((cx - w - size, cy - h, cx + w - size, cy + h), fill=(20, 18, 15))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------- LEAVES ----------

def oak_leaf_png(size: int = 128) -> bytes:
    """Lobed silhouette (8 lobes), vert moyen, RGBA mask."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size / 2, size / 2
    n_lobes = 8
    pts = []
    for i in range(64):
        t = i / 64
        angle = 2 * math.pi * t - math.pi / 2  # start at top
        # Lobe modulation: cos(n_lobes * angle) shapes the radial silhouette
        lobe = 0.78 + 0.22 * math.cos(n_lobes * angle)
        # Stretch vertically (leaves are oval, not circular)
        r_x = (size * 0.42) * lobe
        r_y = (size * 0.48) * lobe
        pts.append((cx + r_x * math.cos(angle), cy + r_y * math.sin(angle)))
    draw.polygon(pts, fill=(75, 130, 55, 255))
    # Central vein
    draw.line((cx, int(size * 0.05), cx, int(size * 0.95)), fill=(45, 85, 35, 220), width=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def pine_needle_png(size: int = 128) -> bytes:
    """Aiguille fine verticale, vert foncé, RGBA. Width ~12% of size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = size // 2
    w = max(2, size // 18)
    # Needle: thin rectangle with rounded caps
    top = int(size * 0.05)
    bot = int(size * 0.95)
    draw.rectangle((cx - w, top, cx + w, bot), fill=(40, 80, 35, 255))
    # Rounded top
    draw.ellipse((cx - w, top - w, cx + w, top + w), fill=(40, 80, 35, 255))
    # Pointed bottom (triangle)
    draw.polygon([(cx - w, bot), (cx + w, bot), (cx, bot + w * 2)], fill=(40, 80, 35, 255))
    # Subtle highlight stripe
    draw.line((cx, top, cx, bot), fill=(70, 110, 55, 200), width=1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def birch_leaf_png(size: int = 128) -> bytes:
    """Triangle pointu dentelé, vert clair, RGBA."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = size / 2
    top_y = size * 0.05
    bot_y = size * 0.95
    half_w = size * 0.32
    # Build a serrated outline: triangle with zigzag edges
    pts = [(cx, top_y)]  # apex
    n_teeth = 10
    # Right side: top to bottom
    for i in range(1, n_teeth + 1):
        t = i / n_teeth
        y = top_y + (bot_y - top_y) * t
        x_outer = cx + half_w * t
        x_inner = cx + half_w * t * 0.85
        pts.append((x_outer, y - (bot_y - top_y) / (n_teeth * 2)))
        pts.append((x_inner, y))
    # Bottom point
    pts.append((cx, bot_y))
    # Left side: bottom to top (mirror)
    for i in range(n_teeth, 0, -1):
        t = i / n_teeth
        y = top_y + (bot_y - top_y) * t
        x_outer = cx - half_w * t
        x_inner = cx - half_w * t * 0.85
        pts.append((x_inner, y))
        pts.append((x_outer, y - (bot_y - top_y) / (n_teeth * 2)))
    draw.polygon(pts, fill=(120, 175, 80, 255))
    # Vein
    draw.line((cx, int(top_y), cx, int(bot_y)), fill=(70, 110, 50, 220), width=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------- REGISTRY ----------

_PROC_TEXTURES: dict[str, callable] = {
    "oak_bark": oak_bark_png,
    "pine_bark": pine_bark_png,
    "birch_bark": birch_bark_png,
    "oak_leaf": oak_leaf_png,
    "pine_needle": pine_needle_png,
    "birch_leaf": birch_leaf_png,
}
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/geom/test_textures.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/geom/_textures.py tests/geom/test_textures.py
git commit -m "feat(geom): procedural bark + leaf textures for oak/pine/birch"
```

---

## Task 6: Resolve `proc:<name>` scheme in builder

**Files:**
- Modify: `src/palubicki/geom/builder.py` (replace `_load_*_texture` with `_resolve_texture`)
- Test: `tests/geom/test_proc_scheme.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/geom/test_proc_scheme.py`:

```python
from pathlib import Path

import pytest

from palubicki.config import (
    Config, ConfigError, EnvelopeConfig, GeomConfig, LightConfig,
    PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.geom.builder import build_mesh, _resolve_texture
from palubicki.sim.simulator import simulate


def _tree(out):
    return simulate(Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.5, ry=1.0, rz=0.5, marker_count=200),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_iterations=4),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        seed=1, output=out,
    ))


def test_resolve_none_returns_none():
    assert _resolve_texture(None) is None


def test_resolve_proc_scheme_returns_bytes():
    png = _resolve_texture("proc:oak_bark")
    assert isinstance(png, bytes) and len(png) > 100


def test_resolve_proc_unknown_raises_configerror():
    with pytest.raises(ConfigError, match="unknown proc texture"):
        _resolve_texture("proc:not_a_real_texture")


def test_resolve_path_reads_file(tmp_path):
    from PIL import Image
    p = tmp_path / "x.png"
    Image.new("RGB", (4, 4), (1, 2, 3)).save(p)
    assert _resolve_texture(p) == p.read_bytes()
    assert _resolve_texture(str(p)) == p.read_bytes()


def test_build_mesh_with_proc_bark_attaches_texture(tmp_path):
    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.5, ry=1.0, rz=0.5, marker_count=200),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_iterations=4),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(bark_texture=Path("proc:oak_bark")),
        seed=1, output=tmp_path / "x.glb",
    )
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    assert mesh.primitives[0].material.base_color_texture_png is not None
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/geom/test_proc_scheme.py -v
```

Expected: FAIL — `_resolve_texture` does not exist.

- [ ] **Step 3: Implement `_resolve_texture` in builder.py**

In `src/palubicki/geom/builder.py`, replace the file content:

```python
from __future__ import annotations

from pathlib import Path

from palubicki.config import Config, ConfigError
from palubicki.geom._textures import _PROC_TEXTURES, default_leaf_png
from palubicki.geom.leaves import build_leaves_primitive
from palubicki.geom.mesh import Material, Mesh
from palubicki.geom.radii import compute_radii
from palubicki.geom.tubes import build_bark_primitive
from palubicki.sim.tree import Tree


def build_mesh(tree: Tree, cfg: Config) -> Mesh:
    compute_radii(tree, r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent)

    bark_png = _resolve_texture(cfg.geom.bark_texture)
    bark_mat = Material(
        name="bark",
        base_color=(*cfg.geom.bark_color, 1.0),
        metallic=0.0,
        roughness=0.9,
        base_color_texture_png=bark_png,
        alpha_mode="OPAQUE",
        alpha_cutoff=0.5,
        double_sided=False,
    )
    bark_prim = build_bark_primitive(tree, ring_sides=cfg.geom.ring_sides, material=bark_mat)
    primitives = [bark_prim]

    if cfg.geom.enable_leaves:
        leaf_png = _resolve_texture(cfg.geom.leaf_texture)
        if leaf_png is None:
            leaf_png = default_leaf_png()
        leaf_mat = Material(
            name="leaf",
            base_color=(0.4, 0.6, 0.2, 1.0),
            metallic=0.0,
            roughness=0.85,
            base_color_texture_png=leaf_png,
            alpha_mode="MASK",
            alpha_cutoff=0.5,
            double_sided=True,
        )
        leaf_prim = build_leaves_primitive(
            tree,
            leaf_size=cfg.geom.leaf_size,
            material=leaf_mat,
            cluster_count=cfg.geom.leaf_cluster_count,
            aspect=cfg.geom.leaf_aspect,
            splay_deg=cfg.geom.leaf_splay_deg,
        )
        primitives.append(leaf_prim)

    return Mesh(primitives=primitives)


def _resolve_texture(value) -> bytes | None:
    if value is None:
        return None
    s = str(value)
    if s.startswith("proc:"):
        name = s[5:]
        if name not in _PROC_TEXTURES:
            raise ConfigError(
                f"unknown proc texture: {name!r} (expected one of {sorted(_PROC_TEXTURES)})"
            )
        return _PROC_TEXTURES[name]()
    return Path(s).read_bytes()
```

Note: the old `_load_bark_texture` and `_load_leaf_texture` are removed — `_resolve_texture` replaces both.

- [ ] **Step 4: Run all tests including goldens**

```bash
.venv/bin/pytest tests/geom/test_proc_scheme.py -v
.venv/bin/pytest -m "not slow" -x
.venv/bin/pytest -m slow tests/golden/ -v
```

Expected: PASS. Goldens unchanged (bark_texture default is None → no texture, leaf_texture default is None → still uses default_leaf_png).

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/geom/builder.py tests/geom/test_proc_scheme.py
git commit -m "feat(geom): proc:<name> scheme for procedural textures"
```

---

## Task 7: Implement `_deep_merge`, `_load_packaged_species`, `_list_species`, and `load_config(species=...)`

**Files:**
- Modify: `src/palubicki/config.py` (add three helpers + extend `load_config`)
- Create: `src/palubicki/configs/__init__.py` (empty)
- Create: `src/palubicki/configs/species/__init__.py` (empty)
- Modify: `pyproject.toml` (include YAML files in wheel)
- Test: `tests/test_config_species.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_species.py`:

```python
from pathlib import Path

import pytest

from palubicki.config import ConfigError, _deep_merge, _list_species, load_config


def test_deep_merge_overrides_scalar_in_nested_dict():
    base = {"a": {"b": 1, "c": 2}}
    over = {"a": {"b": 99}}
    _deep_merge(base, over)
    assert base == {"a": {"b": 99, "c": 2}}


def test_deep_merge_replaces_list_completely():
    base = {"a": [1, 2, 3]}
    over = {"a": [9]}
    _deep_merge(base, over)
    assert base == {"a": [9]}


def test_deep_merge_adds_new_key():
    base = {"a": 1}
    over = {"b": 2}
    _deep_merge(base, over)
    assert base == {"a": 1, "b": 2}


def test_deep_merge_does_not_recurse_when_base_is_not_dict():
    base = {"a": 1}
    over = {"a": {"b": 2}}
    _deep_merge(base, over)
    assert base == {"a": {"b": 2}}


def test_list_species_returns_sorted_names():
    names = _list_species()
    # At minimum, the three V4 species (created in Task 8 — this test will pass after Task 8)
    # For Task 7, we just verify the function works without crashing on the empty package.
    assert isinstance(names, list)
    assert all(isinstance(n, str) for n in names)


def test_unknown_species_raises(tmp_path):
    with pytest.raises(ConfigError, match="unknown species preset"):
        load_config(
            yaml_path=None,
            cli_overrides={},
            output=tmp_path / "x.glb",
            species="redwood",
        )
```

- [ ] **Step 2: Create the `configs` package skeleton**

Create empty file `src/palubicki/configs/__init__.py`:

```bash
mkdir -p src/palubicki/configs/species
touch src/palubicki/configs/__init__.py
touch src/palubicki/configs/species/__init__.py
```

- [ ] **Step 3: Add a YAML inclusion rule in pyproject.toml**

In `pyproject.toml`, replace the `[tool.hatch.build.targets.wheel]` block with:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/palubicki"]

[tool.hatch.build.targets.wheel.force-include]
"src/palubicki/configs/species" = "palubicki/configs/species"
```

This ensures `.yaml` files (not just `.py`) are packaged alongside the Python sources.

- [ ] **Step 4: Run failing tests**

```bash
.venv/bin/pytest tests/test_config_species.py -v
```

Expected: FAIL — `_deep_merge`, `_list_species`, `load_config(species=...)` don't exist.

- [ ] **Step 5: Implement the helpers and extend load_config**

In `src/palubicki/config.py`, after the existing `load_config` function, add:

```python
def _deep_merge(base: dict, override: dict) -> None:
    """Merge `override` into `base` in-place. Recursive on dict-vs-dict; otherwise replace."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _load_packaged_species(name: str) -> dict:
    from importlib import resources
    try:
        text = (
            resources.files("palubicki.configs.species")
            .joinpath(f"{name}.yaml")
            .read_text()
        )
    except (FileNotFoundError, ModuleNotFoundError, AttributeError) as e:
        raise ConfigError(f"unknown species preset: {name!r}") from e
    return yaml.safe_load(text) or {}


def _list_species() -> list[str]:
    from importlib import resources
    try:
        files = resources.files("palubicki.configs.species").iterdir()
    except (FileNotFoundError, ModuleNotFoundError):
        return []
    return sorted(f.stem for f in files if f.name.endswith(".yaml"))
```

Then modify the `load_config` signature and body — replace the existing function:

```python
def load_config(
    *,
    yaml_path: Path | None,
    cli_overrides: dict,
    output: Path,
    species: str | None = None,
) -> Config:
    data: dict = {}
    if species is not None:
        data = _load_packaged_species(species)

    if yaml_path is not None:
        with open(yaml_path) as f:
            user = yaml.safe_load(f) or {}
        _deep_merge(data, user)

    for dotted, value in cli_overrides.items():
        _set_dotted(data, dotted, value)

    sections = {}
    section_field_names = set(_SECTION_TYPES.keys()) | {"forest"}
    top_field_names = {f.name for f in fields(Config)}

    for name, type_ in _SECTION_TYPES.items():
        sec_data = data.get(name, {}) or {}
        allowed = {f.name for f in fields(type_)}
        unknown = set(sec_data) - allowed
        if unknown:
            raise ConfigError(f"unknown keys in section '{name}': {sorted(unknown)}")
        sections[name] = type_(**sec_data)

    if "forest" in data:
        sections["forest"] = _load_forest_config(data["forest"])

    top_kwargs = {k: v for k, v in data.items() if k not in section_field_names and k in top_field_names}
    unknown_top = set(data) - section_field_names - top_field_names
    if unknown_top:
        raise ConfigError(f"unknown top-level keys: {sorted(unknown_top)}")

    if "output" in cli_overrides:
        top_kwargs["output"] = Path(cli_overrides["output"])
    else:
        top_kwargs.setdefault("output", output)

    return Config(**sections, **top_kwargs)
```

- [ ] **Step 6: Reinstall in editable mode and run tests**

The new `configs` subpackage must be picked up by the editable install (force-include may require a refresh):

```bash
.venv/bin/pip install -e . --quiet
.venv/bin/pytest tests/test_config_species.py -v
.venv/bin/pytest -m "not slow" -x
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/config.py src/palubicki/configs/ pyproject.toml tests/test_config_species.py
git commit -m "feat(config): packaged-preset loader (--species) + deep merge"
```

---

## Task 8: Create the three preset YAMLs

**Files:**
- Create: `src/palubicki/configs/species/oak.yaml`
- Create: `src/palubicki/configs/species/pine.yaml`
- Create: `src/palubicki/configs/species/birch.yaml`
- Test: `tests/test_config_species.py` (extend)

- [ ] **Step 1: Write the failing extension tests**

Append to `tests/test_config_species.py`:

```python
def test_list_species_finds_three():
    names = _list_species()
    assert set(names) == {"oak", "pine", "birch"}


def test_load_preset_oak(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="oak")
    assert cfg.envelope.shape == "half_ellipsoid"
    assert cfg.geom.leaf_cluster_count == 1
    assert cfg.geom.bark_texture == Path("proc:oak_bark") or str(cfg.geom.bark_texture) == "proc:oak_bark"


def test_load_preset_pine(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="pine")
    assert cfg.envelope.shape == "cone"
    assert cfg.phyllotaxy.mode == "whorled"
    assert cfg.geom.leaf_cluster_count == 5


def test_load_preset_birch(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="birch")
    assert cfg.envelope.shape == "ellipsoid"
    assert cfg.tropism.w_gravity == pytest.approx(0.45)


def test_user_yaml_overrides_preset(tmp_path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text("tropism:\n  w_gravity: 0.99\n")
    cfg = load_config(yaml_path=user_yaml, cli_overrides={},
                      output=tmp_path / "x.glb", species="oak")
    assert cfg.tropism.w_gravity == pytest.approx(0.99)
    # other oak values unchanged
    assert cfg.envelope.shape == "half_ellipsoid"
    assert cfg.geom.leaf_cluster_count == 1


def test_cli_override_wins_over_user_yaml(tmp_path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text("tropism:\n  w_gravity: 0.5\n")
    cfg = load_config(yaml_path=user_yaml,
                      cli_overrides={"tropism.w_gravity": 0.1},
                      output=tmp_path / "x.glb", species="oak")
    assert cfg.tropism.w_gravity == pytest.approx(0.1)


def test_deep_merge_preserves_sibling_sections(tmp_path):
    """User YAML touching only `tropism` must not erase preset's `envelope` or `phyllotaxy`."""
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text("tropism:\n  w_gravity: 0.3\n")
    cfg = load_config(yaml_path=user_yaml, cli_overrides={},
                      output=tmp_path / "x.glb", species="pine")
    assert cfg.envelope.shape == "cone"  # from pine preset
    assert cfg.phyllotaxy.mode == "whorled"  # from pine preset
    assert cfg.geom.leaf_cluster_count == 5  # from pine preset
    assert cfg.tropism.w_gravity == pytest.approx(0.3)  # from user yaml
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/test_config_species.py -v
```

Expected: FAIL — preset YAMLs don't exist.

- [ ] **Step 3: Create `oak.yaml`**

Create `src/palubicki/configs/species/oak.yaml`:

```yaml
# Quercus robur — dense, étalé, ramure tortueuse
envelope:
  shape: half_ellipsoid
  rx: 5.0
  ry: 6.5
  rz: 5.0
  marker_count: 25000
sim:
  internode_length: 0.12
  lambda_apical: 0.50
  alpha_basipetal: 2.2
  max_iterations: 35
tropism:
  w_gravity: 0.25
  w_phototropism: 0.35
  w_direction_inertia: 0.5
phyllotaxy:
  mode: alternate
  divergence_angle_deg: 137.5
  branch_angle_deg: 55
shedding:
  quality_threshold: 0.15
light:
  enabled: true
  k_absorption: 0.55
geom:
  ring_sides: 10
  pipe_exponent: 2.55
  bark_color: [0.32, 0.22, 0.14]
  bark_texture: "proc:oak_bark"
  leaf_texture: "proc:oak_leaf"
  leaf_size: 0.10
  leaf_cluster_count: 1
  leaf_aspect: 1.0
  leaf_splay_deg: 0
```

- [ ] **Step 4: Create `pine.yaml`**

Create `src/palubicki/configs/species/pine.yaml`:

```yaml
# Pinus sylvestris — conifère conique, étages réguliers, apical dominant
envelope:
  shape: cone
  rx: 2.5
  ry: 9.0
  rz: 2.5
  marker_count: 18000
sim:
  internode_length: 0.18
  lambda_apical: 0.85
  alpha_basipetal: 1.8
  max_iterations: 40
tropism:
  w_gravity: 0.15
  w_phototropism: 0.20
  w_direction_inertia: 0.8
phyllotaxy:
  mode: whorled
  whorl_count: 5
  divergence_angle_deg: 72
  branch_angle_deg: 75
shedding:
  quality_threshold: 0.20
light:
  enabled: true
  k_absorption: 0.65
geom:
  ring_sides: 8
  pipe_exponent: 2.45
  bark_color: [0.45, 0.25, 0.18]
  bark_texture: "proc:pine_bark"
  leaf_texture: "proc:pine_needle"
  leaf_size: 0.08
  leaf_cluster_count: 5
  leaf_aspect: 0.12
  leaf_splay_deg: 25
```

- [ ] **Step 5: Create `birch.yaml`**

Create `src/palubicki/configs/species/birch.yaml`:

```yaml
# Betula pendula — élancé, branches fines, port pleureur léger
envelope:
  shape: ellipsoid
  rx: 2.5
  ry: 7.0
  rz: 2.5
  marker_count: 20000
sim:
  internode_length: 0.10
  lambda_apical: 0.65
  alpha_basipetal: 2.0
  max_iterations: 32
tropism:
  w_gravity: 0.45
  w_phototropism: 0.30
  w_direction_inertia: 0.35
phyllotaxy:
  mode: alternate
  divergence_angle_deg: 137.5
  branch_angle_deg: 45
shedding:
  quality_threshold: 0.10
light:
  enabled: true
  k_absorption: 0.45
geom:
  ring_sides: 8
  pipe_exponent: 2.40
  r_tip: 0.004
  bark_color: [0.85, 0.82, 0.75]
  bark_texture: "proc:birch_bark"
  leaf_texture: "proc:birch_leaf"
  leaf_size: 0.07
  leaf_cluster_count: 2
  leaf_aspect: 0.7
  leaf_splay_deg: 15
```

- [ ] **Step 6: Run tests**

```bash
.venv/bin/pip install -e . --quiet
.venv/bin/pytest tests/test_config_species.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/configs/species/oak.yaml src/palubicki/configs/species/pine.yaml src/palubicki/configs/species/birch.yaml tests/test_config_species.py
git commit -m "feat(config): oak/pine/birch species preset YAMLs"
```

---

## Task 9: Wire `--species` flag into the CLI `generate` subcommand

**Files:**
- Modify: `src/palubicki/cli.py` (add `--species` to `generate`, pass it to `load_config`)
- Test: `tests/test_cli.py` (extend with smoke tests)

- [ ] **Step 1: Write the failing CLI smoke tests**

Append to `tests/test_cli.py`:

```python
@pytest.mark.slow
@pytest.mark.parametrize("species", ["oak", "pine", "birch"])
def test_generate_species_creates_valid_glb(tmp_path, species):
    out = tmp_path / f"{species}.glb"
    res = _run("generate", "--species", species, "--seed", "42",
               "--marker-count", "500",      # speed up
               "--iterations", "8",          # speed up
               "-o", str(out))
    assert res.returncode == 0, res.stderr
    assert out.exists()
    loaded = pygltflib.GLTF2().load(str(out))
    assert len(loaded.meshes) == 1
    assert len(loaded.meshes[0].primitives) >= 2  # bark + leaves
    # Bark texture should be present (proc:<species>_bark)
    assert len(loaded.textures) >= 1


def test_species_unknown_exits_2(tmp_path):
    res = _run("generate", "--species", "redwood", "-o", str(tmp_path / "x.glb"))
    assert res.returncode != 0
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/test_cli.py::test_species_unknown_exits_2 -v
```

Expected: FAIL — `--species` is not a known argparse option.

- [ ] **Step 3: Add `--species` to the `generate` parser**

In `src/palubicki/cli.py`, inside `_build_parser`, locate the `generate` subparser (line 42 area) and add **before** `sub.add_parser("dump-defaults", ...)`:

```python
    from palubicki.config import _list_species
    species_choices = _list_species()
    g.add_argument("--species", choices=species_choices if species_choices else None,
                   default=None,
                   help=f"Load a packaged species preset (choices: {', '.join(species_choices) if species_choices else 'none'})")
```

- [ ] **Step 4: Forward `--species` to `load_config` in `_cmd_generate`**

In `src/palubicki/cli.py`, locate the `cfg = load_config(...)` call in `_cmd_generate` and change it to:

```python
    try:
        cfg = load_config(
            yaml_path=args.config,
            cli_overrides=overrides,
            output=args.output,
            species=args.species,
        )
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
```

- [ ] **Step 5: Run all CLI tests**

```bash
.venv/bin/pytest tests/test_cli.py -v -m "not slow"
.venv/bin/pytest tests/test_cli.py::test_species_unknown_exits_2 -v
.venv/bin/pytest tests/test_cli.py -v -m slow -k "species"
```

Expected: PASS. The slow species smoke tests may take a few seconds (3 species × small marker count).

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/cli.py tests/test_cli.py
git commit -m "feat(cli): --species flag for packaged presets (oak/pine/birch)"
```

---

## Task 10: `dump-defaults --species <name>` prints a preset

**Files:**
- Modify: `src/palubicki/cli.py` (add `--species` to `dump-defaults`)
- Test: `tests/test_cli.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_dump_defaults_species_oak_prints_preset_yaml():
    res = _run("dump-defaults", "--species", "oak")
    assert res.returncode == 0
    data = yaml.safe_load(res.stdout)
    assert data["envelope"]["shape"] == "half_ellipsoid"
    assert data["geom"]["bark_texture"] == "proc:oak_bark"
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/test_cli.py::test_dump_defaults_species_oak_prints_preset_yaml -v
```

Expected: FAIL — `--species` is not recognized by `dump-defaults`.

- [ ] **Step 3: Extend `dump-defaults` parser and command**

In `src/palubicki/cli.py`, change:

```python
    sub.add_parser("dump-defaults", help="Print full default config as YAML")
```

to:

```python
    dd = sub.add_parser("dump-defaults", help="Print full default config as YAML")
    dd.add_argument("--species", default=None,
                    help="Print the packaged preset for this species instead of generic defaults")
```

Then modify `_cmd_dump_defaults`:

```python
def _cmd_dump_defaults(args) -> int:
    if args.species is not None:
        from palubicki.config import _load_packaged_species
        try:
            data = _load_packaged_species(args.species)
        except ConfigError as e:
            print(f"config error: {e}", file=sys.stderr)
            return 2
        yaml.safe_dump(data, sys.stdout, sort_keys=False)
        return 0

    default = Config(
        envelope=EnvelopeConfig(),
        sim=SimConfig(),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        output=Path("tree.glb"),
    )
    yaml.safe_dump(_config_to_dict(default), sys.stdout, sort_keys=False)
    return 0
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_cli.py -v -m "not slow"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/cli.py tests/test_cli.py
git commit -m "feat(cli): dump-defaults --species prints packaged preset"
```

---

## Task 11: Add `species` field to `ForestSeed` and apply preset in `per_tree_config`

**Files:**
- Modify: `src/palubicki/config.py` (add `species` to `ForestSeed`, extend `_load_forest_seed`)
- Modify: `src/palubicki/sim/forest.py` (`per_tree_config` honors species)
- Test: `tests/sim/test_forest_species.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_forest_species.py`:

```python
from pathlib import Path

import pytest

from palubicki.config import (
    Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig,
    LightConfig, PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
    load_config,
)
from palubicki.sim.forest import per_tree_config


def _bare_cfg(tmp_path) -> Config:
    return Config(
        envelope=EnvelopeConfig(),
        sim=SimConfig(),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        output=tmp_path / "x.glb",
        seed=0,
    )


def test_forest_seed_accepts_species_field():
    s = ForestSeed(position=(0.0, 0.0, 0.0), species="oak")
    assert s.species == "oak"


def test_per_tree_config_applies_oak_preset(tmp_path):
    cfg = _bare_cfg(tmp_path)
    seed_entry = ForestSeed(position=(0.0, 0.0, 0.0), species="oak")
    derived = per_tree_config(cfg, seed_entry, tree_index=0)
    # Oak preset values
    assert derived.envelope.shape == "half_ellipsoid"
    assert derived.envelope.rx == pytest.approx(5.0)
    assert derived.phyllotaxy.branch_angle_deg == pytest.approx(55.0)
    # Envelope center is still translated to seed position
    assert derived.envelope.center == (0.0, 0.0, 0.0)


def test_per_tree_config_overrides_win_over_species(tmp_path):
    cfg = _bare_cfg(tmp_path)
    seed_entry = ForestSeed(
        position=(0.0, 0.0, 0.0),
        species="oak",
        overrides={"tropism.w_gravity": 0.99},
    )
    derived = per_tree_config(cfg, seed_entry, tree_index=0)
    assert derived.tropism.w_gravity == pytest.approx(0.99)
    assert derived.envelope.shape == "half_ellipsoid"  # oak preserved


def test_yaml_forest_with_species_per_seed_parses(tmp_path):
    yaml_path = tmp_path / "forest.yaml"
    yaml_path.write_text("""
envelope:
  marker_count: 500
sim:
  max_iterations: 4
forest:
  seeds:
    - position: [0.0, 0.0, 0.0]
      species: oak
    - position: [10.0, 0.0, 0.0]
      species: pine
""")
    cfg = load_config(yaml_path=yaml_path, cli_overrides={},
                      output=tmp_path / "x.glb")
    assert len(cfg.forest.seeds) == 2
    assert cfg.forest.seeds[0].species == "oak"
    assert cfg.forest.seeds[1].species == "pine"
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/sim/test_forest_species.py -v
```

Expected: FAIL — `ForestSeed` doesn't have `species`.

- [ ] **Step 3: Add `species` to `ForestSeed`**

In `src/palubicki/config.py`, modify `ForestSeed`:

```python
@dataclass(frozen=True)
class ForestSeed:
    position: tuple[float, float, float]
    seed: int | None = None
    species: str | None = None
    overrides: dict = field(default_factory=dict)
```

And extend `_load_forest_seed`:

```python
def _load_forest_seed(d: dict) -> "ForestSeed":
    if not isinstance(d, dict):
        raise ConfigError(f"forest seed must be a dict, got {type(d).__name__}")
    allowed = {"position", "seed", "species", "overrides"}
    unknown = set(d) - allowed
    if unknown:
        raise ConfigError(f"unknown keys in forest seed: {sorted(unknown)}")
    if "position" not in d:
        raise ConfigError("forest seed missing 'position'")
    return ForestSeed(
        position=tuple(d["position"]),
        seed=d.get("seed"),
        species=d.get("species"),
        overrides=dict(d.get("overrides") or {}),
    )
```

- [ ] **Step 4: Honor `species` in `per_tree_config`**

In `src/palubicki/sim/forest.py`, replace the `per_tree_config` function:

```python
def per_tree_config(cfg: Config, seed_entry: ForestSeed, tree_index: int) -> Config:
    """Return a new Config: cfg with species preset (if any) + seed_entry.overrides
    applied (dotted keys) and envelope.center translated to seed_entry.position."""
    # Start from the species preset if requested; otherwise from cfg
    if seed_entry.species is not None:
        from palubicki.config import _load_packaged_species, _deep_merge, _SECTION_TYPES
        from dataclasses import fields as _fields

        preset = _load_packaged_species(seed_entry.species)
        # Build a section-by-section new Config by merging preset onto cfg's sections
        new_sections: dict = {}
        for section_name, type_ in _SECTION_TYPES.items():
            cur_section = getattr(cfg, section_name)
            cur_dict = {f.name: getattr(cur_section, f.name) for f in _fields(type_)}
            preset_section = preset.get(section_name, {}) or {}
            allowed = {f.name for f in _fields(type_)}
            unknown = set(preset_section) - allowed
            if unknown:
                raise ConfigError(f"unknown keys in species preset section '{section_name}': {sorted(unknown)}")
            cur_dict.update(preset_section)
            new_sections[section_name] = type_(**cur_dict)
    else:
        new_sections = {s: getattr(cfg, s) for s in _SECTION_FIELDS}

    # Apply seed_entry.overrides (dotted keys) on top
    section_updates: dict[str, dict] = {s: {} for s in _SECTION_FIELDS}
    top_updates: dict[str, object] = {}
    for dotted, value in seed_entry.overrides.items():
        parts = dotted.split(".", 1)
        if len(parts) == 1:
            top_updates[parts[0]] = value
        else:
            section, key = parts
            if section not in _SECTION_FIELDS:
                raise ConfigError(f"unknown section in override: {dotted!r}")
            section_updates[section][key] = value

    for s in _SECTION_FIELDS:
        if section_updates[s]:
            new_sections[s] = replace(new_sections[s], **section_updates[s])

    # Translate envelope center to seed position (after overrides, so explicit
    # envelope.center in overrides wins if user did that)
    if "envelope.center" not in seed_entry.overrides:
        new_sections["envelope"] = replace(new_sections["envelope"], center=tuple(seed_entry.position))

    derived_seed = seed_entry.seed if seed_entry.seed is not None else (cfg.seed + tree_index)

    return Config(
        envelope=new_sections["envelope"],
        sim=new_sections["sim"],
        tropism=new_sections["tropism"],
        phyllotaxy=new_sections["phyllotaxy"],
        shedding=new_sections["shedding"],
        geom=new_sections["geom"],
        light=new_sections["light"],
        forest=cfg.forest,
        seed=top_updates.get("seed", derived_seed),
        output=cfg.output,
        log_level=cfg.log_level,
    )
```

You may need to import `ConfigError` at the top of `forest.py`:

```python
from palubicki.config import Config, ConfigError, EnvelopeConfig, ForestSeed
```

- [ ] **Step 5: Run tests including V3 forest goldens**

```bash
.venv/bin/pytest tests/sim/test_forest_species.py -v
.venv/bin/pytest -m "not slow" -x
.venv/bin/pytest -m slow tests/golden/test_goldens.py::test_golden_forest_v3 -v
```

Expected: PASS. **V3 forest golden must stay unchanged** (no seeds have `species` set, so `per_tree_config` takes the `else` branch identical to the prior behavior).

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/config.py src/palubicki/sim/forest.py tests/sim/test_forest_species.py
git commit -m "feat(sim): ForestSeed.species + per_tree_config applies preset"
```

---

## Task 12: Pin golden hashes for the three species

**Files:**
- Create: `tests/golden/test_species_goldens.py`
- Create: `tests/golden/data/species_oak.sha256` (auto-generated via --update-goldens)
- Create: `tests/golden/data/species_pine.sha256`
- Create: `tests/golden/data/species_birch.sha256`

- [ ] **Step 1: Write the golden test**

Create `tests/golden/test_species_goldens.py`:

```python
import hashlib
from pathlib import Path

import pygltflib
import pytest

from palubicki.cli import main


GOLDEN_DIR = Path(__file__).parent / "data"
pytestmark = pytest.mark.slow


def _hash_buffers(glb_path: Path) -> str:
    """Hash all primitive buffer data (positions, normals, uvs, indices) for stability
    across runs that share the same simulation output."""
    loaded = pygltflib.GLTF2().load(str(glb_path))
    sha = hashlib.sha256()
    for mesh in loaded.meshes:
        for prim in mesh.primitives:
            for acc_idx in (prim.attributes.POSITION, prim.attributes.NORMAL,
                            prim.attributes.TEXCOORD_0, prim.indices):
                if acc_idx is None:
                    continue
                acc = loaded.accessors[acc_idx]
                bv = loaded.bufferViews[acc.bufferView]
                blob = loaded.binary_blob()[bv.byteOffset : bv.byteOffset + bv.byteLength]
                sha.update(blob)
    return sha.hexdigest()


@pytest.mark.parametrize("species", ["oak", "pine", "birch"])
def test_species_golden(tmp_path, update_goldens, species):
    out = tmp_path / f"{species}.glb"
    # Use reduced marker_count and iterations for golden stability + speed.
    # Tuning of the *visual* presets is independent — these hashes pin reproducibility
    # of the (preset + small overrides) combination used here.
    rc = main([
        "generate", "--species", species,
        "--seed", "42",
        "--marker-count", "1000",
        "--iterations", "10",
        "-o", str(out),
    ])
    assert rc == 0

    h = _hash_buffers(out)
    golden = GOLDEN_DIR / f"species_{species}.sha256"
    if update_goldens or not golden.exists():
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden.write_text(h)
        pytest.skip(f"golden written for {species}; re-run without --update-goldens to verify")

    expected = golden.read_text().strip()
    assert h == expected, (
        f"golden mismatch for {species}.\nexpected: {expected}\nactual:   {h}\n"
        f"if intentional (after preset tuning), re-run with --update-goldens after visual review"
    )
```

- [ ] **Step 2: Generate the initial golden files**

```bash
.venv/bin/pytest tests/golden/test_species_goldens.py -v --update-goldens
```

Expected: All three tests SKIP with message "golden written…". Three files appear in `tests/golden/data/`:
- `species_oak.sha256`
- `species_pine.sha256`
- `species_birch.sha256`

- [ ] **Step 3: Re-run without --update-goldens to verify pinning**

```bash
.venv/bin/pytest tests/golden/test_species_goldens.py -v
```

Expected: All three tests PASS.

- [ ] **Step 4: Run the full slow suite to confirm no regressions in V1/V2/V3 goldens**

```bash
.venv/bin/pytest -m slow -v
```

Expected: All slow tests PASS, including the existing `test_golden_ellipsoid`, `test_golden_ellipsoid_light`, and `test_golden_forest_v3`.

If any V1/V2/V3 golden fails, **STOP**. That indicates the leaf cluster refactor (Task 3) broke bit-exact compatibility. Most likely culprits: change to `half_u`/`half_v` semantics, change to indexing arithmetic, or a different traversal order over `surviving` buds. Compare the new `_emit_leaf_cluster` against the original `_emit_cross_quad` line-by-line for the `cluster_count=1, splay=0, aspect=1` path.

- [ ] **Step 5: Commit**

```bash
git add tests/golden/test_species_goldens.py tests/golden/data/species_oak.sha256 tests/golden/data/species_pine.sha256 tests/golden/data/species_birch.sha256
git commit -m "test(golden): pin V4 species hashes (oak, pine, birch)"
```

---

## Task 13: Update README — V4 section + roadmap status

**Files:**
- Modify: `README.md` (add V4 section, mark roadmap entry as done)

- [ ] **Step 1: Add a V4 section to README**

In `README.md`, after the existing V2 section (around line 53) and before "## Tuning notes" (line 54), insert:

```markdown
### V3 — obstacles + forêt multi-arbres

Subcommand `palubicki forest -o scene.glb --config scene.yaml`. The YAML adds a
top-level `forest:` section with multiple seeds (each with its own position,
optional `seed`, `species`, and dotted-key `overrides`) and a list of
obstacles (AABB, Sphere, OBB, Mesh OBJ). Trees compete on a shared marker
cloud and a shared light grid; obstacles kill markers, block growth segments,
and occlude light.

### V4 — species presets

Three packaged presets: `oak`, `pine`, `birch`. Each is a YAML in
`src/palubicki/configs/species/` selected with the `--species` flag.

```bash
palubicki generate --species oak --seed 42 -o oak.glb
palubicki generate --species pine --seed 42 -o pine.glb
palubicki generate --species birch --seed 42 -o birch.glb

# Override a preset value (CLI wins over YAML wins over preset)
palubicki generate --species oak --w-gravity 0.5 -o oak_droopy.glb

# Dump a preset to a file as starting point for a custom species
palubicki dump-defaults --species pine > my_pine.yaml
```

Forêts mixtes : ajouter `species: oak` (ou `pine`/`birch`) à chaque entrée
`forest.seeds` du YAML pour appliquer le preset à cet arbre, puis appliquer
les `overrides` par-dessus.

Textures bark + leaf : générateurs procéduraux PIL packagés sous l'URI
`proc:<name>` (e.g. `bark_texture: "proc:oak_bark"`). Pointer vers un PNG
externe reste possible : `bark_texture: ./my_bark.png`.
```

Also update the "Roadmap" section: change

```
- **V4** : species presets (apple, oak, pine, willow, birch) reproducing Fig. 12.
```

to

```
- ~~**V4** : species presets (oak, pine, birch) — livré~~. Apple, willow, weeping ash reportés (saule en particulier nécessite un tropisme de poids non implémenté).
```

- [ ] **Step 2: Run a basic sanity check**

```bash
.venv/bin/python -c "import yaml; from pathlib import Path; print('README ok')"
```

(Just confirms Python still works; the README is documentation only.)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): V4 species presets section + roadmap update"
```

---

## Final validation

After Task 13, run the full test suite end-to-end:

- [ ] **All tests (fast + slow):**

```bash
.venv/bin/pytest -v
```

Expected: Everything passes. No skipped goldens (all V1/V2/V3/V4 hashes pinned and stable).

- [ ] **Sanity invocations on the three species:**

```bash
mkdir -p out
.venv/bin/palubicki generate --species oak --seed 42 -o out/oak.glb
.venv/bin/palubicki generate --species pine --seed 42 -o out/pine.glb
.venv/bin/palubicki generate --species birch --seed 42 -o out/birch.glb
ls -lh out/oak.glb out/pine.glb out/birch.glb
```

Expected: three `.glb` files produced, none zero-sized. Open each in Quick Look (`open out/oak.glb`) or drag into https://gltf-viewer.donmccurdy.com/ to do the qualitative visual check against Figure 12 criteria:

- **Oak** : silhouette ronde large, branches tortueuses étalées, feuillage dense en touffe.
- **Pine** : cône, étages de branches horizontales bien marqués, flèche apicale visible.
- **Birch** : silhouette élancée verticale, tronc clair, branches légèrement retombantes.

If visual tuning of the preset values is needed (almost certain on first pass), edit the YAML, re-run, and once satisfied:

```bash
.venv/bin/pytest tests/golden/test_species_goldens.py --update-goldens
git add src/palubicki/configs/species/<changed>.yaml tests/golden/data/species_*.sha256
git commit -m "tune(species): <species> preset adjustments + golden re-pin"
```

This visual-tuning loop is **expected** to produce additional commits after the architecture work is done. The 13 tasks above land the infrastructure; tuning is iterative content work that follows.
