# Vigor-driven Internode Length Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make internode length emerge from the continuous Borchert-Honda flux `v_b` (saturating length law) instead of `floor(v_b)` counts + a top-down `age_factor` clock, collapse the substep machinery, add hysteresis dormancy, and couple vigor into diameter.

**Architecture:** `allocate()` returns continuous per-bud flux (no floor). Each active bud emits ≤1 internode/iteration whose length is `shoot_extension_max·(1−e^(−v_b/vigor_ref))`. Dormancy is decided by an EMA `recent_vigor` against `vigor_dormancy`. `_grow_tree` becomes a single bud-major pass (substep machinery deleted). Diameter keeps the pipe model but seeds tip radius from recorded internode vigor. The 5 species presets are recalibrated toward realism.

**Tech Stack:** Python 3.14, NumPy, pytest. Run tests with `.venv/bin/pytest` (venv is at `.venv/`, never persists across shells — always prefix `.venv/bin/`).

**Spec:** `docs/superpowers/specs/2026-05-29-vigor-driven-internode-length-design.md`

---

## File Structure

- `src/palubicki/sim/bh.py` — `allocate()` returns `dict[Bud, float]`; all `floor()` removed.
- `src/palubicki/sim/tree.py` — add `Internode.vigor: float`, `Bud.recent_vigor: float`.
- `src/palubicki/sim/elongation.py` — delete `compute_target_with_age`; add pure `shoot_extension(v_b, …)`; keep `update_lengths`.
- `src/palubicki/config.py` — add `shoot_extension_max`, `vigor_ref`, `vigor_dormancy`, `vigor_smoothing`, `vigor_diameter_gain`; remove `internode_length`, `n_substeps_max`, `re_perceive_per_substep`, `ElongationConfig.age_factor_*`; update validators.
- `src/palubicki/sim/simulator.py` — rewrite `_grow_tree` as single pass; EMA dormancy; saturating length in `_internode_target`; record vigor in `_emit_node`; delete `_SubstepChain` + `_reperceive_substep_terminals`.
- `src/palubicki/sim/radii.py` — vigor-seeded tip radius in `compute_radii`.
- `src/palubicki/sim/diagnostics.py` — add `internode_length_by_order` + proximal/distal summary.
- `src/palubicki/configs/species/{birch,fir,maple,oak,pine}.yaml` — recalibrate.
- Tests: `tests/sim/test_bh.py`, `tests/sim/test_elongation.py`, `tests/sim/test_simulator.py`, `tests/sim/test_diagnostics.py`, plus golden regen.

> **Note on intentional breakage (PoC, no back-compat):** the bit-exact tests `test_simulator_v1_bit_exact_when_light_disabled`, `test_simulate_v2_bit_exact_after_refactor`, any `pinned` digest tests, and the elongation `age_factor` tests WILL break by design. Tasks 9–11 update/retire them. Do not try to preserve old hashes.

---

### Task 1: `bh.py` returns continuous flux (remove floor)

**Files:**
- Modify: `src/palubicki/sim/bh.py:8-28` (signature/docstring), `:93,98,104,134,143` (floors)
- Test: `tests/sim/test_bh.py`

- [ ] **Step 1: Update the existing integer-assertion tests to float expectations**

In `tests/sim/test_bh.py`, change the three count assertions to the continuous values:

```python
def test_single_bud_n_equals_alpha_times_q():
    tree, bud = _single_bud_tree()
    quality = {bud: 4}
    n_by_bud = allocate(tree, quality=quality, alpha=2.0, lambda_apical=0.5)
    assert n_by_bud[bud] == pytest.approx(8.0)


def test_zero_quality_yields_zero_growth():
    tree, bud = _single_bud_tree()
    quality = {bud: 0}
    n_by_bud = allocate(tree, quality=quality, alpha=2.0, lambda_apical=0.5)
    assert n_by_bud[bud] == pytest.approx(0.0)
```

And the split test (replace the `floor` comment + assertions):

```python
    quality = {main_bud: 4, lat_bud: 2}
    n_by_bud = allocate(tree, quality=quality, alpha=1.0, lambda_apical=0.7)
    # v_root = 6; v_total = 6; v_main = 6*(0.7*4)/(0.7*4+0.3*2) = 4.941...
    assert n_by_bud[main_bud] == pytest.approx(4.9411764, rel=1e-5)
    assert n_by_bud[lat_bud] == pytest.approx(1.0588235, rel=1e-5)
    assert n_by_bud[main_bud] + n_by_bud[lat_bud] == pytest.approx(6.0)
```

Add `import pytest` at the top of the file if not present.

- [ ] **Step 2: Add a new test asserting fractional flux survives**

```python
def test_fractional_flux_is_not_floored():
    tree, bud = _single_bud_tree()
    quality = {bud: 1}
    n_by_bud = allocate(tree, quality=quality, alpha=1.5, lambda_apical=0.5)
    # v_b = 1.5 — must NOT be floored to 1
    assert n_by_bud[bud] == pytest.approx(1.5)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/sim/test_bh.py -q`
Expected: FAIL — current `allocate` floors, so `1.5 → 1`, `4.94 → 4`.

- [ ] **Step 4: Remove floors in `bh.py`**

Change the docstring/signature at `bh.py:8-16`:

```python
def allocate(
    tree: Tree,
    *,
    quality: dict[Bud, int],
    alpha: float,
    lambda_apical: float,
    v_subtree: dict[int, float] | None = None,
) -> dict[Bud, float]:
    """Borchert-Honda two-pass allocation. Returns the continuous flux v_b per bud.

    If ``v_subtree`` is provided (precomputed by ``compute_v_subtree``), the basipetal
    pass is skipped — useful when the caller also feeds shedding from the same dict.
    """
```

Change `n_by_bud: dict[Bud, int]` → `dict[Bud, float]` at `:26`. Then replace every `math.floor(...)` assignment with the raw expression:
- `:93` → `n_by_bud[b] = v_here * qb / total_q`
- `:98` → `n_by_bud[terminal] = v_terminal`
- `:104` → `n_by_bud[b] = v_lateral * share`
- `:134` → `n_by_bud[terminal_here] = v_main`
- `:143` → `n_by_bud[b] = v_lat * share`

Remove the now-unused `import math` at `:3` only if no other `math.` use remains (grep first; if none, remove it).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_bh.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/bh.py tests/sim/test_bh.py
git commit -m "sim/bh: allocate() returns continuous v_b flux (remove floor) (#20)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Add `Internode.vigor` and `Bud.recent_vigor` fields

**Files:**
- Modify: `src/palubicki/sim/tree.py:18-25` (Bud), `:51-61` (Internode)
- Test: `tests/sim/test_simulator.py`

- [ ] **Step 1: Write a failing test for the new fields' defaults**

Append to `tests/sim/test_simulator.py`:

```python
def test_bud_and_internode_have_vigor_fields():
    import numpy as np
    from palubicki.sim.tree import Bud, Internode, Node
    root = Node(position=np.zeros(3))
    bud = Bud(position=np.zeros(3), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=root)
    assert bud.recent_vigor == 0.0
    child = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=root, child_node=child, length=1.0, is_main_axis=True)
    assert iod.vigor == 0.0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/sim/test_simulator.py::test_bud_and_internode_have_vigor_fields -q`
Expected: FAIL with `AttributeError`/`TypeError` (no such field).

- [ ] **Step 3: Add the fields**

In `tree.py`, add to `Bud` (after `axis_node_ordinal: int = 0`):

```python
    # EMA of this bud's per-iteration BH flux v_b. Governs the hysteresis
    # dormancy decision (recent_vigor < vigor_dormancy -> DORMANT) so a single
    # starved/lucky iteration cannot flip the bud's state. Updated each iteration.
    recent_vigor: float = 0.0
```

Add to `Internode` (after `length_target: float = 0.0`, before `quality_history`):

```python
    # The continuous BH flux v_b that produced this internode. Drives the
    # vigor-seeded tip radius in radii.py and the internode-length diagnostics.
    vigor: float = 0.0
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/pytest tests/sim/test_simulator.py::test_bud_and_internode_have_vigor_fields -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/tree.py tests/sim/test_simulator.py
git commit -m "sim/tree: add Bud.recent_vigor and Internode.vigor (#20)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Saturating length law + delete `compute_target_with_age`

**Files:**
- Modify: `src/palubicki/sim/elongation.py:21-40` (delete), top of file
- Test: `tests/sim/test_elongation.py`

- [ ] **Step 1: Replace the age_factor tests with shoot_extension tests**

In `tests/sim/test_elongation.py`, delete every test that imports `compute_target_with_age` (the block of `test_compute_target_*`), and add at the top of the file:

```python
import math
import pytest
from palubicki.sim.elongation import shoot_extension


def test_shoot_extension_zero_vigor_is_zero():
    assert shoot_extension(0.0, shoot_extension_max=0.3, vigor_ref=1.0) == 0.0


def test_shoot_extension_saturates_below_max():
    # large v_b approaches but never exceeds shoot_extension_max
    got = shoot_extension(100.0, shoot_extension_max=0.3, vigor_ref=1.0)
    assert got < 0.3
    assert got == pytest.approx(0.3, abs=1e-6)


def test_shoot_extension_knee_at_vigor_ref():
    # at v_b == vigor_ref, length == max*(1-1/e)
    got = shoot_extension(1.0, shoot_extension_max=0.3, vigor_ref=1.0)
    assert got == pytest.approx(0.3 * (1.0 - math.exp(-1.0)))


def test_shoot_extension_monotonic_in_vigor():
    a = shoot_extension(0.5, shoot_extension_max=0.3, vigor_ref=1.0)
    b = shoot_extension(1.5, shoot_extension_max=0.3, vigor_ref=1.0)
    assert b > a


def test_shoot_extension_near_linear_for_small_vigor():
    # small v_b -> approximately max * v_b / vigor_ref
    got = shoot_extension(0.01, shoot_extension_max=0.3, vigor_ref=1.0)
    assert got == pytest.approx(0.3 * 0.01, rel=1e-2)
```

Keep all the existing `test_update_lengths_*` tests, but remove the `age_factor_decay=0.0` kwarg from the two that pass it (`test_update_lengths_at_birth_is_small_fraction_of_target` at line 85) since that kwarg is being deleted from `ElongationConfig`:

```python
    cfg = ElongationConfig(enabled=True, tau_years=3.0)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/sim/test_elongation.py -q`
Expected: FAIL — `shoot_extension` does not exist; import errors.

- [ ] **Step 3: Edit `elongation.py`**

Update the module docstring's first line to drop "age_factor on target length", and replace the `compute_target_with_age` function (lines 21-40) with:

```python
def shoot_extension(v_b: float, shoot_extension_max: float, vigor_ref: float) -> float:
    """Saturating physiological length response to BH flux.

    length = shoot_extension_max * (1 - exp(-v_b / vigor_ref))

    Small v_b is ~linear in resource; large v_b asymptotes to a finite annual
    shoot extension (a meristem rate limit, not an arbitrary clamp). Replaces the
    old top-down age_factor(birth_time) decay (#20).
    """
    if vigor_ref <= 0:
        return shoot_extension_max
    return shoot_extension_max * (1.0 - math.exp(-v_b / vigor_ref))
```

Leave `update_lengths` (the sigmoid ramp) and `import math` untouched. Remove the `from palubicki.config import ElongationConfig` import only if unused after the edit — it is still used by `update_lengths`, so keep it.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/sim/test_elongation.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/elongation.py tests/sim/test_elongation.py
git commit -m "sim/elongation: saturating shoot_extension law; drop age_factor target (#20)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Config — add vigor fields, remove obsolete ones

**Files:**
- Modify: `src/palubicki/config.py:43` (remove `internode_length`), `:54` (remove `re_perceive_per_substep`), `:60-67` (remove `n_substeps_max`), `:206-223` (`ElongationConfig` age_factor fields), `:379-423` (validators)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for new config defaults + removed-field validation**

Append to `tests/test_config.py`:

```python
def test_simconfig_has_vigor_fields_with_defaults():
    from palubicki.config import SimConfig
    s = SimConfig()
    assert s.shoot_extension_max > 0
    assert s.vigor_ref > 0
    assert s.vigor_dormancy >= 0
    assert 0 < s.vigor_smoothing <= 1
    assert s.vigor_diameter_gain >= 0


def test_simconfig_dropped_internode_length():
    from palubicki.config import SimConfig
    assert not hasattr(SimConfig(), "internode_length")
    assert not hasattr(SimConfig(), "n_substeps_max")
    assert not hasattr(SimConfig(), "re_perceive_per_substep")


def test_invalid_vigor_ref_raises():
    import pytest
    from palubicki.config import Config, SimConfig, ConfigError
    with pytest.raises(ConfigError):
        Config(sim=SimConfig(vigor_ref=0.0)).validate()
```

> If `Config.validate()` is invoked differently (e.g. in `__post_init__` or a module function), match the existing pattern in `tests/test_config.py` — read a nearby validation test first and mirror it.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_config.py -q -k "vigor or dropped"`
Expected: FAIL.

- [ ] **Step 3: Edit `SimConfig`**

Remove line 43 (`internode_length`), line 54 (`re_perceive_per_substep`), and lines 60-67 (the `n_substeps_max` comment block + field). Update the `internode_length_jitter` doc (line 68-73) to read "σ as a fraction of the computed shoot extension". Add these fields to `SimConfig` (near the former `internode_length`):

```python
    shoot_extension_max: float = field(default=0.3, metadata={"ui": {"min": 0.02, "max": 1.0, "step": 0.01}})
    vigor_ref: float = field(default=1.0, metadata={"ui": {"min": 0.05, "max": 5.0, "step": 0.05}})
    vigor_dormancy: float = field(default=1.0, metadata={"ui": {"min": 0.0, "max": 5.0, "step": 0.05}})
    vigor_smoothing: float = field(default=0.5, metadata={"ui": {"min": 0.05, "max": 1.0, "step": 0.05}})
    vigor_diameter_gain: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
```

> `vigor_diameter_gain` defaults to 0.0 (pure pipe model); presets opt in (Task 9).

- [ ] **Step 4: Edit `ElongationConfig`**

Remove `age_factor_min` (line 218-220) and `age_factor_decay` (line 221-223). Keep `enabled` and `tau_years`. Update the class docstring first line to drop "+ age_factor on target length".

- [ ] **Step 5: Edit validators (`config.py:379-423`)**

Remove the `internode_length <= 0` check (385-386) and the two `age_factor_*` checks (417-423). Add to the `SimConfig` validation block:

```python
        if s.shoot_extension_max <= 0:
            raise ConfigError(f"sim.shoot_extension_max must be > 0, got {s.shoot_extension_max}")
        if s.vigor_ref <= 0:
            raise ConfigError(f"sim.vigor_ref must be > 0, got {s.vigor_ref}")
        if s.vigor_dormancy < 0:
            raise ConfigError(f"sim.vigor_dormancy must be >= 0, got {s.vigor_dormancy}")
        if not (0.0 < s.vigor_smoothing <= 1.0):
            raise ConfigError(f"sim.vigor_smoothing must be in (0, 1], got {s.vigor_smoothing}")
        if s.vigor_diameter_gain < 0:
            raise ConfigError(f"sim.vigor_diameter_gain must be >= 0, got {s.vigor_diameter_gain}")
```

Keep the `internode_length_jitter` range check (it references only the jitter field).

- [ ] **Step 6: Run to verify pass**

Run: `.venv/bin/pytest tests/test_config.py -q -k "vigor or dropped or invalid_vigor"`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "config: add vigor_* fields; remove internode_length/n_substeps_max/age_factor (#20)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Rewrite `_grow_tree` as a single bud-major pass

**Files:**
- Modify: `src/palubicki/sim/simulator.py` — `_grow_tree` (221-345), `_internode_target` (348-368), `_emit_node` (371-407), delete `_SubstepChain` (35-40) and `_reperceive_substep_terminals` (450-end-of-fn), remove `n_substeps_max`/`re_perceive_per_substep`/`compute_target_with_age` references and the `from ... import compute_target_with_age`.
- Test: `tests/sim/test_simulator.py`

- [ ] **Step 1: Write failing tests for the new behavior**

Append to `tests/sim/test_simulator.py`:

```python
def test_each_bud_emits_at_most_one_internode_per_iteration(tmp_path):
    # With the substep machinery gone, node count per iteration is bounded by
    # active buds. A single-bud seed grows at most one internode in iteration 0.
    import numpy as np
    from palubicki.config import Config, EnvelopeConfig, SimConfig
    from palubicki.sim.simulator import simulate
    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=400),
        sim=SimConfig(max_simulation_years=1.0, shoot_extension_max=0.3, vigor_ref=1.0,
                      vigor_dormancy=0.5),
        seed=7, output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)
    # exactly the root's first internode after one growth year
    assert len(tree.all_internodes) <= 2


def test_internode_records_vigor(tmp_path):
    import numpy as np
    from palubicki.config import Config, EnvelopeConfig, SimConfig
    from palubicki.sim.simulator import simulate
    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=600),
        sim=SimConfig(max_simulation_years=8.0, shoot_extension_max=0.3, vigor_ref=1.0,
                      vigor_dormancy=0.5),
        seed=7, output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)
    assert tree.all_internodes
    assert all(iod.vigor > 0 for iod in tree.all_internodes)


def test_length_scales_with_vigor(tmp_path):
    # Proximal (high-flux) internodes should be longer than distal ones — emergent
    # tapering with NO age term.
    import numpy as np
    from palubicki.config import Config, EnvelopeConfig, SimConfig
    from palubicki.sim.simulator import simulate
    from palubicki.sim.diagnostics import _walk_internodes, _axis_orders
    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=1.0, ry=3.0, rz=1.0, marker_count=4000),
        sim=SimConfig(max_simulation_years=20.0, shoot_extension_max=0.3, vigor_ref=1.0,
                      vigor_dormancy=0.5),
        seed=7, output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)
    iods = _walk_internodes(tree.root)
    orders = _axis_orders(tree.root)
    order0 = [iod.length_target for iod in iods if orders[id(iod)] == 0]
    high = max(orders.values())
    distal = [iod.length_target for iod in iods if orders[id(iod)] == high]
    assert order0 and distal
    assert (sum(order0) / len(order0)) > (sum(distal) / len(distal))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/sim/test_simulator.py -q -k "emits_at_most_one or records_vigor or length_scales"`
Expected: FAIL (config kwargs unknown until Task 4 is merged; logic not yet rewritten).

- [ ] **Step 3: Delete `_SubstepChain` and `_reperceive_substep_terminals`**

Remove the `_SubstepChain` dataclass (lines 35-40) and the entire `_reperceive_substep_terminals` function (line 450 to its end). Remove `from palubicki.sim.elongation import compute_target_with_age, update_lengths` → change to `from palubicki.sim.elongation import shoot_extension, update_lengths`.

- [ ] **Step 4: Rewrite `_grow_tree` (replace lines ~243-345 body)**

Replace the substep block (everything from `new_positions: list[...]` through `return nodes_created, new_positions`) with a single bud-major pass:

```python
    new_positions: list[np.ndarray] = []
    nodes_created = 0

    if cfg.sim.sympodial.enabled:
        promote_lateral_if_failing(tree, quality, cfg.sim.sympodial)
    v_subtree = compute_v_subtree(tree, quality)
    v_by_bud = allocate(
        tree, quality=quality,
        alpha=cfg.sim.alpha_basipetal, lambda_apical=cfg.sim.lambda_apical,
        v_subtree=v_subtree,
    )
    record_qualities(tree, v_subtree=v_subtree)

    s = cfg.sim.vigor_smoothing
    new_active: list[Bud] = []
    for bud in list(tree.active_buds):
        v_b = float(v_by_bud.get(bud, 0.0))
        # Hysteresis: smooth v_b, then threshold the EMA. A single starved/lucky
        # iteration cannot flip the bud's active/dormant state (#20).
        bud.recent_vigor = (1.0 - s) * bud.recent_vigor + s * v_b
        v_perc = res.direction[bud]
        v_perc_norm = float(np.linalg.norm(v_perc))
        if bud.recent_vigor < cfg.sim.vigor_dormancy or v_perc_norm < 1e-12:
            bud.state = BudState.DORMANT
            new_active.append(bud)
            continue

        light_grad = light_info.gradient[bud] if light_info else None
        is_main = (bud is bud.parent_node.terminal_bud)
        d = growth_direction(
            v_perception=res.direction[bud],
            current_direction=bud.direction,
            cfg=cfg.tropism,
            is_main_axis=is_main,
            light_gradient=light_grad,
            axis_order=bud.axis_order,
        )
        # U-turn check on the blended growth direction (envelope-boundary curl).
        if float(np.dot(d, bud.direction)) < cfg.sim.cos_min_perception:
            bud.state = BudState.DORMANT
            new_active.append(bud)
            continue

        target = _internode_target(bud, v_b, cfg, iteration, t, state)
        new_pos = bud.position + d * target

        if forest.obstacles:
            if segment_blocked(bud.position, new_pos, forest.obstacles):
                bud.state = BudState.DORMANT
                new_active.append(bud)
                continue
            if any_contains(new_pos, forest.obstacles):
                bud.state = BudState.DEAD
                continue

        new_node, terminal = _emit_node(
            bud, d, new_pos, target, v_b, is_main, light_info, tree, cfg, t, state
        )
        new_positions.append(new_pos)
        nodes_created += 1
        new_active.extend(new_node.lateral_buds)
        new_active.append(terminal)

    tree.active_buds = [b for b in new_active if b.state != BudState.DEAD]
    return nodes_created, new_positions
```

Update the `_grow_tree` docstring: replace the step-major substep explanation with: "Single bud-major pass: each active bud computes its BH flux `v_b`, updates its `recent_vigor` EMA, and (unless dormant by hysteresis, U-turn, or obstacle) emits exactly one internode whose length saturates with `v_b`. Perception and light are computed once per iteration upstream, so no in-iteration re-perception is needed."

- [ ] **Step 5: Rewrite `_internode_target` to use the saturating law**

```python
def _internode_target(cur: Bud, v_b: float, cfg: Config, iteration: int, t: float, state: _SimState) -> float:
    """Saturating shoot-extension length for the new internode, optionally jittered.

    The jitter RNG is salted by (seed, _ILEN_SALT, iteration, node_index) so the
    draw is reproducible and independent of perception/light ordering."""
    base_length = shoot_extension(v_b, cfg.sim.shoot_extension_max, cfg.sim.vigor_ref)
    if cfg.sim.internode_length_jitter > 0:
        ss = np.random.SeedSequence([cfg.seed, _ILEN_SALT, iteration, state.node_index])
        rng = np.random.default_rng(ss.generate_state(1)[0])
        factor = max(0.5, min(1.5, rng.normal(1.0, cfg.sim.internode_length_jitter)))
        base_length *= factor
    return base_length
```

> Note: this drops the `compute_target_with_age` call entirely. The elongation sigmoid ramp still applies later via `update_lengths` (length starts at 0 when `elongation.enabled`).

- [ ] **Step 6: Thread `v_b` into `_emit_node` and record it**

Change the `_emit_node` signature to accept `v_b` and set `vigor=v_b` on the Internode:

```python
def _emit_node(
    cur: Bud, d: np.ndarray, new_pos: np.ndarray, target: float, v_b: float, is_main: bool,
    light_info, tree: Tree, cfg: Config, t: float, state: _SimState,
) -> tuple[Node, Bud]:
```

In the `Internode(...)` constructor add `vigor=v_b,` alongside `length_target=target`.

- [ ] **Step 7: Run the new tests + the obstacle/dormancy tests**

Run: `.venv/bin/pytest tests/sim/test_simulator.py -q -k "emits_at_most_one or records_vigor or length_scales or obstacle or dormant"`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/palubicki/sim/simulator.py tests/sim/test_simulator.py
git commit -m "sim/simulator: single bud-major pass; vigor->saturating length; EMA dormancy (#20)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Vigor-seeded tip radius

**Files:**
- Modify: `src/palubicki/sim/radii.py:17-45`
- Test: `tests/sim/test_simulator.py` (or a new `tests/sim/test_radii.py`)

- [ ] **Step 1: Write failing tests**

Create `tests/sim/test_radii.py`:

```python
import numpy as np
from palubicki.sim.tree import Internode, Node, Tree
from palubicki.sim.radii import compute_radii


def _two_tip_tree(vigor_a: float, vigor_b: float):
    root = Node(position=np.zeros(3))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    trunk = Internode(parent_node=root, child_node=mid, length=1.0, is_main_axis=True)
    root.children_internodes.append(trunk)
    mid.parent_internode = trunk
    a_node = Node(position=np.array([0.5, 2.0, 0.0]))
    b_node = Node(position=np.array([-0.5, 2.0, 0.0]))
    ia = Internode(parent_node=mid, child_node=a_node, length=1.0, is_main_axis=True, vigor=vigor_a)
    ib = Internode(parent_node=mid, child_node=b_node, length=1.0, is_main_axis=False, vigor=vigor_b)
    mid.children_internodes.extend([ia, ib])
    a_node.parent_internode = ia
    b_node.parent_internode = ib
    tree = Tree(root=root, all_internodes=[trunk, ia, ib])
    return tree, ia, ib


def test_gain_zero_recovers_pure_pipe_model():
    tree, ia, ib = _two_tip_tree(5.0, 0.1)
    compute_radii(tree, r_tip=0.01, exponent=2.0, vigor_ref=1.0, vigor_diameter_gain=0.0)
    assert ia.diameter == ib.diameter  # vigor ignored


def test_higher_vigor_tip_is_thicker():
    tree, ia, ib = _two_tip_tree(5.0, 0.1)
    compute_radii(tree, r_tip=0.01, exponent=2.0, vigor_ref=1.0, vigor_diameter_gain=1.0)
    assert ia.diameter > ib.diameter
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/sim/test_radii.py -q`
Expected: FAIL — `compute_radii` has no `vigor_ref`/`vigor_diameter_gain` params.

- [ ] **Step 3: Edit `radii.py`**

Add the two kwargs (defaulting so existing callers without them still work, but we will update callers in Step 5):

```python
def compute_radii(
    tree: Tree, *, r_tip: float, exponent: float,
    vigor_ref: float = 1.0, vigor_diameter_gain: float = 0.0,
) -> None:
    """Fill `internode.diameter` in-place using pipe model r^n = sum(r_child^n).

    Tip internodes (no descendant internodes) seed their radius as
    ``r_tip * (1 + vigor_diameter_gain * iod.vigor / vigor_ref)`` so vigorous
    lineages seed thicker pipes (#20). vigor_diameter_gain=0 -> flat r_tip.
    """
    for iod in tree.root.children_internodes:
        _set_radius_iterative(iod.child_node, iod, r_tip, exponent, vigor_ref, vigor_diameter_gain)


def _set_radius_iterative(
    root_node: Node, root_iod: Internode, r_tip: float, n: float,
    vigor_ref: float, vigor_diameter_gain: float,
) -> None:
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
            r = r_tip * (1.0 + vigor_diameter_gain * iod.vigor / vigor_ref)
        else:
            sum_pow = sum(radius[id(c.child_node)] ** n for c in node.children_internodes)
            r = sum_pow ** (1.0 / n)
        iod.diameter = 2.0 * r
        radius[id(node)] = r
```

Update `update_diameters_incremental` (lines 6-14) to pass the new kwargs through:

```python
def update_diameters_incremental(
    tree: Tree, r_tip: float, exponent: float,
    vigor_ref: float = 1.0, vigor_diameter_gain: float = 0.0,
) -> None:
    compute_radii(tree, r_tip=r_tip, exponent=exponent,
                  vigor_ref=vigor_ref, vigor_diameter_gain=vigor_diameter_gain)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/sim/test_radii.py -q`
Expected: PASS

- [ ] **Step 5: Wire the simulator's diameter calls to pass vigor params**

In `simulator.py`, find both `update_diameters_incremental(...)` call sites (grep `update_diameters_incremental`) and add the kwargs, e.g. the finalization call at line ~92:

```python
        update_diameters_incremental(
            tree, r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent,
            vigor_ref=cfg.sim.vigor_ref, vigor_diameter_gain=cfg.sim.vigor_diameter_gain,
        )
```

Apply the same to any per-iteration call site.

- [ ] **Step 6: Run the simulator suite (non-slow)**

Run: `.venv/bin/pytest tests/sim/ -q -m "not slow"`
Expected: PASS (except the known bit-exact tests handled in Task 8).

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/sim/radii.py src/palubicki/sim/simulator.py tests/sim/test_radii.py
git commit -m "sim/radii: vigor-seeded tip radius (gain=0 recovers pipe model) (#20)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Diagnostics — internode length by axis order

**Files:**
- Modify: `src/palubicki/sim/diagnostics.py` (add metric fn, wire into `compute_metrics`, `_SCALAR_KEYS`, `format_report`)
- Test: `tests/sim/test_diagnostics.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/sim/test_diagnostics.py`:

```python
def test_internode_length_by_order_present_and_tapers():
    import numpy as np
    from palubicki.sim.tree import Internode, Node, Tree
    from palubicki.sim.diagnostics import compute_metrics
    # trunk (order 0, long) -> lateral (order 1, short)
    root = Node(position=np.zeros(3))
    mid = Node(position=np.array([0.0, 2.0, 0.0]))
    trunk = Internode(parent_node=root, child_node=mid, length=2.0, is_main_axis=True)
    trunk.length_target = 2.0
    root.children_internodes.append(trunk); mid.parent_internode = trunk
    tip = Node(position=np.array([1.0, 2.5, 0.0]))
    lat = Internode(parent_node=mid, child_node=tip, length=0.5, is_main_axis=False)
    lat.length_target = 0.5
    mid.children_internodes.append(lat); tip.parent_internode = lat
    tree = Tree(root=root, all_internodes=[trunk, lat])
    m = compute_metrics(tree)
    assert "internode_length_by_order" in m
    assert m["internode_length_proximal_mean"] > m["internode_length_distal_mean"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_internode_length_by_order_present_and_tapers -q`
Expected: FAIL — keys absent.

- [ ] **Step 3: Add the metric to `diagnostics.py`**

Add after `_divergence_angle_metrics` (use `length_target`, the finalized length):

```python
def _internode_length_metrics(
    internodes: list[Internode],
    axis_orders: dict[int, int],
) -> dict:
    """Internode length grouped by axis_order, plus proximal (lowest order)
    vs distal (highest order) means. Verifies emergent tapering with no age
    term (#20). Uses length_target (finalized length)."""
    by_order: dict[int, list[float]] = defaultdict(list)
    for L in internodes:
        by_order[axis_orders[id(L)]].append(float(L.length_target))
    out = {o: _stats(v) for o, v in by_order.items()}
    if by_order:
        lo = min(by_order); hi = max(by_order)
        prox = float(np.mean(by_order[lo]))
        dist = float(np.mean(by_order[hi]))
    else:
        prox = dist = float("nan")
    return {
        "internode_length_by_order": out,
        "internode_length_proximal_mean": prox,
        "internode_length_distal_mean": dist,
    }
```

Wire into `compute_metrics` (after the `_divergence_angle_metrics` update):

```python
    out.update(_internode_length_metrics(internodes, axis_orders))
```

Add `"internode_length_proximal_mean"` and `"internode_length_distal_mean"` to `_SCALAR_KEYS`. In `_aggregate`, `internode_length_by_order` is a per-order dict of stats; mirror the `_ANGLE_KEYS` aggregation by adding `"internode_length_by_order"` to `_ANGLE_KEYS` (its leaves are `_stats` dicts, same shape).

In `format_report`, append to the Architecture block:

```python
    for k in ("internode_length_proximal_mean", "internode_length_distal_mean"):
        lines.append(f"  {k:24s} {_fmt_scalar(metrics.get(k))}".rstrip())
```

- [ ] **Step 4: Run to verify pass + full diagnostics suite**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/diagnostics.py tests/sim/test_diagnostics.py
git commit -m "sim/diagnostics: internode_length_by_order + proximal/distal taper metric (#20)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Fix the intentionally-broken bit-exact / cross-reference tests

**Files:**
- Modify: `tests/sim/test_simulator.py` (bit-exact + golden-digest tests), `tests/golden/test_goldens.py` (`_cfg_ellipsoid` uses `internode_length=`), any other test still passing removed kwargs.
- Test: the whole suite.

- [ ] **Step 1: Find every remaining reference to removed symbols**

Run:
```bash
grep -rn "internode_length\b\|n_substeps_max\|re_perceive_per_substep\|age_factor\|compute_target_with_age" tests/ src/
```
Expected: hits only where they still need fixing (e.g. `tests/golden/test_goldens.py` `_cfg_ellipsoid`, schema/edit tests, dump-defaults golden).

- [ ] **Step 2: Update `tests/golden/test_goldens.py`**

In `_cfg_ellipsoid`, replace `internode_length=0.1` with `shoot_extension_max=0.3, vigor_ref=1.0, vigor_dormancy=0.5`.

- [ ] **Step 3: Update bit-exact tests in `tests/sim/test_simulator.py`**

The bit-exact digests (`test_simulator_v1_bit_exact_when_light_disabled`, `test_simulate_v2_bit_exact_after_refactor`) pin pre-change hashes and are now invalid by design. Either delete them (PoC, no back-compat) or, if keeping the structure, recompute and update the pinned digest. Recommended: delete the two stale pins and rely on `test_simulate_is_deterministic` (run twice, compare) for reproducibility coverage. Confirm `test_simulate_is_deterministic` still passes.

- [ ] **Step 4: Update any edit/schema/dump-defaults tests**

Run `grep -rn "internode_length\|n_substeps\|re_perceive\|age_factor" tests/edit tests/test_cli.py tests/test_config_yaml.py` and remove/replace the removed keys. If `tests/test_cli.py` pins `dump-defaults` YAML output, regenerate the expected text from `.venv/bin/python -m palubicki dump-defaults`.

- [ ] **Step 5: Run the full non-slow suite**

Run: `.venv/bin/pytest -q -m "not slow"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "tests: update for vigor-driven length; retire stale bit-exact pins (#20)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Recalibrate the 5 species presets (toward realism)

**Files:**
- Modify: `src/palubicki/configs/species/{birch,fir,maple,oak,pine}.yaml`
- Test: `tests/test_config_species.py`, `tests/golden/test_species_goldens.py`, `palubicki diagnose`

This task is empirical and iterative; the steps describe the loop, not fixed values.

- [ ] **Step 1: Strip removed keys from every preset**

For each YAML, delete `sim.internode_length`, `sim.elongation.age_factor_min`, `sim.elongation.age_factor_decay`, and any `sim.n_substeps_max` / `sim.re_perceive_per_substep`. Keep `sim.elongation.enabled` and `sim.elongation.tau_years`.

- [ ] **Step 2: Add starting vigor params per preset**

Add under `sim:` for each species (starting points — birch shown; mirror per species, scaling `shoot_extension_max` from each old `internode_length`):

```yaml
sim:
  shoot_extension_max: 0.30   # ~ old internode_length / age_factor ceiling
  vigor_ref: 1.0
  vigor_dormancy: 1.0
  vigor_smoothing: 0.5
  vigor_diameter_gain: 0.5    # opt into the vigor->diameter taper
```

- [ ] **Step 3: Confirm presets load + validate**

Run: `.venv/bin/pytest tests/test_config_species.py -q`
Expected: PASS (no unknown/missing keys).

- [ ] **Step 4: Diagnose each species and tune**

For each species run:
```bash
.venv/bin/python -m palubicki diagnose --species birch --seeds 1,2,3
```
Inspect `tree_height`, `internode_length_proximal_mean` vs `..._distal_mean` (proximal must exceed distal), `trunk_base_diameter`, Strahler/Horton. Tune `alpha_basipetal` / `vigor_ref` so heights are species-plausible and internode lengths land in the ~0.015–0.086 m range (the repo's measured internode scale). Tune `vigor_diameter_gain` for trunk taper. Repeat until each species reads sane.

> If `diagnose` lacks a `--species`/`--seeds` flag in this build, check `_cmd_diagnose` in `src/palubicki/cli.py:454` for the actual flags and adapt the command.

- [ ] **Step 5: Visual check**

For each species, generate + preview:
```bash
.venv/bin/python -m palubicki generate --species birch -o /tmp/birch.glb
.venv/bin/python -m palubicki preview /tmp/birch.glb -o /tmp/birch.png
```
Open each PNG; confirm plausible trunk taper, crown shape, and no envelope spikes. Iterate Step 4 if not.

- [ ] **Step 6: Commit the recalibrated presets**

```bash
git add src/palubicki/configs/species/
git commit -m "configs: recalibrate 5 species presets for vigor-driven length (#20)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Regenerate goldens

**Files:**
- Modify: `tests/golden/data/*` (regenerated artifacts)

- [ ] **Step 1: Regenerate goldens after visual review**

Run: `.venv/bin/pytest tests/golden/ -q --update-goldens`
Expected: goldens written (tests skip with "golden written").

- [ ] **Step 2: Verify goldens are green without the flag**

Run: `.venv/bin/pytest tests/golden/ -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/golden/data/
git commit -m "tests/golden: regenerate goldens for vigor-driven length (#20)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Full-suite verification + acceptance check

**Files:** none (verification only)

- [ ] **Step 1: Run the entire suite (including slow)**

Run: `.venv/bin/pytest -q`
Expected: PASS

- [ ] **Step 2: Grep-confirm acceptance criteria**

Run:
```bash
grep -rn "math.floor\|floor(" src/palubicki/sim/bh.py
grep -rn "age_factor\|n_substeps_max\|re_perceive_per_substep\|_SubstepChain\|compute_target_with_age" src/palubicki/
```
Expected: no matches (all removed).

- [ ] **Step 3: Confirm emergent tapering in diagnostics for one species**

Run: `.venv/bin/python -m palubicki diagnose --species oak --seeds 1,2,3`
Expected: `internode_length_proximal_mean` > `internode_length_distal_mean`.

- [ ] **Step 4: Final commit (if any stragglers) and push**

```bash
git push
```

---

## Self-Review Notes

- **Spec coverage:** §1 length law → Task 3/5; §2 hysteresis → Task 2/5; §3 single pass → Task 5; §4 diameter → Task 6; §5 config → Task 4; §6 diagnostics → Task 7; §7 calibration → Task 9; intentional-breakage tests → Task 8; goldens → Task 10; acceptance → Task 11.
- **Type consistency:** `allocate` returns `dict[Bud, float]` (Task 1) and is consumed as float `v_by_bud` (Task 5). `shoot_extension(v_b, shoot_extension_max, vigor_ref)` signature is identical in Task 3 (def) and Task 5 (call). `_emit_node(..., v_b, ...)` and `_internode_target(bud, v_b, ...)` carry `v_b` consistently. `compute_radii(..., vigor_ref, vigor_diameter_gain)` matches Task 6 def and Task 6/9 calls.
- **Placeholder scan:** calibration values in Task 9 are explicitly empirical starting points (the only non-fixed values), consistent with the spec's "provisional defaults" framing.
