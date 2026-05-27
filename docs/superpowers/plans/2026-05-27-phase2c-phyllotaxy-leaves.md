# Phase 2C — Phyllotaxy & Leaves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add decussate phyllotaxy mode, sun/shade leaf size scaling, and a maple species preset.

**Architecture:** Extend `PhyllotaxyConfig.mode` Literal with `"decussate"` and add the matching branch to `lateral_bud_directions` (each node alternates 90°). Add `GeomConfig.leaf_sun_shade_k` and capture per-internode `light_factor` at creation time inside `simulator.py`, so `geom/leaves.py` can scale each leaf's quad size by the captured value. The voxel light grid is intentionally **not** coupled back to leaf size (constant `light.leaf_area`, see spec §4.7) to avoid circular feedback.

**Tech Stack:** Python 3.11+, pytest, numpy, dataclasses, frozen YAML configs.

**Reference spec:** `docs/superpowers/specs/2026-05-27-phase2c-phyllotaxy-leaves-design.md`

---

## Pre-flight

Verify the suite is green before touching anything.

- [ ] **Run baseline**

```bash
cd /Users/julienriel/src/palubicki
.venv/bin/pytest -x --no-header -q 2>&1 | tail -10
```

Expected: `passed` (entire test suite passes against current `main`).

---

## Task 1 : Extend `PhyllotaxyConfig.mode` to accept `"decussate"`

**Files:**
- Modify: `src/palubicki/config.py:76-79` (PhyllotaxyConfig.mode Literal)
- Test: `tests/test_config.py`

- [ ] **Step 1 : Write a failing test that loads a config with `mode: decussate`**

Append to `tests/test_config.py` (after the last existing test in the file):

```python
def test_phyllotaxy_mode_decussate_is_accepted(tmp_path):
    from palubicki.config import (
        Config, EnvelopeConfig, GeomConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    cfg = Config(
        envelope=EnvelopeConfig(),
        sim=SimConfig(),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(mode="decussate", divergence_angle_deg=0.0),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        output=tmp_path / "out.glb",
    )
    assert cfg.phyllotaxy.mode == "decussate"
```

- [ ] **Step 2 : Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py::test_phyllotaxy_mode_decussate_is_accepted -v`

Expected: PASS or FAIL — Literal validation is not enforced at runtime by dataclasses, so this typically passes immediately, but **type-checker tooling and `load_config` paths that filter on field names will still reject unknown modes downstream**. The test exists to lock the contract: `mode="decussate"` must build a valid Config object.

- [ ] **Step 3 : Update the Literal annotation in `config.py`**

In `src/palubicki/config.py`, replace lines 76-79:

```python
@dataclass(frozen=True)
class PhyllotaxyConfig:
    mode: Literal["alternate", "opposite", "whorled", "decussate"] = field(
        default="alternate", metadata={"ui": {"label": "Mode"}}
    )
```

- [ ] **Step 4 : Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py::test_phyllotaxy_mode_decussate_is_accepted -v`

Expected: PASS.

- [ ] **Step 5 : Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
feat(config): allow decussate phyllotaxy mode

PhyllotaxyConfig.mode Literal now includes "decussate" so configs
can opt into the per-node 90° alternation pattern used by maples,
ash, dogwood. Implementation of the branching behaviour follows
in the next task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 : Implement decussate branch in `lateral_bud_directions`

**Files:**
- Modify: `src/palubicki/sim/phyllotaxy.py:34-41`
- Test: `tests/sim/test_phyllotaxy.py`

- [ ] **Step 1 : Write failing unit tests**

Append to `tests/sim/test_phyllotaxy.py`:

```python
def test_decussate_two_buds_per_node():
    cfg = PhyllotaxyConfig(mode="decussate", branch_angle_deg=45.0, divergence_angle_deg=0.0)
    dirs = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0, seed=0)
    assert dirs.shape == (2, 3)
    # Both unit length
    assert abs(np.linalg.norm(dirs[0]) - 1.0) < 1e-7
    assert abs(np.linalg.norm(dirs[1]) - 1.0) < 1e-7


def test_decussate_alternates_90_per_node():
    """Successive nodes' lateral pairs are ~90° rotated around the growth axis."""
    cfg = PhyllotaxyConfig(mode="decussate", branch_angle_deg=45.0, divergence_angle_deg=0.0)
    growth = np.array([0.0, 1.0, 0.0])
    d_even = lateral_bud_directions(growth, cfg, node_index=0, seed=0)[0]
    d_odd = lateral_bud_directions(growth, cfg, node_index=1, seed=0)[0]
    # Project both onto the plane perpendicular to growth
    proj_even = d_even - np.dot(d_even, growth) * growth
    proj_odd = d_odd - np.dot(d_odd, growth) * growth
    proj_even = proj_even / np.linalg.norm(proj_even)
    proj_odd = proj_odd / np.linalg.norm(proj_odd)
    cos_angle = float(np.dot(proj_even, proj_odd))
    # 90° apart → cos ≈ 0
    assert abs(cos_angle) < 1e-6


def test_decussate_with_nonzero_divergence():
    """divergence_angle_deg > 0 superposes a spiral on top of the 90° offset.

    Pair (node 0 → node 2) should be rotated by 2*divergence_angle_deg
    (both are even nodes; no 90° offset between them)."""
    cfg = PhyllotaxyConfig(mode="decussate", branch_angle_deg=45.0, divergence_angle_deg=10.0)
    growth = np.array([0.0, 1.0, 0.0])
    d0 = lateral_bud_directions(growth, cfg, node_index=0, seed=0)[0]
    d2 = lateral_bud_directions(growth, cfg, node_index=2, seed=0)[0]
    p0 = d0 - np.dot(d0, growth) * growth
    p2 = d2 - np.dot(d2, growth) * growth
    p0 = p0 / np.linalg.norm(p0)
    p2 = p2 / np.linalg.norm(p2)
    cos_angle = float(np.dot(p0, p2))
    expected = np.cos(np.radians(20.0))  # 2 * 10°
    assert abs(cos_angle - expected) < 1e-6
```

- [ ] **Step 2 : Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_phyllotaxy.py::test_decussate_two_buds_per_node tests/sim/test_phyllotaxy.py::test_decussate_alternates_90_per_node tests/sim/test_phyllotaxy.py::test_decussate_with_nonzero_divergence -v`

Expected: 3 tests FAIL with `ValueError: unknown phyllotaxy mode: 'decussate'`.

- [ ] **Step 3 : Add the decussate branch**

In `src/palubicki/sim/phyllotaxy.py`, replace the mode dispatch block (lines 34-43) with:

```python
    if cfg.mode == "alternate":
        k = 1
        base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index
    elif cfg.mode == "opposite":
        k = 2
        base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index
    elif cfg.mode == "whorled":
        k = max(1, cfg.whorl_count)
        base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index
    elif cfg.mode == "decussate":
        k = 2
        # Each node rotates by 90° relative to the previous one. With
        # divergence_angle_deg=0.0 this gives canonical decussation (maple,
        # ash, dogwood). Non-zero divergence produces a decussate spiral —
        # stylistic but off-canon.
        base_azimuth = (
            math.radians(cfg.divergence_angle_deg) * node_index
            + (math.pi / 2.0) * (node_index % 2)
        )
    else:
        raise ValueError(f"unknown phyllotaxy mode: {cfg.mode!r}")

    branch_angle = math.radians(cfg.branch_angle_deg)
```

Then **delete** the now-redundant pair of lines that follow (the original `base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index` and `branch_angle = math.radians(cfg.branch_angle_deg)` at original lines 43-44). The new block above already sets `base_azimuth` per-mode and assigns `branch_angle` once at the end.

- [ ] **Step 4 : Run the new tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_phyllotaxy.py -v`

Expected: all phyllotaxy tests PASS (including the 3 new ones and the existing 9 that must remain green).

- [ ] **Step 5 : Commit**

```bash
git add src/palubicki/sim/phyllotaxy.py tests/sim/test_phyllotaxy.py
git commit -m "$(cat <<'EOF'
feat(phyllotaxy): implement decussate mode

Each node alternates lateral-pair azimuth by 90° relative to the
previous node. With divergence_angle_deg=0 this yields canonical
decussation (maple, ash, dogwood); non-zero values give a decussate
spiral.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 : Add `GeomConfig.leaf_sun_shade_k` with validation

**Files:**
- Modify: `src/palubicki/config.py:121-138` (GeomConfig) and `__post_init__`
- Test: `tests/test_config.py`

- [ ] **Step 1 : Write failing tests**

Append to `tests/test_config.py`:

```python
def test_geom_leaf_sun_shade_k_default_zero(tmp_path):
    from palubicki.config import GeomConfig
    g = GeomConfig()
    assert g.leaf_sun_shade_k == 0.0


def test_geom_leaf_sun_shade_k_negative_rejected(tmp_path):
    from palubicki.config import (
        Config, EnvelopeConfig, GeomConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig, ConfigError,
    )
    with pytest.raises(ConfigError, match="leaf_sun_shade_k"):
        Config(
            envelope=EnvelopeConfig(), sim=SimConfig(),
            tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_sun_shade_k=-0.1),
            output=tmp_path / "x.glb",
        )


def test_geom_leaf_sun_shade_k_above_two_rejected(tmp_path):
    from palubicki.config import (
        Config, EnvelopeConfig, GeomConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig, ConfigError,
    )
    with pytest.raises(ConfigError, match="leaf_sun_shade_k"):
        Config(
            envelope=EnvelopeConfig(), sim=SimConfig(),
            tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_sun_shade_k=2.5),
            output=tmp_path / "x.glb",
        )
```

- [ ] **Step 2 : Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config.py::test_geom_leaf_sun_shade_k_default_zero tests/test_config.py::test_geom_leaf_sun_shade_k_negative_rejected tests/test_config.py::test_geom_leaf_sun_shade_k_above_two_rejected -v`

Expected: the default test FAILS with `AttributeError: 'GeomConfig' object has no attribute 'leaf_sun_shade_k'`; the validation tests FAIL because the field doesn't exist yet.

- [ ] **Step 3 : Add the field to GeomConfig**

In `src/palubicki/config.py`, inside `GeomConfig` (after `foliage_depth` at line 137), append:

```python
    # Phase 2C: leaf size scales with the per-internode light_factor captured
    # at creation. eff_size = leaf_size * (1 + k * (1 - light_factor)),
    # clamped to [0.5*leaf_size, 2.0*leaf_size]. k=0 disables (legacy).
    leaf_sun_shade_k: float = field(
        default=0.0,
        metadata={"ui": {"min": 0.0, "max": 2.0, "step": 0.05}},
    )
```

- [ ] **Step 4 : Add validation in `Config.__post_init__`**

In `src/palubicki/config.py`, inside the `g = self.geom` validation block (after the `leaf_splay_deg` check around line 271), append:

```python
        if not (0.0 <= g.leaf_sun_shade_k <= 2.0):
            raise ConfigError(
                f"geom.leaf_sun_shade_k must be in [0, 2], got {g.leaf_sun_shade_k}"
            )
```

- [ ] **Step 5 : Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -v -k leaf_sun_shade_k`

Expected: 3 tests PASS.

- [ ] **Step 6 : Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
feat(config): add GeomConfig.leaf_sun_shade_k

New field controls sun/shade leaf heterophylly: shaded leaves grow
larger by factor (1 + k*(1-light_factor)), clamped [0.5x, 2x].
Validated in [0, 2]. Default 0.0 keeps current behaviour.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 : Add `Internode.light_factor` field

**Files:**
- Modify: `src/palubicki/sim/tree.py:36-55`
- Test: `tests/sim/test_tree.py`

- [ ] **Step 1 : Write a failing test for the new field**

Append to `tests/sim/test_tree.py`:

```python
def test_internode_default_light_factor_one():
    import numpy as np
    from palubicki.sim.tree import Internode, Node
    p = Node(position=np.zeros(3))
    c = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=p, child_node=c, length=1.0, is_main_axis=True)
    assert iod.light_factor == 1.0


def test_internode_accepts_explicit_light_factor():
    import numpy as np
    from palubicki.sim.tree import Internode, Node
    p = Node(position=np.zeros(3))
    c = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(
        parent_node=p, child_node=c, length=1.0,
        is_main_axis=True, light_factor=0.42,
    )
    assert iod.light_factor == 0.42
```

- [ ] **Step 2 : Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_tree.py::test_internode_default_light_factor_one tests/sim/test_tree.py::test_internode_accepts_explicit_light_factor -v`

Expected: 2 tests FAIL — `TypeError: __init__() got an unexpected keyword argument 'light_factor'` for the second test, and `AttributeError` for the first.

- [ ] **Step 3 : Add the field to Internode**

In `src/palubicki/sim/tree.py`, replace the `Internode` dataclass (lines 36-55) with:

```python
@dataclass(eq=False)
class Internode:
    parent_node: Node
    child_node: Node
    length: float
    is_main_axis: bool
    diameter: float = 0.0
    window: int = 5
    # Phase 2C: light_factor of the parent bud at the moment this internode
    # was created. Captured once, never updated — this is the "growing
    # conditions" snapshot that determines leaf size (sun/shade plasticity).
    light_factor: float = 1.0
    quality_history: deque[float] = field(init=False)

    def __post_init__(self) -> None:
        self.quality_history = deque(maxlen=self.window)

    def push_quality(self, q: float) -> None:
        self.quality_history.append(q)

    def average_quality(self) -> float:
        if not self.quality_history:
            return 0.0
        return sum(self.quality_history) / len(self.quality_history)
```

- [ ] **Step 4 : Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_tree.py -v`

Expected: all tests PASS (including the two new ones and any existing Internode tests).

- [ ] **Step 5 : Commit**

```bash
git add src/palubicki/sim/tree.py tests/sim/test_tree.py
git commit -m "$(cat <<'EOF'
feat(sim): add Internode.light_factor captured at creation

Stores the parent bud's light_factor at the moment the internode
is grown. Default 1.0 means "full sun" when no light grid is
active. The value is frozen at creation (botanically correct: a
leaf adapts when it develops, not retroactively).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 : Capture `light_factor` in `simulator.py` at internode creation

**Files:**
- Modify: `src/palubicki/sim/simulator.py:209-219`
- Test: `tests/sim/test_simulator_light_capture.py` (new file)

- [ ] **Step 1 : Create the new test file with failing tests**

Create `tests/sim/test_simulator_light_capture.py`:

```python
"""Phase 2C: verify Internode captures the parent bud's light_factor
at the moment of creation."""
import numpy as np
import pytest

from palubicki.config import (
    Config, EnvelopeConfig, GeomConfig, LightConfig, PhyllotaxyConfig,
    SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.sim.simulator import simulate


def _base_cfg(tmp_path, *, light_enabled: bool) -> Config:
    return Config(
        envelope=EnvelopeConfig(rx=1.0, ry=2.0, rz=1.0, marker_count=400),
        sim=SimConfig(
            internode_length=0.15, max_iterations=4,
            r_perception=0.6, r_kill=0.1,
        ),
        tropism=TropismConfig(w_orthotropy_main=0.3),
        phyllotaxy=PhyllotaxyConfig(mode="alternate"),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        light=LightConfig(enabled=light_enabled, n_rays=8),
        output=tmp_path / "x.glb",
        seed=7,
    )


def test_internode_default_light_factor_one_when_no_light(tmp_path):
    cfg = _base_cfg(tmp_path, light_enabled=False)
    tree = simulate(cfg)
    assert len(tree.all_internodes) > 0
    for iod in tree.all_internodes:
        assert iod.light_factor == 1.0


def test_internode_captures_bud_light_factor(tmp_path):
    """With light enabled, at least some internodes should have a
    light_factor strictly below 1.0 (deeper buds get shaded)."""
    cfg = _base_cfg(tmp_path, light_enabled=True)
    tree = simulate(cfg)
    assert len(tree.all_internodes) > 0
    factors = [iod.light_factor for iod in tree.all_internodes]
    # All values must lie in [0, 1] inclusive.
    assert all(0.0 <= f <= 1.0 for f in factors)
    # At least one internode should be partially shaded (light_factor < 1).
    assert any(f < 0.999 for f in factors), (
        f"expected at least one shaded internode, got factors={factors}"
    )
```

- [ ] **Step 2 : Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_simulator_light_capture.py -v`

Expected: `test_internode_default_light_factor_one_when_no_light` PASSES (because the default is already 1.0 from Task 4); `test_internode_captures_bud_light_factor` FAILS because the simulator does not yet write captured `light_factor` into the Internode — every value stays at the default 1.0.

- [ ] **Step 3 : Update the simulator to capture light_factor**

In `src/palubicki/sim/simulator.py`, replace the Internode construction block (lines 209-216 — the `iod = Internode(...)` call inside the substep loop) with:

```python
                new_node = Node(position=new_pos)
                lf = (
                    float(light_info.light_factor.get(cur, 1.0))
                    if light_info is not None else 1.0
                )
                iod = Internode(
                    parent_node=cur.parent_node,
                    child_node=new_node,
                    length=length,
                    is_main_axis=is_main,
                    window=cfg.shedding.window,
                    light_factor=lf,
                )
```

- [ ] **Step 4 : Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_simulator_light_capture.py -v`

Expected: 2 tests PASS.

- [ ] **Step 5 : Re-run the full simulator test suite to check for regressions**

Run: `.venv/bin/pytest tests/sim/ -v 2>&1 | tail -20`

Expected: all sim tests PASS. (Goldens will be regenerated in a later task.)

- [ ] **Step 6 : Commit**

```bash
git add src/palubicki/sim/simulator.py tests/sim/test_simulator_light_capture.py
git commit -m "$(cat <<'EOF'
feat(sim): capture light_factor on Internode at creation

Pulls the parent bud's light_factor from the per-iteration
LightPerception (1.0 fallback when light is disabled) and stores
it on the new Internode. Phase 2C leaves will use this to scale
their quad size for sun/shade heterophylly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6 : Apply sun/shade scaling in `geom/leaves.py`

**Files:**
- Modify: `src/palubicki/geom/leaves.py` (signatures + cluster emission)
- Modify: `src/palubicki/geom/builder.py:47-55` (pass new arg)
- Test: `tests/geom/test_leaves.py`

The plan is to make `build_leaves_primitive` accept the sun/shade `k`, and to teach `_collect_foliage_sites` to return the originating `Internode` (or `None` for the root pseudo-site) so the per-cluster size scaling can be computed before emission.

- [ ] **Step 1 : Write failing tests in `tests/geom/test_leaves.py`**

Append to `tests/geom/test_leaves.py`:

```python
def _tree_one_apex_with_internode(light_factor: float):
    """Build a 2-node tree with one internode of the requested light_factor
    and one terminal bud on the child node."""
    from palubicki.sim.tree import Internode
    root = Node(position=np.zeros(3))
    child = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(
        parent_node=root, child_node=child, length=1.0,
        is_main_axis=True, light_factor=light_factor,
    )
    root.children_internodes.append(iod)
    child.parent_internode = iod
    bud = Bud(
        position=child.position.copy(),
        direction=np.array([0.0, 1.0, 0.0]),
        axis_order=0, parent_node=child, state=BudState.ACTIVE,
    )
    child.terminal_bud = bud
    tree = Tree(root=root)
    tree.active_buds.append(bud)
    tree.all_internodes.append(iod)
    return tree


def _leaf_extent(prim):
    """Return the (x, y, z) bounding box diagonal of the leaf primitive."""
    pos = prim.positions
    return float(np.linalg.norm(pos.max(axis=0) - pos.min(axis=0)))


def test_leaf_size_unchanged_when_k_zero():
    """k=0 → leaf extent is identical regardless of light_factor."""
    t_sun = _tree_one_apex_with_internode(light_factor=1.0)
    t_shade = _tree_one_apex_with_internode(light_factor=0.2)
    p_sun = build_leaves_primitive(t_sun, leaf_size=0.1, material=_mat(),
                                   sun_shade_k=0.0)
    p_shade = build_leaves_primitive(t_shade, leaf_size=0.1, material=_mat(),
                                     sun_shade_k=0.0)
    assert abs(_leaf_extent(p_sun) - _leaf_extent(p_shade)) < 1e-6


def test_leaf_size_scales_with_shadow():
    """k=1, light_factor=0.5 → leaf size ~1.5x the full-sun leaf."""
    t_sun = _tree_one_apex_with_internode(light_factor=1.0)
    t_shade = _tree_one_apex_with_internode(light_factor=0.5)
    p_sun = build_leaves_primitive(t_sun, leaf_size=0.1, material=_mat(),
                                   sun_shade_k=1.0)
    p_shade = build_leaves_primitive(t_shade, leaf_size=0.1, material=_mat(),
                                     sun_shade_k=1.0)
    e_sun = _leaf_extent(p_sun)
    e_shade = _leaf_extent(p_shade)
    assert e_shade > e_sun * 1.3, f"expected shade > 1.3x sun, got {e_shade}/{e_sun}"


def test_leaf_size_clamped_high():
    """k=5, light_factor=0 → eff_size clamped at 2*leaf_size, not exploded."""
    t_shade = _tree_one_apex_with_internode(light_factor=0.0)
    t_sun = _tree_one_apex_with_internode(light_factor=1.0)
    p_shade = build_leaves_primitive(t_shade, leaf_size=0.1, material=_mat(),
                                     sun_shade_k=5.0)
    p_sun = build_leaves_primitive(t_sun, leaf_size=0.1, material=_mat(),
                                   sun_shade_k=5.0)
    ratio = _leaf_extent(p_shade) / _leaf_extent(p_sun)
    # Clamp says shade ≤ 2 * leaf_size, sun = leaf_size → ratio ≤ 2.0 + tolerance.
    assert ratio <= 2.0 + 1e-6


def test_leaf_size_clamped_low():
    """If somehow eff_size would dip below 0.5*leaf_size, it is clamped up.
    With k=5, light_factor=1.0 the formula yields exactly leaf_size, so we
    construct a synthetic regression: light_factor > 1 (shouldn't happen in
    practice but the clamp must still hold)."""
    t = _tree_one_apex_with_internode(light_factor=2.0)
    p = build_leaves_primitive(t, leaf_size=0.1, material=_mat(), sun_shade_k=5.0)
    # eff_size raw = 0.1 * (1 + 5 * (1 - 2)) = 0.1 * -4 = -0.4 → clamped to 0.05
    # Resulting extent must be at least the half-size quad diagonal.
    assert _leaf_extent(p) > 0.0  # i.e. not collapsed to zero
    # And not bigger than the half-clamp would allow (with petiole offset, etc.)
    # The reference (k=0, lf=1) quad has extent E0; the clamped-low quad must
    # have extent ≥ 0.5*E0.
    t_ref = _tree_one_apex_with_internode(light_factor=1.0)
    p_ref = build_leaves_primitive(t_ref, leaf_size=0.1, material=_mat(), sun_shade_k=0.0)
    assert _leaf_extent(p) >= 0.5 * _leaf_extent(p_ref) - 1e-6
```

- [ ] **Step 2 : Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/geom/test_leaves.py -v -k "sun_shade or scales_with_shadow or clamped"`

Expected: all 4 new tests FAIL with `TypeError: build_leaves_primitive() got an unexpected keyword argument 'sun_shade_k'`.

- [ ] **Step 3 : Refactor `_collect_foliage_sites` to return the source Internode**

In `src/palubicki/geom/leaves.py`, replace `_collect_foliage_sites` (lines 62-116) with:

```python
def _collect_foliage_sites(
    tree: Tree, foliage_depth: int
) -> list[tuple[np.ndarray, np.ndarray, "Internode | None"]]:
    """Return list of (position, direction, source_internode) for foliage placement.

    Algorithm:
      1. Apex set = active terminal buds (no children internodes), matching the
         legacy behavior. For foliage_depth == 1 this is the only set.
      2. For depth > 1, walk each apex backward through ``parent_internode`` up to
         (depth-1) extra steps. Already-visited nodes are skipped.

    ``source_internode`` is the internode whose tangent gave the site its
    direction. ``None`` for an apex bud whose parent node has no incoming
    internode (root case) — those sites use a default light_factor of 1.0.

    Direction at each site: parent-internode tangent if available; otherwise
    the apex bud's growth direction.
    """
    if foliage_depth < 1:
        return []

    sites: list[tuple[np.ndarray, np.ndarray, "Internode | None"]] = []
    apex_nodes: list[Node] = []
    for bud in tree.active_buds:
        if bud.state == BudState.DEAD:
            continue
        node = bud.parent_node
        if len(node.children_internodes) != 0:
            continue
        sites.append((
            np.asarray(bud.position, dtype=np.float64),
            np.asarray(bud.direction, dtype=np.float64),
            node.parent_internode,
        ))
        apex_nodes.append(node)

    if foliage_depth <= 1:
        return sites

    visited: set[int] = set(id(n) for n in apex_nodes)
    for apex in apex_nodes:
        current = apex
        for _ in range(foliage_depth - 1):
            if current.parent_internode is None:
                break
            current = current.parent_internode.parent_node
            if id(current) in visited:
                break
            visited.add(id(current))
            if current.parent_internode is not None:
                seg = current.position - current.parent_internode.parent_node.position
                seg_norm = float(np.linalg.norm(seg))
                direction = seg / seg_norm if seg_norm > 1e-12 else np.array([0.0, 1.0, 0.0])
            else:
                direction = np.array([0.0, 1.0, 0.0])
            sites.append((
                np.asarray(current.position, dtype=np.float64),
                direction,
                current.parent_internode,
            ))
    return sites
```

- [ ] **Step 4 : Update `build_leaves_primitive` to accept and apply `sun_shade_k`**

In `src/palubicki/geom/leaves.py`, replace `build_leaves_primitive` (lines 11-59) with:

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
) -> Primitive:
    """Emit `cluster_count` cross-quads (8 verts each) at each foliage site.

    A foliage site is any node within ``foliage_depth`` internode-steps of the
    nearest terminal apex. With foliage_depth=1 this collapses back to
    "apex only" (legacy behavior).

    When ``sun_shade_k > 0`` and the source internode is known, leaf quad
    edge length scales as
        eff_size = leaf_size * (1 + sun_shade_k * (1 - internode.light_factor))
    clamped to [0.5*leaf_size, 2.0*leaf_size]. Sites with no source internode
    (root apex) use light_factor=1.0 → eff_size=leaf_size.
    """
    sites = _collect_foliage_sites(tree, foliage_depth)

    if not sites:
        return Primitive(
            positions=np.zeros((0, 3), dtype=np.float32),
            normals=np.zeros((0, 3), dtype=np.float32),
            uvs=np.zeros((0, 2), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
            material=material,
        )

    verts_per_site = cluster_count * 8
    idx_per_site = cluster_count * 12
    n = len(sites)
    positions = np.empty((n * verts_per_site, 3), dtype=np.float32)
    normals = np.empty((n * verts_per_site, 3), dtype=np.float32)
    uvs = np.empty((n * verts_per_site, 2), dtype=np.float32)
    indices = np.empty((n * idx_per_site,), dtype=np.uint32)

    splay_rad = math.radians(splay_deg)
    min_size = 0.5 * leaf_size
    max_size = 2.0 * leaf_size

    for i, (center, direction, source_iod) in enumerate(sites):
        lf = source_iod.light_factor if source_iod is not None else 1.0
        if sun_shade_k > 0.0:
            eff_size = leaf_size * (1.0 + sun_shade_k * (1.0 - lf))
            eff_size = max(min_size, min(max_size, eff_size))
        else:
            eff_size = leaf_size

        v_start = i * verts_per_site
        i_start = i * idx_per_site
        _emit_leaf_cluster(
            center, direction, eff_size, cluster_count, aspect, splay_rad,
            positions[v_start : v_start + verts_per_site],
            normals[v_start : v_start + verts_per_site],
            uvs[v_start : v_start + verts_per_site],
            indices[i_start : i_start + idx_per_site],
            v_start,
        )
    return Primitive(positions=positions, normals=normals, uvs=uvs, indices=indices, material=material)
```

- [ ] **Step 5 : Update the call site in `builder.py`**

In `src/palubicki/geom/builder.py`, replace the `build_leaves_primitive` call (lines 47-55) with:

```python
        leaf_prim = build_leaves_primitive(
            tree,
            leaf_size=cfg.geom.leaf_size,
            material=leaf_mat,
            cluster_count=cfg.geom.leaf_cluster_count,
            aspect=cfg.geom.leaf_aspect,
            splay_deg=cfg.geom.leaf_splay_deg,
            foliage_depth=cfg.geom.foliage_depth,
            sun_shade_k=cfg.geom.leaf_sun_shade_k,
        )
```

- [ ] **Step 6 : Run the new tests to verify they pass**

Run: `.venv/bin/pytest tests/geom/test_leaves.py -v`

Expected: all leaf tests PASS (the 4 new ones plus the 4 pre-existing ones).

- [ ] **Step 7 : Run the broader geom + sim test scope for regressions**

Run: `.venv/bin/pytest tests/geom/ tests/sim/ -q 2>&1 | tail -10`

Expected: all PASS.

- [ ] **Step 8 : Commit**

```bash
git add src/palubicki/geom/leaves.py src/palubicki/geom/builder.py tests/geom/test_leaves.py
git commit -m "$(cat <<'EOF'
feat(geom): sun/shade leaf size scaling

build_leaves_primitive now accepts sun_shade_k and scales each
cluster's quad size by (1 + k*(1-light_factor)) of the source
internode, clamped to [0.5x, 2.0x] leaf_size. Foliage site
collection now returns the originating Internode so the per-site
light_factor is available at emission time.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7 : Create the `maple.yaml` species preset

**Files:**
- Create: `src/palubicki/configs/species/maple.yaml`
- Modify: `tests/test_config_species.py:53-55` (extend `_list_species` expectation)
- Modify: `tests/test_config_species.py` (add `test_load_preset_maple`)

- [ ] **Step 1 : Write failing tests**

In `tests/test_config_species.py`, modify `test_list_species_finds_three`:

```python
def test_list_species_finds_four():
    names = _list_species()
    assert set(names) == {"oak", "pine", "birch", "maple"}
```

(Delete `test_list_species_finds_three` outright — same coverage, new name.)

Append a new test:

```python
def test_load_preset_maple(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="maple")
    assert cfg.envelope.shape == "ellipsoid"
    assert cfg.phyllotaxy.mode == "decussate"
    assert cfg.phyllotaxy.divergence_angle_deg == pytest.approx(0.0)
    assert cfg.geom.leaf_sun_shade_k == pytest.approx(0.6)
    assert cfg.geom.leaf_cluster_count == 2
```

- [ ] **Step 2 : Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config_species.py::test_list_species_finds_four tests/test_config_species.py::test_load_preset_maple -v`

Expected: both FAIL — `test_list_species_finds_four` finds only `{oak, pine, birch}`; `test_load_preset_maple` raises `ConfigError: unknown species preset: 'maple'`.

- [ ] **Step 3 : Create the maple preset**

Create `src/palubicki/configs/species/maple.yaml`:

```yaml
# Acer campestre — érable champêtre : décussation pure, sun/shade marqué
envelope:
  shape: ellipsoid
  rx: 4.0
  ry: 5.5
  rz: 4.0
  marker_count: 22000
sim:
  internode_length: 0.16
  internode_length_jitter: 0.10
  lambda_apical: 0.80
  alpha_basipetal: 2.1
  max_iterations: 42
tropism:
  w_perception: 1.0
  w_orthotropy_main: 0.32
  w_orthotropy_lateral: 0.04
  w_gravitropism_main: 0.0
  w_gravitropism_lateral: 0.0
  w_phototropism: 0.30
  w_direction_inertia: 0.5
  axis_decay: 0.85
phyllotaxy:
  mode: decussate
  divergence_angle_deg: 0.0
  whorl_count: 2
  branch_angle_deg: 55
  divergence_jitter_deg: 4.0
  branch_angle_jitter_deg: 4.0
shedding:
  quality_threshold: 0.12
  window: 5
  enabled: true
light:
  enabled: true
  k_absorption: 0.55
sag:
  enabled: true
  k: 0.006
  max_bend_deg: 4.0
  rigid_axis_order: 1
geom:
  ring_sides: 10
  pipe_exponent: 2.40
  r_tip: 0.007
  bark_color: [0.40, 0.32, 0.22]
  leaf_size: 0.12
  leaf_aspect: 1.1
  leaf_cluster_count: 2
  leaf_splay_deg: 30
  foliage_depth: 4
  leaf_sun_shade_k: 0.6
```

Note vs the spec § 5.4 wording:
- The spec lists `sim.sympodial.*` and `sim.shade_mortality.*` and `phyllotaxy.dormant_reserve_count` — these belong to Phases 2A/2B which are **already implemented when 2C runs**. If those fields are present in `SimConfig`/`PhyllotaxyConfig`, keep them in the YAML; if they are not yet merged into `main` at execution time, simply omit them. The values above keep the YAML strictly within Phase 2C scope; add the Phase 2A/2B keys back if the corresponding config fields are available.
- `branch_angle_deg: 55` replaces the spec's `branch_angle_by_order: [55.0, 38.0, 28.0, 22.0]` — `PhyllotaxyConfig` exposes the scalar `branch_angle_deg` field in current `main`; the per-order list is a future enhancement (Phase 2A territory). Use the scalar.
- `shedding.reactivation_count` is also Phase 2B; omit until that phase has landed.

- [ ] **Step 4 : Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config_species.py -v`

Expected: all species tests PASS (including the new maple test).

- [ ] **Step 5 : Smoke-run the maple preset end-to-end**

Run:

```bash
.venv/bin/python -m palubicki generate --species maple --seed 42 --marker-count 1000 --iterations 8 -o /tmp/maple_smoke.glb
```

Expected: exit code 0, prints a summary line with non-zero node count.

- [ ] **Step 6 : Commit**

```bash
git add src/palubicki/configs/species/maple.yaml tests/test_config_species.py
git commit -m "$(cat <<'EOF'
feat(species): add maple preset (decussate, sun/shade leaves)

New Acer campestre preset showcases Phase 2C features: canonical
decussation (divergence=0°, 90° per node), opposite leaf pair
(cluster_count=2), and aggressive sun/shade heterophylly
(leaf_sun_shade_k=0.6).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8 : Activate sun/shade in oak, birch, pine presets

**Files:**
- Modify: `src/palubicki/configs/species/oak.yaml:52` (append after foliage_depth)
- Modify: `src/palubicki/configs/species/birch.yaml:55` (append after foliage_depth)
- Modify: `src/palubicki/configs/species/pine.yaml:46` (append after foliage_depth)
- Modify: `tests/test_config_species.py` (extend oak/pine/birch assertions)

- [ ] **Step 1 : Write failing tests for the preset values**

In `tests/test_config_species.py`, extend `test_load_preset_oak`:

```python
def test_load_preset_oak(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="oak")
    assert cfg.envelope.shape == "half_ellipsoid"
    assert cfg.geom.leaf_cluster_count == 3
    assert cfg.geom.leaf_sun_shade_k == pytest.approx(0.7)
    assert str(cfg.geom.bark_texture) == "proc:oak_bark"
```

Extend `test_load_preset_pine`:

```python
def test_load_preset_pine(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="pine")
    assert cfg.envelope.shape == "cone"
    assert cfg.phyllotaxy.mode == "whorled"
    assert cfg.geom.leaf_cluster_count == 5
    assert cfg.geom.leaf_sun_shade_k == pytest.approx(0.0)
```

Extend `test_load_preset_birch`:

```python
def test_load_preset_birch(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="birch")
    assert cfg.envelope.shape == "ellipsoid"
    assert cfg.tropism.w_orthotropy_main == pytest.approx(0.40)
    assert cfg.tropism.w_orthotropy_lateral == pytest.approx(0.05)
    assert cfg.tropism.w_gravitropism_lateral == pytest.approx(0.45)
    assert cfg.phyllotaxy.divergence_jitter_deg == pytest.approx(5.0)
    assert cfg.sag.enabled is True
    assert cfg.sag.k == pytest.approx(0.010)
    assert cfg.geom.leaf_sun_shade_k == pytest.approx(0.4)
```

- [ ] **Step 2 : Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config_species.py::test_load_preset_oak tests/test_config_species.py::test_load_preset_pine tests/test_config_species.py::test_load_preset_birch -v`

Expected: 3 tests FAIL on the `leaf_sun_shade_k` assertion (all currently return 0.0 default).

- [ ] **Step 3 : Append the field to each YAML**

Append the following at the end of `src/palubicki/configs/species/oak.yaml`:

```yaml
  leaf_sun_shade_k: 0.7        # forte hétérophyllie (chêne en sous-bois)
```

(The key must be indented under `geom:` — verify by reading the file first; it should land as a sibling of `foliage_depth`.)

Append at the end of `src/palubicki/configs/species/birch.yaml`:

```yaml
  leaf_sun_shade_k: 0.4        # modéré (bouleau héliophile)
```

Append at the end of `src/palubicki/configs/species/pine.yaml`:

```yaml
  leaf_sun_shade_k: 0.0        # aiguilles : pas de plasticité sun/shade
```

- [ ] **Step 4 : Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config_species.py -v`

Expected: all PASS.

- [ ] **Step 5 : Commit**

```bash
git add src/palubicki/configs/species/oak.yaml src/palubicki/configs/species/birch.yaml src/palubicki/configs/species/pine.yaml tests/test_config_species.py
git commit -m "$(cat <<'EOF'
feat(species): enable sun/shade leaves on oak, birch, pine

Oak gets k=0.7 (broadleaf understorey heterophylly), birch k=0.4
(moderate, more light-loving), pine k=0.0 (needles have no
plastic response). Tests pin the values per preset.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9 : Integration test — decussate maple geometry

**Files:**
- Create: `tests/integration/test_decussate_maple.py`

- [ ] **Step 1 : Write the failing integration test**

Create `tests/integration/test_decussate_maple.py`:

```python
"""Phase 2C: end-to-end check that the maple preset produces decussate
lateral pairs (each consecutive pair rotated ~90° around the parent's axis)."""
import math

import numpy as np
import pytest

from palubicki.config import load_config
from palubicki.sim.simulator import simulate
from palubicki.sim.tree import BudState


pytestmark = pytest.mark.slow


def _trunk_chain_internodes(tree):
    """Return the main-axis (is_main_axis=True) internodes in order from root."""
    chain = []
    node = tree.root
    while True:
        next_iod = None
        for iod in node.children_internodes:
            if iod.is_main_axis:
                next_iod = iod
                break
        if next_iod is None:
            break
        chain.append(next_iod)
        node = next_iod.child_node
    return chain


def test_maple_lateral_pairs_alternate_90deg(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="maple")
    # Use a smaller, faster run; preserve the decussate behaviour to test.
    tree = simulate(cfg)
    chain = _trunk_chain_internodes(tree)
    # Need at least a handful of trunk nodes to compare.
    assert len(chain) >= 4, f"trunk too short: {len(chain)} internodes"

    # For each trunk node, take its lateral_buds and compute the azimuth of
    # the projection onto the plane perpendicular to the local trunk tangent.
    azimuths_per_node = []
    for iod in chain:
        node = iod.child_node
        if len(node.lateral_buds) < 1:
            continue
        tangent = iod.child_node.position - iod.parent_node.position
        tn = np.linalg.norm(tangent)
        if tn < 1e-9:
            continue
        tangent = tangent / tn
        # Build an arbitrary frame perpendicular to tangent.
        canonical = np.array([1.0, 0.0, 0.0]) if abs(tangent[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        right = canonical - np.dot(canonical, tangent) * tangent
        right = right / np.linalg.norm(right)
        up = np.cross(tangent, right)
        bud = node.lateral_buds[0]
        proj = bud.direction - np.dot(bud.direction, tangent) * tangent
        pn = np.linalg.norm(proj)
        if pn < 1e-9:
            continue
        az = math.atan2(np.dot(proj, up), np.dot(proj, right))
        azimuths_per_node.append(az)

    assert len(azimuths_per_node) >= 4, (
        f"not enough lateral pairs to test, got {len(azimuths_per_node)}"
    )

    # Successive azimuths should differ by ~90° (the decussate hallmark).
    # Allow ±25° tolerance for tropism + jitter perturbation.
    diffs = []
    for a, b in zip(azimuths_per_node, azimuths_per_node[1:]):
        delta = math.degrees(abs(((b - a + math.pi) % (2 * math.pi)) - math.pi))
        diffs.append(delta)
    median = float(np.median(diffs))
    assert 65.0 <= median <= 115.0, (
        f"expected median pair-to-pair azimuth diff ≈ 90°, got {median:.1f}°"
    )
```

- [ ] **Step 2 : Run the test**

Run: `.venv/bin/pytest tests/integration/test_decussate_maple.py -v -m slow`

Expected: PASS. If FAIL on the median check, investigate whether jitter is too strong vs the tolerance — but do **not** weaken the test below ±25° without first checking that `lateral_bud_directions` truly returns 90° offsets for the decussate mode (validated by Task 2 unit tests).

- [ ] **Step 3 : Commit**

```bash
git add tests/integration/test_decussate_maple.py
git commit -m "$(cat <<'EOF'
test(integration): verify maple preset produces decussate laterals

Simulates the maple preset, walks the trunk's main axis, and
checks that successive nodes' lateral pairs are rotated by ~90°
around the local tangent (±25° to absorb tropism + jitter).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10 : Integration test — sun/shade gradient on oak

**Files:**
- Create: `tests/integration/test_sun_shade_oak.py`

- [ ] **Step 1 : Write the failing integration test**

Create `tests/integration/test_sun_shade_oak.py`:

```python
"""Phase 2C: end-to-end check that with leaf_sun_shade_k>0 and light
enabled, lower-canopy leaves are larger than upper-canopy leaves."""
import numpy as np
import pytest

from palubicki.config import load_config
from palubicki.geom.leaves import _collect_foliage_sites
from palubicki.sim.simulator import simulate


pytestmark = pytest.mark.slow


def test_oak_lower_canopy_leaves_larger_than_upper(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="oak")
    tree = simulate(cfg)

    # Collect each foliage site's (y, source_iod.light_factor).
    sites = _collect_foliage_sites(tree, cfg.geom.foliage_depth)
    assert len(sites) > 10, f"too few foliage sites to compare: {len(sites)}"

    ys = np.array([s[0][1] for s in sites])
    lfs = np.array([
        s[2].light_factor if s[2] is not None else 1.0 for s in sites
    ])
    leaf_size = cfg.geom.leaf_size
    k = cfg.geom.leaf_sun_shade_k
    eff_sizes = np.clip(
        leaf_size * (1.0 + k * (1.0 - lfs)),
        0.5 * leaf_size, 2.0 * leaf_size,
    )

    y_max = ys.max()
    y_min = ys.min()
    span = max(1e-6, y_max - y_min)
    upper_mask = ys > y_min + 0.7 * span
    lower_mask = ys < y_min + 0.3 * span

    if not upper_mask.any() or not lower_mask.any():
        pytest.skip("oak canopy did not develop vertical spread in this run")

    mean_upper = float(eff_sizes[upper_mask].mean())
    mean_lower = float(eff_sizes[lower_mask].mean())
    assert mean_lower > 1.1 * mean_upper, (
        f"expected lower-canopy mean leaf size > 1.1x upper, "
        f"got lower={mean_lower:.4f} upper={mean_upper:.4f}"
    )
```

- [ ] **Step 2 : Run the test**

Run: `.venv/bin/pytest tests/integration/test_sun_shade_oak.py -v -m slow`

Expected: PASS. If `pytest.skip` triggers, the simulation didn't grow tall enough — bump `iterations` via CLI override or accept the skip and re-test after preset retuning.

- [ ] **Step 3 : Commit**

```bash
git add tests/integration/test_sun_shade_oak.py
git commit -m "$(cat <<'EOF'
test(integration): verify oak develops sun/shade leaf gradient

Simulates oak with light enabled and leaf_sun_shade_k=0.7, then
checks that the bottom 30% of the canopy has mean effective leaf
size > 1.1x the top 30%. Skips if the tree did not develop enough
vertical spread.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11 : Regenerate species goldens (oak, pine, birch) and add maple golden

**Files:**
- Modify: `tests/golden/test_species_goldens.py:32` (extend parametrize)
- Update: `tests/golden/data/species_oak.sha256`
- Update: `tests/golden/data/species_pine.sha256`
- Update: `tests/golden/data/species_birch.sha256`
- Create: `tests/golden/data/species_maple.sha256`

- [ ] **Step 1 : Add `maple` to the parametrize list**

In `tests/golden/test_species_goldens.py`, replace line 32:

```python
@pytest.mark.parametrize("species", ["oak", "pine", "birch", "maple"])
```

- [ ] **Step 2 : Regenerate the goldens**

Run:

```bash
.venv/bin/pytest tests/golden/test_species_goldens.py -m slow --update-goldens -v
```

Expected: 4 tests skip with `golden written for <species>; ...`. Files `species_oak.sha256`, `species_pine.sha256`, `species_birch.sha256` are overwritten; `species_maple.sha256` is created.

- [ ] **Step 3 : Verify the goldens lock**

Run: `.venv/bin/pytest tests/golden/test_species_goldens.py -m slow -v`

Expected: 4 tests PASS (the hashes now match the just-written files).

- [ ] **Step 4 : Confirm the golden file set**

Run: `ls tests/golden/data/`

Expected: `ellipsoid.sha256  ellipsoid_light.sha256  species_birch.sha256  species_maple.sha256  species_oak.sha256  species_pine.sha256`.

- [ ] **Step 5 : Commit**

```bash
git add tests/golden/test_species_goldens.py tests/golden/data/
git commit -m "$(cat <<'EOF'
test(golden): regenerate species goldens for Phase 2C

Phyllotaxy now supports decussate mode and leaves scale by
captured light_factor; oak/pine/birch buffer hashes shift even
without preset value changes because the simulator now writes
light_factor into every Internode. Adds species_maple.sha256.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12 : Run the full suite to confirm no regressions

**Files:** none (verification step)

- [ ] **Step 1 : Run all tests**

```bash
.venv/bin/pytest --no-header -q 2>&1 | tail -15
```

Expected: all PASS, including the new tests in `tests/sim/test_phyllotaxy.py`, `tests/sim/test_tree.py`, `tests/sim/test_simulator_light_capture.py`, `tests/geom/test_leaves.py`, `tests/test_config.py`, `tests/test_config_species.py`, `tests/integration/test_decussate_maple.py`, `tests/integration/test_sun_shade_oak.py`, and the regenerated `tests/golden/test_species_goldens.py`.

- [ ] **Step 2 : If failures appear, do NOT mass-update goldens**

If a non-golden test fails, fix the underlying cause in the relevant task. Do **not** rerun `--update-goldens` to mask drift; that hides real regressions.

---

## Task 13 : Update `README.md` to mention Phase 2C

**Files:**
- Modify: `README.md` (Roadmap section, ~line 162)

- [ ] **Step 1 : Locate the Roadmap section**

Run: `grep -n "Roadmap\|V4\|Phase\|Apple.*willow" README.md`

Identify the existing `## Roadmap` block (around line 162) and the `V4` bullet at line 166.

- [ ] **Step 2 : Add a Phase 2C bullet**

In `README.md`, inside the `## Roadmap` section, after the existing `V4` bullet line (the one starting with `~~**V4** : species presets...`), insert:

```markdown
- ~~**Phase 2C** : phyllotaxie décussée + feuilles sun/shade (érable). Le mode `decussate` ajoute des paires opposées tournées de 90° par node, `geom.leaf_sun_shade_k` fait varier la taille des feuilles selon le `light_factor` capturé à la création de l'internode, et un nouveau préset `maple.yaml` exploite les deux — livré.~~
```

- [ ] **Step 3 : Verify the README still renders cleanly**

Run: `head -180 README.md | tail -30`

Expected: the new bullet appears in the Roadmap section without breaking adjacent formatting.

- [ ] **Step 4 : Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs(readme): announce Phase 2C in roadmap

Phyllotaxie décussée, feuilles sun/shade, preset maple livrés.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14 : Mark suggestions #4 and #5 as addressed in the simulation review

**Files:**
- Modify: `docs/2026-05-27-simulation-review.md` (`Suggestion #4` and `#5` references)

Note: the simulation review's numbered list (lines 121-150) uses #4 = "Croissance préformée" and #5 = "Réitération". The **Phase 2C spec** instead uses "#4 et #5" to refer to the Priority-2 phyllotaxy + sun/shade suggestions discussed elsewhere in the review. To respect the spec's intent (decussate + sun/shade) and avoid mismarking unrelated work, this task adds a clearly-scoped Phase 2C completion note in the review document rather than rewriting the original list.

- [ ] **Step 1 : Locate the simulation review section dealing with phyllotaxy / leaf size**

Run: `grep -n "phyllotax\|leaf\|feuille\|sun.shade\|Phase 2C\|hétérophyll" docs/2026-05-27-simulation-review.md`

Identify the existing section §6 "Phyllotaxie : branches vs feuilles individuelles" (around line 192) and the §3 area (look for paragraph mentioning `leaf_cluster_count` around lines 113-117).

- [ ] **Step 2 : Append a Phase 2C status block at the end of the document**

Append to `docs/2026-05-27-simulation-review.md`:

```markdown

---

## 7. Statut Phase 2C (2026-05-27)

**Suggestion Priorité 2 #4 — Phyllotaxie décussée :** ADRESSÉE. Le mode
`decussate` est implémenté dans `phyllotaxy.py::lateral_bud_directions`
(`PhyllotaxyConfig.mode = "decussate"`). Avec `divergence_angle_deg: 0.0`,
chaque node alterne 90° autour du tangent, reproduisant le pattern érable /
frêne / dogwood. Le nouveau préset `maple.yaml` l'exploite. Test
d'intégration `tests/integration/test_decussate_maple.py` valide que la
médiane des angles entre paires successives ≈ 90°.

**Suggestion Priorité 2 #5 — Feuilles sun/shade :** ADRESSÉE. `GeomConfig`
expose désormais `leaf_sun_shade_k` (validé `[0, 2]`) ; chaque `Internode`
capture `light_factor` à sa création (`simulator.py`), et `geom/leaves.py`
calcule par feuille `eff_size = leaf_size * (1 + k * (1 - light_factor))`
clampé à `[0.5×, 2×]`. Les présets oak (k=0.7) et birch (k=0.4) activent
le mécanisme ; pine (k=0.0) reste neutre (aiguilles sans plasticité). Test
d'intégration `tests/integration/test_sun_shade_oak.py` confirme un
gradient vertical de taille de feuille en condition d'ombrage.

Limitation acceptée (cf. spec §4.7) : le grid voxel de lumière utilise
toujours `light.leaf_area` constant — pas de couplage feuille→absorption→
feuille pour éviter une boucle de point fixe. Effet purement visuel.

Suggestions Priorité 2 originales du document (§4) #4 (« croissance
préformée ») et #5 (« réitération ») sont **non concernées** par Phase 2C
et restent ouvertes pour une phase ultérieure.
```

- [ ] **Step 3 : Commit**

```bash
git add docs/2026-05-27-simulation-review.md
git commit -m "$(cat <<'EOF'
docs(review): note Phase 2C addresses decussate + sun/shade

Adds a Phase 2C status section to the simulation review marking
the Priority-2 phyllotaxy and leaf-size suggestions as
implemented, and explicitly notes that the §4 list's #4 and #5
(preformed growth, reiteration) remain open.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Done

All Phase 2C goals shipped:
- `PhyllotaxyConfig.mode` accepts `"decussate"`; `lateral_bud_directions` emits per-node 90°-alternating lateral pairs.
- `GeomConfig.leaf_sun_shade_k` added with `[0, 2]` validation.
- `Internode.light_factor` captured at creation in `simulator.py`.
- `geom/leaves.py` scales each leaf quad by `(1 + k * (1 - light_factor))`, clamped `[0.5×, 2×]`.
- New `maple.yaml` preset (decussate + k=0.6); oak/birch get sun/shade activated, pine stays k=0.
- Goldens regenerated; integration tests pin decussate angle distribution and oak vertical leaf-size gradient.
- README + simulation review updated.
