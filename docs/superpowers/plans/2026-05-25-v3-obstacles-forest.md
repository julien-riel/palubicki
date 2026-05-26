# V3 Obstacles & Forest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add static obstacles (AABB, sphere, OBB, mesh OBJ) and multi-tree forest simulation sharing a single `MarkerCloud` + `LightGrid`. Obstacles filter markers at init, block growth segments, occlude light voxels, and kill buds that end up inside them. New `palubicki forest` CLI subcommand emits a glTF scene with one node per tree plus an `obstacles` node. Backward-compat bit-exact V2 when `forest.seeds == ()` and `forest.obstacles == ()`.

**Architecture:** New `sim/obstacles.py` (Obstacle protocol + 4 impls + helpers), `sim/forest.py` (Forest dataclass + build helpers), `geom/obstacle_geom.py` (triangulation). `sim/light.py` extended with `rebuild_from_forest`. `sim/simulator.py` refactored into `_iteration_step` + two public entry points (`simulate`, `simulate_forest`). `export/gltf.py` extended with `write_glb_forest`. `config.py` adds `ForestConfig`/obstacle dataclasses; YAML loading supports the discriminated union over `kind:`.

**Tech Stack:** Python 3.14, numpy, scipy, trimesh (NEW dependency, for mesh obstacles), pytest, existing dataclass-based config. Use `.venv/bin/pytest`, `.venv/bin/python` etc. — bash sessions don't persist venv activation across calls.

**Spec:** `docs/superpowers/specs/2026-05-25-v3-obstacles-forest-design.md`

**File structure:**
- CREATE `src/palubicki/sim/obstacles.py` — Obstacle protocol + AABB/Sphere/OBB/Mesh impls + helpers
- CREATE `src/palubicki/sim/forest.py` — Forest dataclass + build_forest + per_tree_config + forest_light_bounds
- CREATE `src/palubicki/geom/obstacle_geom.py` — triangulation primitives
- CREATE `tests/sim/test_obstacles.py` — unit tests for all obstacle types and helpers
- CREATE `tests/sim/test_forest.py` — unit tests for forest helpers and build_forest
- CREATE `tests/sim/test_obstacle_voxelize.py` — voxelization tests
- CREATE `tests/integration/test_obstacles_behavior.py` — wall/roof shape changes
- CREATE `tests/integration/test_forest_behavior.py` — multi-tree competition
- CREATE `tests/fixtures/forest_minimal.yaml` — minimal scene for CLI smoke test
- CREATE `tests/fixtures/unit_cube.obj` — small OBJ for MeshObstacle tests
- MODIFY `pyproject.toml` — add `trimesh` dependency
- MODIFY `src/palubicki/config.py` — Obstacle*/ForestSeed/ForestConfig + YAML dispatcher
- MODIFY `src/palubicki/sim/light.py` — `rebuild_from_forest` + obstacle mask application
- MODIFY `src/palubicki/sim/simulator.py` — extract `_iteration_step`, add `simulate_forest`
- MODIFY `src/palubicki/export/gltf.py` — `write_glb_forest`
- MODIFY `src/palubicki/cli.py` — `palubicki forest` subcommand
- MODIFY `tests/test_config.py` — config dataclasses + YAML loader tests
- MODIFY `tests/sim/test_light_grid.py` — `rebuild_from_forest` cases
- MODIFY `tests/sim/test_simulator.py` — V2 bit-exact + forest cases
- MODIFY `tests/test_cli.py` — `forest` subcommand
- MODIFY `tests/integration/test_smoke.py` — one forest case
- MODIFY `tests/golden/test_goldens.py` — V3 golden

---

## Task 1: Add `trimesh` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add trimesh to dependencies**

Open `pyproject.toml` and append `"trimesh>=4.0",` to the `dependencies` list. The resulting block (existing entries kept):

```toml
dependencies = [
    "numpy>=1.26",
    "scipy>=1.11",
    "pygltflib>=1.16",
    "Pillow>=10.0",
    "pyyaml>=6.0",
    "trimesh>=4.0",
]
```

- [ ] **Step 2: Install**

Run: `.venv/bin/pip install -e ".[dev]"`
Expected: trimesh and its transitive deps installed without errors.

- [ ] **Step 3: Verify import**

Run: `.venv/bin/python -c "import trimesh; print(trimesh.__version__)"`
Expected: a version string printed (no ImportError).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add trimesh dependency for V3 mesh obstacles"
```

---

## Task 2: Obstacle config dataclasses

**Files:**
- Modify: `src/palubicki/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config.py`:

```python
def test_obstacle_aabb_defaults():
    from palubicki.config import ObstacleAABB
    o = ObstacleAABB()
    assert o.kind == "aabb"
    assert o.min == (0.0, 0.0, 0.0)
    assert o.max == (1.0, 1.0, 1.0)


def test_obstacle_sphere_defaults():
    from palubicki.config import ObstacleSphere
    o = ObstacleSphere()
    assert o.kind == "sphere"
    assert o.center == (0.0, 0.0, 0.0)
    assert o.radius == 1.0


def test_obstacle_obb_defaults():
    from palubicki.config import ObstacleOBB
    o = ObstacleOBB()
    assert o.kind == "obb"
    assert o.center == (0.0, 0.0, 0.0)
    assert o.half_extents == (1.0, 1.0, 1.0)
    assert o.axes == (1, 0, 0, 0, 1, 0, 0, 0, 1)


def test_obstacle_mesh_defaults():
    from palubicki.config import ObstacleMesh
    from pathlib import Path
    o = ObstacleMesh(path=Path("foo.obj"))
    assert o.kind == "mesh"
    assert o.path == Path("foo.obj")
    assert o.translate == (0.0, 0.0, 0.0)
    assert o.scale == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config.py::test_obstacle_aabb_defaults -v`
Expected: FAIL with `ImportError` (`ObstacleAABB` not in `palubicki.config`).

- [ ] **Step 3: Add dataclasses to config.py**

Insert after the `LightConfig` dataclass in `src/palubicki/config.py`:

```python
@dataclass(frozen=True)
class ObstacleAABB:
    kind: Literal["aabb"] = "aabb"
    min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    max: tuple[float, float, float] = (1.0, 1.0, 1.0)


@dataclass(frozen=True)
class ObstacleSphere:
    kind: Literal["sphere"] = "sphere"
    center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius: float = 1.0


@dataclass(frozen=True)
class ObstacleOBB:
    kind: Literal["obb"] = "obb"
    center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    half_extents: tuple[float, float, float] = (1.0, 1.0, 1.0)
    axes: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


@dataclass(frozen=True)
class ObstacleMesh:
    kind: Literal["mesh"] = "mesh"
    path: Path = field(default_factory=lambda: Path("obstacle.obj"))
    translate: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: float = 1.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -k obstacle -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "feat(config): add obstacle dataclasses (AABB, Sphere, OBB, Mesh)"
```

---

## Task 3: ForestSeed + ForestConfig dataclasses

**Files:**
- Modify: `src/palubicki/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config.py`:

```python
def test_forest_seed_defaults():
    from palubicki.config import ForestSeed
    s = ForestSeed(position=(1.0, 0.0, 2.0))
    assert s.position == (1.0, 0.0, 2.0)
    assert s.seed is None
    assert s.overrides == {}


def test_forest_config_defaults():
    from palubicki.config import ForestConfig
    f = ForestConfig()
    assert f.seeds == ()
    assert f.obstacles == ()
    assert f.export_obstacles_geometry is True


def test_config_default_forest_is_empty():
    from palubicki.config import (
        Config, EnvelopeConfig, SimConfig, TropismConfig, PhyllotaxyConfig,
        SheddingConfig, GeomConfig, LightConfig, ForestConfig,
    )
    from pathlib import Path
    c = Config(
        envelope=EnvelopeConfig(), sim=SimConfig(), tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(), shedding=SheddingConfig(), geom=GeomConfig(),
        light=LightConfig(), output=Path("/tmp/x.glb"),
    )
    assert c.forest.seeds == ()
    assert c.forest.obstacles == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config.py::test_forest_seed_defaults -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add dataclasses and wire into Config**

Insert after `ObstacleMesh` in `src/palubicki/config.py`:

```python
@dataclass(frozen=True)
class ForestSeed:
    position: tuple[float, float, float]
    seed: int | None = None
    overrides: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ForestConfig:
    seeds: tuple = ()
    obstacles: tuple = ()
    export_obstacles_geometry: bool = True
```

Then modify the `Config` dataclass to add a `forest` field. Find the `Config` dataclass and add `forest: ForestConfig = field(default_factory=ForestConfig)` right after the `light` line:

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
    forest: ForestConfig = field(default_factory=ForestConfig)
    seed: int = 0
    output: Path = field(default_factory=lambda: Path("tree.glb"))
    log_level: str = "INFO"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -k "forest_seed or forest_config or default_forest" -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "feat(config): add ForestSeed and ForestConfig dataclasses"
```

---

## Task 4: YAML loader for forest section (discriminated union)

**Files:**
- Modify: `src/palubicki/config.py`
- Test: `tests/test_config_yaml.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_config_yaml.py`:

```python
def test_load_config_with_obstacles(tmp_path):
    from palubicki.config import load_config, ObstacleAABB, ObstacleSphere, ObstacleMesh
    yaml_path = tmp_path / "scene.yaml"
    yaml_path.write_text("""
forest:
  obstacles:
    - kind: aabb
      min: [0.0, 0.0, 0.0]
      max: [2.0, 1.0, 2.0]
    - kind: sphere
      center: [5.0, 0.0, 5.0]
      radius: 1.5
""")
    cfg = load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")
    assert len(cfg.forest.obstacles) == 2
    assert isinstance(cfg.forest.obstacles[0], ObstacleAABB)
    assert cfg.forest.obstacles[0].min == (0.0, 0.0, 0.0)
    assert cfg.forest.obstacles[0].max == (2.0, 1.0, 2.0)
    assert isinstance(cfg.forest.obstacles[1], ObstacleSphere)
    assert cfg.forest.obstacles[1].radius == 1.5


def test_load_config_with_forest_seeds(tmp_path):
    from palubicki.config import load_config, ForestSeed
    yaml_path = tmp_path / "scene.yaml"
    yaml_path.write_text("""
forest:
  seeds:
    - position: [0.0, 0.0, 0.0]
    - position: [5.0, 0.0, 0.0]
      seed: 42
      overrides:
        envelope.shape: cone
        tropism.w_gravity: 0.5
""")
    cfg = load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")
    assert len(cfg.forest.seeds) == 2
    assert cfg.forest.seeds[0].position == (0.0, 0.0, 0.0)
    assert cfg.forest.seeds[0].seed is None
    assert cfg.forest.seeds[1].position == (5.0, 0.0, 0.0)
    assert cfg.forest.seeds[1].seed == 42
    assert cfg.forest.seeds[1].overrides == {"envelope.shape": "cone", "tropism.w_gravity": 0.5}


def test_load_config_unknown_obstacle_kind_raises(tmp_path):
    from palubicki.config import load_config, ConfigError
    import pytest
    yaml_path = tmp_path / "scene.yaml"
    yaml_path.write_text("""
forest:
  obstacles:
    - kind: tetrahedron
      min: [0, 0, 0]
""")
    with pytest.raises(ConfigError, match="unknown obstacle kind"):
        load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config_yaml.py -k "obstacles or forest_seeds or unknown_obstacle" -v`
Expected: FAIL — loader doesn't yet handle `forest.obstacles`/`forest.seeds`.

- [ ] **Step 3: Add loader functions**

Insert at the bottom of `src/palubicki/config.py` (after `_set_dotted`):

```python
_OBSTACLE_TYPES = {
    "aabb": ObstacleAABB,
    "sphere": ObstacleSphere,
    "obb": ObstacleOBB,
    "mesh": ObstacleMesh,
}


def _load_obstacle(d: dict):
    if not isinstance(d, dict):
        raise ConfigError(f"obstacle must be a dict, got {type(d).__name__}")
    kind = d.get("kind")
    if kind is None:
        raise ConfigError(f"obstacle missing 'kind' field: {d}")
    type_ = _OBSTACLE_TYPES.get(kind)
    if type_ is None:
        raise ConfigError(f"unknown obstacle kind: {kind!r} (expected one of {sorted(_OBSTACLE_TYPES)})")
    fields_allowed = {f.name for f in fields(type_)}
    payload = {k: v for k, v in d.items() if k != "kind"}
    unknown = set(payload) - fields_allowed
    if unknown:
        raise ConfigError(f"unknown keys in obstacle {kind!r}: {sorted(unknown)}")
    if "path" in payload:
        payload["path"] = Path(payload["path"])
    for tuple_field in ("min", "max", "center", "half_extents", "translate", "axes"):
        if tuple_field in payload:
            payload[tuple_field] = tuple(payload[tuple_field])
    return type_(**payload)


def _load_forest_seed(d: dict) -> "ForestSeed":
    if not isinstance(d, dict):
        raise ConfigError(f"forest seed must be a dict, got {type(d).__name__}")
    allowed = {"position", "seed", "overrides"}
    unknown = set(d) - allowed
    if unknown:
        raise ConfigError(f"unknown keys in forest seed: {sorted(unknown)}")
    if "position" not in d:
        raise ConfigError("forest seed missing 'position'")
    return ForestSeed(
        position=tuple(d["position"]),
        seed=d.get("seed"),
        overrides=dict(d.get("overrides") or {}),
    )


def _load_forest_config(d: dict) -> "ForestConfig":
    if not isinstance(d, dict):
        raise ConfigError(f"forest section must be a dict, got {type(d).__name__}")
    allowed = {"seeds", "obstacles", "export_obstacles_geometry"}
    unknown = set(d) - allowed
    if unknown:
        raise ConfigError(f"unknown keys in forest section: {sorted(unknown)}")
    seeds = tuple(_load_forest_seed(s) for s in (d.get("seeds") or ()))
    obstacles = tuple(_load_obstacle(o) for o in (d.get("obstacles") or ()))
    export = bool(d.get("export_obstacles_geometry", True))
    return ForestConfig(seeds=seeds, obstacles=obstacles, export_obstacles_geometry=export)
```

Then modify `load_config()` to handle the `forest` section. Find the loop that builds `sections` and add a special-case for `forest`:

Replace this block in `load_config()`:

```python
    sections = {}
    section_field_names = set(_SECTION_TYPES.keys())
    top_field_names = {f.name for f in fields(Config)}

    for name, type_ in _SECTION_TYPES.items():
        sec_data = data.get(name, {}) or {}
        allowed = {f.name for f in fields(type_)}
        unknown = set(sec_data) - allowed
        if unknown:
            raise ConfigError(f"unknown keys in section '{name}': {sorted(unknown)}")
        sections[name] = type_(**sec_data)
```

with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config_yaml.py -k "obstacles or forest_seeds or unknown_obstacle" -v`
Expected: 3 PASSED.

- [ ] **Step 5: Verify V2 tests still pass**

Run: `.venv/bin/pytest tests/test_config_yaml.py tests/test_config.py -v`
Expected: ALL PASS (no regression).

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/config.py tests/test_config_yaml.py
git commit -m "feat(config): YAML loaders for forest seeds and obstacle union"
```

---

## Task 5: ObstacleAABB implementation

**Files:**
- Create: `src/palubicki/sim/obstacles.py`
- Create: `tests/sim/test_obstacles.py`

- [ ] **Step 1: Write failing tests**

Create `tests/sim/test_obstacles.py`:

```python
import numpy as np
import pytest

from palubicki.config import ObstacleAABB
from palubicki.sim.obstacles import AABBObstacle


def test_aabb_contains_center():
    cfg = ObstacleAABB(min=(0.0, 0.0, 0.0), max=(2.0, 2.0, 2.0))
    o = AABBObstacle(cfg)
    pts = np.array([[1.0, 1.0, 1.0], [3.0, 0.0, 0.0], [0.0, 1.0, 1.0]])
    out = o.contains(pts)
    assert out.tolist() == [True, False, True]   # boundary inclusive


def test_aabb_contains_empty_array():
    o = AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))
    out = o.contains(np.zeros((0, 3)))
    assert out.shape == (0,)


def test_aabb_segment_intersects_traverse():
    o = AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))
    # Segment from outside left to outside right, through the box
    assert o.segment_intersects(np.array([-1.0, 0.5, 0.5]), np.array([2.0, 0.5, 0.5])) is True


def test_aabb_segment_intersects_start_inside():
    o = AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))
    assert o.segment_intersects(np.array([0.5, 0.5, 0.5]), np.array([2.0, 0.5, 0.5])) is True


def test_aabb_segment_intersects_end_inside():
    o = AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))
    assert o.segment_intersects(np.array([-1.0, 0.5, 0.5]), np.array([0.5, 0.5, 0.5])) is True


def test_aabb_segment_intersects_miss():
    o = AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))
    assert o.segment_intersects(np.array([2.0, 2.0, 2.0]), np.array([3.0, 2.0, 2.0])) is False


def test_aabb_segment_short_segment_below_box():
    o = AABBObstacle(ObstacleAABB(min=(0, 1, 0), max=(1, 2, 1)))
    # Segment goes left-to-right at y=0.5, never reaches y=1
    assert o.segment_intersects(np.array([-1.0, 0.5, 0.5]), np.array([2.0, 0.5, 0.5])) is False


def test_aabb_aabb_returns_min_max():
    o = AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 2, 3)))
    amin, amax = o.aabb()
    assert tuple(amin) == (0.0, 0.0, 0.0)
    assert tuple(amax) == (1.0, 2.0, 3.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_obstacles.py -v`
Expected: FAIL with `ImportError` (no `palubicki.sim.obstacles` module).

- [ ] **Step 3: Create obstacles.py with AABBObstacle**

Create `src/palubicki/sim/obstacles.py`:

```python
# src/palubicki/sim/obstacles.py
from __future__ import annotations

from typing import Protocol

import numpy as np

from palubicki.config import ObstacleAABB

LAI_OPAQUE: float = 1e6


class Obstacle(Protocol):
    def contains(self, points: np.ndarray) -> np.ndarray: ...
    def segment_intersects(self, p0: np.ndarray, p1: np.ndarray) -> bool: ...
    def aabb(self) -> tuple[np.ndarray, np.ndarray]: ...
    def voxelize(self, grid) -> np.ndarray: ...


class AABBObstacle:
    def __init__(self, cfg: ObstacleAABB):
        self._min = np.asarray(cfg.min, dtype=np.float64)
        self._max = np.asarray(cfg.max, dtype=np.float64)

    def contains(self, points: np.ndarray) -> np.ndarray:
        pts = np.asarray(points, dtype=np.float64)
        if pts.shape[0] == 0:
            return np.zeros(0, dtype=bool)
        return np.all((pts >= self._min) & (pts <= self._max), axis=1)

    def segment_intersects(self, p0: np.ndarray, p1: np.ndarray) -> bool:
        p0 = np.asarray(p0, dtype=np.float64)
        p1 = np.asarray(p1, dtype=np.float64)
        d = p1 - p0
        t_enter = 0.0
        t_exit = 1.0
        for axis in range(3):
            if abs(d[axis]) < 1e-12:
                if p0[axis] < self._min[axis] or p0[axis] > self._max[axis]:
                    return False
                continue
            inv = 1.0 / d[axis]
            t1 = (self._min[axis] - p0[axis]) * inv
            t2 = (self._max[axis] - p0[axis]) * inv
            t_lo, t_hi = (t1, t2) if t1 <= t2 else (t2, t1)
            t_enter = max(t_enter, t_lo)
            t_exit = min(t_exit, t_hi)
            if t_enter > t_exit:
                return False
        return t_enter <= t_exit

    def aabb(self) -> tuple[np.ndarray, np.ndarray]:
        return self._min.copy(), self._max.copy()

    def voxelize(self, grid) -> np.ndarray:
        # Implemented in Task 13.
        raise NotImplementedError("voxelize: implemented in Task 13")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_obstacles.py -v`
Expected: 8 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/obstacles.py tests/sim/test_obstacles.py
git commit -m "feat(sim): AABBObstacle (contains + segment_intersects + aabb)"
```

---

## Task 6: ObstacleSphere implementation

**Files:**
- Modify: `src/palubicki/sim/obstacles.py`
- Modify: `tests/sim/test_obstacles.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/sim/test_obstacles.py`:

```python
from palubicki.config import ObstacleSphere
from palubicki.sim.obstacles import SphereObstacle


def test_sphere_contains():
    o = SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0))
    pts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.1, 0.0, 0.0], [-0.5, 0.5, 0.5]])
    out = o.contains(pts)
    assert out.tolist() == [True, True, False, True]


def test_sphere_segment_traverse():
    o = SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0))
    assert o.segment_intersects(np.array([-2.0, 0.0, 0.0]), np.array([2.0, 0.0, 0.0])) is True


def test_sphere_segment_endpoint_inside():
    o = SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0))
    assert o.segment_intersects(np.array([2.0, 0.0, 0.0]), np.array([0.5, 0.0, 0.0])) is True


def test_sphere_segment_miss():
    o = SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0))
    assert o.segment_intersects(np.array([2.0, 2.0, 0.0]), np.array([3.0, 2.0, 0.0])) is False


def test_sphere_aabb():
    o = SphereObstacle(ObstacleSphere(center=(5.0, 1.0, -2.0), radius=2.0))
    amin, amax = o.aabb()
    assert tuple(amin) == (3.0, -1.0, -4.0)
    assert tuple(amax) == (7.0, 3.0, 0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_obstacles.py -k sphere -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add SphereObstacle to obstacles.py**

Append to `src/palubicki/sim/obstacles.py` (just before any helpers section):

```python
from palubicki.config import ObstacleSphere


class SphereObstacle:
    def __init__(self, cfg: ObstacleSphere):
        self._center = np.asarray(cfg.center, dtype=np.float64)
        self._radius = float(cfg.radius)
        self._r2 = self._radius * self._radius

    def contains(self, points: np.ndarray) -> np.ndarray:
        pts = np.asarray(points, dtype=np.float64)
        if pts.shape[0] == 0:
            return np.zeros(0, dtype=bool)
        delta = pts - self._center
        return np.einsum("ij,ij->i", delta, delta) <= self._r2

    def segment_intersects(self, p0: np.ndarray, p1: np.ndarray) -> bool:
        p0 = np.asarray(p0, dtype=np.float64)
        p1 = np.asarray(p1, dtype=np.float64)
        d = p1 - p0
        f = p0 - self._center
        a = float(np.dot(d, d))
        if a < 1e-24:
            return float(np.dot(f, f)) <= self._r2
        b = 2.0 * float(np.dot(f, d))
        c = float(np.dot(f, f)) - self._r2
        disc = b * b - 4.0 * a * c
        if disc < 0:
            return False
        sqrt_disc = float(np.sqrt(disc))
        t1 = (-b - sqrt_disc) / (2.0 * a)
        t2 = (-b + sqrt_disc) / (2.0 * a)
        # Segment intersects iff [t1, t2] overlaps [0, 1]
        return t2 >= 0.0 and t1 <= 1.0

    def aabb(self) -> tuple[np.ndarray, np.ndarray]:
        r = np.array([self._radius, self._radius, self._radius])
        return self._center - r, self._center + r

    def voxelize(self, grid) -> np.ndarray:
        raise NotImplementedError("voxelize: implemented in Task 13")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_obstacles.py -k sphere -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/obstacles.py tests/sim/test_obstacles.py
git commit -m "feat(sim): SphereObstacle (contains + segment_intersects)"
```

---

## Task 7: ObstacleOBB implementation

**Files:**
- Modify: `src/palubicki/sim/obstacles.py`
- Modify: `tests/sim/test_obstacles.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/sim/test_obstacles.py`:

```python
from palubicki.config import ObstacleOBB
from palubicki.sim.obstacles import OBBObstacle


def test_obb_axis_aligned_equivalent_to_aabb():
    # Identity axes → behaves like AABB centered at center
    cfg = ObstacleOBB(center=(1.0, 1.0, 1.0), half_extents=(1.0, 1.0, 1.0))
    o = OBBObstacle(cfg)
    pts = np.array([[1.0, 1.0, 1.0], [0.0, 0.0, 0.0], [3.0, 1.0, 1.0]])
    out = o.contains(pts)
    assert out.tolist() == [True, True, False]


def test_obb_rotated_45deg_around_y():
    # Rotated 45° around y: a point at (1,0,0) world is outside the rotated box
    # whose half_extents are (0.5, 0.5, 0.5) — corners reach sqrt(0.5) ≈ 0.707 in world.
    import math
    c, s = math.cos(math.pi / 4), math.sin(math.pi / 4)
    axes = (c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c)   # rotation matrix R^T (world → local)
    cfg = ObstacleOBB(center=(0, 0, 0), half_extents=(0.5, 0.5, 0.5), axes=axes)
    o = OBBObstacle(cfg)
    out = o.contains(np.array([[0.7, 0.0, 0.0], [0.5, 0.0, 0.0]]))
    # (0.7, 0, 0) is outside (rotated half-extent in world ≈ 0.707 but the FACE at +x in local
    # is at world x ≈ 0.5/c = 0.707 along its rotated normal; (0.7,0,0) maps to local x = 0.7*c ≈ 0.495,
    # local z = 0.7*-s ≈ -0.495 — inside the local AABB ±0.5).
    # We assert that (0.5, 0, 0) is inside (local x = 0.5*c ≈ 0.354, local z = 0.5*-s ≈ -0.354, inside).
    assert out[1] is np.True_ or bool(out[1]) is True


def test_obb_segment_intersects_axis_aligned():
    # With identity rotation, OBB segment_intersects must match AABB behavior
    cfg = ObstacleOBB(center=(0, 0, 0), half_extents=(0.5, 0.5, 0.5))
    o = OBBObstacle(cfg)
    assert o.segment_intersects(np.array([-2.0, 0.0, 0.0]), np.array([2.0, 0.0, 0.0])) is True
    assert o.segment_intersects(np.array([2.0, 2.0, 0.0]), np.array([3.0, 2.0, 0.0])) is False


def test_obb_aabb_envelope():
    # 90° rotation around y: half_extents (2, 1, 1) → world AABB ±(2, 1, 2) approximately
    axes = (0.0, 0.0, 1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 0.0)
    cfg = ObstacleOBB(center=(0, 0, 0), half_extents=(2.0, 1.0, 1.0), axes=axes)
    o = OBBObstacle(cfg)
    amin, amax = o.aabb()
    # After 90° y rotation, local x-axis maps to world z (length 2), local z-axis maps to world x (length 1)
    # Expanded world AABB = max projection of local half-extents on each world axis
    assert amin[0] == pytest.approx(-1.0, abs=1e-9)
    assert amax[0] == pytest.approx(1.0, abs=1e-9)
    assert amin[2] == pytest.approx(-2.0, abs=1e-9)
    assert amax[2] == pytest.approx(2.0, abs=1e-9)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_obstacles.py -k obb -v`
Expected: FAIL.

- [ ] **Step 3: Add OBBObstacle to obstacles.py**

Append to `src/palubicki/sim/obstacles.py`:

```python
from palubicki.config import ObstacleOBB


class OBBObstacle:
    """Oriented box. `axes` is a row-major 3x3 orthonormal rotation matrix R that
    maps WORLD vectors to LOCAL (point_local = R @ (point_world - center)). A point
    is inside iff |local[i]| <= half_extents[i] for all i."""

    def __init__(self, cfg: ObstacleOBB):
        self._center = np.asarray(cfg.center, dtype=np.float64)
        self._half = np.asarray(cfg.half_extents, dtype=np.float64)
        self._R = np.asarray(cfg.axes, dtype=np.float64).reshape(3, 3)

    def _to_local(self, pts: np.ndarray) -> np.ndarray:
        return (pts - self._center) @ self._R.T

    def contains(self, points: np.ndarray) -> np.ndarray:
        pts = np.asarray(points, dtype=np.float64)
        if pts.shape[0] == 0:
            return np.zeros(0, dtype=bool)
        local = self._to_local(pts)
        return np.all(np.abs(local) <= self._half, axis=1)

    def segment_intersects(self, p0: np.ndarray, p1: np.ndarray) -> bool:
        # Transform segment into local frame, then slab test against [-half, +half]
        p0_l = self._to_local(np.asarray(p0, dtype=np.float64).reshape(1, 3))[0]
        p1_l = self._to_local(np.asarray(p1, dtype=np.float64).reshape(1, 3))[0]
        d = p1_l - p0_l
        t_enter = 0.0
        t_exit = 1.0
        for axis in range(3):
            if abs(d[axis]) < 1e-12:
                if p0_l[axis] < -self._half[axis] or p0_l[axis] > self._half[axis]:
                    return False
                continue
            inv = 1.0 / d[axis]
            t1 = (-self._half[axis] - p0_l[axis]) * inv
            t2 = (self._half[axis] - p0_l[axis]) * inv
            t_lo, t_hi = (t1, t2) if t1 <= t2 else (t2, t1)
            t_enter = max(t_enter, t_lo)
            t_exit = min(t_exit, t_hi)
            if t_enter > t_exit:
                return False
        return t_enter <= t_exit

    def aabb(self) -> tuple[np.ndarray, np.ndarray]:
        # World AABB = center ± |R^T| @ half_extents (extent of all 8 corners projected
        # to world axes equals sum of |R^T_ij| * half_extents_j for each world axis i).
        extent = np.abs(self._R.T) @ self._half
        return self._center - extent, self._center + extent

    def voxelize(self, grid) -> np.ndarray:
        raise NotImplementedError("voxelize: implemented in Task 13")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_obstacles.py -k obb -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/obstacles.py tests/sim/test_obstacles.py
git commit -m "feat(sim): OBBObstacle (oriented box with local-frame slab test)"
```

---

## Task 8: ObstacleMesh implementation

**Files:**
- Modify: `src/palubicki/sim/obstacles.py`
- Modify: `tests/sim/test_obstacles.py`
- Create: `tests/fixtures/unit_cube.obj`

- [ ] **Step 1: Create fixture cube OBJ**

Create `tests/fixtures/unit_cube.obj` with a cube from (0,0,0) to (1,1,1):

```
v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
v 0 0 1
v 1 0 1
v 1 1 1
v 0 1 1
f 1 2 3 4
f 5 8 7 6
f 1 5 6 2
f 2 6 7 3
f 3 7 8 4
f 4 8 5 1
```

- [ ] **Step 2: Write failing tests**

Append to `tests/sim/test_obstacles.py`:

```python
from pathlib import Path
from palubicki.config import ObstacleMesh
from palubicki.sim.obstacles import MeshObstacle


CUBE_OBJ = Path(__file__).parent.parent / "fixtures" / "unit_cube.obj"


def test_mesh_contains_unit_cube():
    o = MeshObstacle(ObstacleMesh(path=CUBE_OBJ))
    pts = np.array([
        [0.5, 0.5, 0.5],   # inside
        [2.0, 0.5, 0.5],   # outside
        [-0.1, 0.5, 0.5],  # outside
    ])
    out = o.contains(pts)
    assert out[0]
    assert not out[1]
    assert not out[2]


def test_mesh_translate_scale():
    o = MeshObstacle(ObstacleMesh(path=CUBE_OBJ, translate=(10.0, 0.0, 0.0), scale=2.0))
    # Original cube was (0..1)^3; scaled to (0..2)^3 then translated by +10x → (10..12)^3
    pts = np.array([[11.0, 1.0, 1.0], [0.5, 0.5, 0.5], [11.0, 3.0, 1.0]])
    out = o.contains(pts)
    assert out.tolist() == [True, False, False]


def test_mesh_segment_traverse():
    o = MeshObstacle(ObstacleMesh(path=CUBE_OBJ))
    assert o.segment_intersects(np.array([-1.0, 0.5, 0.5]), np.array([2.0, 0.5, 0.5])) is True


def test_mesh_segment_miss():
    o = MeshObstacle(ObstacleMesh(path=CUBE_OBJ))
    assert o.segment_intersects(np.array([2.0, 2.0, 2.0]), np.array([3.0, 2.0, 2.0])) is False


def test_mesh_segment_endpoint_inside():
    o = MeshObstacle(ObstacleMesh(path=CUBE_OBJ))
    assert o.segment_intersects(np.array([2.0, 0.5, 0.5]), np.array([0.5, 0.5, 0.5])) is True


def test_mesh_aabb():
    o = MeshObstacle(ObstacleMesh(path=CUBE_OBJ, translate=(1.0, 2.0, 3.0), scale=2.0))
    amin, amax = o.aabb()
    np.testing.assert_allclose(amin, [1.0, 2.0, 3.0])
    np.testing.assert_allclose(amax, [3.0, 4.0, 5.0])
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_obstacles.py -k mesh -v`
Expected: FAIL with `ImportError` or `NameError`.

- [ ] **Step 4: Add MeshObstacle to obstacles.py**

Append to `src/palubicki/sim/obstacles.py`:

```python
from palubicki.config import ObstacleMesh


class MeshObstacle:
    """Wraps a trimesh.Trimesh. Supports translate + uniform scale (applied at load).
    Uses trimesh.contains for point-in-mesh and ray casting for segment intersection."""

    def __init__(self, cfg: ObstacleMesh):
        import trimesh
        mesh = trimesh.load(str(cfg.path), force="mesh")
        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError(f"path {cfg.path} did not load as a single Trimesh")
        mesh = mesh.copy()
        if cfg.scale != 1.0:
            mesh.apply_scale(cfg.scale)
        if cfg.translate != (0.0, 0.0, 0.0):
            mesh.apply_translation(np.asarray(cfg.translate, dtype=np.float64))
        self._mesh = mesh
        self._ray = trimesh.ray.ray_triangle.RayMeshIntersector(mesh)

    def contains(self, points: np.ndarray) -> np.ndarray:
        pts = np.asarray(points, dtype=np.float64)
        if pts.shape[0] == 0:
            return np.zeros(0, dtype=bool)
        return self._mesh.contains(pts)

    def segment_intersects(self, p0: np.ndarray, p1: np.ndarray) -> bool:
        p0 = np.asarray(p0, dtype=np.float64)
        p1 = np.asarray(p1, dtype=np.float64)
        # Endpoint-inside test (cheap; covers buds-already-inside cases)
        if bool(self._mesh.contains(p0.reshape(1, 3))[0]) or bool(self._mesh.contains(p1.reshape(1, 3))[0]):
            return True
        d = p1 - p0
        seg_len = float(np.linalg.norm(d))
        if seg_len < 1e-12:
            return False
        direction = d / seg_len
        locations, _, _ = self._ray.intersects_location(
            ray_origins=p0.reshape(1, 3),
            ray_directions=direction.reshape(1, 3),
            multiple_hits=False,
        )
        if len(locations) == 0:
            return False
        # Distance from p0 to the first hit
        dist = float(np.linalg.norm(locations[0] - p0))
        return dist <= seg_len

    def aabb(self) -> tuple[np.ndarray, np.ndarray]:
        bb = self._mesh.bounds   # (2, 3): [[xmin, ymin, zmin], [xmax, ymax, zmax]]
        return bb[0].astype(np.float64), bb[1].astype(np.float64)

    def voxelize(self, grid) -> np.ndarray:
        raise NotImplementedError("voxelize: implemented in Task 13")

    @property
    def trimesh(self):
        return self._mesh
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_obstacles.py -k mesh -v`
Expected: 6 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/obstacles.py tests/sim/test_obstacles.py tests/fixtures/unit_cube.obj
git commit -m "feat(sim): MeshObstacle via trimesh (contains + ray segment test)"
```

---

## Task 9: Obstacle helpers + factory

**Files:**
- Modify: `src/palubicki/sim/obstacles.py`
- Modify: `tests/sim/test_obstacles.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/sim/test_obstacles.py`:

```python
from palubicki.config import ForestConfig
from palubicki.sim.obstacles import (
    build_obstacles, filter_markers, segment_blocked, any_contains,
)


def test_build_obstacles_dispatches_by_kind():
    cfg = ForestConfig(obstacles=(
        ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)),
        ObstacleSphere(center=(5, 0, 0), radius=2.0),
    ))
    obs = build_obstacles(cfg)
    assert isinstance(obs[0], AABBObstacle)
    assert isinstance(obs[1], SphereObstacle)


def test_filter_markers_drops_inside():
    obs = [AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))]
    pts = np.array([[0.5, 0.5, 0.5], [2.0, 0.5, 0.5], [0.0, 0.0, 0.0]])
    out = filter_markers(pts, obs)
    assert out.shape == (1, 3)
    assert np.allclose(out[0], [2.0, 0.5, 0.5])


def test_filter_markers_empty_obstacles_passthrough():
    pts = np.array([[1.0, 2.0, 3.0]])
    out = filter_markers(pts, [])
    np.testing.assert_array_equal(out, pts)


def test_segment_blocked_any_obstacle():
    obs = [
        AABBObstacle(ObstacleAABB(min=(10, 10, 10), max=(11, 11, 11))),
        SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0)),
    ]
    assert segment_blocked(np.array([-2.0, 0.0, 0.0]), np.array([2.0, 0.0, 0.0]), obs) is True


def test_segment_blocked_no_obstacle():
    assert segment_blocked(np.array([0, 0, 0]), np.array([1, 1, 1]), []) is False


def test_any_contains_true_when_any_obstacle_contains():
    obs = [SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0))]
    assert any_contains(np.array([0.5, 0.0, 0.0]), obs) is True
    assert any_contains(np.array([2.0, 0.0, 0.0]), obs) is False


def test_any_contains_empty_obstacles_false():
    assert any_contains(np.array([0.0, 0.0, 0.0]), []) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_obstacles.py -k "build_obstacles or filter_markers or segment_blocked or any_contains" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add helpers to obstacles.py**

Append to `src/palubicki/sim/obstacles.py`:

```python
def build_obstacles(cfg) -> list:
    """Instantiate concrete obstacles from ForestConfig.obstacles."""
    out = []
    for entry in cfg.obstacles:
        if isinstance(entry, ObstacleAABB):
            out.append(AABBObstacle(entry))
        elif isinstance(entry, ObstacleSphere):
            out.append(SphereObstacle(entry))
        elif isinstance(entry, ObstacleOBB):
            out.append(OBBObstacle(entry))
        elif isinstance(entry, ObstacleMesh):
            out.append(MeshObstacle(entry))
        else:
            raise TypeError(f"unknown obstacle config type: {type(entry).__name__}")
    return out


def filter_markers(positions: np.ndarray, obstacles: list) -> np.ndarray:
    """Drop positions that fall inside any obstacle."""
    if len(obstacles) == 0 or len(positions) == 0:
        return positions
    keep = np.ones(len(positions), dtype=bool)
    for o in obstacles:
        keep &= ~o.contains(positions)
    return positions[keep]


def segment_blocked(p0: np.ndarray, p1: np.ndarray, obstacles: list) -> bool:
    """True iff any obstacle blocks the segment [p0, p1]."""
    for o in obstacles:
        if o.segment_intersects(p0, p1):
            return True
    return False


def any_contains(point: np.ndarray, obstacles: list) -> bool:
    """True iff `point` lies inside any obstacle."""
    if len(obstacles) == 0:
        return False
    pts = np.asarray(point, dtype=np.float64).reshape(1, 3)
    for o in obstacles:
        if bool(o.contains(pts)[0]):
            return True
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_obstacles.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/obstacles.py tests/sim/test_obstacles.py
git commit -m "feat(sim): obstacle helpers (build, filter_markers, segment_blocked, any_contains)"
```

---

## Task 10: `per_tree_config` helper

**Files:**
- Create: `src/palubicki/sim/forest.py`
- Create: `tests/sim/test_forest.py`

- [ ] **Step 1: Write failing tests**

Create `tests/sim/test_forest.py`:

```python
from pathlib import Path

import numpy as np
import pytest

from palubicki.config import (
    Config, EnvelopeConfig, ForestSeed, GeomConfig, LightConfig, PhyllotaxyConfig,
    SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.sim.forest import per_tree_config


def _base_cfg(**overrides) -> Config:
    return Config(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0),
        sim=SimConfig(), tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=Path("/tmp/x.glb"), seed=7,
        **overrides,
    )


def test_per_tree_config_translates_envelope():
    cfg = _base_cfg()
    seed = ForestSeed(position=(5.0, 0.0, 5.0))
    out = per_tree_config(cfg, seed, tree_index=0)
    assert out.envelope.center == (5.0, 0.0, 5.0)
    assert out.envelope.rx == 2.0   # other envelope fields preserved


def test_per_tree_config_applies_dotted_overrides():
    cfg = _base_cfg()
    seed = ForestSeed(
        position=(0.0, 0.0, 0.0),
        overrides={"envelope.shape": "cone", "tropism.w_gravity": 0.5},
    )
    out = per_tree_config(cfg, seed, tree_index=0)
    assert out.envelope.shape == "cone"
    assert out.tropism.w_gravity == 0.5


def test_per_tree_config_seed_derivation():
    cfg = _base_cfg()
    s_none = ForestSeed(position=(0.0, 0.0, 0.0))
    s_explicit = ForestSeed(position=(0.0, 0.0, 0.0), seed=99)
    assert per_tree_config(cfg, s_none, tree_index=3).seed == 7 + 3
    assert per_tree_config(cfg, s_explicit, tree_index=3).seed == 99


def test_per_tree_config_does_not_mutate_input():
    cfg = _base_cfg()
    seed = ForestSeed(position=(1.0, 0.0, 1.0), overrides={"sim.r_perception": 0.9})
    _ = per_tree_config(cfg, seed, tree_index=0)
    assert cfg.envelope.center == (0.0, 0.0, 0.0)   # original untouched
    assert cfg.sim.r_perception == 0.6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_forest.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Create forest.py with per_tree_config**

Create `src/palubicki/sim/forest.py`:

```python
# src/palubicki/sim/forest.py
from __future__ import annotations

from dataclasses import fields, replace
from typing import TYPE_CHECKING

import numpy as np

from palubicki.config import Config, EnvelopeConfig, ForestSeed

if TYPE_CHECKING:
    from palubicki.sim.markers import MarkerCloud
    from palubicki.sim.tree import Tree


_SECTION_FIELDS = {
    "envelope", "sim", "tropism", "phyllotaxy", "shedding", "geom", "light",
}


def per_tree_config(cfg: Config, seed_entry: ForestSeed, tree_index: int) -> Config:
    """Return a new Config: cfg with seed_entry.overrides applied (dotted keys) and
    envelope.center translated to seed_entry.position."""
    section_updates: dict[str, dict] = {s: {} for s in _SECTION_FIELDS}
    top_updates: dict[str, object] = {}

    for dotted, value in seed_entry.overrides.items():
        parts = dotted.split(".", 1)
        if len(parts) == 1:
            top_updates[parts[0]] = value
        else:
            section, key = parts
            if section not in _SECTION_FIELDS:
                from palubicki.config import ConfigError
                raise ConfigError(f"unknown section in override: {dotted!r}")
            section_updates[section][key] = value

    # Apply section overrides via replace()
    new_sections = {}
    for s in _SECTION_FIELDS:
        cur = getattr(cfg, s)
        updates = section_updates[s]
        if updates:
            new_sections[s] = replace(cur, **updates)
        else:
            new_sections[s] = cur

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_forest.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/forest.py tests/sim/test_forest.py
git commit -m "feat(sim): per_tree_config helper (apply overrides + translate envelope)"
```

---

## Task 11: `forest_light_bounds` helper

**Files:**
- Modify: `src/palubicki/sim/forest.py`
- Modify: `tests/sim/test_forest.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/sim/test_forest.py`:

```python
from palubicki.config import ObstacleAABB
from palubicki.sim.forest import forest_light_bounds
from palubicki.sim.obstacles import AABBObstacle


def test_forest_light_bounds_single_envelope_no_obstacle():
    env = EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, center=(0.0, 0.0, 0.0), shape="ellipsoid")
    origin, size = forest_light_bounds([env], obstacles=[])
    # Envelope AABB: x ∈ ±2, y ∈ ±3, z ∈ ±2
    # 10% pad below/above on x,z → factor 1.2; 10% below + 30% above on y → factor 1.4
    extent = np.array([4.0, 6.0, 4.0])
    expected_origin = np.array([-2.0, -3.0, -2.0]) - 0.1 * extent
    np.testing.assert_allclose(origin, expected_origin)
    expected_size = extent + np.array([0.2 * 4.0, 0.4 * 6.0, 0.2 * 4.0])
    np.testing.assert_allclose(size, expected_size)


def test_forest_light_bounds_multi_envelope_union():
    env_a = EnvelopeConfig(rx=1.0, ry=1.0, rz=1.0, center=(0.0, 0.0, 0.0), shape="ellipsoid")
    env_b = EnvelopeConfig(rx=1.0, ry=1.0, rz=1.0, center=(5.0, 0.0, 0.0), shape="ellipsoid")
    origin, size = forest_light_bounds([env_a, env_b], obstacles=[])
    # AABB union spans x in [-1, 6], y in [-1, 1], z in [-1, 1]
    extent = np.array([7.0, 2.0, 2.0])
    expected_origin = np.array([-1.0, -1.0, -1.0]) - 0.1 * extent
    np.testing.assert_allclose(origin, expected_origin)
    np.testing.assert_allclose(size, extent + np.array([0.2 * 7.0, 0.4 * 2.0, 0.2 * 2.0]))


def test_forest_light_bounds_with_obstacle_extends_aabb():
    env = EnvelopeConfig(rx=1.0, ry=1.0, rz=1.0, center=(0.0, 0.0, 0.0), shape="ellipsoid")
    obstacle = AABBObstacle(ObstacleAABB(min=(10.0, -2.0, -2.0), max=(12.0, 0.0, 2.0)))
    origin, size = forest_light_bounds([env], obstacles=[obstacle])
    # Union AABB: x in [-1, 12], y in [-2, 1], z in [-2, 2]
    extent = np.array([13.0, 3.0, 4.0])
    expected_origin = np.array([-1.0, -2.0, -2.0]) - 0.1 * extent
    np.testing.assert_allclose(origin, expected_origin)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_forest.py -k forest_light_bounds -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add forest_light_bounds to forest.py**

Append to `src/palubicki/sim/forest.py`:

```python
def _envelope_aabb(env: EnvelopeConfig) -> tuple[np.ndarray, np.ndarray]:
    c = np.asarray(env.center, dtype=np.float64)
    if env.shape == "sphere":
        r = env.rx
        return c - r, c + r
    if env.shape == "ellipsoid":
        r = np.array([env.rx, env.ry, env.rz])
        return c - r, c + r
    if env.shape == "half_ellipsoid":
        amin = c - np.array([env.rx, 0.0, env.rz])
        amax = c + np.array([env.rx, env.ry, env.rz])
        return amin, amax
    if env.shape == "cone":
        amin = c - np.array([env.rx, 0.0, env.rz])
        amax = c + np.array([env.rx, env.ry, env.rz])
        return amin, amax
    raise ValueError(f"unknown envelope shape: {env.shape}")


def forest_light_bounds(envelopes: list[EnvelopeConfig], obstacles: list) -> tuple[np.ndarray, np.ndarray]:
    """Auto-fit AABB(union envelopes + obstacles) + V2-style sky margin
    (10% pad in x/z below/above, 10% below + 30% above in y)."""
    mins = []
    maxs = []
    for env in envelopes:
        amin, amax = _envelope_aabb(env)
        mins.append(amin)
        maxs.append(amax)
    for o in obstacles:
        amin, amax = o.aabb()
        mins.append(amin)
        maxs.append(amax)
    aabb_min = np.min(np.stack(mins), axis=0)
    aabb_max = np.max(np.stack(maxs), axis=0)
    extent = aabb_max - aabb_min
    origin = aabb_min - 0.1 * extent
    margin_top = np.array([0.1 * extent[0], 0.3 * extent[1], 0.1 * extent[2]])
    size = (aabb_max + margin_top) - origin
    return origin, size
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_forest.py -k forest_light_bounds -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/forest.py tests/sim/test_forest.py
git commit -m "feat(sim): forest_light_bounds helper (AABB union + sky margin)"
```

---

## Task 12: `Forest` dataclass + `build_forest`

**Files:**
- Modify: `src/palubicki/sim/forest.py`
- Modify: `tests/sim/test_forest.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/sim/test_forest.py`:

```python
from palubicki.sim.forest import Forest, build_forest, all_active_buds


def test_build_forest_single_tree_default():
    """When forest.seeds is empty, build_forest creates a 1-tree forest from cfg.envelope."""
    cfg = _base_cfg()
    forest = build_forest(cfg)
    assert isinstance(forest, Forest)
    assert len(forest.trees) == 1
    assert forest.obstacles == []
    assert forest.markers.alive_count == cfg.envelope.marker_count
    # Root is at envelope.center (translated to y=0)
    root = forest.trees[0].root
    assert tuple(root.position) == (cfg.envelope.center[0], 0.0, cfg.envelope.center[2])


def test_build_forest_two_trees():
    from palubicki.config import ForestConfig, ForestSeed
    cfg = _base_cfg(forest=ForestConfig(seeds=(
        ForestSeed(position=(0.0, 0.0, 0.0)),
        ForestSeed(position=(5.0, 0.0, 0.0)),
    )))
    forest = build_forest(cfg)
    assert len(forest.trees) == 2
    # Each tree has its own root at the seed position (translated to y=0)
    assert tuple(forest.trees[0].root.position) == (0.0, 0.0, 0.0)
    assert tuple(forest.trees[1].root.position) == (5.0, 0.0, 0.0)
    # Markers: 2 × marker_count, minus 0 inside obstacles
    assert forest.markers.alive_count == 2 * cfg.envelope.marker_count


def test_build_forest_obstacles_filter_markers():
    from palubicki.config import ForestConfig, ForestSeed, ObstacleAABB
    cfg = _base_cfg(forest=ForestConfig(
        seeds=(ForestSeed(position=(0.0, 0.0, 0.0)),),
        # Big AABB covering the lower half of the envelope (y < 0)
        obstacles=(ObstacleAABB(min=(-5, -5, -5), max=(5, 0, 5)),),
    ))
    forest = build_forest(cfg)
    # About half the markers should have been dropped
    assert 0.3 * cfg.envelope.marker_count < forest.markers.alive_count < 0.7 * cfg.envelope.marker_count


def test_all_active_buds_deterministic_order():
    from palubicki.config import ForestConfig, ForestSeed
    cfg = _base_cfg(forest=ForestConfig(seeds=(
        ForestSeed(position=(0.0, 0.0, 0.0)),
        ForestSeed(position=(5.0, 0.0, 0.0)),
    )))
    forest = build_forest(cfg)
    buds = all_active_buds(forest)
    # Initially each tree has 1 root bud → 2 total, in tree order
    assert len(buds) == 2
    assert buds[0] is forest.trees[0].active_buds[0]
    assert buds[1] is forest.trees[1].active_buds[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_forest.py -k "build_forest or all_active_buds" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add Forest dataclass and build_forest**

Append to `src/palubicki/sim/forest.py`:

```python
from dataclasses import dataclass, field as _dc_field

from palubicki.sim.markers import MarkerCloud
from palubicki.sim.envelope import sample_markers
from palubicki.sim.obstacles import build_obstacles, filter_markers
from palubicki.sim.tree import Bud, Node, Tree


@dataclass
class Forest:
    trees: list[Tree]
    seeds: list[ForestSeed]
    obstacles: list
    per_tree_cfgs: list[Config]
    markers: MarkerCloud
    light_grid: object | None = None              # LightGrid | None — typed loosely to avoid cycles
    obstacle_voxel_mask: np.ndarray | None = None


def all_active_buds(forest: Forest) -> list[Bud]:
    """Flatten active buds across trees in (tree_index, bud_index_in_tree) order."""
    out: list[Bud] = []
    for tree in forest.trees:
        out.extend(tree.active_buds)
    return out


def build_forest(cfg: Config) -> Forest:
    """Build the initial Forest from cfg.

    - If cfg.forest.seeds is empty, create one tree using cfg.envelope as-is.
    - Otherwise, derive a per_tree_config for each seed; sample its markers.
    - Concatenate all markers and filter via obstacles.
    - Light grid is created LATER (in simulator) if cfg.light.enabled.
    """
    obstacles = build_obstacles(cfg.forest)
    seeds_input = cfg.forest.seeds
    if not seeds_input:
        # Single-tree mode: one synthetic seed at envelope.center
        synthetic_seed = ForestSeed(position=tuple(cfg.envelope.center))
        seeds_list = [synthetic_seed]
        per_tree_cfgs = [cfg]
    else:
        seeds_list = list(seeds_input)
        per_tree_cfgs = [per_tree_config(cfg, s, i) for i, s in enumerate(seeds_list)]

    # Sample markers per-tree using each tree's own RNG/envelope
    marker_chunks: list[np.ndarray] = []
    trees: list[Tree] = []
    for tree_index, ptc in enumerate(per_tree_cfgs):
        rng = np.random.default_rng(ptc.seed)
        marker_chunks.append(sample_markers(ptc.envelope, rng))

        # Build root bud at seed position (y forced to 0, matching V2 simulate)
        root_pos = np.array([ptc.envelope.center[0], 0.0, ptc.envelope.center[2]], dtype=float)
        root = Node(position=root_pos)
        bud = Bud(
            position=root_pos.copy(),
            direction=np.array([0.0, 1.0, 0.0]),
            axis_order=0,
            parent_node=root,
        )
        root.terminal_bud = bud
        trees.append(Tree(root=root, active_buds=[bud]))

    all_markers = np.concatenate(marker_chunks, axis=0) if marker_chunks else np.zeros((0, 3))
    filtered = filter_markers(all_markers, obstacles)
    cloud = MarkerCloud(filtered)

    return Forest(
        trees=trees,
        seeds=seeds_list,
        obstacles=obstacles,
        per_tree_cfgs=per_tree_cfgs,
        markers=cloud,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_forest.py -k "build_forest or all_active_buds" -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/forest.py tests/sim/test_forest.py
git commit -m "feat(sim): Forest dataclass + build_forest (samples markers, filters via obstacles)"
```

---

## Task 13: Obstacle `voxelize()` implementations

**Files:**
- Modify: `src/palubicki/sim/obstacles.py`
- Create: `tests/sim/test_obstacle_voxelize.py`

- [ ] **Step 1: Write failing tests**

Create `tests/sim/test_obstacle_voxelize.py`:

```python
from pathlib import Path

import numpy as np

from palubicki.config import (
    LightConfig, ObstacleAABB, ObstacleSphere, ObstacleOBB, ObstacleMesh,
    EnvelopeConfig,
)
from palubicki.sim.light import LightGrid
from palubicki.sim.obstacles import (
    AABBObstacle, SphereObstacle, OBBObstacle, MeshObstacle,
)


def _grid(origin, size, resolution):
    cfg = LightConfig(grid_origin=tuple(origin), grid_size=tuple(size), grid_resolution=resolution)
    env = EnvelopeConfig()
    return LightGrid.from_config(cfg, env)


def test_voxelize_aabb_central_cells():
    grid = _grid(origin=(0, 0, 0), size=(8, 8, 8), resolution=(8, 8, 8))
    obs = AABBObstacle(ObstacleAABB(min=(2.5, 2.5, 2.5), max=(5.5, 5.5, 5.5)))
    mask = obs.voxelize(grid)
    assert mask.shape == (8, 8, 8)
    # Cells whose center lies inside [2.5, 5.5]^3 are indices 3, 4, 5 (centers 3.5, 4.5, 5.5)
    # Cell center 5.5 is at the upper boundary; AABB.contains is inclusive
    expected_indices = np.array([3, 4, 5])
    for i in range(8):
        for j in range(8):
            for k in range(8):
                expected = i in expected_indices and j in expected_indices and k in expected_indices
                assert bool(mask[i, j, k]) == expected, f"cell {i,j,k}"


def test_voxelize_sphere():
    grid = _grid(origin=(-4, -4, -4), size=(8, 8, 8), resolution=(8, 8, 8))
    obs = SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=2.0))
    mask = obs.voxelize(grid)
    # Voxel at the center is inside
    # Center cell: index 4 (center coord = -4 + 4.5 = 0.5, distance to origin = ~0.87 < 2)
    assert bool(mask[4, 4, 4]) is True
    # Corner cell at (0, 0, 0) → center (-3.5, -3.5, -3.5), dist ~6 → outside
    assert bool(mask[0, 0, 0]) is False


def test_voxelize_obb_identity_matches_aabb():
    grid = _grid(origin=(0, 0, 0), size=(8, 8, 8), resolution=(8, 8, 8))
    aabb = AABBObstacle(ObstacleAABB(min=(2.5, 2.5, 2.5), max=(5.5, 5.5, 5.5)))
    obb = OBBObstacle(ObstacleOBB(center=(4.0, 4.0, 4.0), half_extents=(1.5, 1.5, 1.5)))
    mask_aabb = aabb.voxelize(grid)
    mask_obb = obb.voxelize(grid)
    np.testing.assert_array_equal(mask_aabb, mask_obb)


def test_voxelize_mesh_cube():
    grid = _grid(origin=(0, 0, 0), size=(4, 4, 4), resolution=(4, 4, 4))
    obs = MeshObstacle(ObstacleMesh(
        path=Path(__file__).parent.parent / "fixtures" / "unit_cube.obj",
        translate=(1.0, 1.0, 1.0),
        scale=2.0,
    ))
    # Cube spans world (1,1,1)..(3,3,3). Voxel size = 1. Cell centers: 0.5, 1.5, 2.5, 3.5.
    # Inside cube: indices where center ∈ (1, 3), i.e. indices 1 and 2.
    mask = obs.voxelize(grid)
    assert bool(mask[1, 1, 1]) is True
    assert bool(mask[2, 2, 2]) is True
    assert bool(mask[0, 0, 0]) is False
    assert bool(mask[3, 3, 3]) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_obstacle_voxelize.py -v`
Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement voxelize() on each obstacle**

Modify `src/palubicki/sim/obstacles.py`. Replace each `voxelize` stub with the implementation below (shared logic factored into a helper).

Add a module-level helper at the bottom of the file (after the helpers from Task 9):

```python
def _voxelize_via_centers(grid, contains_callable) -> np.ndarray:
    """Generic voxelization: build the array of cell centers, query contains(), reshape."""
    nx, ny, nz = grid.resolution
    i_idx = np.arange(nx)
    j_idx = np.arange(ny)
    k_idx = np.arange(nz)
    ii, jj, kk = np.meshgrid(i_idx, j_idx, k_idx, indexing="ij")
    centers = (grid.origin
               + (np.stack([ii, jj, kk], axis=-1).astype(np.float64) + 0.5)
               * grid.cell_size)   # (nx, ny, nz, 3)
    flat = centers.reshape(-1, 3)
    inside = contains_callable(flat)
    return inside.reshape(nx, ny, nz)
```

Then replace each `voxelize` stub:

- In `AABBObstacle`:

```python
    def voxelize(self, grid) -> np.ndarray:
        return _voxelize_via_centers(grid, self.contains)
```

- In `SphereObstacle`:

```python
    def voxelize(self, grid) -> np.ndarray:
        return _voxelize_via_centers(grid, self.contains)
```

- In `OBBObstacle`:

```python
    def voxelize(self, grid) -> np.ndarray:
        return _voxelize_via_centers(grid, self.contains)
```

- In `MeshObstacle`:

```python
    def voxelize(self, grid) -> np.ndarray:
        return _voxelize_via_centers(grid, self.contains)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_obstacle_voxelize.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Confirm full obstacles suite still green**

Run: `.venv/bin/pytest tests/sim/test_obstacles.py tests/sim/test_obstacle_voxelize.py -v`
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/obstacles.py tests/sim/test_obstacle_voxelize.py
git commit -m "feat(sim): obstacle.voxelize() via cell-center sampling"
```

---

## Task 14: `LightGrid.rebuild_from_forest` + obstacle mask application

**Files:**
- Modify: `src/palubicki/sim/light.py`
- Modify: `tests/sim/test_light_grid.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/sim/test_light_grid.py`:

```python
def test_rebuild_from_forest_two_trees_lai_sums():
    """LAI from a forest of 2 trees = sum of per-tree LAI (when injected at the
    same cells; we make this trivial by giving each tree a single leaf at a
    distinct cell)."""
    from palubicki.config import (
        EnvelopeConfig, ForestConfig, ForestSeed, LightConfig,
    )
    from palubicki.sim.forest import build_forest
    from palubicki.sim.light import LightGrid
    from palubicki.sim.tree import Bud, BudState, Node, Tree

    # Build a forest manually: 2 trees, each with a single terminal-bud leaf
    # at a known position.
    env = EnvelopeConfig(rx=1, ry=1, rz=1)
    light_cfg = LightConfig(
        enabled=True, grid_origin=(0, 0, 0), grid_size=(2, 2, 2),
        grid_resolution=(2, 2, 2), leaf_area=0.04, internode_area_scale=0.0,
    )
    grid = LightGrid.from_config(light_cfg, env)

    # Two trees, each at a separate position, both contributing one leaf
    root_a = Node(position=np.array([0.5, 0.5, 0.5]))
    bud_a = Bud(position=root_a.position.copy(), direction=np.array([0, 1, 0]),
                axis_order=0, parent_node=root_a)
    root_a.terminal_bud = bud_a
    tree_a = Tree(root=root_a, active_buds=[bud_a])

    root_b = Node(position=np.array([1.5, 0.5, 0.5]))
    bud_b = Bud(position=root_b.position.copy(), direction=np.array([0, 1, 0]),
                axis_order=0, parent_node=root_b)
    root_b.terminal_bud = bud_b
    tree_b = Tree(root=root_b, active_buds=[bud_b])

    from palubicki.sim.forest import Forest
    forest = Forest(
        trees=[tree_a, tree_b],
        seeds=[],
        obstacles=[],
        per_tree_cfgs=[],
        markers=None,   # type: ignore[arg-type]
    )

    grid.rebuild_from_forest(forest, light_cfg, r_tip=0.005, exponent=2.49)

    cell_volume = float(np.prod(grid.cell_size))
    expected_lai = light_cfg.leaf_area / cell_volume
    # Cell (0,0,0) holds tree_a's leaf; cell (1,0,0) holds tree_b's leaf
    assert grid.lai[0, 0, 0] == np.float32(expected_lai)
    assert grid.lai[1, 0, 0] == np.float32(expected_lai)


def test_rebuild_from_forest_applies_obstacle_mask():
    from palubicki.config import (
        EnvelopeConfig, ForestConfig, ForestSeed, LightConfig, ObstacleAABB,
    )
    from palubicki.sim.forest import build_forest
    from palubicki.sim.light import LightGrid
    from palubicki.sim.obstacles import LAI_OPAQUE

    env = EnvelopeConfig()
    light_cfg = LightConfig(
        enabled=True, grid_origin=(0, 0, 0), grid_size=(4, 4, 4),
        grid_resolution=(4, 4, 4),
    )
    grid = LightGrid.from_config(light_cfg, env)

    # Build a minimal forest with an obstacle and a precomputed mask
    from palubicki.sim.obstacles import AABBObstacle
    obstacle = AABBObstacle(ObstacleAABB(min=(0.0, 0.0, 0.0), max=(2.0, 2.0, 2.0)))
    mask = obstacle.voxelize(grid)
    assert mask.sum() > 0

    from palubicki.sim.forest import Forest
    forest = Forest(
        trees=[],
        seeds=[],
        obstacles=[obstacle],
        per_tree_cfgs=[],
        markers=None,   # type: ignore[arg-type]
        obstacle_voxel_mask=mask,
    )

    grid.rebuild_from_forest(forest, light_cfg, r_tip=0.005, exponent=2.49)

    # Cells in mask should be LAI_OPAQUE; others zero
    assert (grid.lai[mask] == np.float32(LAI_OPAQUE)).all()
    assert (grid.lai[~mask] == np.float32(0.0)).all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_light_grid.py -k "rebuild_from_forest" -v`
Expected: FAIL (`rebuild_from_forest` method does not exist).

- [ ] **Step 3: Add rebuild_from_forest to LightGrid**

In `src/palubicki/sim/light.py`, locate the `LightGrid` class and add a new method right after `rebuild_from_tree` (before `sample_transmission`):

```python
    def rebuild_from_forest(
        self,
        forest,
        cfg: LightConfig,
        *,
        r_tip: float | None = None,
        exponent: float | None = None,
    ) -> None:
        """Full rebuild for a forest. Zero LAI → inject leaves+internodes per tree →
        apply obstacle mask (lai[mask] = LAI_OPAQUE)."""
        from palubicki.sim.obstacles import LAI_OPAQUE

        self.lai.fill(0.0)
        cell_volume = float(np.prod(self.cell_size))
        if cell_volume <= 0:
            if forest.obstacle_voxel_mask is not None:
                self.lai[forest.obstacle_voxel_mask] = np.float32(LAI_OPAQUE)
            return

        leaf_lai = cfg.leaf_area / cell_volume
        sub_step = float(np.min(self.cell_size))

        for tree in forest.trees:
            if r_tip is not None and exponent is not None:
                compute_radii(tree, r_tip=r_tip, exponent=exponent)
            stack = [tree.root]
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

        if forest.obstacle_voxel_mask is not None:
            self.lai[forest.obstacle_voxel_mask] = np.float32(LAI_OPAQUE)
```

- [ ] **Step 4: Run new tests**

Run: `.venv/bin/pytest tests/sim/test_light_grid.py -k "rebuild_from_forest" -v`
Expected: 2 PASSED.

- [ ] **Step 5: Confirm V2 light tests still pass**

Run: `.venv/bin/pytest tests/sim/test_light_grid.py -v`
Expected: ALL PASS (V2 tests untouched).

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/light.py tests/sim/test_light_grid.py
git commit -m "feat(sim): LightGrid.rebuild_from_forest with obstacle mask application"
```

---

## Task 15: Refactor `simulate` into `_iteration_step` (V2 bit-exact preserved)

**Files:**
- Modify: `src/palubicki/sim/simulator.py`
- Modify: `tests/sim/test_simulator.py`

This refactor extracts the per-iteration body of `simulate()` into a function operating on a `Forest`. The behavior MUST stay bit-exact V2 for the single-tree path (validated by existing goldens). New API: `simulate_forest()` is added but only delegated to from `simulate()` if `cfg.forest.seeds == ()` and `cfg.forest.obstacles == ()` — we'll wire it more aggressively in Task 16, but at this step we ONLY restructure; output must be identical.

- [ ] **Step 1: Write the V2 bit-exact preservation test**

Append to `tests/sim/test_simulator.py`:

```python
def test_simulate_v2_bit_exact_after_refactor(tmp_path):
    """After refactor: simulate(cfg) with empty forest must produce the same Tree as
    a hash-pinned baseline. The baseline is recomputed once and saved in the test."""
    import hashlib
    import json
    from palubicki.config import (
        Config, EnvelopeConfig, GeomConfig, LightConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    cfg = Config(
        envelope=EnvelopeConfig(rx=3, ry=5, rz=3, shape="ellipsoid", marker_count=5000),
        sim=SimConfig(max_iterations=10),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        light=LightConfig(),
        output=tmp_path / "x.glb",
        seed=42,
    )
    tree = simulate(cfg)
    positions = []
    stack = [tree.root]
    while stack:
        node = stack.pop()
        positions.append(tuple(node.position.tolist()))
        for iod in node.children_internodes:
            stack.append(iod.child_node)
    digest = hashlib.sha256(json.dumps(sorted(positions), sort_keys=True).encode()).hexdigest()
    # This hash is pinned by running ONCE against the V2 code, before refactor.
    # If the hash changes, the refactor broke bit-exactness — investigate.
    EXPECTED = None   # to be filled in Step 2 below
    assert EXPECTED is None or digest == EXPECTED, f"V2 bit-exact broken: {digest}"
    # Side-effect: print so we can copy the value if needed
    print(f"V2 hash: {digest}")
```

- [ ] **Step 2: Capture the baseline hash BEFORE refactor**

Run: `.venv/bin/pytest tests/sim/test_simulator.py::test_simulate_v2_bit_exact_after_refactor -v -s`
Expected: PASSES (EXPECTED is None so the assertion is skipped). Copy the printed `V2 hash:` value and replace `EXPECTED = None` with `EXPECTED = "<that hex string>"` in the test.

- [ ] **Step 3: Run test against original code to confirm pinned hash**

Run: `.venv/bin/pytest tests/sim/test_simulator.py::test_simulate_v2_bit_exact_after_refactor -v`
Expected: PASS. This is now the bit-exact V2 baseline guard.

- [ ] **Step 4: Refactor simulator.py**

Replace the body of `src/palubicki/sim/simulator.py` with a refactored version that introduces `_iteration_step(forest, cfg, iteration)` while preserving exact V2 behavior. Full replacement:

```python
# src/palubicki/sim/simulator.py
from __future__ import annotations

import logging
import time

import numpy as np

from palubicki.config import Config
from palubicki.sim.bh import allocate, compute_v_subtree
from palubicki.sim.forest import Forest, all_active_buds, build_forest, forest_light_bounds
from palubicki.sim.light import LightGrid
from palubicki.sim.light_perception import perceive_light
from palubicki.sim.phyllotaxy import lateral_bud_directions
from palubicki.sim.shedding import record_qualities, shed_low_quality
from palubicki.sim.space_competition import perceive
from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree
from palubicki.sim.tropisms import growth_direction

logger = logging.getLogger(__name__)


def simulate(cfg: Config) -> Tree:
    """Single-tree entry point (V1/V2 backward-compat).
    Delegates to simulate_forest and returns trees[0]."""
    forest = simulate_forest(cfg)
    return forest.trees[0]


def simulate_forest(cfg: Config) -> Forest:
    forest = build_forest(cfg)
    if cfg.light.enabled:
        forest.light_grid = LightGrid.from_config(cfg.light, cfg.envelope)
        # Adjust grid bounds for forest mode (auto-fit including obstacles)
        if cfg.light.grid_origin is None or cfg.light.grid_size is None:
            envs = [ptc.envelope for ptc in forest.per_tree_cfgs]
            origin, size = forest_light_bounds(envs, forest.obstacles)
            nx, ny, nz = cfg.light.grid_resolution
            forest.light_grid.origin = origin
            forest.light_grid.cell_size = size / np.array([nx, ny, nz], dtype=np.float64)
        # Voxelize obstacles into mask (one-shot)
        if forest.obstacles:
            mask = forest.obstacles[0].voxelize(forest.light_grid)
            for o in forest.obstacles[1:]:
                mask = mask | o.voxelize(forest.light_grid)
            forest.obstacle_voxel_mask = mask
    no_new_streak = 0
    t0 = time.time()
    state = _SimState()
    for iteration in range(cfg.sim.max_iterations):
        if not any(t.active_buds for t in forest.trees):
            break
        nodes_created = _iteration_step(forest, cfg, iteration, state, t0)
        if nodes_created == 0:
            no_new_streak += 1
        else:
            no_new_streak = 0
        if no_new_streak >= 2:
            break
    return forest


class _SimState:
    """Mutable counters shared across iterations: node_index for phyllotaxy."""
    def __init__(self):
        self.node_index = 0


def _iteration_step(forest: Forest, cfg: Config, iteration: int, state: _SimState, t0: float) -> int:
    """One simulation step on the whole forest. Returns total nodes created.

    For backward-compat: when len(trees)==1 and obstacles==[], this must produce
    bit-exactly the same evolution as V2's simulate() loop body."""
    light_grid = forest.light_grid
    union_buds = all_active_buds(forest)

    if light_grid is not None:
        light_grid.rebuild_from_forest(
            forest, cfg.light,
            r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent,
        )
        light_info = perceive_light(
            union_buds, light_grid, cfg.light,
            seed=int(np.random.SeedSequence([cfg.seed, iteration]).generate_state(1)[0]),
        )
    else:
        light_info = None

    res = perceive(
        union_buds, forest.markers,
        r_perception=cfg.sim.r_perception,
        theta_perception_deg=cfg.sim.theta_perception_deg,
    )

    if light_info is not None:
        quality = {b: res.quality[b] * light_info.light_factor[b] for b in union_buds}
    else:
        quality = dict(res.quality)

    new_node_positions: list[np.ndarray] = []
    nodes_created_this_step = 0

    for tree in forest.trees:
        v_subtree = compute_v_subtree(tree, quality)
        n_by_bud = allocate(
            tree, quality=quality,
            alpha=cfg.sim.alpha_basipetal, lambda_apical=cfg.sim.lambda_apical,
            v_subtree=v_subtree,
        )
        record_qualities(tree, v_subtree=v_subtree)

        new_active: list[Bud] = []
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

                # NOTE: obstacle blocking is added in Task 17.

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

                lateral_dirs = lateral_bud_directions(d, cfg.phyllotaxy, node_index=state.node_index)
                state.node_index += 1
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
                            [terminal], forest.markers,
                            r_perception=cfg.sim.r_perception,
                            theta_perception_deg=cfg.sim.theta_perception_deg,
                        )
                        res.direction[terminal] = sub_result.direction[terminal]
                        res.quality[terminal] = sub_result.quality[terminal]
                        if light_grid is not None and light_info is not None:
                            lf, grad = light_grid.sample_hemisphere(
                                terminal.position,
                                n_rays=cfg.light.n_rays,
                                light_direction=np.asarray(cfg.light.light_direction, dtype=np.float64),
                                k=cfg.light.k_absorption,
                                seed=int(np.random.SeedSequence([cfg.seed, iteration, step + 1]).generate_state(1)[0]),
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
        forest.markers.kill_near(np.array(new_node_positions), cfg.sim.r_kill)

    for tree in forest.trees:
        shed_low_quality(tree, cfg=cfg.shedding)

    logger.info(
        "[%.1fs] sim/iter %d/%d  trees=%d  nodes_created=%d",
        time.time() - t0,
        iteration + 1, cfg.sim.max_iterations,
        len(forest.trees),
        nodes_created_this_step,
    )
    return nodes_created_this_step
```

- [ ] **Step 5: Run the bit-exact preservation test**

Run: `.venv/bin/pytest tests/sim/test_simulator.py::test_simulate_v2_bit_exact_after_refactor -v`
Expected: PASS (the V2 hash is unchanged).

- [ ] **Step 6: Run all sim tests + goldens to confirm no regression**

Run: `.venv/bin/pytest tests/sim/ tests/golden/ -v`
Expected: ALL PASS — V2 goldens (light enabled/disabled, all envelopes) still hash-stable.

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/sim/simulator.py tests/sim/test_simulator.py
git commit -m "refactor(sim): extract _iteration_step into simulate_forest (V2 bit-exact)"
```

---

## Task 16: `simulate_forest` multi-tree case tests

**Files:**
- Modify: `tests/sim/test_simulator.py`

This task adds tests for actual multi-tree behavior (no obstacles yet — obstacles add growth-blocking in Task 17).

- [ ] **Step 1: Write multi-tree tests**

Append to `tests/sim/test_simulator.py`:

```python
def test_simulate_forest_two_distant_trees_grow_independently(tmp_path):
    """Two trees far apart (envelopes disjoint) → each tree grows independently."""
    from palubicki.config import (
        Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig, LightConfig,
        PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate_forest

    cfg = Config(
        envelope=EnvelopeConfig(rx=2, ry=3, rz=2, shape="ellipsoid", marker_count=3000),
        sim=SimConfig(max_iterations=8),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "x.glb", seed=42,
        forest=ForestConfig(seeds=(
            ForestSeed(position=(0.0, 0.0, 0.0)),
            ForestSeed(position=(20.0, 0.0, 0.0)),
        )),
    )
    forest = simulate_forest(cfg)
    assert len(forest.trees) == 2
    assert len(forest.trees[0].all_internodes) > 0
    assert len(forest.trees[1].all_internodes) > 0


def test_simulate_forest_reproducible(tmp_path):
    """Two runs with the same cfg produce identical trees."""
    from palubicki.config import (
        Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig, LightConfig,
        PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate_forest

    def make_cfg():
        return Config(
            envelope=EnvelopeConfig(rx=2, ry=3, rz=2, shape="ellipsoid", marker_count=2000),
            sim=SimConfig(max_iterations=6),
            tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
            output=tmp_path / "x.glb", seed=99,
            forest=ForestConfig(seeds=(
                ForestSeed(position=(0.0, 0.0, 0.0)),
                ForestSeed(position=(5.0, 0.0, 0.0)),
            )),
        )

    f1 = simulate_forest(make_cfg())
    f2 = simulate_forest(make_cfg())
    for t1, t2 in zip(f1.trees, f2.trees):
        assert len(t1.all_internodes) == len(t2.all_internodes)
        for i1, i2 in zip(t1.all_internodes, t2.all_internodes):
            np.testing.assert_allclose(i1.child_node.position, i2.child_node.position)
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/pytest tests/sim/test_simulator.py -k "two_distant or reproducible" -v`
Expected: 2 PASSED.

- [ ] **Step 3: Run full sim test suite for regression check**

Run: `.venv/bin/pytest tests/sim/ -v`
Expected: ALL PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/sim/test_simulator.py
git commit -m "test(sim): simulate_forest multi-tree growth and reproducibility"
```

---

## Task 17: Add obstacle blocking in growth loop

**Files:**
- Modify: `src/palubicki/sim/simulator.py`
- Modify: `tests/sim/test_simulator.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/sim/test_simulator.py`:

```python
def test_simulate_forest_segment_blocked_makes_bud_dormant(tmp_path):
    """A wall right above the root → the trunk bud becomes DORMANT after 1 step (cannot grow)."""
    from palubicki.config import (
        Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig, LightConfig,
        ObstacleAABB, PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate_forest
    from palubicki.sim.tree import BudState

    cfg = Config(
        envelope=EnvelopeConfig(rx=2, ry=3, rz=2, shape="ellipsoid", marker_count=2000),
        sim=SimConfig(max_iterations=4, internode_length=0.5),
        tropism=TropismConfig(w_gravity=0.0),   # don't fight gravity, just go up
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),  # disable shedding for clarity
        geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "x.glb", seed=42,
        forest=ForestConfig(
            seeds=(ForestSeed(position=(0.0, 0.0, 0.0)),),
            # Wall covering y ∈ [0.1, 0.4], i.e. blocks any segment going up from y=0
            obstacles=(ObstacleAABB(min=(-5, 0.1, -5), max=(5, 0.4, 5)),),
        ),
    )
    forest = simulate_forest(cfg)
    # The trunk can't grow upward — the bud should be DORMANT and the tree should
    # have at most 0 internodes from upward growth (laterals may still grow if any).
    upward_internodes = sum(
        1 for iod in forest.trees[0].all_internodes
        if (iod.child_node.position[1] - iod.parent_node.position[1]) > 0.05
    )
    assert upward_internodes == 0


def test_simulate_forest_bud_inside_obstacle_dies(tmp_path):
    """A bud growing into an obstacle (point-inside test, not just segment) → DEAD."""
    from palubicki.config import (
        Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig, LightConfig,
        ObstacleSphere, PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate_forest
    cfg = Config(
        envelope=EnvelopeConfig(rx=2, ry=3, rz=2, shape="ellipsoid", marker_count=2000),
        sim=SimConfig(max_iterations=6, internode_length=0.3),
        tropism=TropismConfig(w_gravity=0.0),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "x.glb", seed=42,
        forest=ForestConfig(
            seeds=(ForestSeed(position=(0.0, 0.0, 0.0)),),
            # Big sphere centered far above the tree — buds reaching it get killed
            obstacles=(ObstacleSphere(center=(0.0, 5.0, 0.0), radius=0.5),),
        ),
    )
    forest = simulate_forest(cfg)
    # No internode endpoint should lie inside the sphere
    sphere_center = np.array([0.0, 5.0, 0.0])
    for iod in forest.trees[0].all_internodes:
        dist = np.linalg.norm(iod.child_node.position - sphere_center)
        assert dist > 0.5, f"internode endpoint {iod.child_node.position} is inside the obstacle"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_simulator.py -k "segment_blocked or inside_obstacle_dies" -v`
Expected: FAIL — obstacle blocking is not yet wired into the growth loop.

- [ ] **Step 3: Add obstacle checks to _iteration_step**

In `src/palubicki/sim/simulator.py`, locate the growth substep block. After computing `new_pos = current_bud.position + d * cfg.sim.internode_length` and BEFORE creating the `new_node`, insert these two checks. The current section is:

```python
                new_pos = current_bud.position + d * cfg.sim.internode_length

                # NOTE: obstacle blocking is added in Task 17.

                new_node = Node(position=new_pos)
```

Replace it with:

```python
                new_pos = current_bud.position + d * cfg.sim.internode_length

                # V3: obstacle blocking
                if forest.obstacles:
                    from palubicki.sim.obstacles import segment_blocked, any_contains
                    if segment_blocked(current_bud.position, new_pos, forest.obstacles):
                        current_bud.state = BudState.DORMANT
                        new_active.append(current_bud)
                        break
                    if any_contains(new_pos, forest.obstacles):
                        current_bud.state = BudState.DEAD
                        break

                new_node = Node(position=new_pos)
```

- [ ] **Step 4: Run obstacle tests**

Run: `.venv/bin/pytest tests/sim/test_simulator.py -k "segment_blocked or inside_obstacle_dies" -v`
Expected: 2 PASSED.

- [ ] **Step 5: Run V2 bit-exact + sim suite + goldens**

Run: `.venv/bin/pytest tests/sim/ tests/golden/ -v`
Expected: ALL PASS — single-tree path with no obstacles is unchanged (the `if forest.obstacles:` short-circuits when empty).

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/simulator.py tests/sim/test_simulator.py
git commit -m "feat(sim): obstacle blocking in growth (segment → DORMANT, point-inside → DEAD)"
```

---

## Task 18: Obstacle geometry triangulation

**Files:**
- Create: `src/palubicki/geom/obstacle_geom.py`
- Create: `tests/geom/test_obstacle_geom.py`

- [ ] **Step 1: Write failing tests**

Create `tests/geom/test_obstacle_geom.py`:

```python
from pathlib import Path
import numpy as np

from palubicki.config import (
    ObstacleAABB, ObstacleSphere, ObstacleOBB, ObstacleMesh,
)
from palubicki.geom.mesh import Material
from palubicki.geom.obstacle_geom import build_obstacle_primitive
from palubicki.sim.obstacles import (
    AABBObstacle, SphereObstacle, OBBObstacle, MeshObstacle,
)


def _mat():
    return Material(
        name="obstacle", base_color=(0.5, 0.5, 0.55, 0.3),
        metallic=0.0, roughness=0.9, base_color_texture_png=None,
        alpha_mode="BLEND", alpha_cutoff=0.5, double_sided=True,
    )


def test_build_obstacle_primitive_aabb():
    obs = [AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))]
    prim = build_obstacle_primitive(obs, _mat())
    assert prim.positions.shape[1] == 3
    assert prim.indices.shape[0] % 3 == 0
    # 12 triangles for a cube = 36 indices
    assert prim.indices.shape[0] == 36


def test_build_obstacle_primitive_sphere():
    obs = [SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0))]
    prim = build_obstacle_primitive(obs, _mat())
    # UV sphere at (16, 8) lat/long: triangles = 2 * 16 * 8 = 256 → 768 indices
    assert prim.indices.shape[0] > 0
    assert prim.positions.shape[0] > 0


def test_build_obstacle_primitive_combines_multiple():
    obs = [
        AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1))),
        SphereObstacle(ObstacleSphere(center=(5, 0, 0), radius=1.0)),
    ]
    prim = build_obstacle_primitive(obs, _mat())
    # Indices = AABB(36) + sphere(>0)
    assert prim.indices.shape[0] > 36


def test_build_obstacle_primitive_empty_returns_none():
    out = build_obstacle_primitive([], _mat())
    assert out is None


def test_build_obstacle_primitive_mesh():
    cube_path = Path(__file__).parent.parent / "fixtures" / "unit_cube.obj"
    obs = [MeshObstacle(ObstacleMesh(path=cube_path))]
    prim = build_obstacle_primitive(obs, _mat())
    assert prim.indices.shape[0] >= 12   # at least 12 triangle indices for a cube
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/geom/test_obstacle_geom.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement obstacle_geom.py**

First read `src/palubicki/geom/mesh.py` to see the `Primitive` definition (it's used by `Mesh`):

Run: `.venv/bin/python -c "from palubicki.geom.mesh import Primitive; import inspect; print(inspect.getsource(Primitive))"`

Use the actual signature (fields: `positions`, `normals`, `uvs`, `indices`, `material`). Then create `src/palubicki/geom/obstacle_geom.py`:

```python
# src/palubicki/geom/obstacle_geom.py
from __future__ import annotations

import numpy as np

from palubicki.geom.mesh import Material, Primitive
from palubicki.sim.obstacles import (
    AABBObstacle, MeshObstacle, OBBObstacle, SphereObstacle,
)


def build_obstacle_primitive(obstacles: list, material: Material) -> Primitive | None:
    if not obstacles:
        return None

    all_pos: list[np.ndarray] = []
    all_norm: list[np.ndarray] = []
    all_uv: list[np.ndarray] = []
    all_idx: list[np.ndarray] = []
    vertex_offset = 0

    for o in obstacles:
        pos, norm, uv, idx = _triangulate(o)
        all_pos.append(pos)
        all_norm.append(norm)
        all_uv.append(uv)
        all_idx.append(idx + vertex_offset)
        vertex_offset += len(pos)

    return Primitive(
        positions=np.concatenate(all_pos, axis=0).astype(np.float32),
        normals=np.concatenate(all_norm, axis=0).astype(np.float32),
        uvs=np.concatenate(all_uv, axis=0).astype(np.float32),
        indices=np.concatenate(all_idx, axis=0).astype(np.uint32),
        material=material,
    )


def _triangulate(obstacle) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if isinstance(obstacle, AABBObstacle):
        amin, amax = obstacle.aabb()
        return _box_triangles(amin, amax, R=None)
    if isinstance(obstacle, OBBObstacle):
        center = obstacle._center
        half = obstacle._half
        # R^T maps local → world; vertices in local are (±half), then transformed.
        return _box_triangles_oriented(center, half, obstacle._R.T)
    if isinstance(obstacle, SphereObstacle):
        return _uv_sphere(obstacle._center, obstacle._radius, n_lat=16, n_lon=8)
    if isinstance(obstacle, MeshObstacle):
        tm = obstacle.trimesh
        return (
            np.asarray(tm.vertices, dtype=np.float64),
            np.asarray(tm.vertex_normals, dtype=np.float64),
            np.zeros((len(tm.vertices), 2), dtype=np.float64),
            np.asarray(tm.faces, dtype=np.uint32).reshape(-1),
        )
    raise TypeError(f"unknown obstacle type: {type(obstacle).__name__}")


def _box_triangles(amin: np.ndarray, amax: np.ndarray, R: np.ndarray | None) -> tuple[np.ndarray, ...]:
    # 8 corners
    x0, y0, z0 = amin
    x1, y1, z1 = amax
    corners = np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ], dtype=np.float64)
    if R is not None:
        corners = corners @ R.T
    # 6 faces, 2 triangles each, with outward normals
    faces_idx = np.array([
        [0, 1, 2], [0, 2, 3],   # z0 face (normal -z)
        [4, 6, 5], [4, 7, 6],   # z1 face (normal +z)
        [0, 4, 5], [0, 5, 1],   # y0 face (normal -y)
        [3, 2, 6], [3, 6, 7],   # y1 face (normal +y)
        [0, 3, 7], [0, 7, 4],   # x0 face (normal -x)
        [1, 5, 6], [1, 6, 2],   # x1 face (normal +x)
    ], dtype=np.uint32).reshape(-1)
    # Per-vertex normals = approximate by averaging face normals; for a box we just
    # use a single normal pointing outward from centroid (visual debug quality).
    centroid = corners.mean(axis=0)
    normals = corners - centroid
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.where(norms > 1e-12, normals / norms, np.array([0.0, 1.0, 0.0]))
    uvs = np.zeros((len(corners), 2), dtype=np.float64)
    return corners, normals, uvs, faces_idx


def _box_triangles_oriented(center: np.ndarray, half: np.ndarray, R_local_to_world: np.ndarray):
    # Build the axis-aligned box at origin with half-extents, then rotate + translate
    amin = -half
    amax = half
    pos, norm, uv, idx = _box_triangles(amin, amax, R=R_local_to_world)
    pos = pos + center
    return pos, norm, uv, idx


def _uv_sphere(center: np.ndarray, radius: float, *, n_lat: int, n_lon: int):
    # n_lat = lon segments (around equator), n_lon = lat segments (pole to pole)
    pos: list[np.ndarray] = []
    norm: list[np.ndarray] = []
    uv: list[np.ndarray] = []
    for i in range(n_lon + 1):
        v = i / n_lon
        phi = v * np.pi
        for j in range(n_lat + 1):
            u = j / n_lat
            theta = u * 2.0 * np.pi
            n = np.array([np.sin(phi) * np.cos(theta), np.cos(phi), np.sin(phi) * np.sin(theta)])
            pos.append(center + radius * n)
            norm.append(n)
            uv.append(np.array([u, v]))
    pos_arr = np.stack(pos)
    norm_arr = np.stack(norm)
    uv_arr = np.stack(uv)
    idx: list[int] = []
    stride = n_lat + 1
    for i in range(n_lon):
        for j in range(n_lat):
            a = i * stride + j
            b = a + 1
            c = a + stride
            d = c + 1
            idx.extend([a, c, b, b, c, d])
    idx_arr = np.asarray(idx, dtype=np.uint32)
    return pos_arr, norm_arr, uv_arr, idx_arr
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/geom/test_obstacle_geom.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/geom/obstacle_geom.py tests/geom/test_obstacle_geom.py
git commit -m "feat(geom): triangulate obstacles (AABB/Sphere/OBB/Mesh) for export"
```

---

## Task 19: `write_glb_forest` multi-node scene

**Files:**
- Modify: `src/palubicki/export/gltf.py`
- Modify: `tests/export/` (add a forest export test)

- [ ] **Step 1: Read existing write_glb to understand structure**

Run: `.venv/bin/python -c "from palubicki.export.gltf import write_glb; import inspect; print(inspect.getsourcefile(write_glb))"`

Open that file and read it carefully — the implementation strategy below assumes pygltflib + scene/node structure. Adapt to actual code patterns.

- [ ] **Step 2: Write failing test**

Create `tests/export/test_gltf_forest.py`:

```python
import pygltflib
from pathlib import Path

import numpy as np
import pytest

from palubicki.config import (
    Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig, LightConfig,
    ObstacleAABB, PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.export.gltf import write_glb_forest
from palubicki.sim.simulator import simulate_forest


def test_write_glb_forest_has_one_node_per_tree(tmp_path):
    cfg = Config(
        envelope=EnvelopeConfig(rx=2, ry=3, rz=2, marker_count=1500),
        sim=SimConfig(max_iterations=4),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "scene.glb", seed=42,
        forest=ForestConfig(seeds=(
            ForestSeed(position=(0.0, 0.0, 0.0)),
            ForestSeed(position=(8.0, 0.0, 0.0)),
        )),
    )
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, tmp_path / "scene.glb", asset_meta={"seed": 42})

    loaded = pygltflib.GLTF2().load(str(tmp_path / "scene.glb"))
    names = [n.name for n in loaded.nodes]
    assert "tree_0" in names
    assert "tree_1" in names


def test_write_glb_forest_includes_obstacles_node(tmp_path):
    cfg = Config(
        envelope=EnvelopeConfig(rx=2, ry=3, rz=2, marker_count=1500),
        sim=SimConfig(max_iterations=4),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "scene.glb", seed=42,
        forest=ForestConfig(
            seeds=(ForestSeed(position=(0.0, 0.0, 0.0)),),
            obstacles=(ObstacleAABB(min=(3, 0, -1), max=(4, 2, 1)),),
            export_obstacles_geometry=True,
        ),
    )
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, tmp_path / "scene.glb", asset_meta={"seed": 42})

    loaded = pygltflib.GLTF2().load(str(tmp_path / "scene.glb"))
    names = [n.name for n in loaded.nodes]
    assert "obstacles" in names


def test_write_glb_forest_embeds_config_in_asset_extras(tmp_path):
    cfg = Config(
        envelope=EnvelopeConfig(rx=2, ry=3, rz=2, marker_count=1500),
        sim=SimConfig(max_iterations=4),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "scene.glb", seed=42,
        forest=ForestConfig(seeds=(ForestSeed(position=(0.0, 0.0, 0.0)),)),
    )
    forest = simulate_forest(cfg)
    write_glb_forest(
        forest, cfg, tmp_path / "scene.glb",
        asset_meta={"seed": 42, "config": {"forest": {"seeds": [{"position": [0, 0, 0]}]}}},
    )

    loaded = pygltflib.GLTF2().load(str(tmp_path / "scene.glb"))
    extras = loaded.asset.extras or {}
    assert "config" in extras
```

- [ ] **Step 3: Add write_glb_forest to gltf.py**

Append to `src/palubicki/export/gltf.py` (it reuses the existing `_add_accessor` and `_add_material` helpers; the pattern mirrors `write_glb` but emits one `pygltflib.Mesh`+`pygltflib.Node` per tree and an extra for obstacles):

```python
def write_glb_forest(forest, cfg, output_path: Path, *, asset_meta: dict) -> None:
    """Write a multi-tree glTF scene: one node per tree + optional 'obstacles' node."""
    from palubicki.geom.builder import build_mesh
    from palubicki.geom.obstacle_geom import build_obstacle_primitive

    # Build per-tree palubicki meshes
    tree_meshes: list[tuple[str, Mesh]] = []
    for i, tree in enumerate(forest.trees):
        per_tree_cfg = forest.per_tree_cfgs[i] if i < len(forest.per_tree_cfgs) else cfg
        tree_meshes.append((f"tree_{i}", build_mesh(tree, per_tree_cfg)))

    # Build obstacle primitive (optional)
    obstacle_primitive = None
    if cfg.forest.export_obstacles_geometry and forest.obstacles:
        obstacle_mat = Material(
            name="obstacle",
            base_color=(0.5, 0.5, 0.55, 0.3),
            metallic=0.0,
            roughness=0.9,
            base_color_texture_png=None,
            alpha_mode="BLEND",
            alpha_cutoff=0.5,
            double_sided=True,
        )
        obstacle_primitive = build_obstacle_primitive(forest.obstacles, obstacle_mat)

    # Sanity: there must be at least one non-empty mesh (trees or obstacles)
    has_geometry = any(
        any(p.positions.shape[0] > 0 for p in m.primitives) for _, m in tree_meshes
    ) or (obstacle_primitive is not None and obstacle_primitive.positions.shape[0] > 0)
    if not has_geometry:
        raise ExportError("empty forest - no trees produced geometry and no obstacles to export")

    gltf = pygltflib.GLTF2()
    gltf.asset = pygltflib.Asset(
        version="2.0",
        generator="palubicki",
        extras=dict(asset_meta) if asset_meta else None,
    )

    buffer_data = bytearray()
    buffer_views: list[pygltflib.BufferView] = []
    accessors: list[pygltflib.Accessor] = []
    materials: list[pygltflib.Material] = []
    textures: list[pygltflib.Texture] = []
    images: list[pygltflib.Image] = []
    samplers: list[pygltflib.Sampler] = []

    gltf_meshes: list[pygltflib.Mesh] = []
    gltf_nodes: list[pygltflib.Node] = []

    def _emit_mesh(name: str, primitives_iter) -> None:
        gltf_prims: list[pygltflib.Primitive] = []
        for prim in primitives_iter:
            if prim is None or prim.positions.shape[0] == 0:
                continue
            pos_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.positions,
                                    _COMPONENT_FLOAT, _TYPE_VEC3, _TARGET_ARRAY, with_minmax=True)
            nor_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.normals,
                                    _COMPONENT_FLOAT, _TYPE_VEC3, _TARGET_ARRAY, with_minmax=False)
            uv_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.uvs,
                                   _COMPONENT_FLOAT, _TYPE_VEC2, _TARGET_ARRAY, with_minmax=False)
            idx_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.indices,
                                    _COMPONENT_UINT, _TYPE_SCALAR, _TARGET_ELEMENT_ARRAY, with_minmax=False)
            mat_idx = _add_material(prim.material, buffer_data, buffer_views,
                                    materials, textures, images, samplers)
            gltf_prims.append(pygltflib.Primitive(
                attributes=pygltflib.Attributes(POSITION=pos_acc, NORMAL=nor_acc, TEXCOORD_0=uv_acc),
                indices=idx_acc,
                material=mat_idx,
            ))
        if not gltf_prims:
            return
        gltf_meshes.append(pygltflib.Mesh(primitives=gltf_prims))
        gltf_nodes.append(pygltflib.Node(name=name, mesh=len(gltf_meshes) - 1))

    for name, mesh in tree_meshes:
        _emit_mesh(name, mesh.primitives)

    if obstacle_primitive is not None:
        _emit_mesh("obstacles", [obstacle_primitive])

    gltf.meshes = gltf_meshes
    gltf.nodes = gltf_nodes
    gltf.scenes = [pygltflib.Scene(nodes=list(range(len(gltf_nodes))))]
    gltf.scene = 0
    gltf.bufferViews = buffer_views
    gltf.accessors = accessors
    gltf.materials = materials
    gltf.textures = textures
    gltf.images = images
    gltf.samplers = samplers
    gltf.buffers = [pygltflib.Buffer(byteLength=len(buffer_data))]
    gltf.set_binary_blob(bytes(buffer_data))
    gltf.save_binary(str(output_path))
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/export/test_gltf_forest.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Verify V2 export tests still pass**

Run: `.venv/bin/pytest tests/export/ -v`
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/export/gltf.py tests/export/test_gltf_forest.py
git commit -m "feat(export): write_glb_forest (one node per tree + obstacles node)"
```

---

## Task 20: CLI `palubicki forest` subcommand

**Files:**
- Modify: `src/palubicki/cli.py`
- Create: `tests/fixtures/forest_minimal.yaml`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Create fixture YAML**

Create `tests/fixtures/forest_minimal.yaml`:

```yaml
envelope:
  shape: ellipsoid
  rx: 1.5
  ry: 2.0
  rz: 1.5
  marker_count: 1000
sim:
  max_iterations: 4
seed: 42
forest:
  seeds:
    - position: [0.0, 0.0, 0.0]
    - position: [5.0, 0.0, 0.0]
  obstacles:
    - kind: aabb
      min: [2.0, 0.0, -1.0]
      max: [3.0, 1.5, 1.0]
  export_obstacles_geometry: true
```

- [ ] **Step 2: Write failing CLI tests**

Append to `tests/test_cli.py`:

```python
def test_cli_forest_subcommand_generates_glb(tmp_path):
    from palubicki.cli import main
    output = tmp_path / "scene.glb"
    code = main([
        "forest",
        "-o", str(output),
        "--config", "tests/fixtures/forest_minimal.yaml",
    ])
    assert code == 0
    assert output.exists()
    assert output.stat().st_size > 0


def test_cli_forest_help_returns_zero():
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "palubicki", "forest", "--help"],
        capture_output=True,
    )
    assert result.returncode == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cli.py -k "forest_subcommand or forest_help" -v`
Expected: FAIL — `forest` subcommand doesn't exist.

- [ ] **Step 4: Add `forest` subcommand to CLI**

Modify `src/palubicki/cli.py`. In `_build_parser()`, add the new subcommand after `dc = sub.add_parser("dump-config", ...)`:

```python
    fst = sub.add_parser("forest", help="Generate a multi-tree forest with optional obstacles and write .glb")
    fst.add_argument("-o", "--output", type=Path, required=True)
    fst.add_argument("--config", type=Path, required=True)
    fst.add_argument("--seed", type=int, default=None, help="Override cfg.seed")
    fst.add_argument("--log-level", choices=["DEBUG", "INFO", "WARN", "WARNING", "ERROR"], default="INFO")
    fst.add_argument("--validate", action="store_true")
    fst.add_argument("--save-config", type=Path, default=None)
```

In `main()`, add the dispatch after the existing `dump-config` branch:

```python
    if args.command == "forest":
        return _cmd_forest(args)
```

Then add `_cmd_forest` near the existing `_cmd_generate`:

```python
def _cmd_forest(args) -> int:
    logging.basicConfig(level=getattr(logging, args.log_level.replace("WARN", "WARNING")),
                        format="%(message)s")

    overrides: dict = {}
    if args.seed is not None:
        overrides["seed"] = args.seed

    try:
        cfg = load_config(yaml_path=args.config, cli_overrides=overrides, output=args.output)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    try:
        from palubicki.sim.simulator import simulate_forest
        from palubicki.export.gltf import write_glb_forest

        forest = simulate_forest(cfg)
        asset_meta = {
            "seed": cfg.seed,
            "n_trees": len(forest.trees),
            "n_obstacles": len(forest.obstacles),
            "config": _config_to_dict(cfg),
        }
        write_glb_forest(forest, cfg, cfg.output, asset_meta=asset_meta)
    except ExportError as e:
        print(f"export error: {e}", file=sys.stderr)
        return 1

    if args.save_config is not None:
        with open(args.save_config, "w") as f:
            yaml.safe_dump(_config_to_dict(cfg), f, sort_keys=False)

    if args.validate:
        import pygltflib
        loaded = pygltflib.GLTF2().load(str(cfg.output))
        n_nodes = len(loaded.nodes)
        print(f"validated: {n_nodes} nodes", file=sys.stderr)

    return 0
```

Also extend `_config_to_dict` to serialize the new `forest` field. The existing helper iterates `fields(cfg)` and dispatches on dataclass — it'll auto-serialize `forest: ForestConfig`. But the `obstacles` and `seeds` tuples contain dataclasses with nested fields (Path for mesh, dict for overrides). Verify by running:

Run: `.venv/bin/python -c "from palubicki.cli import _config_to_dict; from palubicki.config import Config, EnvelopeConfig, SimConfig, TropismConfig, PhyllotaxyConfig, SheddingConfig, GeomConfig, LightConfig; from pathlib import Path; cfg = Config(envelope=EnvelopeConfig(), sim=SimConfig(), tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(), shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(), output=Path('/tmp/x.glb')); print(_config_to_dict(cfg))"`

If `forest` is serialized as `{"seeds": (), "obstacles": (), ...}` you're good; if you see issues with nested obstacle dataclasses, extend `_scalar` to handle them. For tuples of dataclasses, add this branch to `_scalar`:

```python
def _scalar(v):
    if isinstance(v, Path):
        return str(v)
    if isinstance(v, tuple):
        return [_scalar(x) if not isinstance(x, (int, float, str)) else x for x in v]
    if is_dataclass(v):
        return {f.name: _scalar(getattr(v, f.name)) for f in fields(v)}
    if isinstance(v, dict):
        return {k: _scalar(val) for k, val in v.items()}
    return v
```

- [ ] **Step 5: Run forest CLI tests**

Run: `.venv/bin/pytest tests/test_cli.py -k "forest_subcommand or forest_help" -v`
Expected: 2 PASSED.

- [ ] **Step 6: Confirm V2 CLI still works**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: ALL PASS.

- [ ] **Step 7: Smoke test by hand**

Run:
```bash
.venv/bin/palubicki forest -o /tmp/forest_test.glb --config tests/fixtures/forest_minimal.yaml --validate
```
Expected: `validated: N nodes` printed (where N >= 2 trees + 1 obstacles), no errors.

- [ ] **Step 8: Commit**

```bash
git add src/palubicki/cli.py tests/fixtures/forest_minimal.yaml tests/test_cli.py
git commit -m "feat(cli): palubicki forest subcommand (multi-tree + obstacles)"
```

---

## Task 21: Integration + behavioral tests

**Files:**
- Create: `tests/integration/test_obstacles_behavior.py`
- Create: `tests/integration/test_forest_behavior.py`
- Modify: `tests/integration/test_smoke.py`

- [ ] **Step 1: Write obstacle behavioral test**

Create `tests/integration/test_obstacles_behavior.py`:

```python
import numpy as np
import pytest

from palubicki.config import (
    Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig, LightConfig,
    ObstacleAABB, PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.sim.simulator import simulate_forest


@pytest.mark.slow
def test_obstacle_wall_deflects_crown(tmp_path):
    """A wall close to the tree → fewer internodes on the wall side than on the open side."""
    def _make_cfg(with_wall: bool):
        return Config(
            envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=4000),
            sim=SimConfig(max_iterations=15),
            tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
            output=tmp_path / "x.glb", seed=42,
            forest=ForestConfig(
                seeds=(ForestSeed(position=(0.0, 0.0, 0.0)),),
                obstacles=((ObstacleAABB(min=(1.0, 0.0, -3.0), max=(1.2, 5.0, 3.0)),) if with_wall else ()),
            ),
        )

    forest_open = simulate_forest(_make_cfg(False))
    forest_wall = simulate_forest(_make_cfg(True))

    # Count internode endpoints with x > 0.8 (wall side) vs x < -0.8 (open side)
    def _count(side_filter):
        tree = forest_wall.trees[0] if side_filter == "wall" else forest_open.trees[0]
        if side_filter == "wall":
            xs = [iod.child_node.position[0] for iod in tree.all_internodes]
            return sum(1 for x in xs if x > 0.8)
        # baseline check: open tree should have plenty of mass on the +x side
        xs = [iod.child_node.position[0] for iod in tree.all_internodes]
        return sum(1 for x in xs if x > 0.8)

    open_count = _count("open")
    wall_count = _count("wall")
    # The wall is at x=1.0–1.2 → very few internodes should have x > 0.8 in the wall case
    assert wall_count < 0.5 * open_count, f"open={open_count}, wall={wall_count}"
```

- [ ] **Step 2: Write forest behavioral test**

Create `tests/integration/test_forest_behavior.py`:

```python
import numpy as np
import pytest

from palubicki.config import (
    Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig, LightConfig,
    PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.sim.simulator import simulate, simulate_forest


@pytest.mark.slow
def test_two_trees_compete_for_space(tmp_path):
    """Two trees close together → the inner-facing sides have fewer internodes than the outer-facing sides."""
    cfg = Config(
        envelope=EnvelopeConfig(rx=1.5, ry=3.0, rz=1.5, marker_count=3000),
        sim=SimConfig(max_iterations=12),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "x.glb", seed=42,
        forest=ForestConfig(seeds=(
            ForestSeed(position=(-1.5, 0.0, 0.0)),
            ForestSeed(position=(1.5, 0.0, 0.0)),
        )),
    )
    forest = simulate_forest(cfg)

    tree_left, tree_right = forest.trees[0], forest.trees[1]
    # tree_left at x=-1.5; inner side = +x (towards 0), outer side = -x
    left_inner = sum(1 for iod in tree_left.all_internodes if iod.child_node.position[0] > -1.5)
    left_outer = sum(1 for iod in tree_left.all_internodes if iod.child_node.position[0] < -1.5)
    # We expect at least somewhat asymmetric mass (inner < outer); allow small margin since
    # the trees can still grow inward where markers from the OTHER tree's envelope provide pulls.
    # Loose assertion: outer >= inner.
    assert left_outer >= left_inner - 5, f"left_inner={left_inner}, left_outer={left_outer}"


@pytest.mark.slow
def test_simulate_vs_simulate_forest_single_tree_match(tmp_path):
    """simulate(cfg) and simulate_forest(cfg) on cfg with no forest.seeds must produce the same tree."""
    cfg = Config(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_iterations=8),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "x.glb", seed=42,
    )
    tree_a = simulate(cfg)
    forest_b = simulate_forest(cfg)
    tree_b = forest_b.trees[0]
    assert len(tree_a.all_internodes) == len(tree_b.all_internodes)
    for ia, ib in zip(tree_a.all_internodes, tree_b.all_internodes):
        np.testing.assert_allclose(ia.child_node.position, ib.child_node.position)
```

- [ ] **Step 3: Add a forest smoke case**

Open `tests/integration/test_smoke.py` and append:

```python
@pytest.mark.slow
def test_smoke_forest_two_trees_with_obstacle(tmp_path):
    from palubicki.config import (
        Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig, LightConfig,
        ObstacleAABB, PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate_forest
    from palubicki.export.gltf import write_glb_forest

    cfg = Config(
        envelope=EnvelopeConfig(marker_count=1000),
        sim=SimConfig(max_iterations=5),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "smoke.glb", seed=42,
        forest=ForestConfig(
            seeds=(
                ForestSeed(position=(0.0, 0.0, 0.0)),
                ForestSeed(position=(5.0, 0.0, 0.0)),
            ),
            obstacles=(ObstacleAABB(min=(2.0, 0.0, -1.0), max=(3.0, 1.5, 1.0)),),
        ),
    )
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, cfg.output, asset_meta={"seed": 42})
    assert cfg.output.exists()
    assert cfg.output.stat().st_size > 0
```

- [ ] **Step 4: Run all integration tests**

Run: `.venv/bin/pytest tests/integration/ -v -m slow`
Expected: ALL PASS.

- [ ] **Step 5: Run full suite (smoke check)**

Run: `.venv/bin/pytest -x --tb=short`
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_obstacles_behavior.py tests/integration/test_forest_behavior.py tests/integration/test_smoke.py
git commit -m "test(integration): V3 obstacles + forest behavioral cases"
```

---

## Task 22: V3 golden test

**Files:**
- Modify: `tests/golden/test_goldens.py`

- [ ] **Step 1: Write a forest golden test**

Append to `tests/golden/test_goldens.py`:

```python
@pytest.mark.slow
def test_golden_forest_v3(tmp_path):
    """Pin a hash for a deterministic V3 forest run."""
    import hashlib
    import json
    from palubicki.config import (
        Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig, LightConfig,
        ObstacleAABB, PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate_forest

    cfg = Config(
        envelope=EnvelopeConfig(rx=1.5, ry=2.5, rz=1.5, shape="ellipsoid", marker_count=2000),
        sim=SimConfig(max_iterations=10),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(),
        light=LightConfig(enabled=True),
        output=tmp_path / "x.glb", seed=42,
        forest=ForestConfig(
            seeds=(
                ForestSeed(position=(0.0, 0.0, 0.0)),
                ForestSeed(position=(4.0, 0.0, 0.0)),
                ForestSeed(position=(2.0, 0.0, 3.0)),
            ),
            obstacles=(ObstacleAABB(min=(1.5, 0.0, -1.0), max=(2.5, 2.0, 1.0)),),
        ),
    )
    forest = simulate_forest(cfg)
    positions = []
    for tree_index, tree in enumerate(forest.trees):
        stack = [tree.root]
        while stack:
            node = stack.pop()
            positions.append((tree_index, tuple(np.round(node.position, 6).tolist())))
            for iod in node.children_internodes:
                stack.append(iod.child_node)
    digest = hashlib.sha256(json.dumps(sorted(positions), sort_keys=True, default=list).encode()).hexdigest()
    EXPECTED = None   # pin once after a stable run
    if EXPECTED is not None:
        assert digest == EXPECTED, f"V3 forest hash drifted: {digest}"
    print(f"V3 forest golden hash: {digest}")
```

- [ ] **Step 2: Capture hash by running with `-s`**

Run: `.venv/bin/pytest tests/golden/test_goldens.py::test_golden_forest_v3 -v -s -m slow`
Expected: PASS (EXPECTED is None). Copy the printed hash and replace `EXPECTED = None` with `EXPECTED = "<that hex string>"`.

- [ ] **Step 3: Re-run to confirm pinned hash**

Run: `.venv/bin/pytest tests/golden/test_goldens.py::test_golden_forest_v3 -v -m slow`
Expected: PASS — hash matches.

- [ ] **Step 4: Run full golden suite**

Run: `.venv/bin/pytest tests/golden/ -v -m slow`
Expected: ALL PASS — V1, V2, V3 goldens all stable.

- [ ] **Step 5: Run full project tests (final acceptance gate)**

Run: `.venv/bin/pytest --tb=short`
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/golden/test_goldens.py
git commit -m "test(golden): pin V3 forest hash (3 trees, 1 AABB, light enabled)"
```

---

## Final Acceptance

After Task 22:

- [ ] Run `.venv/bin/pytest --tb=short -v`. All tests pass.
- [ ] Run `.venv/bin/pytest --cov=palubicki.sim.obstacles --cov=palubicki.sim.forest --cov-report=term-missing`. Verify coverage ≥ 85%.
- [ ] Manual smoke: `.venv/bin/palubicki forest -o /tmp/v3_smoke.glb --config tests/fixtures/forest_minimal.yaml --validate`. Inspect with a glTF viewer to confirm visual sanity (2 trees, 1 AABB box visible).
- [ ] Update top-level `README.md` "Roadmap" section to mark V3 as delivered, with a `V3` example block similar to the V2 one. (Bundled in this final commit.)

Final commit:

```bash
git add README.md
git commit -m "docs(readme): V3 delivered — obstacles + forest"
```
