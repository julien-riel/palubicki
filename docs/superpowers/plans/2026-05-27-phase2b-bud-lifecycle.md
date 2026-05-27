# Phase 2B — Bud Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add shade-induced bud mortality and epicormic reiteration via dormant reserve buds.

**Architecture:** Two additive subsystems on top of Phase 2A. `kill_shaded_buds()` walks active buds, increments a per-bud `low_light_steps` counter when `light_factor` drops below threshold, and flips state to `DEAD` after N consecutive low-light iterations. A new `BudState.RESERVE` represents pre-formed dormant buds attached to each node; the shedding pass calls `activate_reserves_on_shed()` when it removes a child subtree, converting RESERVE buds to ACTIVE and routing them into `tree.active_buds`.

**Tech Stack:** Python 3.11+, pytest, numpy, dataclasses, frozen YAML configs.

**Reference spec:** `docs/superpowers/specs/2026-05-27-phase2b-bud-lifecycle-design.md`

---

## Pre-flight

Before starting any task, confirm the test suite passes at HEAD (Phase 2A complete).

- [ ] **Run baseline**

```bash
cd /Users/julienriel/src/palubicki
.venv/bin/pytest -x --no-header -q 2>&1 | tail -10
```

Expected: `passed` (the suite is green before Phase 2B work begins). If Phase 2A has not landed, stop and surface the gap — this plan assumes `Bud.low_quality_steps` already exists.

- [ ] **Confirm Phase 2A field is present**

```bash
.venv/bin/python -c "from dataclasses import fields; from palubicki.sim.tree import Bud; print(sorted(f.name for f in fields(Bud)))"
```

Expected output must include `low_quality_steps`. If not, halt — Phase 2A is a hard prerequisite.

---

## Task 1: Add `BudState.RESERVE` enum value

**Files:**
- Modify: `src/palubicki/sim/tree.py:11-14` (BudState enum)
- Test: `tests/sim/test_tree.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_tree.py`:

```python
def test_bud_state_has_reserve():
    assert BudState.RESERVE is not None
    assert BudState.RESERVE not in (BudState.ACTIVE, BudState.DORMANT, BudState.DEAD)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/pytest tests/sim/test_tree.py::test_bud_state_has_reserve -v
```

Expected: FAIL with `AttributeError: RESERVE`.

- [ ] **Step 3: Add `RESERVE` to the enum**

In `src/palubicki/sim/tree.py`, replace the `BudState` block (lines 11-14):

```python
class BudState(Enum):
    ACTIVE = auto()
    DORMANT = auto()    # bud that failed (U-turn, no markers, etc.)
    DEAD = auto()       # irrecoverable
    RESERVE = auto()    # pre-formed dormant bud, reactivable on shed
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/pytest tests/sim/test_tree.py::test_bud_state_has_reserve -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/tree.py tests/sim/test_tree.py
git commit -m "feat(tree): add BudState.RESERVE for preformed dormant buds"
```

---

## Task 2: Add `Bud.low_light_steps` field

**Files:**
- Modify: `src/palubicki/sim/tree.py` (Bud dataclass)
- Test: `tests/sim/test_tree.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_tree.py`:

```python
def test_bud_default_low_light_steps_is_zero():
    bud = Bud(position=np.zeros(3), direction=np.array([0, 1, 0]),
              axis_order=0, parent_node=Node(position=np.zeros(3)))
    assert bud.low_light_steps == 0
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/pytest tests/sim/test_tree.py::test_bud_default_low_light_steps_is_zero -v
```

Expected: FAIL with `AttributeError: 'Bud' object has no attribute 'low_light_steps'`.

- [ ] **Step 3: Add the field**

In `src/palubicki/sim/tree.py`, add `low_light_steps: int = 0` to the `Bud` dataclass, immediately after the existing `low_quality_steps` field added by Phase 2A. Do NOT rewrite the dataclass — only add the new field.

After the edit, the Bud dataclass should look like:

```python
@dataclass(eq=False)
class Bud:
    position: np.ndarray
    direction: np.ndarray
    axis_order: int
    parent_node: "Node"
    age: int = 0
    state: BudState = BudState.ACTIVE
    low_quality_steps: int = 0     # Phase 2A
    low_light_steps: int = 0       # Phase 2B
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/pytest tests/sim/test_tree.py::test_bud_default_low_light_steps_is_zero -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/tree.py tests/sim/test_tree.py
git commit -m "feat(tree): add Bud.low_light_steps counter for shade mortality"
```

---

## Task 3: Add `Node.dormant_reserve_buds` field

**Files:**
- Modify: `src/palubicki/sim/tree.py` (Node dataclass)
- Test: `tests/sim/test_tree.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_tree.py`:

```python
def test_node_default_dormant_reserve_buds_is_empty_list():
    node = Node(position=np.zeros(3))
    assert node.dormant_reserve_buds == []
    # Confirm each Node gets its own list (no shared default).
    other = Node(position=np.zeros(3))
    node.dormant_reserve_buds.append("sentinel")
    assert other.dormant_reserve_buds == []
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/pytest tests/sim/test_tree.py::test_node_default_dormant_reserve_buds_is_empty_list -v
```

Expected: FAIL with `AttributeError: 'Node' object has no attribute 'dormant_reserve_buds'`.

- [ ] **Step 3: Add the field**

In `src/palubicki/sim/tree.py`, add `dormant_reserve_buds` to the `Node` dataclass, immediately after `lateral_buds`:

```python
@dataclass(eq=False)
class Node:
    position: np.ndarray
    parent_internode: Optional["Internode"] = None
    children_internodes: list["Internode"] = field(default_factory=list)
    terminal_bud: Optional[Bud] = None
    lateral_buds: list[Bud] = field(default_factory=list)
    dormant_reserve_buds: list[Bud] = field(default_factory=list)   # Phase 2B
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/pytest tests/sim/test_tree.py::test_node_default_dormant_reserve_buds_is_empty_list -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/tree.py tests/sim/test_tree.py
git commit -m "feat(tree): add Node.dormant_reserve_buds for reiteration reserve"
```

---

## Task 4: Add `ShadeMortalityConfig` dataclass + Config wiring

**Files:**
- Modify: `src/palubicki/config.py` (new dataclass, add to Config, register in `_SECTION_TYPES`, validate in `__post_init__`)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_shade_mortality_config_defaults():
    from palubicki.config import ShadeMortalityConfig
    c = ShadeMortalityConfig()
    assert c.enabled is False
    assert c.light_threshold == 0.15
    assert c.n_consecutive_steps == 3


def test_config_includes_shade_mortality(tmp_path):
    from palubicki.config import ShadeMortalityConfig
    cfg = _make_config(output=tmp_path / "out.glb")
    assert isinstance(cfg.sim.shade_mortality, ShadeMortalityConfig)
    assert cfg.sim.shade_mortality.enabled is False


def test_config_rejects_light_threshold_out_of_range(tmp_path):
    from palubicki.config import ShadeMortalityConfig
    with pytest.raises(ConfigError, match="light_threshold"):
        _make_config(
            sim=SimConfig(shade_mortality=ShadeMortalityConfig(light_threshold=1.5)),
            output=tmp_path / "out.glb",
        )


def test_config_rejects_n_consecutive_steps_zero(tmp_path):
    from palubicki.config import ShadeMortalityConfig
    with pytest.raises(ConfigError, match="n_consecutive_steps"):
        _make_config(
            sim=SimConfig(shade_mortality=ShadeMortalityConfig(n_consecutive_steps=0)),
            output=tmp_path / "out.glb",
        )


def test_config_rejects_shade_mortality_enabled_without_light(tmp_path):
    from palubicki.config import LightConfig, ShadeMortalityConfig
    with pytest.raises(ConfigError, match="shade_mortality.*light"):
        _make_config(
            sim=SimConfig(shade_mortality=ShadeMortalityConfig(enabled=True)),
            light=LightConfig(enabled=False),
            output=tmp_path / "out.glb",
        )
```

Also update the `_make_config` helper at the top of the file so callers can override `light=`. Replace the helper with:

```python
def _make_config(**overrides):
    from palubicki.config import LightConfig
    base = dict(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=1.0, ry=1.0, rz=1.0),
        sim=SimConfig(),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        light=LightConfig(),
    )
    base.update(overrides)
    return Config(**base)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/pytest tests/test_config.py::test_shade_mortality_config_defaults tests/test_config.py::test_config_includes_shade_mortality tests/test_config.py::test_config_rejects_light_threshold_out_of_range tests/test_config.py::test_config_rejects_n_consecutive_steps_zero tests/test_config.py::test_config_rejects_shade_mortality_enabled_without_light -v
```

Expected: ALL FAIL — `ShadeMortalityConfig` does not exist.

- [ ] **Step 3: Add `ShadeMortalityConfig` and wire it into `SimConfig`**

In `src/palubicki/config.py`, add the new dataclass immediately after the existing `SimConfig` block:

```python
@dataclass(frozen=True)
class ShadeMortalityConfig:
    """Kills buds whose light_factor stays below threshold for N consecutive steps."""
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    # Light factor below which a bud is considered "shaded".
    # 0.0 = total darkness, 1.0 = full sun (Beer-Lambert output).
    # 0.15 = typical closed-canopy understory.
    light_threshold: float = field(
        default=0.15, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.01}}
    )
    # Consecutive steps under threshold before death. 3 = patient
    # (a passing shadow won't kill), 1 = ultra-reactive.
    n_consecutive_steps: int = field(
        default=3, metadata={"ui": {"min": 1, "max": 10, "step": 1}}
    )
```

Then add a `shade_mortality` field to `SimConfig`. Locate the existing `SimConfig` block and append at the end of its fields:

```python
    # Phase 2B: shade-induced bud mortality.
    shade_mortality: "ShadeMortalityConfig" = field(default_factory=lambda: ShadeMortalityConfig())
```

Note: `SimConfig` is `frozen=True` — adding a `default_factory` field is fine since it remains immutable at instantiation.

- [ ] **Step 4: Add validation in `Config.__post_init__`**

In `src/palubicki/config.py`, inside `Config.__post_init__`, after the existing `sim` block validations and BEFORE the `tropism` block, insert:

```python
        sm = s.shade_mortality
        if not (0.0 <= sm.light_threshold <= 1.0):
            raise ConfigError(
                f"sim.shade_mortality.light_threshold must be in [0, 1], got {sm.light_threshold}"
            )
        if sm.n_consecutive_steps < 1:
            raise ConfigError(
                f"sim.shade_mortality.n_consecutive_steps must be >= 1, got {sm.n_consecutive_steps}"
            )
        if sm.enabled and not self.light.enabled:
            raise ConfigError(
                "sim.shade_mortality.enabled=True requires light.enabled=True"
            )
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.venv/bin/pytest tests/test_config.py -k "shade_mortality or includes_shade" -v
```

Expected: 5 PASS.

- [ ] **Step 6: Run the full config suite to confirm no regression**

```bash
.venv/bin/pytest tests/test_config.py tests/test_config_yaml.py tests/test_config_species.py -q
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "feat(config): add ShadeMortalityConfig + validation"
```

---

## Task 5: Add `PhyllotaxyConfig.dormant_reserve_count`

**Files:**
- Modify: `src/palubicki/config.py` (PhyllotaxyConfig + validation)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_phyllotaxy_dormant_reserve_count_default():
    p = PhyllotaxyConfig()
    assert p.dormant_reserve_count == 0


def test_config_rejects_negative_dormant_reserve_count(tmp_path):
    with pytest.raises(ConfigError, match="dormant_reserve_count"):
        _make_config(
            phyllotaxy=PhyllotaxyConfig(dormant_reserve_count=-1),
            output=tmp_path / "out.glb",
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/pytest tests/test_config.py::test_phyllotaxy_dormant_reserve_count_default tests/test_config.py::test_config_rejects_negative_dormant_reserve_count -v
```

Expected: FAIL — `dormant_reserve_count` does not exist.

- [ ] **Step 3: Add the field**

In `src/palubicki/config.py`, add to `PhyllotaxyConfig` after `branch_angle_jitter_deg`:

```python
    # Phase 2B: count of pre-formed RESERVE buds emitted per new node.
    # 0 = disabled. 1-2 typical for strongly reiterating broadleaves (oak, poplar).
    dormant_reserve_count: int = field(
        default=0, metadata={"ui": {"min": 0, "max": 5, "step": 1}}
    )
```

- [ ] **Step 4: Add validation in `Config.__post_init__`**

In `Config.__post_init__`, inside the existing `p = self.phyllotaxy` block, append:

```python
        if p.dormant_reserve_count < 0:
            raise ConfigError(
                f"phyllotaxy.dormant_reserve_count must be >= 0, got {p.dormant_reserve_count}"
            )
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.venv/bin/pytest tests/test_config.py::test_phyllotaxy_dormant_reserve_count_default tests/test_config.py::test_config_rejects_negative_dormant_reserve_count -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "feat(config): add PhyllotaxyConfig.dormant_reserve_count"
```

---

## Task 6: Add `SheddingConfig.reactivation_count`

**Files:**
- Modify: `src/palubicki/config.py` (SheddingConfig + validation)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_shedding_reactivation_count_default():
    s = SheddingConfig()
    assert s.reactivation_count == 1


def test_config_rejects_negative_reactivation_count(tmp_path):
    with pytest.raises(ConfigError, match="reactivation_count"):
        _make_config(
            shedding=SheddingConfig(reactivation_count=-1),
            output=tmp_path / "out.glb",
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/pytest tests/test_config.py::test_shedding_reactivation_count_default tests/test_config.py::test_config_rejects_negative_reactivation_count -v
```

Expected: FAIL — field missing.

- [ ] **Step 3: Add the field**

In `src/palubicki/config.py`, replace the `SheddingConfig` block with:

```python
@dataclass(frozen=True)
class SheddingConfig:
    quality_threshold: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 5.0, "step": 0.05}})
    window: int = field(default=5, metadata={"ui": {"min": 1, "max": 20, "step": 1}})
    enabled: bool = field(default=True, metadata={"ui": {"label": "Enabled"}})
    # Phase 2B: number of RESERVE buds to activate per shed branch.
    # 0 = disable reiteration even if reserves exist; 1 typical; 2-3 for poplar/willow.
    reactivation_count: int = field(
        default=1, metadata={"ui": {"min": 0, "max": 5, "step": 1}}
    )
```

- [ ] **Step 4: Add validation in `Config.__post_init__`**

In `Config.__post_init__`, after the `p = self.phyllotaxy` block, add a new `sh = self.shedding` block:

```python
        sh = self.shedding
        if sh.reactivation_count < 0:
            raise ConfigError(
                f"shedding.reactivation_count must be >= 0, got {sh.reactivation_count}"
            )
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.venv/bin/pytest tests/test_config.py::test_shedding_reactivation_count_default tests/test_config.py::test_config_rejects_negative_reactivation_count -v
```

Expected: PASS.

- [ ] **Step 6: Run full config + shedding tests as regression check**

```bash
.venv/bin/pytest tests/test_config.py tests/sim/test_shedding.py -q
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "feat(config): add SheddingConfig.reactivation_count"
```

---

## Task 7: Implement `sim/shade_mortality.py`

**Files:**
- Create: `src/palubicki/sim/shade_mortality.py`
- Create: `tests/sim/test_shade_mortality.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sim/test_shade_mortality.py`:

```python
import numpy as np

from palubicki.config import ShadeMortalityConfig
from palubicki.sim.shade_mortality import kill_shaded_buds
from palubicki.sim.tree import Bud, BudState, Node


def _make_bud(state=BudState.ACTIVE):
    node = Node(position=np.zeros(3))
    return Bud(
        position=np.zeros(3),
        direction=np.array([0.0, 1.0, 0.0]),
        axis_order=0,
        parent_node=node,
        state=state,
    )


def test_kill_skipped_when_disabled():
    bud = _make_bud()
    cfg = ShadeMortalityConfig(enabled=False, light_threshold=0.5, n_consecutive_steps=1)
    n = kill_shaded_buds([bud], {bud: 0.0}, cfg)
    assert n == 0
    assert bud.state is BudState.ACTIVE
    assert bud.low_light_steps == 0


def test_counter_increments_under_threshold():
    bud = _make_bud()
    cfg = ShadeMortalityConfig(enabled=True, light_threshold=0.5, n_consecutive_steps=10)
    kill_shaded_buds([bud], {bud: 0.1}, cfg)
    assert bud.low_light_steps == 1
    assert bud.state is BudState.ACTIVE


def test_counter_resets_above_threshold():
    bud = _make_bud()
    bud.low_light_steps = 4
    cfg = ShadeMortalityConfig(enabled=True, light_threshold=0.5, n_consecutive_steps=10)
    kill_shaded_buds([bud], {bud: 0.9}, cfg)
    assert bud.low_light_steps == 0
    assert bud.state is BudState.ACTIVE


def test_dies_after_n_consecutive_steps():
    bud = _make_bud()
    cfg = ShadeMortalityConfig(enabled=True, light_threshold=0.5, n_consecutive_steps=3)
    for _ in range(2):
        kill_shaded_buds([bud], {bud: 0.0}, cfg)
        assert bud.state is BudState.ACTIVE
    killed = kill_shaded_buds([bud], {bud: 0.0}, cfg)
    assert killed == 1
    assert bud.state is BudState.DEAD


def test_doesnt_kill_reserves_or_dormants():
    reserve = _make_bud(state=BudState.RESERVE)
    dormant = _make_bud(state=BudState.DORMANT)
    dead = _make_bud(state=BudState.DEAD)
    cfg = ShadeMortalityConfig(enabled=True, light_threshold=0.5, n_consecutive_steps=1)
    light = {reserve: 0.0, dormant: 0.0, dead: 0.0}
    n = kill_shaded_buds([reserve, dormant, dead], light, cfg)
    assert n == 0
    assert reserve.state is BudState.RESERVE
    assert reserve.low_light_steps == 0
    assert dormant.state is BudState.DORMANT
    assert dead.state is BudState.DEAD


def test_missing_light_factor_defaults_to_full_sun():
    bud = _make_bud()
    cfg = ShadeMortalityConfig(enabled=True, light_threshold=0.5, n_consecutive_steps=1)
    # No entry for this bud → default 1.0 (full sun) → counter resets, no death.
    kill_shaded_buds([bud], {}, cfg)
    assert bud.state is BudState.ACTIVE
    assert bud.low_light_steps == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/pytest tests/sim/test_shade_mortality.py -v
```

Expected: ALL FAIL with `ModuleNotFoundError: palubicki.sim.shade_mortality`.

- [ ] **Step 3: Implement `sim/shade_mortality.py`**

Create `src/palubicki/sim/shade_mortality.py`:

```python
# src/palubicki/sim/shade_mortality.py
from __future__ import annotations

from palubicki.config import ShadeMortalityConfig
from palubicki.sim.tree import Bud, BudState


def kill_shaded_buds(
    buds: list[Bud],
    light_factor: dict[Bud, float],
    cfg: ShadeMortalityConfig,
) -> int:
    """Mark ACTIVE buds DEAD when light_factor stays below threshold for N steps.

    Returns the number of buds killed in this call.

    Only ACTIVE buds are considered. RESERVE / DORMANT / DEAD are skipped
    entirely (their counters are not touched).

    A bud missing from ``light_factor`` is treated as receiving full sun (1.0)
    — a conservative default that does not trigger mortality.
    """
    if not cfg.enabled:
        return 0
    killed = 0
    for bud in buds:
        if bud.state is not BudState.ACTIVE:
            continue
        lf = light_factor.get(bud, 1.0)
        if lf < cfg.light_threshold:
            bud.low_light_steps += 1
            if bud.low_light_steps >= cfg.n_consecutive_steps:
                bud.state = BudState.DEAD
                killed += 1
        else:
            bud.low_light_steps = 0
    return killed
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/pytest tests/sim/test_shade_mortality.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/shade_mortality.py tests/sim/test_shade_mortality.py
git commit -m "feat(sim): add shade_mortality.kill_shaded_buds()"
```

---

## Task 8: Implement `sim/reiteration.py`

**Files:**
- Create: `src/palubicki/sim/reiteration.py`
- Create: `tests/sim/test_reiteration.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sim/test_reiteration.py`:

```python
import numpy as np

from palubicki.sim.reiteration import activate_reserves_on_shed
from palubicki.sim.tree import Bud, BudState, Node


def _node_with_reserves(k: int) -> Node:
    node = Node(position=np.zeros(3))
    for _ in range(k):
        b = Bud(
            position=np.zeros(3),
            direction=np.array([1.0, 0.0, 0.0]),
            axis_order=1,
            parent_node=node,
            state=BudState.RESERVE,
        )
        b.low_quality_steps = 7   # Phase 2A counter — must be reset on activation
        b.low_light_steps = 5     # Phase 2B counter — same
        b.age = 12
        node.dormant_reserve_buds.append(b)
    return node


def test_activate_returns_empty_when_no_reserves():
    node = _node_with_reserves(0)
    out = activate_reserves_on_shed(node, n_to_activate=2)
    assert out == []
    assert node.lateral_buds == []


def test_activate_pops_n_buds():
    node = _node_with_reserves(3)
    out = activate_reserves_on_shed(node, n_to_activate=2)
    assert len(out) == 2
    assert len(node.dormant_reserve_buds) == 1
    assert len(node.lateral_buds) == 2


def test_activated_buds_change_state_to_active():
    node = _node_with_reserves(2)
    out = activate_reserves_on_shed(node, n_to_activate=2)
    for b in out:
        assert b.state is BudState.ACTIVE
    for b in node.lateral_buds:
        assert b.state is BudState.ACTIVE


def test_activated_buds_have_counters_reset():
    node = _node_with_reserves(1)
    out = activate_reserves_on_shed(node, n_to_activate=1)
    b = out[0]
    assert b.low_quality_steps == 0
    assert b.low_light_steps == 0
    assert b.age == 0


def test_activate_caps_at_available_reserves():
    node = _node_with_reserves(2)
    out = activate_reserves_on_shed(node, n_to_activate=5)
    assert len(out) == 2
    assert node.dormant_reserve_buds == []
    assert len(node.lateral_buds) == 2


def test_activate_zero_or_negative_is_noop():
    node = _node_with_reserves(2)
    assert activate_reserves_on_shed(node, n_to_activate=0) == []
    assert activate_reserves_on_shed(node, n_to_activate=-3) == []
    assert len(node.dormant_reserve_buds) == 2
    assert node.lateral_buds == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/pytest tests/sim/test_reiteration.py -v
```

Expected: ALL FAIL with `ModuleNotFoundError: palubicki.sim.reiteration`.

- [ ] **Step 3: Implement `sim/reiteration.py`**

Create `src/palubicki/sim/reiteration.py`:

```python
# src/palubicki/sim/reiteration.py
from __future__ import annotations

from palubicki.sim.tree import Bud, BudState, Node


def activate_reserves_on_shed(
    parent_node: Node,
    n_to_activate: int = 1,
) -> list[Bud]:
    """Activate up to ``n_to_activate`` RESERVE buds attached to ``parent_node``.

    Activated buds:
      - transition state RESERVE -> ACTIVE,
      - are removed from ``parent_node.dormant_reserve_buds``,
      - are appended to ``parent_node.lateral_buds``,
      - have their counters (low_quality_steps, low_light_steps, age) reset.

    If fewer reserves exist than requested, activates all available without
    raising. If ``n_to_activate`` <= 0 or no reserves remain, returns [].

    The caller is responsible for appending the returned buds to
    ``tree.active_buds`` so they participate in subsequent iterations.
    """
    if n_to_activate <= 0 or not parent_node.dormant_reserve_buds:
        return []
    n_actual = min(n_to_activate, len(parent_node.dormant_reserve_buds))
    activated: list[Bud] = []
    for _ in range(n_actual):
        bud = parent_node.dormant_reserve_buds.pop()
        bud.state = BudState.ACTIVE
        bud.low_quality_steps = 0
        bud.low_light_steps = 0
        bud.age = 0
        parent_node.lateral_buds.append(bud)
        activated.append(bud)
    return activated
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/pytest tests/sim/test_reiteration.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/reiteration.py tests/sim/test_reiteration.py
git commit -m "feat(sim): add reiteration.activate_reserves_on_shed()"
```

---

## Task 9: Add `_reserve_directions` to phyllotaxy

**Files:**
- Modify: `src/palubicki/sim/phyllotaxy.py`
- Modify: `tests/sim/test_phyllotaxy.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/sim/test_phyllotaxy.py`:

```python
from palubicki.sim.phyllotaxy import reserve_bud_directions


def test_reserve_directions_count():
    cfg = PhyllotaxyConfig(mode="alternate", branch_angle_deg=45.0, dormant_reserve_count=3)
    dirs = reserve_bud_directions(
        np.array([0.0, 1.0, 0.0]), cfg,
        node_index=0, seed=0, count=3,
    )
    assert dirs.shape == (3, 3)
    for d in dirs:
        assert abs(np.linalg.norm(d) - 1.0) < 1e-7


def test_reserve_directions_count_zero_returns_empty():
    cfg = PhyllotaxyConfig(mode="alternate", branch_angle_deg=45.0)
    dirs = reserve_bud_directions(
        np.array([0.0, 1.0, 0.0]), cfg,
        node_index=0, seed=0, count=0,
    )
    assert dirs.shape == (0, 3)


def test_reserve_directions_opposite_to_laterals():
    """Reserves point to the opposite azimuth half-plane from laterals."""
    cfg = PhyllotaxyConfig(
        mode="alternate", branch_angle_deg=45.0, divergence_angle_deg=0.0,
        dormant_reserve_count=1,
    )
    growth = np.array([0.0, 1.0, 0.0])
    lateral = lateral_bud_directions(growth, cfg, node_index=0, seed=0)[0]
    reserve = reserve_bud_directions(growth, cfg, node_index=0, seed=0, count=1)[0]
    # Project onto plane perpendicular to growth.
    lat_perp = lateral - np.dot(lateral, growth) * growth
    res_perp = reserve - np.dot(reserve, growth) * growth
    lat_perp = lat_perp / np.linalg.norm(lat_perp)
    res_perp = res_perp / np.linalg.norm(res_perp)
    # Approximately opposite azimuth (cos ≈ -1, jitter aside).
    assert float(np.dot(lat_perp, res_perp)) < -0.9


def test_reserve_branch_angle_tighter_than_laterals():
    """Reserves emerge at a tighter angle (closer to growth axis)."""
    cfg = PhyllotaxyConfig(
        mode="alternate", branch_angle_deg=60.0,
        dormant_reserve_count=1,
    )
    growth = np.array([0.0, 1.0, 0.0])
    lateral = lateral_bud_directions(growth, cfg, node_index=0, seed=0)[0]
    reserve = reserve_bud_directions(growth, cfg, node_index=0, seed=0, count=1)[0]
    # Tighter = larger dot product with growth direction.
    assert float(np.dot(reserve, growth)) > float(np.dot(lateral, growth))


def test_reserve_directions_deterministic():
    cfg = PhyllotaxyConfig(
        mode="alternate", branch_angle_deg=45.0,
        divergence_jitter_deg=5.0, branch_angle_jitter_deg=5.0,
        dormant_reserve_count=2,
    )
    d_a = reserve_bud_directions(np.array([0, 1, 0]), cfg, node_index=7, seed=42, count=2)
    d_b = reserve_bud_directions(np.array([0, 1, 0]), cfg, node_index=7, seed=42, count=2)
    np.testing.assert_array_equal(d_a, d_b)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/pytest tests/sim/test_phyllotaxy.py -k "reserve" -v
```

Expected: ALL FAIL — `reserve_bud_directions` does not exist.

- [ ] **Step 3: Implement `reserve_bud_directions`**

In `src/palubicki/sim/phyllotaxy.py`, add a separate RNG salt and the function. After the existing `_PHYLLO_SALT` line, add:

```python
# Distinct salt so reserve jitter does not collide with lateral jitter for the
# same (seed, node_index).
_RESERVE_SALT = int.from_bytes(b"rsrv", "big")
```

At the end of the file, append:

```python
def reserve_bud_directions(
    growth_direction: np.ndarray,
    cfg: PhyllotaxyConfig,
    node_index: int,
    *,
    seed: int,
    count: int,
) -> np.ndarray:
    """Return (count, 3) unit vectors for RESERVE bud directions at this node.

    Reserves are placed on the AZIMUTH HALF-PLANE OPPOSITE to the laterals
    (base_azimuth + pi) and at a TIGHTER branch angle (half the lateral
    branch_angle, capped at 30°) so the activated bud emerges in a direction
    complementary to the lost lateral subtree. Jitter is half of lateral jitter.

    If ``count == 0`` returns a (0, 3) empty array.
    """
    if count <= 0:
        return np.empty((0, 3), dtype=np.float64)
    g = np.asarray(growth_direction, dtype=np.float64)
    g = g / np.linalg.norm(g)
    right, up = _frame_perpendicular_to(g)

    base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index + math.pi
    branch_angle = min(math.radians(30.0), math.radians(cfg.branch_angle_deg) * 0.5)

    div_jitter = cfg.divergence_jitter_deg * 0.5
    ang_jitter = cfg.branch_angle_jitter_deg * 0.5
    if div_jitter > 0 or ang_jitter > 0:
        ss = np.random.SeedSequence([seed, _RESERVE_SALT, node_index])
        rng = np.random.default_rng(ss.generate_state(1)[0])
        if div_jitter > 0:
            base_azimuth += math.radians(rng.normal(0.0, div_jitter))
        if ang_jitter > 0:
            branch_angle += math.radians(rng.normal(0.0, ang_jitter))
            branch_angle = max(0.0, min(math.pi / 2, branch_angle))

    cos_b = math.cos(branch_angle)
    sin_b = math.sin(branch_angle)

    out = np.empty((count, 3), dtype=np.float64)
    for i in range(count):
        az = base_azimuth + 2.0 * math.pi * i / count
        radial = math.cos(az) * right + math.sin(az) * up
        out[i] = cos_b * g + sin_b * radial
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/pytest tests/sim/test_phyllotaxy.py -v
```

Expected: ALL PASS (including pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/phyllotaxy.py tests/sim/test_phyllotaxy.py
git commit -m "feat(phyllotaxy): add reserve_bud_directions for RESERVE buds"
```

---

## Task 10: Emit RESERVE buds at node creation in the simulator

**Files:**
- Modify: `src/palubicki/sim/simulator.py` (after the laterals block ~line 240)
- Test: `tests/sim/test_simulator.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_simulator.py`:

```python
def test_simulator_emits_dormant_reserves_when_configured(tmp_path):
    """When phyllotaxy.dormant_reserve_count > 0, every new node carries
    that many RESERVE buds in node.dormant_reserve_buds."""
    from palubicki.config import (
        Config, EnvelopeConfig, GeomConfig, LightConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate
    from palubicki.sim.tree import BudState

    cfg = Config(
        envelope=EnvelopeConfig(shape="half_ellipsoid", rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_iterations=8),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(mode="alternate", dormant_reserve_count=2),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        light=LightConfig(),
        output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)

    # Walk all nodes, count reserves.
    seen_nodes = 0
    total_reserves = 0
    stack = [tree.root]
    while stack:
        n = stack.pop()
        seen_nodes += 1
        for r in n.dormant_reserve_buds:
            assert r.state is BudState.RESERVE
        # Root has no parent emission, so it should have 0 reserves; others should have 2.
        if n is not tree.root:
            assert len(n.dormant_reserve_buds) == 2, (
                f"expected 2 reserves on emitted node, got {len(n.dormant_reserve_buds)}"
            )
        total_reserves += len(n.dormant_reserve_buds)
        for iod in n.children_internodes:
            stack.append(iod.child_node)

    assert seen_nodes > 1
    assert total_reserves > 0


def test_simulator_no_reserves_when_count_zero(tmp_path):
    from palubicki.config import (
        Config, EnvelopeConfig, GeomConfig, LightConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    cfg = Config(
        envelope=EnvelopeConfig(shape="half_ellipsoid", rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_iterations=5),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(mode="alternate", dormant_reserve_count=0),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        light=LightConfig(),
        output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)
    stack = [tree.root]
    while stack:
        n = stack.pop()
        assert n.dormant_reserve_buds == []
        for iod in n.children_internodes:
            stack.append(iod.child_node)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/pytest tests/sim/test_simulator.py::test_simulator_emits_dormant_reserves_when_configured tests/sim/test_simulator.py::test_simulator_no_reserves_when_count_zero -v
```

Expected: `test_simulator_emits_dormant_reserves_when_configured` FAILS (count==0 always), the other PASSES already.

- [ ] **Step 3: Add the import and emission block in `simulator.py`**

In `src/palubicki/sim/simulator.py`, add the import alongside the existing phyllotaxy import:

```python
from palubicki.sim.phyllotaxy import lateral_bud_directions, reserve_bud_directions
```

Locate the lateral-emission block in the substep loop. It currently looks like (around line 229-241):

```python
                lateral_dirs = lateral_bud_directions(
                    d, cfg.phyllotaxy,
                    node_index=state.node_index,
                    seed=cfg.seed,
                )
                state.node_index += 1
                for ld in lateral_dirs:
                    lat = Bud(
                        position=new_pos.copy(), direction=ld,
                        axis_order=cur.axis_order + 1, parent_node=new_node,
                    )
                    new_node.lateral_buds.append(lat)

                new_active.extend(new_node.lateral_buds)
```

Replace it with (note `state.node_index` is captured BEFORE the increment to feed both helpers with the same index):

```python
                node_idx = state.node_index
                lateral_dirs = lateral_bud_directions(
                    d, cfg.phyllotaxy,
                    node_index=node_idx,
                    seed=cfg.seed,
                )
                state.node_index += 1
                for ld in lateral_dirs:
                    lat = Bud(
                        position=new_pos.copy(), direction=ld,
                        axis_order=cur.axis_order + 1, parent_node=new_node,
                    )
                    new_node.lateral_buds.append(lat)

                # Phase 2B: emit RESERVE buds (not added to active_buds).
                if cfg.phyllotaxy.dormant_reserve_count > 0:
                    reserve_dirs = reserve_bud_directions(
                        d, cfg.phyllotaxy,
                        node_index=node_idx,
                        seed=cfg.seed,
                        count=cfg.phyllotaxy.dormant_reserve_count,
                    )
                    for rd in reserve_dirs:
                        res = Bud(
                            position=new_pos.copy(), direction=rd,
                            axis_order=cur.axis_order + 1, parent_node=new_node,
                            state=BudState.RESERVE,
                        )
                        new_node.dormant_reserve_buds.append(res)

                new_active.extend(new_node.lateral_buds)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/pytest tests/sim/test_simulator.py::test_simulator_emits_dormant_reserves_when_configured tests/sim/test_simulator.py::test_simulator_no_reserves_when_count_zero -v
```

Expected: BOTH PASS.

- [ ] **Step 5: Sanity-run the full sim suite (no goldens yet)**

```bash
.venv/bin/pytest tests/sim/ -q
```

Expected: green. Existing sim tests use `dormant_reserve_count=0` by default → no behavior change.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/simulator.py tests/sim/test_simulator.py
git commit -m "feat(sim): emit RESERVE buds at each new node when configured"
```

---

## Task 11: Hook `kill_shaded_buds` into the simulator iteration

**Files:**
- Modify: `src/palubicki/sim/simulator.py` (after perceive_light, before per-tree loop)
- Test: `tests/sim/test_simulator.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_simulator.py`:

```python
def test_simulator_kills_shaded_buds_when_enabled(tmp_path):
    """With shade_mortality enabled and light enabled, a bud forced under
    threshold for N consecutive steps must end up DEAD."""
    from palubicki.config import (
        Config, EnvelopeConfig, GeomConfig, LightConfig, PhyllotaxyConfig,
        ShadeMortalityConfig, SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate
    from palubicki.sim.tree import BudState

    cfg = Config(
        envelope=EnvelopeConfig(shape="half_ellipsoid", rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(
            max_iterations=15,
            shade_mortality=ShadeMortalityConfig(
                enabled=True, light_threshold=0.99, n_consecutive_steps=2,
            ),
        ),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(mode="alternate"),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        light=LightConfig(enabled=True, k_absorption=2.0),
        output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)
    # With threshold near 1.0 and high absorption, most buds end up shaded → dead.
    dead = 0
    alive = 0
    stack = [tree.root]
    while stack:
        n = stack.pop()
        for b in ([n.terminal_bud] if n.terminal_bud else []) + n.lateral_buds:
            if b.state is BudState.DEAD:
                dead += 1
            elif b.state is BudState.ACTIVE:
                alive += 1
        for iod in n.children_internodes:
            stack.append(iod.child_node)
    assert dead > 0, "expected shade mortality to kill at least one bud"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/pytest tests/sim/test_simulator.py::test_simulator_kills_shaded_buds_when_enabled -v
```

Expected: FAIL — `dead == 0` because the hook is not wired yet.

- [ ] **Step 3: Wire `kill_shaded_buds` into `_iteration_step`**

In `src/palubicki/sim/simulator.py`, add the import alongside other sim imports:

```python
from palubicki.sim.shade_mortality import kill_shaded_buds
```

Locate the block right after `light_info = perceive_light(...)` and the `else: light_info = None` block (around line 99-100). Insert the shade-mortality pass BEFORE the call to `perceive(...)`:

```python
    # Phase 2B: shade-induced bud mortality runs AFTER perceive_light populates
    # light_factor and BEFORE marker perception / allocation so that dead buds
    # do not consume markers or appear in the substep loop.
    if light_info is not None and cfg.sim.shade_mortality.enabled:
        kill_shaded_buds(
            union_buds, light_info.light_factor, cfg.sim.shade_mortality
        )
        for tree in forest.trees:
            tree.active_buds = [
                b for b in tree.active_buds if b.state is not BudState.DEAD
            ]
        union_buds = all_active_buds(forest)
```

The resulting order inside `_iteration_step` is: light_grid rebuild → perceive_light → **kill_shaded_buds (NEW)** → perceive (markers) → per-tree allocate + substep loop → marker kill → shed_low_quality.

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/pytest tests/sim/test_simulator.py::test_simulator_kills_shaded_buds_when_enabled -v
```

Expected: PASS.

- [ ] **Step 5: Run full sim suite**

```bash
.venv/bin/pytest tests/sim/ -q
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/simulator.py tests/sim/test_simulator.py
git commit -m "feat(sim): apply shade mortality between light perception and allocation"
```

---

## Task 12: Hook `activate_reserves_on_shed` into shedding

**Files:**
- Modify: `src/palubicki/sim/shedding.py` (extend `_walk_and_shed` to call reiteration)
- Modify: `tests/sim/test_shedding.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_shedding.py`:

```python
def test_shed_activates_reserves_when_branch_shed():
    """When an internode is shed, one RESERVE bud on its parent node should
    be activated and appear in tree.active_buds."""
    from palubicki.sim.tree import BudState

    root = Node(position=np.zeros(3))
    # Attach two children: one healthy, one starved.
    for i, q in enumerate([5, 0]):
        child = Node(position=np.array([float(i), 1.0, 0.0]))
        iod = Internode(parent_node=root, child_node=child, length=1.0,
                        is_main_axis=(i == 0), window=3)
        root.children_internodes.append(iod)
        child.parent_internode = iod
        bud = Bud(position=child.position, direction=np.array([0, 1, 0]),
                  axis_order=0, parent_node=child)
        child.terminal_bud = bud
    # Add 2 RESERVE buds on the root so reiteration has something to draw on.
    reserves = []
    for _ in range(2):
        rb = Bud(position=np.zeros(3), direction=np.array([1.0, 0.0, 0.0]),
                 axis_order=1, parent_node=root, state=BudState.ACTIVE)
        # Manually set RESERVE state (the helper for sim emission isn't used here).
        rb.state = BudState.RESERVE
        root.dormant_reserve_buds.append(rb)
        reserves.append(rb)

    buds = [root.children_internodes[i].child_node.terminal_bud for i in range(2)]
    tree = Tree(root=root, active_buds=list(buds),
                all_internodes=[c.parent_internode for c in
                                [root.children_internodes[0].child_node,
                                 root.children_internodes[1].child_node]])
    quality = {buds[0]: 5, buds[1]: 0}
    for _ in range(5):
        record_qualities(tree, quality=quality)

    cfg = SheddingConfig(quality_threshold=0.5, window=3, enabled=True, reactivation_count=1)
    shed_low_quality(tree, cfg=cfg)

    # The starved child was shed; one reserve became ACTIVE and joined active_buds.
    assert len(root.dormant_reserve_buds) == 1
    activated = [b for b in root.lateral_buds if b.state is BudState.ACTIVE]
    assert len(activated) == 1
    assert activated[0] in tree.active_buds


def test_shed_reactivation_count_zero_no_activation():
    from palubicki.sim.tree import BudState

    root = Node(position=np.zeros(3))
    child = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=root, child_node=child, length=1.0,
                    is_main_axis=True, window=3)
    root.children_internodes.append(iod)
    child.parent_internode = iod
    bud = Bud(position=child.position, direction=np.array([0, 1, 0]),
              axis_order=0, parent_node=child)
    child.terminal_bud = bud
    rb = Bud(position=np.zeros(3), direction=np.array([1.0, 0.0, 0.0]),
             axis_order=1, parent_node=root, state=BudState.RESERVE)
    root.dormant_reserve_buds.append(rb)

    tree = Tree(root=root, active_buds=[bud], all_internodes=[iod])
    for _ in range(5):
        record_qualities(tree, quality={bud: 0})

    cfg = SheddingConfig(quality_threshold=0.5, window=3, enabled=True, reactivation_count=0)
    shed_low_quality(tree, cfg=cfg)

    # Reserve untouched.
    assert len(root.dormant_reserve_buds) == 1
    assert rb.state is BudState.RESERVE
    assert rb not in tree.active_buds
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/pytest tests/sim/test_shedding.py::test_shed_activates_reserves_when_branch_shed tests/sim/test_shedding.py::test_shed_reactivation_count_zero_no_activation -v
```

Expected: first FAILS (no activation), second probably PASSES already (no hook exists at all).

- [ ] **Step 3: Wire the hook into shedding**

In `src/palubicki/sim/shedding.py`:

Add the import after the existing imports:

```python
from palubicki.sim.reiteration import activate_reserves_on_shed
```

Modify `shed_low_quality` to thread the `Tree` through to the walker so activated buds can be appended. Replace the body of `shed_low_quality` with:

```python
def shed_low_quality(tree: Tree, *, cfg: SheddingConfig) -> None:
    if not cfg.enabled:
        return
    dead_bud_ids: set[int] = set()
    dead_iod_ids: set[int] = set()
    activated_buds: list[Bud] = []
    _walk_and_shed(tree.root, cfg, dead_bud_ids, dead_iod_ids, activated_buds)
    if dead_bud_ids:
        tree.active_buds = [b for b in tree.active_buds if id(b) not in dead_bud_ids]
    if dead_iod_ids:
        tree.all_internodes = [i for i in tree.all_internodes if id(i) not in dead_iod_ids]
    if activated_buds:
        tree.active_buds.extend(activated_buds)
```

Replace `_walk_and_shed` with the version that calls `activate_reserves_on_shed` on each shed:

```python
def _walk_and_shed(
    root: Node,
    cfg: SheddingConfig,
    dead_bud_ids: set[int],
    dead_iod_ids: set[int],
    activated_buds: list[Bud],
) -> None:
    """Iterative pre-order walk: shed low-quality subtrees, activate reserves."""
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        for iod in list(node.children_internodes):
            if (
                len(iod.quality_history) >= cfg.window
                and iod.average_quality() < cfg.quality_threshold
            ):
                _kill_subtree(iod.child_node, dead_bud_ids, dead_iod_ids)
                node.children_internodes = [
                    i for i in node.children_internodes if i is not iod
                ]
                dead_iod_ids.add(id(iod))
                # Phase 2B: wake up reserves on the parent of the shed branch.
                activated = activate_reserves_on_shed(
                    node, n_to_activate=cfg.reactivation_count
                )
                activated_buds.extend(activated)
            else:
                stack.append(iod.child_node)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/pytest tests/sim/test_shedding.py -v
```

Expected: ALL PASS (pre-existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/shedding.py tests/sim/test_shedding.py
git commit -m "feat(shedding): activate RESERVE buds on each shed branch"
```

---

## Task 13: Integration test — shade carves the lower canopy

**Files:**
- Create: `tests/integration/test_shade_carves_canopy.py`

- [ ] **Step 1: Write the integration test**

Create `tests/integration/test_shade_carves_canopy.py`:

```python
# tests/integration/test_shade_carves_canopy.py
import pytest

from palubicki.cli import main


pytestmark = pytest.mark.slow


def _count_active_dead_in_lower_half(tree):
    from palubicki.sim.tree import BudState
    ys = []
    stack = [tree.root]
    nodes = []
    while stack:
        n = stack.pop()
        nodes.append(n)
        ys.append(float(n.position[1]))
        for iod in n.children_internodes:
            stack.append(iod.child_node)
    if not ys:
        return 0, 0
    y_min, y_max = min(ys), max(ys)
    y_mid = 0.5 * (y_min + y_max)
    active = dead = 0
    for n in nodes:
        if float(n.position[1]) > y_mid:
            continue
        for b in ([n.terminal_bud] if n.terminal_bud else []) + n.lateral_buds:
            if b.state is BudState.ACTIVE:
                active += 1
            elif b.state is BudState.DEAD:
                dead += 1
    return active, dead


def _simulate_oak_with_shade(tmp_path, *, shade_enabled: bool):
    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate

    cli_overrides = {
        "sim.shade_mortality.enabled": shade_enabled,
        "sim.max_iterations": 25,
        "envelope.marker_count": 3000,
    }
    cfg = load_config(
        yaml_path=None, cli_overrides=cli_overrides,
        output=tmp_path / "oak.glb", species="oak",
    )
    return simulate(cfg)


def test_shade_carves_lower_canopy(tmp_path):
    tree_on = _simulate_oak_with_shade(tmp_path, shade_enabled=True)
    active_on, dead_on = _count_active_dead_in_lower_half(tree_on)
    total_on = active_on + dead_on
    assert total_on > 0, "lower half empty; tree may not have grown"
    ratio_dead_on = dead_on / total_on

    tree_off = _simulate_oak_with_shade(tmp_path, shade_enabled=False)
    active_off, dead_off = _count_active_dead_in_lower_half(tree_off)
    total_off = active_off + dead_off
    assert total_off > 0
    ratio_dead_off = dead_off / total_off

    # Shade mortality must produce STRICTLY MORE dead buds in the shaded half
    # than the marker-starvation-only baseline.
    assert ratio_dead_on > ratio_dead_off, (
        f"shade_on={ratio_dead_on:.2f} not greater than shade_off={ratio_dead_off:.2f}"
    )
```

- [ ] **Step 2: Run the test (it will need the oak preset shade_mortality flag — but loader allows the override even with current YAML)**

```bash
.venv/bin/pytest tests/integration/test_shade_carves_canopy.py -v -m slow
```

Expected: PASS (oak preset already enables light; CLI override toggles shade_mortality).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_shade_carves_canopy.py
git commit -m "test(integration): verify shade mortality carves lower canopy"
```

---

## Task 14: Integration test — reiteration after shed

**Files:**
- Create: `tests/integration/test_reiteration_after_shed.py`

- [ ] **Step 1: Write the integration test**

Create `tests/integration/test_reiteration_after_shed.py`:

```python
# tests/integration/test_reiteration_after_shed.py
from unittest.mock import patch

import pytest

from palubicki.cli import main


pytestmark = pytest.mark.slow


def test_reiteration_produces_activations(tmp_path):
    """With reserves > 0 and reactivation > 0, shed-driven activations occur.
    With reserves == 0, activations must be zero even if many sheds happen."""
    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate
    import palubicki.sim.shedding as shedding_mod

    counter = {"calls": 0, "activations": 0}
    real = shedding_mod.activate_reserves_on_shed

    def spy(parent_node, n_to_activate=1):
        counter["calls"] += 1
        out = real(parent_node, n_to_activate=n_to_activate)
        counter["activations"] += len(out)
        return out

    # Run 1: oak preset (reserves=2, reactivation=1) — expect activations.
    with patch.object(shedding_mod, "activate_reserves_on_shed", side_effect=spy):
        cfg = load_config(
            yaml_path=None,
            cli_overrides={"sim.max_iterations": 25, "envelope.marker_count": 3000},
            output=tmp_path / "oak.glb", species="oak",
        )
        simulate(cfg)
    oak_activations = counter["activations"]

    counter["calls"] = 0
    counter["activations"] = 0

    # Run 2: oak preset but force reserves to 0 — expect zero activations.
    with patch.object(shedding_mod, "activate_reserves_on_shed", side_effect=spy):
        cfg = load_config(
            yaml_path=None,
            cli_overrides={
                "sim.max_iterations": 25,
                "envelope.marker_count": 3000,
                "phyllotaxy.dormant_reserve_count": 0,
            },
            output=tmp_path / "oak0.glb", species="oak",
        )
        simulate(cfg)
    no_reserve_activations = counter["activations"]

    assert oak_activations > 0, "expected oak preset to produce shed-driven activations"
    assert no_reserve_activations == 0, (
        f"expected 0 activations with dormant_reserve_count=0, got {no_reserve_activations}"
    )
```

- [ ] **Step 2: Run the test**

```bash
.venv/bin/pytest tests/integration/test_reiteration_after_shed.py -v -m slow
```

Expected: PASS once oak preset adds `dormant_reserve_count: 2` and `reactivation_count: 1` (next task). For now this test depends on Task 15 — run it after Task 15.

- [ ] **Step 3: Commit (test only, will be exercised after preset update)**

```bash
git add tests/integration/test_reiteration_after_shed.py
git commit -m "test(integration): verify reserve-bud reiteration after shed"
```

---

## Task 15: Update species presets (oak / pine / birch)

**Files:**
- Modify: `src/palubicki/configs/species/oak.yaml`
- Modify: `src/palubicki/configs/species/pine.yaml`
- Modify: `src/palubicki/configs/species/birch.yaml`

These are ADDITIONS, not rewrites. Preserve every existing key in each file.

- [ ] **Step 1: Update `oak.yaml`**

In `src/palubicki/configs/species/oak.yaml`, add a `shade_mortality` block under `sim:` (after `max_iterations`), add `dormant_reserve_count` under the existing `phyllotaxy:` block, and add `reactivation_count` under the existing `shedding:` block.

After edit, the oak file should contain (showing only the touched sections):

```yaml
sim:
  internode_length: 0.18
  internode_length_jitter: 0.12
  lambda_apical: 0.75
  alpha_basipetal: 2.2
  max_iterations: 45
  shade_mortality:
    enabled: true
    light_threshold: 0.20
    n_consecutive_steps: 3
# ... tropism unchanged ...
phyllotaxy:
  mode: alternate
  divergence_angle_deg: 137.5
  divergence_jitter_deg: 6.0
  branch_angle_deg: 60
  branch_angle_jitter_deg: 5.0
  dormant_reserve_count: 2
shedding:
  quality_threshold: 0.15
  reactivation_count: 1
```

- [ ] **Step 2: Update `pine.yaml`**

In `src/palubicki/configs/species/pine.yaml`, add a `shade_mortality` block under `sim:`, set `dormant_reserve_count: 0` under `phyllotaxy:`, and `reactivation_count: 0` under `shedding:`:

```yaml
sim:
  internode_length: 0.18
  internode_length_jitter: 0.08
  lambda_apical: 0.85
  alpha_basipetal: 1.8
  max_iterations: 40
  shade_mortality:
    enabled: true
    light_threshold: 0.12
    n_consecutive_steps: 4
# ... tropism unchanged ...
phyllotaxy:
  mode: whorled
  whorl_count: 5
  divergence_angle_deg: 72
  divergence_jitter_deg: 3.0
  branch_angle_deg: 75
  branch_angle_jitter_deg: 4.0
  dormant_reserve_count: 0
shedding:
  quality_threshold: 0.20
  reactivation_count: 0
```

- [ ] **Step 3: Update `birch.yaml`**

In `src/palubicki/configs/species/birch.yaml`, add the three sections:

```yaml
sim:
  internode_length: 0.18
  internode_length_jitter: 0.15
  lambda_apical: 0.95
  alpha_basipetal: 2.0
  max_iterations: 45
  shade_mortality:
    enabled: true
    light_threshold: 0.20
    n_consecutive_steps: 3
# ... tropism, sag unchanged ...
phyllotaxy:
  mode: alternate
  divergence_angle_deg: 137.5
  divergence_jitter_deg: 5.0
  branch_angle_deg: 45
  branch_angle_jitter_deg: 4.0
  dormant_reserve_count: 1
shedding:
  quality_threshold: 0.02
  reactivation_count: 1
```

- [ ] **Step 4: Verify presets load cleanly**

```bash
.venv/bin/python -c "
from palubicki.config import load_config
from pathlib import Path
for sp in ('oak', 'pine', 'birch'):
    cfg = load_config(yaml_path=None, cli_overrides={}, output=Path('/tmp/x.glb'), species=sp)
    print(sp, 'shade_mortality:', cfg.sim.shade_mortality.enabled, cfg.sim.shade_mortality.light_threshold,
          'reserves:', cfg.phyllotaxy.dormant_reserve_count,
          'reactivation:', cfg.shedding.reactivation_count)
"
```

Expected output:

```
oak shade_mortality: True 0.2 reserves: 2 reactivation: 1
pine shade_mortality: True 0.12 reserves: 0 reactivation: 0
birch shade_mortality: True 0.2 reserves: 1 reactivation: 1
```

- [ ] **Step 5: Run the previously-deferred reiteration integration test**

```bash
.venv/bin/pytest tests/integration/test_reiteration_after_shed.py tests/integration/test_shade_carves_canopy.py -v -m slow
```

Expected: BOTH PASS.

- [ ] **Step 6: Run the unit + integration suite (everything but goldens)**

```bash
.venv/bin/pytest -q --deselect tests/golden
```

Expected: green.

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/configs/species/oak.yaml src/palubicki/configs/species/pine.yaml src/palubicki/configs/species/birch.yaml
git commit -m "feat(presets): wire shade_mortality + reiteration into oak/pine/birch"
```

---

## Task 16: Regenerate goldens

**Files:**
- Modify: `tests/golden/data/species_oak.sha256`
- Modify: `tests/golden/data/species_pine.sha256`
- Modify: `tests/golden/data/species_birch.sha256`
- Modify (possibly): any other `.sha256` files whose configs depend on default sim parameters

- [ ] **Step 1: Run goldens to see which ones drift**

```bash
.venv/bin/pytest tests/golden -v -m slow 2>&1 | tail -30
```

Expected: at least the species goldens FAIL with hash mismatch.

- [ ] **Step 2: Regenerate goldens with the `--update-goldens` flag**

```bash
.venv/bin/pytest tests/golden -m slow --update-goldens 2>&1 | tail -30
```

Expected: previously-failing golden files are rewritten; the run reports skipped tests (per `conftest.py` behavior on first write).

- [ ] **Step 3: Re-run goldens to confirm they now pass**

```bash
.venv/bin/pytest tests/golden -m slow -v 2>&1 | tail -30
```

Expected: all green.

- [ ] **Step 4: Run the full test suite as a final regression**

```bash
.venv/bin/pytest -q
```

Expected: green.

- [ ] **Step 5: Commit**

```bash
git add tests/golden/data/
git commit -m "test(golden): regenerate goldens after Phase 2B bud-lifecycle changes"
```

---

## Task 17: Update README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a Phase 2B section to the README**

In `README.md`, locate the `### V4 — species presets` block (around line 107-122). Immediately after it, insert a new section:

```markdown
### Phase 2B — bud lifecycle (shade mortality + reiteration)

Two new mechanisms make the canopy carve itself realistically and recover from
branch loss:

- **Shade-induced mortality** (`sim.shade_mortality`): a bud whose `light_factor`
  stays below `light_threshold` for `n_consecutive_steps` consecutive iterations
  dies (state → DEAD). This produces a natural live-crown ratio — lower branches
  in deep shade die off instead of dragging quality down. Requires
  `light.enabled: true` (the config raises `ConfigError` otherwise).
- **Reiteration via dormant reserves** (`phyllotaxy.dormant_reserve_count` +
  `shedding.reactivation_count`): every emitted node carries K pre-formed
  RESERVE buds (state `BudState.RESERVE`, invisible to perception and light).
  When the shedding pass removes a child subtree, `reactivation_count` reserves
  on the parent node flip to ACTIVE and join `tree.active_buds`. This is the
  epicormic-shoot / water-sprout mechanism — strong in oak and poplar, absent
  in conifers.

Species defaults:

| Species | shade_mortality.threshold | reserves / node | activations / shed |
|---------|---------------------------|-----------------|--------------------|
| oak     | 0.20                      | 2               | 1                  |
| pine    | 0.12                      | 0               | 0                  |
| birch   | 0.20                      | 1               | 1                  |
```

- [ ] **Step 2: Verify the change reads well**

```bash
.venv/bin/python -c "print(open('README.md').read().count('Phase 2B'))"
```

Expected: at least `1`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): document Phase 2B shade mortality + reiteration"
```

---

## Task 18: Mark suggestions #3 and #8 as addressed in the simulation review

**Files:**
- Modify: `docs/2026-05-27-simulation-review.md`

The review's section "4. Suggestions d'amélioration (priorisées)" lists numbered items. Phase 2B is recorded against items **#3** and **#8** per the spec's mapping. Apply the markers exactly as described below — do not also annotate #5 or other items unless explicitly requested.

- [ ] **Step 1: Read the relevant section to locate items #3 and #8**

```bash
.venv/bin/python -c "
import re
text = open('docs/2026-05-27-simulation-review.md').read()
for m in re.finditer(r'^\d+\.\s\*\*[^\n]+', text, flags=re.M):
    print(m.start(), m.group(0)[:120])
"
```

Use the output to locate the exact line text of items 3 and 8 in section 4.

- [ ] **Step 2: Mark item #3 as addressed**

Locate item 3 in `docs/2026-05-27-simulation-review.md` (it begins with `3. **Angle d'insertion qui s'ouvre avec l'âge/le poids.**`). Prepend `[ADDRESSED — Phase 2B]` to its first line. Use the `Edit` tool with the exact old line to perform the replacement; the new first line should read:

```
3. **[ADDRESSED — Phase 2B] Angle d'insertion qui s'ouvre avec l'âge/le poids.** Au lieu de sag
```

(Same wording, just the marker prepended after the number.)

- [ ] **Step 3: Mark item #8 as addressed**

Locate item 8 (begins with `8. **`alpha_basipetal` qui décroît avec l'âge du tree**`). Prepend `[ADDRESSED — Phase 2B]`:

```
8. **[ADDRESSED — Phase 2B] `alpha_basipetal` qui décroît avec l'âge du tree** (carbon use
```

- [ ] **Step 4: Verify both markers appear**

```bash
.venv/bin/python -c "
text = open('docs/2026-05-27-simulation-review.md').read()
assert text.count('[ADDRESSED — Phase 2B]') == 2, text.count('[ADDRESSED — Phase 2B]')
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add docs/2026-05-27-simulation-review.md
git commit -m "docs(review): mark suggestions #3 and #8 as addressed by Phase 2B"
```

---

## Final verification

- [ ] **Run the whole suite one last time**

```bash
.venv/bin/pytest -q
```

Expected: green, including goldens.

- [ ] **Confirm Phase 2B surface area landed**

```bash
.venv/bin/python -c "
from palubicki.config import ShadeMortalityConfig, PhyllotaxyConfig, SheddingConfig
from palubicki.sim.tree import BudState, Bud, Node
from palubicki.sim.shade_mortality import kill_shaded_buds
from palubicki.sim.reiteration import activate_reserves_on_shed
from palubicki.sim.phyllotaxy import reserve_bud_directions
assert BudState.RESERVE
assert PhyllotaxyConfig().dormant_reserve_count == 0
assert SheddingConfig().reactivation_count == 1
assert ShadeMortalityConfig().n_consecutive_steps == 3
print('Phase 2B surface area present')
"
```

Expected: `Phase 2B surface area present`.

Phase 2B is now complete: shade-mortality and reiteration are wired end-to-end through configs, sim modules, simulator hooks, presets, goldens, README, and review doc.
