# V2 BHls Hybrid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add voxel-based light shadowing (BHls) on top of V1's space competition (BHse). Q becomes `nb_markers × light_factor`. Light affects BH allocation, shedding, and adds local phototropism. `light.enabled=False` keeps V1 bit-exact.

**Architecture:** New `sim/light.py` (LightGrid: LAI grid + Beer-Lambert + hemispheric sampling) and `sim/light_perception.py` (per-bud orchestration). Extend `sim/tropisms.py` for local phototropism. `compute_radii` moved from `geom/radii.py` to `sim/radii.py` (needed during sim for internode LAI injection). `sim/simulator.py` orchestrates the new flow.

**Tech Stack:** Python 3.14, numpy, scipy (already used for kdtree), pytest, existing dataclass-based config.

**Spec:** `docs/superpowers/specs/2026-05-25-v2-bhls-hybrid-design.md`

**File structure:**
- CREATE `src/palubicki/sim/light.py` — LightGrid (data + rebuild + ray-march + hemispheric sampling)
- CREATE `src/palubicki/sim/light_perception.py` — perceive_light orchestration
- CREATE `src/palubicki/sim/radii.py` — moved `compute_radii` (was `geom/radii.py`)
- CREATE `tests/sim/test_light_grid.py` — unit tests for LightGrid
- CREATE `tests/sim/test_light_perception.py` — unit tests for perceive_light
- CREATE `tests/sim/test_radii_moved.py` — confirms move works (rename of existing geom test)
- CREATE `tests/integration/test_light_behavior.py` — V1 vs V2 silhouette comparison
- MODIFY `src/palubicki/config.py` — add LightConfig
- MODIFY `src/palubicki/sim/tropisms.py` — accept `light_gradient` kwarg
- MODIFY `src/palubicki/sim/simulator.py` — orchestrate light
- MODIFY `src/palubicki/geom/radii.py` — re-export from `sim/radii.py` (backward-compat shim)
- MODIFY `src/palubicki/cli.py` — `--light-enabled` and key tuning flags
- MODIFY `tests/sim/test_tropisms.py` — light_gradient cases
- MODIFY `tests/sim/test_simulator.py` — light enabled cases
- MODIFY `tests/integration/test_smoke.py` — one light case per envelope
- MODIFY `tests/golden/test_goldens.py` — new golden for light enabled
- MODIFY `tests/geom/test_radii.py` — update import path

---

## Task 1: Add LightConfig dataclass

**Files:**
- Modify: `src/palubicki/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_light_config_defaults():
    from palubicki.config import LightConfig
    c = LightConfig()
    assert c.enabled is False
    assert c.grid_origin is None
    assert c.grid_size is None
    assert c.grid_resolution == (64, 64, 64)
    assert c.k_absorption == 0.5
    assert c.leaf_area == 0.04
    assert c.internode_area_scale == 1.0
    assert c.n_rays == 16
    assert c.light_direction == (0.0, 1.0, 0.0)


def test_light_config_validation_rejects_zero_rays():
    from palubicki.config import ConfigError, LightConfig
    from palubicki.config import Config, EnvelopeConfig, SimConfig, TropismConfig, PhyllotaxyConfig, SheddingConfig, GeomConfig
    from pathlib import Path
    import pytest
    with pytest.raises(ConfigError, match="n_rays"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(),
            light=LightConfig(n_rays=0),
            output=Path("/tmp/x.glb"),
        )


def test_light_config_validation_rejects_negative_k_absorption():
    from palubicki.config import ConfigError, LightConfig
    from palubicki.config import Config, EnvelopeConfig, SimConfig, TropismConfig, PhyllotaxyConfig, SheddingConfig, GeomConfig
    from pathlib import Path
    import pytest
    with pytest.raises(ConfigError, match="k_absorption"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(),
            light=LightConfig(k_absorption=-0.1),
            output=Path("/tmp/x.glb"),
        )


def test_config_default_light_is_disabled():
    from palubicki.config import Config, EnvelopeConfig, SimConfig, TropismConfig, PhyllotaxyConfig, SheddingConfig, GeomConfig, LightConfig
    from pathlib import Path
    c = Config(
        envelope=EnvelopeConfig(), sim=SimConfig(), tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(), shedding=SheddingConfig(), geom=GeomConfig(),
        light=LightConfig(),
        output=Path("/tmp/x.glb"),
    )
    assert c.light.enabled is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config.py::test_light_config_defaults -v`
Expected: FAIL with `ImportError` (`LightConfig` not in `palubicki.config`).

- [ ] **Step 3: Add LightConfig dataclass to config.py**

Add after `SheddingConfig` in `src/palubicki/config.py`:

```python
@dataclass(frozen=True)
class LightConfig:
    enabled: bool = False
    grid_origin: tuple[float, float, float] | None = None
    grid_size: tuple[float, float, float] | None = None
    grid_resolution: tuple[int, int, int] = (64, 64, 64)
    k_absorption: float = 0.5
    leaf_area: float = 0.04
    internode_area_scale: float = 1.0
    n_rays: int = 16
    light_direction: tuple[float, float, float] = (0.0, 1.0, 0.0)
```

Then modify `Config`:

```python
@dataclass(frozen=True)
class Config:
    envelope: EnvelopeConfig
    sim: SimConfig
    tropism: TropismConfig
    phyllotaxy: PhyllotaxyConfig
    shedding: SheddingConfig
    geom: GeomConfig
    light: LightConfig = field(default_factory=LightConfig)
    seed: int = 0
    output: Path = field(default_factory=lambda: Path("tree.glb"))
    log_level: str = "INFO"
```

Add validation to `__post_init__` (just before the final `if not self.output.parent.exists()` check):

```python
        light = self.light
        if light.n_rays <= 0:
            raise ConfigError(f"light.n_rays must be > 0, got {light.n_rays}")
        if light.k_absorption < 0:
            raise ConfigError(f"light.k_absorption must be >= 0, got {light.k_absorption}")
        if light.leaf_area < 0:
            raise ConfigError(f"light.leaf_area must be >= 0, got {light.leaf_area}")
        if light.internode_area_scale < 0:
            raise ConfigError(f"light.internode_area_scale must be >= 0, got {light.internode_area_scale}")
        if any(r <= 0 for r in light.grid_resolution):
            raise ConfigError(f"light.grid_resolution must be all > 0, got {light.grid_resolution}")
```

Register in `_SECTION_TYPES`:

```python
_SECTION_TYPES = {
    "envelope": EnvelopeConfig,
    "sim": SimConfig,
    "tropism": TropismConfig,
    "phyllotaxy": PhyllotaxyConfig,
    "shedding": SheddingConfig,
    "geom": GeomConfig,
    "light": LightConfig,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: All pass, including existing config tests.

- [ ] **Step 5: Run full V1 test suite to confirm no regression**

Run: `.venv/bin/pytest -q`
Expected: All pre-existing tests pass (light config has `enabled=False` default → no behavior change).

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "feat(config): add LightConfig with defaults and validation"
```

---

## Task 2: Move compute_radii from geom/ to sim/

**Files:**
- Create: `src/palubicki/sim/radii.py`
- Modify: `src/palubicki/geom/radii.py` (becomes shim)
- Test: `tests/sim/test_radii.py` (new), `tests/geom/test_radii.py` (no change — still works via shim)

**Why:** `sim/light.py` needs `compute_radii` to compute internode lateral surface for LAI injection. Architecture rule "sim/ has no geom/ deps" forces moving the function.

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_radii.py`:

```python
import numpy as np

from palubicki.sim.radii import compute_radii
from palubicki.sim.tree import Internode, Node, Tree


def test_compute_radii_single_tip():
    """A tree with one internode → tip radius = r_tip; internode diameter = 2·r_tip."""
    root = Node(position=np.zeros(3))
    tip = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=root, child_node=tip, length=1.0, is_main_axis=True)
    root.children_internodes.append(iod)
    tree = Tree(root=root, all_internodes=[iod])

    compute_radii(tree, r_tip=0.01, exponent=2.0)

    assert iod.diameter == 0.02


def test_compute_radii_pipe_model_two_children():
    """Parent radius² = r_left² + r_right² (n=2). Both tips at r_tip = 0.1 → parent = sqrt(0.02) → diameter = 2·sqrt(0.02)."""
    root = Node(position=np.zeros(3))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    left = Node(position=np.array([-1.0, 2.0, 0.0]))
    right = Node(position=np.array([1.0, 2.0, 0.0]))
    iod_root_mid = Internode(parent_node=root, child_node=mid, length=1.0, is_main_axis=True)
    iod_mid_left = Internode(parent_node=mid, child_node=left, length=1.0, is_main_axis=False)
    iod_mid_right = Internode(parent_node=mid, child_node=right, length=1.0, is_main_axis=True)
    root.children_internodes.append(iod_root_mid)
    mid.children_internodes.extend([iod_mid_left, iod_mid_right])
    tree = Tree(root=root, all_internodes=[iod_root_mid, iod_mid_left, iod_mid_right])

    compute_radii(tree, r_tip=0.1, exponent=2.0)

    assert iod_mid_left.diameter == 0.2
    assert iod_mid_right.diameter == 0.2
    expected_parent_radius = (0.1**2 + 0.1**2) ** 0.5
    assert abs(iod_root_mid.diameter - 2.0 * expected_parent_radius) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/sim/test_radii.py -v`
Expected: FAIL with `ImportError` (`sim.radii` doesn't exist).

- [ ] **Step 3: Create sim/radii.py with the moved function**

Create `src/palubicki/sim/radii.py` (verbatim copy of current `geom/radii.py`):

```python
from __future__ import annotations

from palubicki.sim.tree import Internode, Node, Tree


def compute_radii(tree: Tree, *, r_tip: float, exponent: float) -> None:
    """Fill `internode.diameter` in-place using pipe model r^n = sum(r_child^n).

    Each internode's radius is determined by its child subtree:
    - tip (no descendant internodes): r_tip
    - otherwise: r = (Σ r_child^n)^(1/n) over the child node's outgoing internodes
    """
    for iod in tree.root.children_internodes:
        _set_radius_iterative(iod.child_node, iod, r_tip, exponent)


def _set_radius_iterative(root_node: Node, root_iod: Internode, r_tip: float, n: float) -> None:
    """Iterative post-order computation of radii using pipe model."""
    order: list[tuple[Node, Internode]] = []
    stack: list[tuple[Node, Internode]] = [(root_node, root_iod)]
    while stack:
        node, iod = stack.pop()
        order.append((node, iod))
        for child_iod in node.children_internodes:
            stack.append((child_iod.child_node, child_iod))
    radius: dict[int, float] = {}
    for node, iod in reversed(order):
        if not node.children_internodes:
            r = r_tip
        else:
            sum_pow = sum(radius[id(child_iod.child_node)] ** n for child_iod in node.children_internodes)
            r = sum_pow ** (1.0 / n)
        iod.diameter = 2.0 * r
        radius[id(node)] = r
```

Replace `src/palubicki/geom/radii.py` with a backward-compat shim:

```python
from palubicki.sim.radii import compute_radii  # noqa: F401
```

- [ ] **Step 4: Run all radii tests to verify everything still works**

Run: `.venv/bin/pytest tests/sim/test_radii.py tests/geom/test_radii.py -v`
Expected: All pass (new sim tests + existing geom tests via shim).

- [ ] **Step 5: Run full suite to confirm no regression**

Run: `.venv/bin/pytest -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/radii.py src/palubicki/geom/radii.py tests/sim/test_radii.py
git commit -m "refactor: move compute_radii from geom/ to sim/ (needed by sim/light.py)"
```

---

## Task 3: LightGrid skeleton — dataclass + world_to_cell + from_config

**Files:**
- Create: `src/palubicki/sim/light.py`
- Test: `tests/sim/test_light_grid.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_light_grid.py`:

```python
import numpy as np
import pytest

from palubicki.config import EnvelopeConfig, LightConfig
from palubicki.sim.light import LightGrid


def test_light_grid_explicit_bounds():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    env = EnvelopeConfig()
    grid = LightGrid.from_config(cfg, env)
    np.testing.assert_array_equal(grid.origin, np.array([0.0, 0.0, 0.0]))
    np.testing.assert_array_equal(grid.cell_size, np.array([1.0, 1.0, 1.0]))
    assert grid.resolution == (10, 10, 10)
    assert grid.lai.shape == (10, 10, 10)
    assert grid.lai.dtype == np.float32


def test_world_to_cell_basic():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    assert grid.world_to_cell(np.array([0.5, 0.5, 0.5])) == (0, 0, 0)
    assert grid.world_to_cell(np.array([5.5, 7.2, 1.1])) == (5, 7, 1)
    assert grid.world_to_cell(np.array([9.999, 9.999, 9.999])) == (9, 9, 9)


def test_world_to_cell_out_of_bounds_returns_none():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    assert grid.world_to_cell(np.array([-0.1, 0.0, 0.0])) is None
    assert grid.world_to_cell(np.array([10.1, 0.0, 0.0])) is None
    assert grid.world_to_cell(np.array([0.0, -1.0, 0.0])) is None


def test_cell_to_world_center():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    np.testing.assert_allclose(grid.cell_to_world_center(0, 0, 0), [0.5, 0.5, 0.5])
    np.testing.assert_allclose(grid.cell_to_world_center(5, 7, 1), [5.5, 7.5, 1.5])


def test_from_config_autofit_ellipsoid():
    """When origin/size are None, fit to envelope AABB with sky margin."""
    cfg = LightConfig(grid_origin=None, grid_size=None, grid_resolution=(16, 16, 16))
    env = EnvelopeConfig(shape="ellipsoid", rx=2.0, ry=3.0, rz=2.0, center=(0.0, 0.0, 0.0))
    grid = LightGrid.from_config(cfg, env)
    # AABB of ellipsoid centered at origin: [-2,2] × [-3,3] × [-2,2].
    # origin = aabb_min - 0.1 * extent = -2 - 0.4 = -2.4 etc.
    np.testing.assert_allclose(grid.origin, [-2.4, -3.6, -2.4], atol=1e-9)
    # extent = (4, 6, 4) ; size_y = 6 + 0.3*6 = 7.8 ; size_x = 4 + 0.2*4 = 4.8 ; size_z = 4.8
    np.testing.assert_allclose(grid.cell_size * np.array(cfg.grid_resolution), [4.8, 7.8, 4.8], atol=1e-9)


def test_from_config_autofit_half_ellipsoid_starts_at_y_zero():
    cfg = LightConfig(grid_origin=None, grid_size=None, grid_resolution=(16, 16, 16))
    env = EnvelopeConfig(shape="half_ellipsoid", rx=2.0, ry=3.0, rz=2.0, center=(0.0, 0.0, 0.0))
    grid = LightGrid.from_config(cfg, env)
    # AABB y starts at 0 (half above): y range [0, 3]
    # origin.y = 0 - 0.1 * 3 = -0.3
    np.testing.assert_allclose(grid.origin[1], -0.3, atol=1e-9)


def test_from_config_autofit_cone():
    cfg = LightConfig(grid_origin=None, grid_size=None, grid_resolution=(16, 16, 16))
    env = EnvelopeConfig(shape="cone", rx=1.5, ry=8.0, rz=1.5, center=(0.0, 0.0, 0.0))
    grid = LightGrid.from_config(cfg, env)
    # Cone AABB: x/z in [-rx, rx], y in [0, ry]
    np.testing.assert_allclose(grid.origin, [-1.5 - 0.3, -0.8, -1.5 - 0.3], atol=1e-9)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_light_grid.py -v`
Expected: FAIL with `ImportError` (`palubicki.sim.light` doesn't exist).

- [ ] **Step 3: Create sim/light.py with LightGrid skeleton**

Create `src/palubicki/sim/light.py`:

```python
# src/palubicki/sim/light.py
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from palubicki.config import EnvelopeConfig, LightConfig


def _envelope_aabb(env: EnvelopeConfig) -> tuple[np.ndarray, np.ndarray]:
    """Returns (aabb_min, aabb_max) for the envelope."""
    c = np.asarray(env.center, dtype=np.float64)
    if env.shape == "sphere":
        r = env.rx
        return c - r, c + r
    if env.shape == "ellipsoid":
        r = np.array([env.rx, env.ry, env.rz])
        return c - r, c + r
    if env.shape == "half_ellipsoid":
        r = np.array([env.rx, env.ry, env.rz])
        amin = c - np.array([env.rx, 0.0, env.rz])
        amax = c + r
        return amin, amax
    if env.shape == "cone":
        amin = c - np.array([env.rx, 0.0, env.rz])
        amax = c + np.array([env.rx, env.ry, env.rz])
        return amin, amax
    raise ValueError(f"unknown envelope shape: {env.shape}")


def _autofit_bounds(env: EnvelopeConfig) -> tuple[np.ndarray, np.ndarray]:
    """Return (origin, size) auto-fit to envelope AABB with sky margin."""
    aabb_min, aabb_max = _envelope_aabb(env)
    extent = aabb_max - aabb_min
    height = extent[1]
    origin = aabb_min - 0.1 * extent
    size = extent + np.array([0.2 * extent[0], 0.3 * height, 0.2 * extent[2]]) + 0.2 * extent
    # Note: origin already includes -0.1*extent shift on each axis, so total
    # margin on x/z is 0.1 (origin shift) + 0.1 (size expansion past max) = 0.2,
    # and on y is 0.1 (origin) + 0.3 (sky) + 0.1 (top) = 0.5. Adjust size to
    # close the loop: size = (aabb_max + margin_top) - origin.
    margin_top = np.array([0.1 * extent[0], 0.3 * height + 0.1 * extent[1], 0.1 * extent[2]])
    size = (aabb_max + margin_top) - origin
    return origin, size


@dataclass
class LightGrid:
    origin: np.ndarray            # (3,) float64
    cell_size: np.ndarray         # (3,) float64
    resolution: tuple[int, int, int]
    lai: np.ndarray               # (nx, ny, nz) float32

    @classmethod
    def from_config(cls, light_cfg: LightConfig, env_cfg: EnvelopeConfig) -> "LightGrid":
        if light_cfg.grid_origin is None or light_cfg.grid_size is None:
            origin, size = _autofit_bounds(env_cfg)
        else:
            origin = np.asarray(light_cfg.grid_origin, dtype=np.float64)
            size = np.asarray(light_cfg.grid_size, dtype=np.float64)
        nx, ny, nz = light_cfg.grid_resolution
        cell_size = size / np.array([nx, ny, nz], dtype=np.float64)
        lai = np.zeros((nx, ny, nz), dtype=np.float32)
        return cls(origin=origin, cell_size=cell_size, resolution=(nx, ny, nz), lai=lai)

    def world_to_cell(self, p: np.ndarray) -> tuple[int, int, int] | None:
        local = p - self.origin
        idx = np.floor(local / self.cell_size).astype(int)
        nx, ny, nz = self.resolution
        if (idx[0] < 0 or idx[0] >= nx or idx[1] < 0 or idx[1] >= ny or idx[2] < 0 or idx[2] >= nz):
            return None
        return int(idx[0]), int(idx[1]), int(idx[2])

    def cell_to_world_center(self, i: int, j: int, k: int) -> np.ndarray:
        return self.origin + (np.array([i, j, k], dtype=np.float64) + 0.5) * self.cell_size
```

- [ ] **Step 4: Update test expected values to match the autofit formula**

The autofit formula above computes `size = (aabb_max + margin_top) - origin`. With margin_top = (0.1·ext_x, 0.3·height + 0.1·ext_y, 0.1·ext_z) and origin shifted by -0.1·extent, the total size on each axis is: x: ext_x + 0.2·ext_x = 1.2·ext_x ; y: ext_y + 0.4·ext_y = 1.4·ext_y plus sky 0.3·height = ext_y · (1.4 + 0.3) wait. Let me re-derive:

`size = (aabb_max + margin_top) - origin`
     `= (aabb_max + (0.1*ext_x, 0.3*h + 0.1*ext_y, 0.1*ext_z)) - (aabb_min - 0.1*extent)`
     `= extent + (0.1*ext_x, 0.3*h + 0.1*ext_y, 0.1*ext_z) + 0.1*extent`
     `= (1.2*ext_x, 1.1*ext_y + 0.3*ext_y, 1.2*ext_z)`  (since h = ext_y for these envelopes)
     `= (1.2*ext_x, 1.4*ext_y, 1.2*ext_z)`

Update the ellipsoid test expectation:

```python
def test_from_config_autofit_ellipsoid():
    cfg = LightConfig(grid_origin=None, grid_size=None, grid_resolution=(16, 16, 16))
    env = EnvelopeConfig(shape="ellipsoid", rx=2.0, ry=3.0, rz=2.0, center=(0.0, 0.0, 0.0))
    grid = LightGrid.from_config(cfg, env)
    # AABB: [-2,2] × [-3,3] × [-2,2] → extent (4, 6, 4)
    # origin = aabb_min - 0.1 * extent = (-2.4, -3.6, -2.4)
    # size = (1.2*4, 1.4*6, 1.2*4) = (4.8, 8.4, 4.8)
    np.testing.assert_allclose(grid.origin, [-2.4, -3.6, -2.4], atol=1e-9)
    np.testing.assert_allclose(grid.cell_size * np.array(cfg.grid_resolution), [4.8, 8.4, 4.8], atol=1e-9)


def test_from_config_autofit_cone():
    cfg = LightConfig(grid_origin=None, grid_size=None, grid_resolution=(16, 16, 16))
    env = EnvelopeConfig(shape="cone", rx=1.5, ry=8.0, rz=1.5, center=(0.0, 0.0, 0.0))
    grid = LightGrid.from_config(cfg, env)
    # Cone AABB: x/z in [-rx, rx]=[-1.5,1.5], y in [0, ry]=[0, 8]. extent=(3, 8, 3).
    # origin = aabb_min - 0.1 * extent = (-1.5 - 0.3, 0 - 0.8, -1.5 - 0.3) = (-1.8, -0.8, -1.8)
    np.testing.assert_allclose(grid.origin, [-1.8, -0.8, -1.8], atol=1e-9)
```

Update `test_from_config_autofit_half_ellipsoid_starts_at_y_zero`:

```python
def test_from_config_autofit_half_ellipsoid_starts_at_y_zero():
    cfg = LightConfig(grid_origin=None, grid_size=None, grid_resolution=(16, 16, 16))
    env = EnvelopeConfig(shape="half_ellipsoid", rx=2.0, ry=3.0, rz=2.0, center=(0.0, 0.0, 0.0))
    grid = LightGrid.from_config(cfg, env)
    # AABB y range [0, 3] → extent_y = 3 → origin.y = 0 - 0.1 * 3 = -0.3
    np.testing.assert_allclose(grid.origin[1], -0.3, atol=1e-9)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_light_grid.py -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/light.py tests/sim/test_light_grid.py
git commit -m "feat(sim): LightGrid skeleton with from_config + world_to_cell"
```

---

## Task 4: LightGrid.rebuild_from_tree (leaves only)

**Files:**
- Modify: `src/palubicki/sim/light.py`
- Test: `tests/sim/test_light_grid.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/sim/test_light_grid.py`:

```python
from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree


def _make_tree_with_terminal_at(pos: np.ndarray) -> Tree:
    """Tree: root → one internode → terminal bud at `pos`. No lateral buds."""
    root = Node(position=np.zeros(3))
    leaf_node = Node(position=pos)
    iod = Internode(parent_node=root, child_node=leaf_node, length=float(np.linalg.norm(pos)), is_main_axis=True)
    iod.diameter = 0.01  # avoid 0 for later tasks
    root.children_internodes.append(iod)
    bud = Bud(position=pos.copy(), direction=np.array([0.0, 1.0, 0.0]), axis_order=0, parent_node=leaf_node)
    leaf_node.terminal_bud = bud
    return Tree(root=root, active_buds=[bud], all_internodes=[iod])


def test_rebuild_inject_single_leaf():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
        leaf_area=0.04,
        internode_area_scale=0.0,   # disable internode injection for this test
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))

    grid.rebuild_from_tree(tree, cfg)

    # cell_volume = 1.0 ; leaf adds 0.04 / 1.0 = 0.04 to one voxel
    assert grid.lai[5, 7, 1] == pytest.approx(0.04, rel=1e-6)
    # all other voxels are 0
    assert grid.lai.sum() == pytest.approx(0.04, rel=1e-6)


def test_rebuild_skips_dead_buds():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
        leaf_area=0.04,
        internode_area_scale=0.0,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))
    tree.active_buds[0].state = BudState.DEAD

    grid.rebuild_from_tree(tree, cfg)

    assert grid.lai.sum() == pytest.approx(0.0)


def test_rebuild_skips_non_terminal_nodes():
    """Only terminal buds (leaves) inject LAI, not lateral buds or internal nodes."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
        leaf_area=0.04,
        internode_area_scale=0.0,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))
    # Add a lateral bud at a different cell — should NOT contribute LAI
    lat = Bud(position=np.array([2.5, 3.5, 4.5]), direction=np.array([1.0, 0.0, 0.0]), axis_order=1, parent_node=tree.root)
    tree.root.lateral_buds.append(lat)
    tree.active_buds.append(lat)

    grid.rebuild_from_tree(tree, cfg)

    # Only the terminal contributes
    assert grid.lai[5, 7, 1] == pytest.approx(0.04)
    assert grid.lai[2, 3, 4] == pytest.approx(0.0)


def test_rebuild_idempotent_zeros_first():
    """Repeated rebuilds reset LAI (no accumulation across steps)."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
        leaf_area=0.04,
        internode_area_scale=0.0,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))

    grid.rebuild_from_tree(tree, cfg)
    grid.rebuild_from_tree(tree, cfg)

    assert grid.lai.sum() == pytest.approx(0.04)  # not 0.08
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_light_grid.py::test_rebuild_inject_single_leaf -v`
Expected: FAIL with `AttributeError` (`rebuild_from_tree` not defined).

- [ ] **Step 3: Add rebuild_from_tree (leaves only) to LightGrid**

Add to `src/palubicki/sim/light.py`:

```python
from palubicki.sim.tree import BudState, Tree


    def rebuild_from_tree(self, tree: Tree, cfg: LightConfig) -> None:
        """Full rebuild. Zero LAI, then inject leaves (terminal buds on leaf nodes)."""
        self.lai.fill(0.0)
        cell_volume = float(np.prod(self.cell_size))
        leaf_lai = cfg.leaf_area / cell_volume if cell_volume > 0 else 0.0

        # Inject leaf LAI for each terminal bud on a tip node (no descendants).
        # We walk all nodes iteratively.
        stack = [tree.root]
        while stack:
            node = stack.pop()
            for child_iod in node.children_internodes:
                stack.append(child_iod.child_node)
            bud = node.terminal_bud
            if bud is None or bud.state == BudState.DEAD:
                continue
            if node.children_internodes:
                continue  # not a tip — skip (no leaf at an interior node)
            cell = self.world_to_cell(bud.position)
            if cell is None:
                continue
            self.lai[cell] += leaf_lai
```

(Internode injection added in Task 5.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_light_grid.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/light.py tests/sim/test_light_grid.py
git commit -m "feat(sim): LightGrid.rebuild_from_tree leaf injection"
```

---

## Task 5: LightGrid.rebuild_from_tree (internodes with lateral surface)

**Files:**
- Modify: `src/palubicki/sim/light.py`
- Test: `tests/sim/test_light_grid.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/sim/test_light_grid.py`:

```python
def test_rebuild_inject_internode_vertical():
    """A 1.0-length vertical internode of diameter 0.02 (radius 0.01) on cell_size 0.1
       → ~10 cells get LAI from lateral surface 2π·0.01·0.1 each."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(1.0, 1.0, 1.0),
        grid_resolution=(10, 10, 10),
        leaf_area=0.0,             # disable leaf injection for this test
        internode_area_scale=1.0,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    # Build: root at (0.5, 0.0, 0.5), tip at (0.5, 1.0, 0.5), internode is vertical
    root = Node(position=np.array([0.5, 0.0, 0.5]))
    tip = Node(position=np.array([0.5, 1.0, 0.5]))
    iod = Internode(parent_node=root, child_node=tip, length=1.0, is_main_axis=True)
    iod.diameter = 0.02   # r = 0.01
    root.children_internodes.append(iod)
    # add a terminal bud at tip, but with leaf_area=0 it contributes nothing
    bud = Bud(position=tip.position.copy(), direction=np.array([0.0, 1.0, 0.0]), axis_order=0, parent_node=tip)
    tip.terminal_bud = bud
    tree = Tree(root=root, active_buds=[bud], all_internodes=[iod])

    grid.rebuild_from_tree(tree, cfg)

    # Vertical column at (x=5, z=5), y from 0 to 9. Each cell should have LAI > 0.
    column = grid.lai[5, :, 5]
    assert np.all(column[:10] > 0.0), f"expected all 10 cells filled, got {column[:10]}"
    # Total LAI = total lateral surface / cell_volume = (2π·0.01·1.0) / 0.001 = 62.83...
    expected_total = (2 * np.pi * 0.01 * 1.0) / (0.1 * 0.1 * 0.1)
    assert grid.lai.sum() == pytest.approx(expected_total, rel=1e-4)


def test_rebuild_internode_scaled():
    """internode_area_scale=0.5 → half the LAI from internodes."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(1.0, 1.0, 1.0),
        grid_resolution=(10, 10, 10),
        leaf_area=0.0,
        internode_area_scale=0.5,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    root = Node(position=np.array([0.5, 0.0, 0.5]))
    tip = Node(position=np.array([0.5, 1.0, 0.5]))
    iod = Internode(parent_node=root, child_node=tip, length=1.0, is_main_axis=True)
    iod.diameter = 0.02
    root.children_internodes.append(iod)
    bud = Bud(position=tip.position.copy(), direction=np.array([0.0, 1.0, 0.0]), axis_order=0, parent_node=tip)
    tip.terminal_bud = bud
    tree = Tree(root=root, active_buds=[bud], all_internodes=[iod])

    grid.rebuild_from_tree(tree, cfg)

    expected_total = 0.5 * (2 * np.pi * 0.01 * 1.0) / (0.1 * 0.1 * 0.1)
    assert grid.lai.sum() == pytest.approx(expected_total, rel=1e-4)


def test_rebuild_recomputes_radii():
    """rebuild_from_tree calls compute_radii to populate iod.diameter."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(1.0, 1.0, 1.0),
        grid_resolution=(10, 10, 10),
        leaf_area=0.0,
        internode_area_scale=1.0,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    root = Node(position=np.array([0.5, 0.0, 0.5]))
    tip = Node(position=np.array([0.5, 1.0, 0.5]))
    iod = Internode(parent_node=root, child_node=tip, length=1.0, is_main_axis=True)
    # NO pre-set diameter — let rebuild compute it.
    root.children_internodes.append(iod)
    bud = Bud(position=tip.position.copy(), direction=np.array([0.0, 1.0, 0.0]), axis_order=0, parent_node=tip)
    tip.terminal_bud = bud
    tree = Tree(root=root, active_buds=[bud], all_internodes=[iod])

    grid.rebuild_from_tree(tree, cfg, r_tip=0.005, exponent=2.0)

    # After compute_radii: tip is at r_tip=0.005, single-internode tree → iod.diameter = 0.01
    assert iod.diameter == pytest.approx(0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_light_grid.py::test_rebuild_inject_internode_vertical -v`
Expected: FAIL — LAI is 0 because we haven't added internode injection.

- [ ] **Step 3: Extend rebuild_from_tree with internode injection**

Replace the `rebuild_from_tree` method in `src/palubicki/sim/light.py`:

```python
from palubicki.sim.radii import compute_radii


    def rebuild_from_tree(
        self, tree: Tree, cfg: LightConfig, *, r_tip: float | None = None, exponent: float | None = None,
    ) -> None:
        """Full rebuild. Zero LAI, optionally recompute radii, then inject leaves + internodes."""
        self.lai.fill(0.0)
        cell_volume = float(np.prod(self.cell_size))
        if cell_volume <= 0:
            return

        if r_tip is not None and exponent is not None:
            compute_radii(tree, r_tip=r_tip, exponent=exponent)

        leaf_lai = cfg.leaf_area / cell_volume

        # Walk tree once: collect tips for leaves AND internodes for sub-seg injection.
        stack = [tree.root]
        sub_step = float(np.min(self.cell_size))
        while stack:
            node = stack.pop()
            for child_iod in node.children_internodes:
                stack.append(child_iod.child_node)
                self._inject_internode(child_iod, sub_step, cfg.internode_area_scale, cell_volume)
            bud = node.terminal_bud
            if bud is None or bud.state == BudState.DEAD:
                continue
            if node.children_internodes:
                continue
            cell = self.world_to_cell(bud.position)
            if cell is None:
                continue
            self.lai[cell] += leaf_lai

    def _inject_internode(self, iod, sub_step: float, scale: float, cell_volume: float) -> None:
        """Inject lateral surface LAI along the internode in sub-segments of length sub_step."""
        if iod.diameter <= 0 or scale <= 0 or iod.length <= 0:
            return
        p0 = iod.parent_node.position
        p1 = iod.child_node.position
        seg = p1 - p0
        seg_len = float(np.linalg.norm(seg))
        if seg_len < 1e-12:
            return
        direction = seg / seg_len
        radius = 0.5 * iod.diameter
        n_steps = max(1, int(np.ceil(seg_len / sub_step)))
        actual_step = seg_len / n_steps
        sub_surface = 2.0 * np.pi * radius * actual_step * scale
        sub_lai = sub_surface / cell_volume
        for k in range(n_steps):
            p = p0 + (k + 0.5) * actual_step * direction
            cell = self.world_to_cell(p)
            if cell is not None:
                self.lai[cell] += sub_lai
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_light_grid.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/light.py tests/sim/test_light_grid.py
git commit -m "feat(sim): LightGrid.rebuild_from_tree internode lateral surface injection"
```

---

## Task 6: LightGrid.sample_transmission (Beer-Lambert ray-march)

**Files:**
- Modify: `src/palubicki/sim/light.py`
- Test: `tests/sim/test_light_grid.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/sim/test_light_grid.py`:

```python
def test_sample_transmission_empty_grid_returns_one():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    # No LAI injected at all
    T = grid.sample_transmission(np.array([5.0, 5.0, 5.0]), np.array([0.0, 1.0, 0.0]), k=0.5)
    assert T == pytest.approx(1.0)


def test_sample_transmission_uniform_lai():
    """Uniform LAI L → T(p, dir) = exp(-k * L * dist_in_grid)."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    L = 2.0
    grid.lai.fill(L)
    # Ray from (5, 0.001, 5) going up: travels ~10 units inside grid.
    k = 0.5
    T = grid.sample_transmission(np.array([5.0, 0.001, 5.0]), np.array([0.0, 1.0, 0.0]), k=k)
    expected = np.exp(-k * L * 10.0)
    assert T == pytest.approx(expected, rel=1e-2)


def test_sample_transmission_starts_outside_grid():
    """If origin is outside grid, transmission is 1.0 until the ray enters."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    grid.lai.fill(0.0)   # explicit
    T = grid.sample_transmission(np.array([-5.0, 5.0, 5.0]), np.array([1.0, 0.0, 0.0]), k=0.5)
    assert T == pytest.approx(1.0)


def test_sample_transmission_zero_direction():
    """Zero-length direction is a no-op; return 1.0."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    T = grid.sample_transmission(np.array([5.0, 5.0, 5.0]), np.array([0.0, 0.0, 0.0]), k=0.5)
    assert T == pytest.approx(1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_light_grid.py::test_sample_transmission_empty_grid_returns_one -v`
Expected: FAIL (`sample_transmission` not defined).

- [ ] **Step 3: Add sample_transmission to LightGrid**

Add to `src/palubicki/sim/light.py`:

```python
    def sample_transmission(self, p: np.ndarray, direction: np.ndarray, *, k: float) -> float:
        """Ray-march Beer-Lambert from p along direction. Returns T = exp(-Σ k·LAI·step)."""
        d_norm = float(np.linalg.norm(direction))
        if d_norm < 1e-12:
            return 1.0
        d = direction / d_norm

        step_len = float(np.min(self.cell_size))
        # Max number of steps to traverse the grid diagonally.
        grid_diag = float(np.linalg.norm(self.cell_size * np.array(self.resolution)))
        max_steps = int(np.ceil(grid_diag / step_len)) + 2

        optical_depth = 0.0
        pos = p.astype(np.float64).copy()
        for _ in range(max_steps):
            pos = pos + d * step_len
            cell = self.world_to_cell(pos)
            if cell is None:
                # outside grid in direction of travel — assume zero LAI ahead
                break
            optical_depth += k * float(self.lai[cell]) * step_len
        return float(np.exp(-optical_depth))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_light_grid.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/light.py tests/sim/test_light_grid.py
git commit -m "feat(sim): LightGrid.sample_transmission Beer-Lambert ray-march"
```

---

## Task 7: LightGrid.sample_hemisphere (K cosine-weighted rays)

**Files:**
- Modify: `src/palubicki/sim/light.py`
- Test: `tests/sim/test_light_grid.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/sim/test_light_grid.py`:

```python
def test_sample_hemisphere_open_sky_returns_full_light():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    # Empty grid (LAI=0 everywhere) → all rays transmit fully → light_factor=1.0
    lf, grad = grid.sample_hemisphere(
        np.array([5.0, 5.0, 5.0]),
        n_rays=16,
        light_direction=np.array([0.0, 1.0, 0.0]),
        k=0.5,
        seed=42,
    )
    assert lf == pytest.approx(1.0, rel=1e-4)
    # Gradient = normalize(Σ T_k · d_k) ; with all T_k=1 and cosine-weighted dirs,
    # the sum is biased toward the light direction (z axis = up).
    np.testing.assert_allclose(grad, [0.0, 1.0, 0.0], atol=0.2)


def test_sample_hemisphere_dense_uniform_layer_attenuates():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    grid.lai.fill(1.0)
    lf, _grad = grid.sample_hemisphere(
        np.array([5.0, 0.1, 5.0]),
        n_rays=16,
        light_direction=np.array([0.0, 1.0, 0.0]),
        k=0.5,
        seed=42,
    )
    assert 0.0 < lf < 1.0   # attenuated but not zero (rays exit eventually)


def test_sample_hemisphere_deterministic_with_seed():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    grid.lai.fill(0.3)
    lf1, grad1 = grid.sample_hemisphere(np.array([5.0, 5.0, 5.0]), n_rays=16, light_direction=np.array([0.0, 1.0, 0.0]), k=0.5, seed=7)
    lf2, grad2 = grid.sample_hemisphere(np.array([5.0, 5.0, 5.0]), n_rays=16, light_direction=np.array([0.0, 1.0, 0.0]), k=0.5, seed=7)
    assert lf1 == lf2
    np.testing.assert_array_equal(grad1, grad2)


def test_sample_hemisphere_gradient_points_to_open_side():
    """Place a dense block on the -x side of the bud; gradient should point +x (away from shadow)."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(20, 10, 10),   # finer x resolution
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    # Dense LAI in the -x half
    grid.lai[:10, :, :] = 5.0
    lf, grad = grid.sample_hemisphere(
        np.array([5.0, 5.0, 5.0]),
        n_rays=64,                              # more rays for stability
        light_direction=np.array([0.0, 1.0, 0.0]),
        k=0.5,
        seed=42,
    )
    # The bud sits at x=5 which is at the boundary; rays toward +x see less LAI.
    # Gradient.x should be positive (toward open side).
    assert grad[0] > 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_light_grid.py::test_sample_hemisphere_open_sky_returns_full_light -v`
Expected: FAIL (`sample_hemisphere` not defined).

- [ ] **Step 3: Add sample_hemisphere to LightGrid**

Add to `src/palubicki/sim/light.py`:

```python
    def sample_hemisphere(
        self,
        p: np.ndarray,
        *,
        n_rays: int,
        light_direction: np.ndarray,
        k: float,
        seed: int,
    ) -> tuple[float, np.ndarray]:
        """Sample K cosine-weighted directions around light_direction.

        Returns (light_factor, gradient):
          light_factor = mean(T_k) ∈ [0, 1]
          gradient = normalize(Σ T_k · d_k), or zero vector if Σ ≈ 0
        """
        rng = np.random.default_rng(seed)
        # Build orthonormal basis (u, v, w) with w = light_direction (normalized).
        w = np.asarray(light_direction, dtype=np.float64)
        w_norm = float(np.linalg.norm(w))
        if w_norm < 1e-12:
            return 1.0, np.zeros(3)
        w = w / w_norm
        # Pick a canonical axis not parallel to w.
        canonical = np.array([1.0, 0.0, 0.0]) if abs(w[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u = canonical - np.dot(canonical, w) * w
        u = u / np.linalg.norm(u)
        v = np.cross(w, u)

        # Cosine-weighted hemisphere sampling: concentric disk + projection.
        u1 = rng.random(n_rays)
        u2 = rng.random(n_rays)
        r = np.sqrt(u1)
        phi = 2 * np.pi * u2
        x_d = r * np.cos(phi)
        y_d = r * np.sin(phi)
        z_d = np.sqrt(np.maximum(0.0, 1.0 - u1))
        # Directions in world frame
        dirs = x_d[:, None] * u + y_d[:, None] * v + z_d[:, None] * w   # (n_rays, 3)

        transmissions = np.empty(n_rays)
        for i in range(n_rays):
            transmissions[i] = self.sample_transmission(p, dirs[i], k=k)

        light_factor = float(np.mean(transmissions))
        weighted = (transmissions[:, None] * dirs).sum(axis=0)
        grad_norm = float(np.linalg.norm(weighted))
        gradient = weighted / grad_norm if grad_norm > 1e-12 else np.zeros(3)
        return light_factor, gradient
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_light_grid.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/light.py tests/sim/test_light_grid.py
git commit -m "feat(sim): LightGrid.sample_hemisphere cosine-weighted K-ray"
```

---

## Task 8: perceive_light + LightPerception

**Files:**
- Create: `src/palubicki/sim/light_perception.py`
- Create: `tests/sim/test_light_perception.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_light_perception.py`:

```python
import numpy as np
import pytest

from palubicki.config import EnvelopeConfig, LightConfig
from palubicki.sim.light import LightGrid
from palubicki.sim.light_perception import LightPerception, perceive_light
from palubicki.sim.tree import Bud, Node


def _grid_uniform(L: float) -> LightGrid:
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    grid.lai.fill(L)
    return grid


def test_perceive_light_open_sky():
    grid = _grid_uniform(0.0)
    bud = Bud(position=np.array([5.0, 5.0, 5.0]), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=Node(position=np.zeros(3)))
    cfg = LightConfig(n_rays=16, k_absorption=0.5)
    res = perceive_light([bud], grid, cfg, seed=42)
    assert isinstance(res, LightPerception)
    assert res.light_factor[bud] == pytest.approx(1.0, rel=1e-4)
    np.testing.assert_allclose(res.gradient[bud], [0.0, 1.0, 0.0], atol=0.2)


def test_perceive_light_dense_attenuation():
    grid = _grid_uniform(2.0)
    bud = Bud(position=np.array([5.0, 0.5, 5.0]), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=Node(position=np.zeros(3)))
    cfg = LightConfig(n_rays=16, k_absorption=0.5)
    res = perceive_light([bud], grid, cfg, seed=42)
    assert 0.0 < res.light_factor[bud] < 1.0


def test_perceive_light_empty_bud_list():
    grid = _grid_uniform(0.0)
    cfg = LightConfig(n_rays=16, k_absorption=0.5)
    res = perceive_light([], grid, cfg, seed=42)
    assert res.light_factor == {}
    assert res.gradient == {}


def test_perceive_light_deterministic():
    grid = _grid_uniform(1.0)
    bud = Bud(position=np.array([5.0, 5.0, 5.0]), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=Node(position=np.zeros(3)))
    cfg = LightConfig(n_rays=16, k_absorption=0.5)
    res1 = perceive_light([bud], grid, cfg, seed=42)
    res2 = perceive_light([bud], grid, cfg, seed=42)
    assert res1.light_factor[bud] == res2.light_factor[bud]
    np.testing.assert_array_equal(res1.gradient[bud], res2.gradient[bud])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/sim/test_light_perception.py -v`
Expected: FAIL (`palubicki.sim.light_perception` doesn't exist).

- [ ] **Step 3: Create sim/light_perception.py**

Create `src/palubicki/sim/light_perception.py`:

```python
# src/palubicki/sim/light_perception.py
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from palubicki.config import LightConfig
from palubicki.sim.light import LightGrid
from palubicki.sim.tree import Bud


@dataclass
class LightPerception:
    light_factor: dict[Bud, float] = field(default_factory=dict)
    gradient: dict[Bud, np.ndarray] = field(default_factory=dict)


def perceive_light(
    buds: list[Bud],
    grid: LightGrid,
    cfg: LightConfig,
    *,
    seed: int,
) -> LightPerception:
    """Compute light_factor and gradient at each bud via hemispheric sampling."""
    result = LightPerception()
    light_dir = np.asarray(cfg.light_direction, dtype=np.float64)
    for i, bud in enumerate(buds):
        # Per-bud sub-seed for deterministic but distinct sampling across buds.
        lf, grad = grid.sample_hemisphere(
            bud.position,
            n_rays=cfg.n_rays,
            light_direction=light_dir,
            k=cfg.k_absorption,
            seed=seed + i,
        )
        result.light_factor[bud] = lf
        result.gradient[bud] = grad
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_light_perception.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/light_perception.py tests/sim/test_light_perception.py
git commit -m "feat(sim): perceive_light orchestration"
```

---

## Task 9: tropisms.py — add light_gradient kwarg

**Files:**
- Modify: `src/palubicki/sim/tropisms.py`
- Test: `tests/sim/test_tropisms.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/sim/test_tropisms.py`:

```python
def test_growth_direction_uses_light_gradient_when_provided():
    import numpy as np
    from palubicki.config import TropismConfig
    from palubicki.sim.tropisms import growth_direction
    cfg = TropismConfig(w_perception=0.0, w_gravity=0.0, w_phototropism=1.0, w_direction_inertia=0.0,
                        photo_direction=(0.0, 1.0, 0.0))
    light_grad = np.array([1.0, 0.0, 0.0])  # opposite of photo_direction
    d = growth_direction(
        v_perception=np.zeros(3),
        current_direction=np.array([0.0, 1.0, 0.0]),
        cfg=cfg,
        light_gradient=light_grad,
    )
    # Only phototropism is non-zero; with light_gradient it should override photo_direction
    np.testing.assert_allclose(d, [1.0, 0.0, 0.0], atol=1e-9)


def test_growth_direction_falls_back_to_photo_direction_when_no_gradient():
    import numpy as np
    from palubicki.config import TropismConfig
    from palubicki.sim.tropisms import growth_direction
    cfg = TropismConfig(w_perception=0.0, w_gravity=0.0, w_phototropism=1.0, w_direction_inertia=0.0,
                        photo_direction=(0.0, 1.0, 0.0))
    d = growth_direction(
        v_perception=np.zeros(3),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
        light_gradient=None,
    )
    np.testing.assert_allclose(d, [0.0, 1.0, 0.0], atol=1e-9)


def test_growth_direction_zero_gradient_falls_back_to_photo_direction():
    import numpy as np
    from palubicki.config import TropismConfig
    from palubicki.sim.tropisms import growth_direction
    cfg = TropismConfig(w_perception=0.0, w_gravity=0.0, w_phototropism=1.0, w_direction_inertia=0.0,
                        photo_direction=(0.0, 1.0, 0.0))
    d = growth_direction(
        v_perception=np.zeros(3),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
        light_gradient=np.zeros(3),
    )
    np.testing.assert_allclose(d, [0.0, 1.0, 0.0], atol=1e-9)


def test_growth_direction_v1_signature_still_works():
    """Existing callers that don't pass light_gradient must still work."""
    import numpy as np
    from palubicki.config import TropismConfig
    from palubicki.sim.tropisms import growth_direction
    cfg = TropismConfig()
    d = growth_direction(
        v_perception=np.array([0.0, 1.0, 0.0]),
        current_direction=np.array([0.0, 1.0, 0.0]),
        cfg=cfg,
    )
    assert np.linalg.norm(d) == pytest.approx(1.0)
```

(If `pytest` is not already imported in `test_tropisms.py`, add `import pytest` at the top.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_tropisms.py::test_growth_direction_uses_light_gradient_when_provided -v`
Expected: FAIL (`growth_direction` doesn't accept `light_gradient`).

- [ ] **Step 3: Extend growth_direction with light_gradient parameter**

Replace `growth_direction` in `src/palubicki/sim/tropisms.py`:

```python
def growth_direction(
    *,
    v_perception: np.ndarray,
    current_direction: np.ndarray,
    cfg: TropismConfig,
    light_gradient: np.ndarray | None = None,
) -> np.ndarray:
    """Blend perception + gravity + photo + inertia, return unit vector.

    When `light_gradient` is provided and non-zero, it replaces `cfg.photo_direction`
    in the phototropism term. Otherwise falls back to V1 behavior.
    """
    if light_gradient is not None:
        lg = np.asarray(light_gradient, dtype=np.float64)
        lg_norm = float(np.linalg.norm(lg))
        if lg_norm > 1e-12:
            photo = lg / lg_norm
        else:
            photo = np.asarray(cfg.photo_direction, dtype=np.float64)
            pn = np.linalg.norm(photo)
            if pn > 1e-12:
                photo = photo / pn
    else:
        photo = np.asarray(cfg.photo_direction, dtype=np.float64)
        pn = np.linalg.norm(photo)
        if pn > 1e-12:
            photo = photo / pn

    blend = (
        cfg.w_perception * v_perception
        + cfg.w_gravity * _UP
        + cfg.w_phototropism * photo
        + cfg.w_direction_inertia * current_direction
    )
    n = np.linalg.norm(blend)
    if n < 1e-12:
        cd_n = np.linalg.norm(current_direction)
        if cd_n > 1e-12:
            return current_direction / cd_n
        return _UP.copy()
    return blend / n
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_tropisms.py -v`
Expected: All pass (new tests + 6 existing).

- [ ] **Step 5: Run full V1 suite to confirm no regression**

Run: `.venv/bin/pytest -q`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/tropisms.py tests/sim/test_tropisms.py
git commit -m "feat(sim): tropisms growth_direction accepts light_gradient"
```

---

## Task 10: simulator.py — orchestrate light grid + Q hybrid + light tropism

**Files:**
- Modify: `src/palubicki/sim/simulator.py`
- Test: `tests/sim/test_simulator.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/sim/test_simulator.py`:

```python
def test_simulator_v1_bit_exact_when_light_disabled():
    """light.enabled=False → tree identical to V1 (same internode positions, count)."""
    import numpy as np
    from pathlib import Path
    from palubicki.config import (Config, EnvelopeConfig, SimConfig, TropismConfig,
                                  PhyllotaxyConfig, SheddingConfig, GeomConfig, LightConfig)
    from palubicki.sim.simulator import simulate

    cfg_v1 = Config(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_iterations=8),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        light=LightConfig(enabled=False),
        seed=42,
        output=Path("/tmp/x.glb"),
    )
    tree = simulate(cfg_v1)
    n_internodes_v1 = len(tree.all_internodes)

    # Re-run with light *missing entirely* (default = disabled) — same result.
    cfg_default = Config(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_iterations=8),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        seed=42,
        output=Path("/tmp/x.glb"),
    )
    tree2 = simulate(cfg_default)
    assert len(tree2.all_internodes) == n_internodes_v1


def test_simulator_light_enabled_zero_absorption_equivalent_to_disabled():
    """light.enabled=True with k_absorption=0 → grid transparent → ≈ V1 result.

    Not bit-exact because Q is floats × 1.0 instead of ints; node count and
    rough structure should be identical.
    """
    import numpy as np
    from pathlib import Path
    from palubicki.config import (Config, EnvelopeConfig, SimConfig, TropismConfig,
                                  PhyllotaxyConfig, SheddingConfig, GeomConfig, LightConfig)
    from palubicki.sim.simulator import simulate

    base_kwargs = dict(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_iterations=8),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        seed=42,
        output=Path("/tmp/x.glb"),
    )
    tree_off = simulate(Config(light=LightConfig(enabled=False), **base_kwargs))
    tree_zerok = simulate(Config(light=LightConfig(enabled=True, k_absorption=0.0), **base_kwargs))
    # Same count of internodes (transparent grid → no shadowing)
    assert len(tree_zerok.all_internodes) == len(tree_off.all_internodes)


def test_simulator_light_enabled_reduces_density():
    """light.enabled=True (with real absorption) → tree has fewer internodes than V1
       (self-shading removes some buds)."""
    from pathlib import Path
    from palubicki.config import (Config, EnvelopeConfig, SimConfig, TropismConfig,
                                  PhyllotaxyConfig, SheddingConfig, GeomConfig, LightConfig)
    from palubicki.sim.simulator import simulate

    base_kwargs = dict(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_iterations=10),
        tropism=TropismConfig(w_phototropism=0.3),   # activate photo on light
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        seed=42,
        output=Path("/tmp/x.glb"),
    )
    tree_off = simulate(Config(light=LightConfig(enabled=False), **base_kwargs))
    tree_on = simulate(Config(light=LightConfig(enabled=True, k_absorption=1.0, leaf_area=0.2), **base_kwargs))
    # Self-shading kills some buds → fewer internodes.
    assert len(tree_on.all_internodes) < len(tree_off.all_internodes)


def test_simulator_light_reproducible():
    """Same seed + cfg → identical trees (count + position hash)."""
    from pathlib import Path
    import hashlib
    import numpy as np
    from palubicki.config import (Config, EnvelopeConfig, SimConfig, TropismConfig,
                                  PhyllotaxyConfig, SheddingConfig, GeomConfig, LightConfig)
    from palubicki.sim.simulator import simulate

    def pos_hash(tree):
        positions = np.array([iod.child_node.position for iod in tree.all_internodes])
        return hashlib.sha256(positions.tobytes()).hexdigest()

    base = dict(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_iterations=6),
        tropism=TropismConfig(w_phototropism=0.3),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        light=LightConfig(enabled=True, k_absorption=0.5),
        seed=42,
        output=Path("/tmp/x.glb"),
    )
    t1 = simulate(Config(**base))
    t2 = simulate(Config(**base))
    assert pos_hash(t1) == pos_hash(t2)
```

- [ ] **Step 2: Run tests to verify they fail (or only V1-bit-exact passes)**

Run: `.venv/bin/pytest tests/sim/test_simulator.py::test_simulator_light_enabled_reduces_density -v`
Expected: FAIL (light not wired into simulator).

- [ ] **Step 3: Modify simulator.py to orchestrate light**

Replace the body of `simulate` in `src/palubicki/sim/simulator.py` with:

```python
def simulate(cfg: Config) -> Tree:
    from palubicki.sim.light import LightGrid
    from palubicki.sim.light_perception import perceive_light

    rng = np.random.default_rng(cfg.seed)
    marker_positions = sample_markers(cfg.envelope, rng)
    markers = MarkerCloud(marker_positions)

    root_pos = np.array([cfg.envelope.center[0], 0.0, cfg.envelope.center[2]], dtype=float)
    root = Node(position=root_pos)
    bud = Bud(
        position=root_pos.copy(),
        direction=np.array([0.0, 1.0, 0.0]),
        axis_order=0,
        parent_node=root,
    )
    root.terminal_bud = bud
    tree = Tree(root=root, active_buds=[bud])

    light_grid = LightGrid.from_config(cfg.light, cfg.envelope) if cfg.light.enabled else None

    node_index = 0
    no_new_streak = 0
    t0 = time.time()

    for iteration in range(cfg.sim.max_iterations):
        if not tree.active_buds:
            break

        # V2: rebuild light grid and perceive light per bud
        if light_grid is not None:
            light_grid.rebuild_from_tree(
                tree, cfg.light,
                r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent,
            )
            light_info = perceive_light(tree.active_buds, light_grid, cfg.light, seed=cfg.seed + iteration)
        else:
            light_info = None

        res = perceive(
            tree.active_buds, markers,
            r_perception=cfg.sim.r_perception,
            theta_perception_deg=cfg.sim.theta_perception_deg,
        )

        # V2: Q hybrid
        if light_info is not None:
            quality = {b: res.quality[b] * light_info.light_factor[b] for b in tree.active_buds}
        else:
            quality = res.quality

        n_by_bud = allocate(
            tree, quality=quality,
            alpha=cfg.sim.alpha_basipetal, lambda_apical=cfg.sim.lambda_apical,
        )
        record_qualities(tree, quality=quality)

        new_node_positions: list[np.ndarray] = []
        new_active: list[Bud] = []
        nodes_created_this_step = 0

        for bud_old in list(tree.active_buds):
            n = n_by_bud.get(bud_old, 0)
            v_perc = res.direction[bud_old]
            if n < 1 or np.linalg.norm(v_perc) < 1e-12:
                bud_old.state = BudState.DORMANT
                new_active.append(bud_old)
                continue

            current_bud = bud_old
            for step in range(n):
                light_grad = light_info.gradient[current_bud] if light_info else None
                d = growth_direction(
                    v_perception=res.direction[current_bud],
                    current_direction=current_bud.direction,
                    cfg=cfg.tropism,
                    light_gradient=light_grad,
                )
                new_pos = current_bud.position + d * cfg.sim.internode_length
                new_node = Node(position=new_pos)
                iod = Internode(
                    parent_node=current_bud.parent_node,
                    child_node=new_node,
                    length=cfg.sim.internode_length,
                    is_main_axis=(current_bud is current_bud.parent_node.terminal_bud),
                    window=cfg.shedding.window,
                )
                current_bud.parent_node.children_internodes.append(iod)
                new_node.parent_internode = iod
                tree.all_internodes.append(iod)
                new_node_positions.append(new_pos)
                nodes_created_this_step += 1

                terminal = Bud(
                    position=new_pos.copy(), direction=d,
                    axis_order=current_bud.axis_order, parent_node=new_node,
                )
                new_node.terminal_bud = terminal

                lateral_dirs = lateral_bud_directions(d, cfg.phyllotaxy, node_index=node_index)
                node_index += 1
                for ld in lateral_dirs:
                    lat = Bud(
                        position=new_pos.copy(), direction=ld,
                        axis_order=current_bud.axis_order + 1, parent_node=new_node,
                    )
                    new_node.lateral_buds.append(lat)

                new_active.extend(new_node.lateral_buds)
                current_bud.state = BudState.DEAD
                if step + 1 < n:
                    if cfg.sim.re_perceive_per_substep:
                        sub_result = perceive(
                            [terminal], markers,
                            r_perception=cfg.sim.r_perception,
                            theta_perception_deg=cfg.sim.theta_perception_deg,
                        )
                        res.direction[terminal] = sub_result.direction[terminal]
                        res.quality[terminal] = sub_result.quality[terminal]
                        # V2: re-sample light locally for the new terminal
                        if light_grid is not None and light_info is not None:
                            lf, grad = light_grid.sample_hemisphere(
                                terminal.position,
                                n_rays=cfg.light.n_rays,
                                light_direction=np.asarray(cfg.light.light_direction, dtype=np.float64),
                                k=cfg.light.k_absorption,
                                seed=cfg.seed + iteration + step + 1,
                            )
                            light_info.light_factor[terminal] = lf
                            light_info.gradient[terminal] = grad
                        if np.linalg.norm(res.direction[terminal]) < 1e-12:
                            terminal.state = BudState.DORMANT
                            new_active.append(terminal)
                            break
                    else:
                        res.direction[terminal] = res.direction.get(current_bud, np.zeros(3))
                        res.quality[terminal] = res.quality.get(current_bud, 0)
                        if light_info is not None:
                            light_info.light_factor[terminal] = light_info.light_factor.get(current_bud, 1.0)
                            light_info.gradient[terminal] = light_info.gradient.get(current_bud, np.zeros(3))
                    current_bud = terminal
                else:
                    new_active.append(terminal)

        tree.active_buds = [b for b in new_active if b.state != BudState.DEAD]

        if new_node_positions:
            markers.kill_near(np.array(new_node_positions), cfg.sim.r_kill)

        shed_low_quality(tree, cfg=cfg.shedding)

        if nodes_created_this_step == 0:
            no_new_streak += 1
        else:
            no_new_streak = 0
        if no_new_streak >= 2:
            break

        logger.info(
            "[%.1fs] sim/iter %d/%d  buds=%d active=%d  internodes=%d",
            time.time() - t0,
            iteration + 1, cfg.sim.max_iterations,
            len(tree.active_buds),
            sum(1 for b in tree.active_buds if b.state == BudState.ACTIVE),
            len(tree.all_internodes),
        )

    return tree
```

- [ ] **Step 4: Run new + existing simulator tests**

Run: `.venv/bin/pytest tests/sim/test_simulator.py -v`
Expected: All pass (V1 tests still pass + new V2 tests pass).

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/pytest -q`
Expected: All pass (V1 goldens still pass because light defaults to disabled).

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/simulator.py tests/sim/test_simulator.py
git commit -m "feat(sim): orchestrate light grid + Q hybrid + local phototropism"
```

---

## Task 11: CLI flags for light

**Files:**
- Modify: `src/palubicki/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Inspect existing CLI patterns to follow**

Run: `.venv/bin/python -c "from palubicki.cli import app; print('ok')"` to confirm import.

Read `src/palubicki/cli.py` to find the `generate` command and how `--w-gravity` etc. are wired. Follow the same pattern (typer option → cli_overrides dict → load_config).

- [ ] **Step 2: Write the failing test**

Add to `tests/test_cli.py`:

```python
def test_cli_light_enabled_flag(tmp_path):
    """--light-enabled sets light.enabled=True in the produced .glb config."""
    from typer.testing import CliRunner
    from palubicki.cli import app
    import json
    from pygltflib import GLTF2

    out = tmp_path / "tree_light.glb"
    runner = CliRunner()
    result = runner.invoke(app, [
        "generate", "-o", str(out),
        "--envelope", "ellipsoid", "--envelope-radii", "2", "3", "2",
        "--seed", "42", "--light-enabled",
        "--max-iterations", "4",
    ])
    assert result.exit_code == 0, result.output
    gltf = GLTF2().load(str(out))
    embedded = gltf.asset.extras["config"]
    assert embedded["light"]["enabled"] is True
```

(If `--max-iterations` doesn't exist as a flag, use a small marker_count instead to keep the test fast.)

- [ ] **Step 3: Run the failing test**

Run: `.venv/bin/pytest tests/test_cli.py::test_cli_light_enabled_flag -v`
Expected: FAIL (no `--light-enabled` option).

- [ ] **Step 4: Add CLI options to generate command**

In `src/palubicki/cli.py`, inside the `generate` function signature, add (next to the existing tropism options):

```python
    light_enabled: bool = typer.Option(False, "--light-enabled/--no-light", help="Enable V2 voxel light shadowing (BHls hybrid)"),
    light_k_absorption: float = typer.Option(None, "--light-k", help="Beer-Lambert absorption coefficient"),
    light_n_rays: int = typer.Option(None, "--light-rays", help="Hemispheric rays per bud (default 16)"),
    light_resolution: int = typer.Option(None, "--light-res", help="Light grid resolution N → N×N×N cells"),
```

Then in the override-building block (where other CLI flags become `cli_overrides` dict entries), add:

```python
    if light_enabled:
        cli_overrides["light.enabled"] = True
    if light_k_absorption is not None:
        cli_overrides["light.k_absorption"] = light_k_absorption
    if light_n_rays is not None:
        cli_overrides["light.n_rays"] = light_n_rays
    if light_resolution is not None:
        cli_overrides["light.grid_resolution"] = [light_resolution, light_resolution, light_resolution]
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_cli.py::test_cli_light_enabled_flag -v`
Expected: PASS.

- [ ] **Step 6: Run full CLI tests + smoke**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/cli.py tests/test_cli.py
git commit -m "feat(cli): --light-enabled and light tuning flags"
```

---

## Task 12: Integration + behavioral + golden tests

**Files:**
- Modify: `tests/integration/test_smoke.py`
- Modify: `tests/golden/test_goldens.py`
- Create: `tests/integration/test_light_behavior.py`

- [ ] **Step 1: Inspect existing smoke + golden tests for patterns**

Read `tests/integration/test_smoke.py` and `tests/golden/test_goldens.py` to follow existing parametrization and conventions (envelope shapes, seed=42 typical).

- [ ] **Step 2: Add light-enabled smoke cases**

In `tests/integration/test_smoke.py`, add a parametrized test that runs `generate` end-to-end with `light_enabled=True` for each envelope (sphere, ellipsoid, half_ellipsoid, cone). Confirm: `.glb` is produced, file size > 1KB, and `gltf.asset.extras["config"]["light"]["enabled"] is True`.

```python
@pytest.mark.slow
@pytest.mark.parametrize("shape", ["sphere", "ellipsoid", "half_ellipsoid", "cone"])
def test_smoke_light_enabled_per_envelope(tmp_path, shape):
    from palubicki.cli import app
    from typer.testing import CliRunner
    from pygltflib import GLTF2

    out = tmp_path / f"tree_{shape}.glb"
    runner = CliRunner()
    result = runner.invoke(app, [
        "generate", "-o", str(out),
        "--envelope", shape, "--envelope-radii", "2", "3", "2",
        "--seed", "42", "--light-enabled",
    ])
    assert result.exit_code == 0, result.output
    assert out.stat().st_size > 1024
    gltf = GLTF2().load(str(out))
    assert gltf.asset.extras["config"]["light"]["enabled"] is True
```

- [ ] **Step 3: Add golden hash test for light-enabled tree**

In `tests/golden/test_goldens.py`, add a new golden case mirroring the existing pattern. Adapt to the file's conventions; the new case uses `light.enabled=True` plus a seed and standard ellipsoid. If the existing tests load a `goldens.json` or similar, add a new key like `"ellipsoid_light_42"`. If the convention is one golden file per case, add a new file.

The hash should be computed over the simulator's tree positions (or `.glb` bytes, whichever the file already does). Update goldens via `pytest --update-goldens` (existing mechanism per repo).

- [ ] **Step 4: Create behavioral test**

Create `tests/integration/test_light_behavior.py`:

```python
import hashlib
from pathlib import Path

import numpy as np
import pytest

from palubicki.config import (Config, EnvelopeConfig, SimConfig, TropismConfig,
                              PhyllotaxyConfig, SheddingConfig, GeomConfig, LightConfig)
from palubicki.sim.simulator import simulate


def _base_cfg(**overrides) -> Config:
    base = dict(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=2.0, ry=3.0, rz=2.0, marker_count=3000),
        sim=SimConfig(max_iterations=12),
        tropism=TropismConfig(w_phototropism=0.3),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        seed=42,
        output=Path("/tmp/x.glb"),
    )
    base.update(overrides)
    return Config(**base)


@pytest.mark.slow
def test_light_enabled_reduces_internode_count():
    tree_off = simulate(_base_cfg(light=LightConfig(enabled=False)))
    tree_on = simulate(_base_cfg(light=LightConfig(enabled=True, k_absorption=1.0, leaf_area=0.2)))
    # Self-shading should kill some buds → strictly fewer internodes
    assert len(tree_on.all_internodes) < len(tree_off.all_internodes)


@pytest.mark.slow
def test_light_enabled_raises_centroid():
    """Light-driven shedding+tropism should concentrate biomass higher (positive y)."""
    tree_off = simulate(_base_cfg(light=LightConfig(enabled=False)))
    tree_on = simulate(_base_cfg(light=LightConfig(enabled=True, k_absorption=1.0, leaf_area=0.2)))
    centroid_y_off = np.mean([iod.child_node.position[1] for iod in tree_off.all_internodes])
    centroid_y_on = np.mean([iod.child_node.position[1] for iod in tree_on.all_internodes])
    assert centroid_y_on > centroid_y_off
```

- [ ] **Step 5: Run all new tests**

Run: `.venv/bin/pytest tests/integration/test_light_behavior.py tests/integration/test_smoke.py -m slow -v`
Expected: All pass.

If the centroid test fails for the chosen seed/params, tune `leaf_area`, `k_absorption`, or `marker_count` until the effect is clear. Document the chosen values inline.

- [ ] **Step 6: Run full suite**

Run: `.venv/bin/pytest -q && .venv/bin/pytest -m slow -q`
Expected: All pass (fast + slow).

- [ ] **Step 7: Update README**

Add a "V2 light shadowing" section to `README.md`:

```markdown
### V2 — voxel light shadowing (BHls hybrid)

Enable with `--light-enabled`. The bud's quality becomes
`Q = nb_markers × light_factor`, where `light_factor ∈ [0,1]` is the fraction
of hemispheric rays reaching the bud through accumulated leaf/branch density
(Beer-Lambert). Light also drives local phototropism (the growth direction
biases toward the brightest opening) and shedding (branches in deep shadow
die).

When activating light, also bump `tropism.w_phototropism` from its V1 default
of 0.0 (e.g. `--w-photo 0.3`) so the phototropism term actually pulls toward
light.

```bash
palubicki generate -o oak_light.glb \
  --envelope ellipsoid --envelope-radii 3 5 3 \
  --light-enabled --w-photo 0.3 \
  --seed 42
```
```

(Check that `--w-photo` is the existing CLI flag for `w_phototropism`; if it's different in the codebase, use the actual flag name.)

- [ ] **Step 8: Final commit**

```bash
git add tests/integration/test_smoke.py tests/integration/test_light_behavior.py tests/golden/ README.md
git commit -m "test+docs: V2 integration, golden, behavioral tests + README"
```

---

## Acceptance check

After all 12 tasks:

1. `.venv/bin/pytest -q` — all fast tests pass.
2. `.venv/bin/pytest -m slow -q` — all slow tests pass.
3. `.venv/bin/pytest --cov=src/palubicki/sim/light --cov=src/palubicki/sim/light_perception --cov-report=term` — coverage ≥ 85%.
4. Generate a V2 tree to eyeball:
   ```bash
   .venv/bin/palubicki generate -o /tmp/v2.glb \
     --envelope ellipsoid --envelope-radii 3 5 3 \
     --light-enabled --w-photo 0.3 --seed 42
   ```
   Open `/tmp/v2.glb` in a viewer; silhouette should be more upward-concentrated than the V1 equivalent (same params without `--light-enabled`).
5. V1 goldens unchanged (rétrocompat bit-exact verified by Tasks 1, 10).
6. New V2 golden stable across runs.
