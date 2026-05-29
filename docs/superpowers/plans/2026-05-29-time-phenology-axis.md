# Time / Phenology Axis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the simulator's bare iteration counter with a real fractional-year clock, so growth happens in calendar time and a per-species annual growth window can gate it.

**Architecture:** A new `Clock` (years, `dt` per iteration) is threaded through the forest loop. `Internode.birth_iteration` becomes `birth_time` (years); elongation reads time deltas instead of iteration deltas. `sim.max_iterations` is replaced by `max_simulation_years` + `dt_years` (iteration count derived). A growth-window gate skips emission outside `annual_growth_period`. RNG-salt/`node_index`/logging keep integer iteration indices — only *time* values switch to floats.

**Tech Stack:** Python 3, dataclasses, numpy, pytest. Run everything with the project venv: prefix commands with `.venv/bin/`.

**Invariance contract:** At `dt_years=1.0` with the default window `(0.0, 1.0)`, `birth_time == old birth_iteration`, `tau_years == tau_iterations`, and every iteration grows → trees are bit-identical. The two goldens run with elongation off, so they must not change. Verify in Task 12.

---

## File Structure

- **Create** `src/palubicki/sim/clock.py` — the `Clock` dataclass.
- **Create** `tests/sim/test_clock.py` — unit tests for `Clock`.
- **Create** `tests/integration/test_phenology.py` — acceptance test for the growth window.
- **Modify** `src/palubicki/config.py` — `SimConfig` fields + `num_iterations` property + validation; `ElongationConfig.tau_years`.
- **Modify** `src/palubicki/sim/tree.py` — `Internode.birth_time`; remove `Bud.age`.
- **Modify** `src/palubicki/sim/reiteration.py` — drop `bud.age = 0`.
- **Modify** `src/palubicki/sim/elongation.py` — time-based signatures.
- **Modify** `src/palubicki/sim/simulator.py` — `Clock` integration, growth-window gate, threading `t`.
- **Modify** `src/palubicki/cli.py` — `--years` / `--dt-years` flags, `asset_meta`.
- **Modify** `src/palubicki/configs/species/{oak,birch,maple,pine,fir}.yaml` — key renames.
- **Modify** ~30 test files — mechanical kwarg/assertion renames (Task 10).
- **Modify** `README.md` — time-model paragraph.

---

## Task 1: `Clock` module

**Files:**
- Create: `src/palubicki/sim/clock.py`
- Test: `tests/sim/test_clock.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/sim/test_clock.py
import pytest

from palubicki.sim.clock import Clock


def test_tick_advances_by_dt():
    c = Clock(dt=0.25)
    assert c.t == 0.0
    c.tick()
    assert c.t == pytest.approx(0.25)


def test_year_and_fraction():
    c = Clock(dt=0.25, t=2.5)
    assert c.year() == 2
    assert c.year_fraction() == pytest.approx(0.5)


def test_in_window_inclusive_low_exclusive_high():
    c = Clock(dt=0.25, t=0.0)      # fraction 0.0
    assert c.in_window(0.0, 0.5) is True
    c.t = 0.5                       # fraction 0.5
    assert c.in_window(0.0, 0.5) is False   # high is exclusive
    c.t = 0.75
    assert c.in_window(0.0, 0.5) is False
    c.t = 1.0                       # fraction 0.0 again
    assert c.in_window(0.0, 0.5) is True


def test_full_year_window_always_true():
    for t in (0.0, 1.0, 5.0, 12.0):
        assert Clock(dt=1.0, t=t).in_window(0.0, 1.0) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/sim/test_clock.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'palubicki.sim.clock'`.

- [ ] **Step 3: Write the module**

```python
# src/palubicki/sim/clock.py
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Clock:
    """Fractional-year simulation clock.

    ``t`` is the current simulation time in years; ``dt`` is the time advance
    per simulation iteration. ``year_fraction`` in [0, 1) is the phenology
    coordinate used to gate seasonal growth.
    """
    dt: float
    t: float = 0.0

    def tick(self) -> None:
        self.t += self.dt

    def year(self) -> int:
        return math.floor(self.t)

    def year_fraction(self) -> float:
        return self.t - math.floor(self.t)

    def in_window(self, lo: float, hi: float) -> bool:
        f = self.year_fraction()
        return lo <= f < hi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/sim/test_clock.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/clock.py tests/sim/test_clock.py
git commit -m "feat(sim): add fractional-year Clock (#10)"
```

---

## Task 2: `SimConfig` time fields + `num_iterations` + validation

**Files:**
- Modify: `src/palubicki/config.py` (SimConfig at line 38-70; validation at line 423-424; YAML tuple-coercion near line 596)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
def test_sim_config_time_defaults():
    from palubicki.config import SimConfig
    s = SimConfig()
    assert s.dt_years == 1.0
    assert s.max_simulation_years == 30.0
    assert s.annual_growth_period == (0.0, 1.0)
    assert s.num_iterations == 30


def test_num_iterations_quarterly():
    from palubicki.config import SimConfig
    s = SimConfig(dt_years=0.25, max_simulation_years=10.0)
    assert s.num_iterations == 40


def test_dt_years_must_be_positive(tmp_path):
    from palubicki.config import ConfigError, load_config
    p = tmp_path / "bad.yaml"
    p.write_text("sim:\n  dt_years: 0.0\n")
    with pytest.raises(ConfigError, match="dt_years"):
        load_config(yaml_path=p, cli_overrides={}, output=tmp_path / "o.glb")


def test_annual_growth_period_must_be_ordered(tmp_path):
    from palubicki.config import ConfigError, load_config
    p = tmp_path / "bad.yaml"
    p.write_text("sim:\n  annual_growth_period: [0.6, 0.3]\n")
    with pytest.raises(ConfigError, match="annual_growth_period"):
        load_config(yaml_path=p, cli_overrides={}, output=tmp_path / "o.glb")


def test_annual_growth_period_parsed_from_yaml(tmp_path):
    from palubicki.config import load_config
    p = tmp_path / "ok.yaml"
    p.write_text("sim:\n  annual_growth_period: [0.25, 0.55]\n")
    cfg = load_config(yaml_path=p, cli_overrides={}, output=tmp_path / "o.glb")
    assert cfg.sim.annual_growth_period == (0.25, 0.55)
```

Also update the existing default assertion at line 36:
```python
    assert cfg.sim.max_simulation_years == 30.0   # was: cfg.sim.max_iterations == 30
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_config.py -k "time_defaults or num_iterations or dt_years or annual_growth" -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword 'dt_years'` / `AttributeError`.

- [ ] **Step 3: Edit `SimConfig`**

In `src/palubicki/config.py`, replace the `max_iterations` field (line 46):
```python
    max_iterations: int = field(default=30, metadata={"ui": {"min": 1, "max": 80, "step": 1}})
```
with:
```python
    dt_years: float = field(default=1.0, metadata={"ui": {"min": 0.1, "max": 2.0, "step": 0.05}})
    max_simulation_years: float = field(
        default=30.0, metadata={"ui": {"min": 1.0, "max": 80.0, "step": 1.0}}
    )
    # Fraction of the year [lo, hi) during which growth (new internodes) is
    # active. Default spans the whole year => no seasonal gating. Only bites
    # when dt_years < 1.0 (sub-annual steps).
    annual_growth_period: tuple[float, float] = (0.0, 1.0)
```

Add a property to `SimConfig` (after the fields, before the end of the class — methods are fine on a frozen dataclass):
```python
    @property
    def num_iterations(self) -> int:
        """Iteration budget derived from the time budget."""
        return round(self.max_simulation_years / self.dt_years)
```

- [ ] **Step 4: Edit validation**

In `Config.__post_init__`, replace the `max_iterations` check (lines 423-424):
```python
        if s.max_iterations < 0:
            raise ConfigError(f"sim.max_iterations must be >= 0, got {s.max_iterations}")
```
with:
```python
        if s.dt_years <= 0:
            raise ConfigError(f"sim.dt_years must be > 0, got {s.dt_years}")
        if s.max_simulation_years < 0:
            raise ConfigError(
                f"sim.max_simulation_years must be >= 0, got {s.max_simulation_years}"
            )
        lo, hi = s.annual_growth_period
        if not (0.0 <= lo < hi <= 1.0):
            raise ConfigError(
                f"sim.annual_growth_period must satisfy 0.0 <= lo < hi <= 1.0, "
                f"got {s.annual_growth_period}"
            )
```

- [ ] **Step 5: Edit YAML tuple-coercion**

In `load_config`, find the `sim` section handling (the block around line 603-624 that coerces `sympodial`, `shade_mortality`, etc.). Add, alongside those, a coercion so YAML lists become a tuple:
```python
        if name == "sim" and "annual_growth_period" in sec_data:
            v = sec_data["annual_growth_period"]
            if not isinstance(v, (list, tuple)) or len(v) != 2:
                raise ConfigError(
                    f"sim.annual_growth_period must be a 2-element list, got {v!r}"
                )
            sec_data = {**sec_data, "annual_growth_period": tuple(float(x) for x in v)}
```

- [ ] **Step 6: Run to verify pass**

Run: `.venv/bin/pytest tests/test_config.py -k "time_defaults or num_iterations or dt_years or annual_growth or with_defaults" -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "feat(config): replace max_iterations with dt_years + max_simulation_years (#10)"
```

---

## Task 3: `ElongationConfig.tau_iterations` → `tau_years`

**Files:**
- Modify: `src/palubicki/config.py` (ElongationConfig line 203-205; validation line 403-404)
- Test: `tests/test_config.py`

- [ ] **Step 1: Update the failing tests**

In `tests/test_config.py`, change line 491:
```python
    assert cfg.tau_years == 3.0           # was: cfg.tau_iterations == 3.0
```
and the validation test (lines 504-509):
```python
def test_elongation_validation_tau_must_be_positive(tmp_path):
    from palubicki.config import ConfigError, load_config
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text("sim:\n  elongation:\n    enabled: true\n    tau_years: 0.0\n")
    with pytest.raises(ConfigError, match="tau_years"):
        load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_config.py -k "elongation" -v`
Expected: FAIL — `AttributeError: 'ElongationConfig' object has no attribute 'tau_years'`.

- [ ] **Step 3: Edit `ElongationConfig`**

In `src/palubicki/config.py`, rename the field (line 203-205):
```python
    tau_years: float = field(
        default=3.0, metadata={"ui": {"min": 0.5, "max": 10.0, "step": 0.1}}
    )
```
Update the class docstring (lines 199-200) to say "centered at `tau_years` years after birth". Update validation (lines 403-404):
```python
        if e.tau_years <= 0:
            raise ConfigError(f"sim.elongation.tau_years must be > 0, got {e.tau_years}")
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_config.py -k "elongation" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "refactor(config): rename tau_iterations to tau_years (#10)"
```

---

## Task 4: `Internode.birth_time`; remove `Bud.age`

**Files:**
- Modify: `src/palubicki/sim/tree.py` (Bud.age line 23; Internode.birth_iteration line 53)
- Modify: `src/palubicki/sim/reiteration.py` (line 32 + docstring line 15)
- Test: `tests/sim/test_tree.py`, `tests/sim/test_reiteration.py`

- [ ] **Step 1: Update the failing tests**

In `tests/sim/test_tree.py`, rewrite the two tests (lines 86-101):
```python
def test_internode_has_birth_time_and_length_target_defaults():
    a = Node(position=np.zeros(3))
    b = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=a, child_node=b, length=1.0, is_main_axis=True)
    assert iod.birth_time == 0.0
    assert iod.length_target == 0.0


def test_internode_accepts_birth_time_and_length_target_kwargs():
    a = Node(position=np.zeros(3))
    b = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(
        parent_node=a, child_node=b, length=0.0, is_main_axis=True,
        birth_time=7.0, length_target=0.42,
    )
    assert iod.birth_time == 7.0
    assert iod.length_target == 0.42
```

In `tests/sim/test_reiteration.py`, delete the `b.age = 12` line (line 19) and the `assert b.age == 0` line (line 54).

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/sim/test_tree.py -k birth -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword 'birth_time'`.

- [ ] **Step 3: Edit `tree.py`**

Remove `Bud.age` — delete line 23 (`    age: int = 0`).
Rename the `Internode` field (line 53):
```python
    birth_time: float = 0.0
```

- [ ] **Step 4: Edit `reiteration.py`**

Delete line 32 (`        bud.age = 0`). In the docstring (line 15), change
`(low_quality_steps, low_light_steps, age) reset to 0` →
`(low_quality_steps, low_light_steps) reset to 0`.

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/pytest tests/sim/test_tree.py tests/sim/test_reiteration.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/tree.py src/palubicki/sim/reiteration.py tests/sim/test_tree.py tests/sim/test_reiteration.py
git commit -m "refactor(sim): Internode.birth_time replaces birth_iteration; drop Bud.age (#10)"
```

---

## Task 5: Elongation — time-based signatures

**Files:**
- Modify: `src/palubicki/sim/elongation.py`
- Test: `tests/sim/test_elongation.py`

- [ ] **Step 1: Update the failing tests**

In `tests/sim/test_elongation.py`, apply these renames to call sites:
- `birth_iteration=` → `birth_time=` (values stay; pass as floats, e.g. `birth_time=20.0`)
- `max_iterations=` → `total_years=` (e.g. `total_years=40.0`)
- `current_iteration=` → `current_time=` (e.g. `current_time=3.0`)
- `tau_iterations=` → `tau_years=`
- Rename the test `test_compute_target_max_iterations_zero_returns_base` →
  `test_compute_target_total_years_zero_returns_base` and inside it pass
  `total_years=0.0`.

The helper that builds internodes (around line 67) uses `birth_iteration=birth` — change to `birth_time=float(birth)`.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/sim/test_elongation.py -v`
Expected: FAIL — `TypeError: compute_target_with_age() got an unexpected keyword 'birth_time'`.

- [ ] **Step 3: Edit `elongation.py`**

Rewrite `compute_target_with_age` (lines 21-40):
```python
def compute_target_with_age(
    base_length: float,
    birth_time: float,
    total_years: float,
    cfg: ElongationConfig,
) -> float:
    """target_length = base_length × age_factor(birth_time / total_years)."""
    if not cfg.enabled or total_years <= 0:
        return base_length
    decay = cfg.age_factor_decay
    if decay <= 0:
        return base_length
    t_norm = min(1.0, birth_time / total_years)
    base = math.exp(-decay * t_norm)
    base_at_one = math.exp(-decay)
    factor = (
        cfg.age_factor_min
        + (1.0 - cfg.age_factor_min) * (base - base_at_one) / (1.0 - base_at_one)
    )
    return base_length * factor
```

Rewrite `update_lengths` (lines 43-61):
```python
def update_lengths(tree: Tree, current_time: float, cfg: ElongationConfig) -> None:
    """Recompute Internode.length in-place via sigmoid ramp.

    length(t) = length_target * sigmoid((elapsed - tau) / (tau/2))
    where elapsed = max(0.0, current_time - birth_time) and tau = tau_years.

    No-op if cfg.enabled is False or cfg.tau_years <= 0.
    """
    if not cfg.enabled:
        return
    tau = cfg.tau_years
    if tau <= 0:
        return
    half_tau = tau / 2.0
    for iod in tree.all_internodes:
        elapsed = max(0.0, current_time - iod.birth_time)
        x = (elapsed - tau) / half_tau
        sigma = 1.0 / (1.0 + math.exp(-x))
        iod.length = iod.length_target * sigma
```

Update the module docstring references to `birth_iteration` → `birth_time` and `tau_iterations` → `tau_years`.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/sim/test_elongation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/elongation.py tests/sim/test_elongation.py
git commit -m "refactor(sim): elongation uses time deltas (birth_time/tau_years) (#10)"
```

---

## Task 6: Simulator — Clock integration + growth-window gate

**Files:**
- Modify: `src/palubicki/sim/simulator.py`
- Test: `tests/sim/test_simulator.py` (rename sites only — behavior covered by Task 9 & 11)

This task wires the clock. Several existing tests reference `max_iterations` / `birth_iteration` here; do the mechanical renames in this file's test alongside.

- [ ] **Step 1: Edit `simulate_forest` (lines 55-84)**

Add the import at the top of `simulator.py` (with the other `palubicki.sim` imports):
```python
from palubicki.sim.clock import Clock
```

Replace the loop (lines 59-71):
```python
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
```
with:
```python
    no_new_streak = 0
    t0 = time.time()
    state = _SimState()
    clock = Clock(dt=cfg.sim.dt_years)
    for iteration in range(cfg.sim.num_iterations):
        clock.t = iteration * cfg.sim.dt_years
        if not any(t.active_buds for t in forest.trees):
            break
        if not clock.in_window(*cfg.sim.annual_growth_period):
            # Dormant season: age existing structure, emit nothing. Does NOT
            # count toward the no-growth early-stop (that is for saturation).
            _apply_temporal_dynamics(forest, cfg, clock.t)
            continue
        nodes_created = _iteration_step(forest, cfg, iteration, clock.t, state, t0)
        if nodes_created == 0:
            no_new_streak += 1
        else:
            no_new_streak = 0
        if no_new_streak >= 2:
            break
```

- [ ] **Step 2: Thread `t` through `_iteration_step` (line 163)**

Change the signature:
```python
def _iteration_step(forest: Forest, cfg: Config, iteration: int, t: float, state: _SimState, t0: float) -> int:
```
Update the `_grow_tree` call inside it (line 185-187) to pass `t`:
```python
        created, positions = _grow_tree(
            tree, forest, cfg, iteration, t, state, res, light_info, quality
        )
```
Update the `_apply_temporal_dynamics` call (line 197):
```python
    _apply_temporal_dynamics(forest, cfg, t)
```
Update the log line (lines 199-205): change `cfg.sim.max_iterations` → `cfg.sim.num_iterations` and append the year, e.g.:
```python
    logger.info(
        "[%.1fs] sim/iter %d/%d  year=%.2f  trees=%d  nodes_created=%d",
        time.time() - t0,
        iteration + 1, cfg.sim.num_iterations, t,
        len(forest.trees),
        nodes_created_this_step,
    )
```

- [ ] **Step 3: Thread `t` through `_grow_tree` and `_emit_node`**

`_grow_tree` signature (line 209-212):
```python
def _grow_tree(
    tree: Tree, forest: Forest, cfg: Config, iteration: int, t: float, state: _SimState,
    res, light_info, quality: dict,
) -> tuple[int, list[np.ndarray]]:
```
Inside `_grow_tree`, the calls to `_internode_target` (line 288) and `_emit_node` (lines 306-308) must pass `t`:
```python
            target = _internode_target(cur, cfg, iteration, t, state)
```
```python
            new_node, terminal = _emit_node(
                cur, d, new_pos, target, is_main, light_info, tree, cfg, iteration, t, state
            )
```

`_internode_target` (lines 333-352) — keep `iteration` for the RNG salt, add `t`, and feed the time fields to elongation:
```python
def _internode_target(cur: Bud, cfg: Config, iteration: int, t: float, state: _SimState) -> float:
    base_length = cfg.sim.internode_length
    if cfg.sim.internode_length_jitter > 0:
        ss = np.random.SeedSequence(
            [cfg.seed, _ILEN_SALT, iteration, state.node_index]
        )
        rng = np.random.default_rng(ss.generate_state(1)[0])
        factor = max(0.5, min(1.5, rng.normal(1.0, cfg.sim.internode_length_jitter)))
        base_length = cfg.sim.internode_length * factor
    return compute_target_with_age(
        base_length=base_length,
        birth_time=t,
        total_years=cfg.sim.max_simulation_years,
        cfg=cfg.sim.elongation,
    )
```

`_emit_node` (lines 355-358) — add `t`, set `birth_time`:
```python
def _emit_node(
    cur: Bud, d: np.ndarray, new_pos: np.ndarray, target: float, is_main: bool,
    light_info, tree: Tree, cfg: Config, iteration: int, t: float, state: _SimState,
) -> tuple[Node, Bud]:
```
In the `Internode(...)` construction (lines 367-376), replace `birth_iteration=iteration,` with `birth_time=t,`. (Leave the `Bud(...)` creation as-is; `low_quality_steps`/`low_light_steps` stay.)

- [ ] **Step 4: Edit `_apply_temporal_dynamics` (lines 485-495)**

```python
def _apply_temporal_dynamics(forest: Forest, cfg: Config, t: float) -> None:
    """Per-iteration aging updates. Order matters: lengths first (sag reads
    load = length × diameter²), diameters next (sag reads diameter), sag last."""
    if cfg.sim.elongation.enabled:
        for tree in forest.trees:
            update_lengths(tree, current_time=t, cfg=cfg.sim.elongation)
    for tree in forest.trees:
        update_diameters_incremental(tree, r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent)
    if cfg.sag.enabled:
        for tree in forest.trees:
            apply_sag(tree, cfg=cfg.sag)
```

- [ ] **Step 5: Rename sites in `tests/sim/test_simulator.py`**

In `tests/sim/test_simulator.py` apply: `max_iterations=` → `max_simulation_years=` (float), `tau_iterations=` → `tau_years=`, `birth_iteration` → `birth_time`. (Mechanical — exact lines surfaced by `grep -n`.)

- [ ] **Step 6: Run the simulator + elongation + tree suites**

Run: `.venv/bin/pytest tests/sim/test_simulator.py tests/sim/test_elongation.py tests/sim/test_tree.py tests/integration/test_elongation_chronology.py -v`
Expected: PASS (after Task 9 renames the chronology test; if that test still fails on `birth_iteration`/`sim.max_iterations`, it is fixed in Task 9 — you may run it green there).

> Note: `test_elongation_chronology.py` references `sim.max_iterations` and `birth_iteration`; it is migrated in Task 9. If executing strictly in order, expect that one file to fail until Task 9.

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/sim/simulator.py tests/sim/test_simulator.py
git commit -m "feat(sim): thread Clock through forest loop; growth-window gate (#10)"
```

---

## Task 7: CLI — `--years` / `--dt-years` flags + `asset_meta`

**Files:**
- Modify: `src/palubicki/cli.py` (line 64 arg def; lines 203-204; line 243)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Update the failing tests**

In `tests/test_cli.py`:
- Line 30: `assert data["sim"]["max_simulation_years"] == 30.0`
- Line 115 (the `test_generate_minimal` YAML): change `  max_iterations: 2` → `  max_simulation_years: 2`.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_cli.py -k "dump or generate_minimal" -v`
Expected: FAIL — `KeyError: 'max_simulation_years'` / config error on unknown key `max_iterations`.

- [ ] **Step 3: Edit `cli.py`**

Replace the arg definition (line 64):
```python
    g.add_argument("--iterations", type=int, default=None)
```
with:
```python
    g.add_argument("--years", type=float, default=None, dest="years")
    g.add_argument("--dt-years", type=float, default=None, dest="dt_years")
```
Replace the override mapping (lines 203-204):
```python
    if args.iterations is not None:
        overrides["sim.max_iterations"] = args.iterations
```
with:
```python
    if args.years is not None:
        overrides["sim.max_simulation_years"] = args.years
    if args.dt_years is not None:
        overrides["sim.dt_years"] = args.dt_years
```
Replace the `asset_meta` entry (line 243):
```python
            "iterations": cfg.sim.max_iterations,
```
with:
```python
            "simulation_years": cfg.sim.max_simulation_years,
```

> If `--iterations` / `--years` also appear in the `forest` subcommand parser, apply the same rename there. Surface with `grep -n "iterations" src/palubicki/cli.py`.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/cli.py tests/test_cli.py
git commit -m "feat(cli): --years/--dt-years replace --iterations (#10)"
```

---

## Task 8: Species presets

**Files:**
- Modify: `src/palubicki/configs/species/{oak,birch,maple,pine,fir}.yaml`

- [ ] **Step 1: Edit all five presets**

In each file rename the two keys (values unchanged):
- `  max_iterations: N` → `  max_simulation_years: N`
- `    tau_iterations: X` → `    tau_years: X`

Exact values: oak (45 / 3.0), birch (50 / 2.0), maple (42 / 3.0), pine (50 / 2.5), fir (50 / 2.5).

- [ ] **Step 2: Verify each preset still loads**

Run:
```bash
for s in oak birch maple pine fir; do
  .venv/bin/python -c "from palubicki.config import load_config; from pathlib import Path; load_config(yaml_path=None, cli_overrides={}, output=Path('/tmp/o.glb'), species='$s'); print('$s ok')"
done
```
Expected: `oak ok` … `fir ok` (no `ConfigError`).

- [ ] **Step 3: Commit**

```bash
git add src/palubicki/configs/species/
git commit -m "refactor(species): max_simulation_years + tau_years in presets (#10)"
```

---

## Task 9: Mechanical test migration (remaining files)

**Files:** every test file still referencing the old names. Enumerate first:
```bash
grep -rln "max_iterations\|tau_iterations\|birth_iteration\|current_iteration=" tests/
```

- [ ] **Step 1: Apply the renames across the listed files**

For each file, apply (in this order):
- `sim.max_iterations` (override-dict string key) → `sim.max_simulation_years`
- `max_iterations=N` (SimConfig kwarg) → `max_simulation_years=float(N)`
- `max_iterations: N` (YAML inside test strings / fixtures) → `max_simulation_years: N`
- `data["sim"]["max_iterations"]` → `data["sim"]["max_simulation_years"]`
- `.max_iterations` (attribute reads) → `.max_simulation_years`
- `tau_iterations` → `tau_years`
- `birth_iteration` → `birth_time` (and any compared int literals → floats)
- `current_iteration=` → `current_time=`

Known assertion-bearing spots to fix by value (not just rename):
- `tests/edit/test_schema.py:87` → `assert "max_simulation_years" in names`
- `tests/integration/test_elongation_chronology.py:16` → `"sim.max_simulation_years": 30,`
- `tests/integration/test_elongation_chronology.py:23-24` → `iod.birth_time < 10` / `iod.birth_time >= 20`
- `tests/test_config_yaml.py` lines 17/26/32/37/41/46 → rename key + compare against `max_simulation_years` (expected values become floats: `15.0`, `7.0`, `30.0`)
- `tests/fixtures/forest_minimal.yaml` → `max_simulation_years:`

> `tests/edit/test_schema.py` derives the UI schema from `SimConfig` fields. Removing `max_iterations` and adding `dt_years`/`max_simulation_years` changes the field set — confirm the schema test only asserts presence of the new key, not an exact field list. If it asserts an exact set, update it to include `dt_years`, `max_simulation_years`, `annual_growth_period` and drop `max_iterations`.

- [ ] **Step 2: Run the full suite (excluding slow goldens for speed)**

Run: `.venv/bin/pytest -q -m "not slow"`
Expected: PASS (no errors, no `unknown keys in section 'sim'`, no `AttributeError`).

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "test: migrate to time-axis config field names (#10)"
```

---

## Task 10: Phenology acceptance test

**Files:**
- Create: `tests/integration/test_phenology.py`

- [ ] **Step 1: Write the test**

```python
# tests/integration/test_phenology.py
"""Acceptance for issue #10: annual_growth_period gates growth to a window."""
import math
from pathlib import Path

import pytest

from palubicki.config import load_config
from palubicki.sim.simulator import simulate

pytestmark = pytest.mark.slow


def _run(tmp_path, *, dt_years, window, years=4.0):
    cfg = load_config(
        yaml_path=None,
        cli_overrides={
            "sim.dt_years": dt_years,
            "sim.max_simulation_years": years,
            "sim.annual_growth_period": list(window),
            "envelope.marker_count": 1500,
            "seed": 0,
        },
        output=tmp_path / "o.glb",
    )
    return simulate(cfg)


def _year_fraction(t: float) -> float:
    return t - math.floor(t)


def test_growth_confined_to_first_half_year(tmp_path):
    tree = _run(tmp_path, dt_years=0.25, window=(0.0, 0.5))
    fractions = [_year_fraction(iod.birth_time) for iod in tree.all_internodes]
    assert fractions, "expected some internodes"
    # Every internode is born in the growth window [0.0, 0.5).
    assert all(0.0 <= f < 0.5 for f in fractions), sorted(set(round(f, 3) for f in fractions))


def test_no_internodes_born_in_dormant_half(tmp_path):
    tree = _run(tmp_path, dt_years=0.25, window=(0.0, 0.5))
    dormant = [iod for iod in tree.all_internodes if _year_fraction(iod.birth_time) >= 0.5]
    assert dormant == []


def test_full_year_window_grows_every_step(tmp_path):
    # dt_years=1.0 + default-equivalent full window: growth occurs (sanity that
    # the gate does not suppress the default case).
    tree = _run(tmp_path, dt_years=1.0, window=(0.0, 1.0))
    assert len(tree.all_internodes) > 0
```

- [ ] **Step 2: Run to verify it passes**

Run: `.venv/bin/pytest tests/integration/test_phenology.py -v`
Expected: PASS (3 tests).

> If `test_growth_confined_to_first_half_year` fails with fractions at `0.5`/`0.75`, the loop is not honoring `in_window` — re-check Task 6 Step 1 (the `continue` must skip emission and must not run `_iteration_step`).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_phenology.py
git commit -m "test(integration): phenology growth-window acceptance (#10)"
```

---

## Task 11: README time-model paragraph

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Edit the Phase 2D elongation section**

Around line 198-205, where it currently says "Every internode now tracks its birth iteration … `tau_iterations`", update wording: `birth iteration` → `birth time (years)`, `each iteration` → `each year of simulated time`, and `tau_iterations` → `tau_years`.

- [ ] **Step 2: Add a "Time model" paragraph**

Insert a short subsection (place it near the simulation-overview prose, e.g. after the Phase descriptions):
```markdown
### Time model

The simulator advances in fractional years. `sim.dt_years` is how much time one
iteration represents (default `1.0` — one iteration ≈ one growing year);
`sim.max_simulation_years` is the total simulated span (default `30.0`), so the
iteration count is `round(max_simulation_years / dt_years)`. Each internode
records its `birth_time` in years, and elongation ramps over `tau_years`.
`sim.annual_growth_period = [lo, hi]` (year fractions in `[0, 1)`) gates growth
to a window: with `dt_years < 1.0`, new internodes are only emitted when the
year-fraction falls in `[lo, hi)`; outside it the tree only ages. At the default
`dt_years = 1.0` and `[0.0, 1.0]` window, every iteration grows — identical to
the prior iteration-count behavior.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): document the time / phenology model (#10)"
```

---

## Task 12: Golden verification + full suite

**Files:** none (verification only).

- [ ] **Step 1: Run the goldens**

Run: `.venv/bin/pytest tests/golden/test_goldens.py -v`
Expected: PASS. `test_golden_ellipsoid`, `test_golden_ellipsoid_light`, and `test_golden_forest_v3` must all be green — the hashes must NOT change (invariance contract). If a hash drifted, STOP: a *time* value leaked where an *iteration* index belonged (most likely a missed RNG salt still using `t` instead of `iteration`, or `num_iterations` not reproducing the old count). Do not run `--update-goldens`.

- [ ] **Step 2: Run the entire suite**

Run: `.venv/bin/pytest -q`
Expected: PASS, no skips beyond the usual.

- [ ] **Step 3: Smoke-test the CLI acceptance criterion**

Run: `.venv/bin/palubicki generate --species oak --seed 0 --output /tmp/oak.glb --validate`
Expected: exit 0, `validated: N primitives` on stderr, `/tmp/oak.glb` exists.

- [ ] **Step 4: Final commit (if any stray fixups)**

```bash
git add -A && git commit -m "chore: time-axis cleanup (#10)" || echo "nothing to commit"
```

---

## Self-Review notes

- **Spec coverage:** Clock (T1), config replace/validate (T2), tau rename (T3), birth_time + remove Bud.age (T4), elongation time-deltas (T5), simulator threading + growth-window gate (T6), CLI (T7), presets (T8), test migration (T9), phenology acceptance (T10), README (T11), golden invariance (T12). All spec sections mapped.
- **Type consistency:** `birth_time: float`, `current_time: float`, `total_years: float`, `tau_years: float`, `num_iterations: int`, `Clock.in_window(lo, hi)` used consistently across tasks.
- **Iteration vs time:** `iteration: int` retained for RNG salts/`node_index`/logging in T6; `t: float` used only for `birth_time` and elongation — the spec's core invariant.
