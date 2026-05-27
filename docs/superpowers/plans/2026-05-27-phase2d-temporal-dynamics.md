# Phase 2D — Temporal Dynamics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add progressive internode elongation (S-curve + age-factor), dynamic secondary growth, and idempotent dynamic sag.

**Architecture:** Each `Internode` records its `birth_iteration` and `length_target`; its `length` starts at 0 and ramps via a sigmoid toward target each iteration. `Node.position` stays fixed at its final geometric location at creation time; a new `Node.sag_offset` (recomputed from scratch each iteration) lets `apply_sag` stay idempotent, with `position + sag_offset` consumed by the geometry exporters. Pipe-model diameters are now recomputed each iteration. After the iteration loop, a finalization pass snaps `length = length_target`, then runs one last diameters + sag pass so the exported mesh always has the fully-grown geometry.

**Tech Stack:** Python 3.11+, pytest, numpy, dataclasses, frozen YAML configs.

---

## Working notes for the implementer

- **Activate the venv per Bash call.** The venv lives at `.venv/`; activation does *not* persist across Bash invocations. Always invoke pytest as `.venv/bin/pytest` (or `.venv/bin/python -m pytest`).
- **PoC mode.** No backward compat. Break YAML/API/goldens freely; do not add aliases or fallbacks.
- **Realism over paper-strict.** The full elongation/diameter/sag dynamics are the target — do not ship a minimal variant.
- The spec is at `docs/superpowers/specs/2026-05-27-phase2d-temporal-dynamics-design.md`. Section references below point into it.
- **Critical design point (spec 4.3, 4.6, 7.1):** node positions are placed at their FINAL geometric location at creation (`cur.position + d * target`). `Internode.length` represents the CURRENT effective length; it starts at 0 and grows toward `length_target` via sigmoid. During the sim there is a transient visual gap between parent and child node. The post-sim finalization snaps every `length = length_target`, then recomputes diameters + sag once for the exported geometry.
- The sag refactor is invasive: `tubes.py` and `leaves.py` must read `node.position + node.sag_offset` instead of `node.position`. Do the geometry refactor BEFORE wiring sag into the simulator loop, so the codebase stays in a working state at each commit.

---

## Task 1 — Add `ElongationConfig` dataclass + validation

**Files:**
- Modify: `src/palubicki/config.py` (insert `ElongationConfig` near other sub-configs around line 96; add field on `SimConfig` around line 55; extend `__post_init__` validation; no `_SECTION_TYPES` entry — `elongation` is nested under `sim`)
- Modify: `tests/test_config.py` (add unit tests for the new field defaults + validation paths)

- [ ] **Step 1: Write failing tests for `ElongationConfig` defaults and YAML round-trip**

Append to `tests/test_config.py`:

```python
def test_elongation_defaults_disabled():
    from palubicki.config import ElongationConfig
    cfg = ElongationConfig()
    assert cfg.enabled is False
    assert cfg.tau_iterations == 3.0
    assert cfg.age_factor_min == 0.5
    assert cfg.age_factor_decay == 0.5


def test_sim_config_has_elongation_subdataclass():
    from palubicki.config import SimConfig, ElongationConfig
    s = SimConfig()
    assert isinstance(s.elongation, ElongationConfig)
    assert s.elongation.enabled is False


def test_elongation_validation_tau_must_be_positive(tmp_path):
    from palubicki.config import ConfigError, load_config
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text("sim:\n  elongation:\n    enabled: true\n    tau_iterations: 0.0\n")
    with pytest.raises(ConfigError, match="tau_iterations"):
        load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")


def test_elongation_validation_age_factor_min_bounds(tmp_path):
    from palubicki.config import ConfigError, load_config
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text("sim:\n  elongation:\n    enabled: true\n    age_factor_min: 0.05\n")
    with pytest.raises(ConfigError, match="age_factor_min"):
        load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")


def test_elongation_validation_decay_must_be_nonnegative(tmp_path):
    from palubicki.config import ConfigError, load_config
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text("sim:\n  elongation:\n    enabled: true\n    age_factor_decay: -0.1\n")
    with pytest.raises(ConfigError, match="age_factor_decay"):
        load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")
```

Make sure `pytest` is imported at the top of the file (it already is — verify).

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `.venv/bin/pytest tests/test_config.py -k "elongation" -v`
Expected: ImportError / AttributeError — `ElongationConfig` does not exist yet.

- [ ] **Step 3: Add the `ElongationConfig` dataclass**

In `src/palubicki/config.py`, immediately after `SagConfig` (around line 119) and before `GeomConfig`, insert:

```python
@dataclass(frozen=True)
class ElongationConfig:
    """Progressive internode elongation (S-curve) + age_factor on target length.

    Each Internode records its birth_iteration and length_target at creation.
    Its effective ``length`` ramps from 0 toward ``length_target`` via a sigmoid
    centered at ``tau_iterations`` after birth (so length ≈ 0.5 * target at
    age=tau, ≈ 0.88 * target at age=2*tau).

    The target itself is scaled by an ``age_factor`` that decays exponentially
    with birth_iteration / max_iterations: internodes born early reach a long
    target; internodes born late reach a shorter one (capped by age_factor_min).
    """
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    tau_iterations: float = field(
        default=3.0, metadata={"ui": {"min": 0.5, "max": 10.0, "step": 0.1}}
    )
    age_factor_min: float = field(
        default=0.5, metadata={"ui": {"min": 0.1, "max": 1.0, "step": 0.05}}
    )
    age_factor_decay: float = field(
        default=0.5, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.1}}
    )
```

- [ ] **Step 4: Wire `elongation` field into `SimConfig`**

In `src/palubicki/config.py`, append the field at the end of `SimConfig` (after `internode_length_jitter`, around line 54):

```python
    elongation: ElongationConfig = field(default_factory=ElongationConfig)
```

- [ ] **Step 5: Add validation in `Config.__post_init__`**

In `src/palubicki/config.py`, inside `__post_init__` after the existing `sim` validation block (immediately after the `s.max_iterations` check around line 236), append:

```python
        e = self.sim.elongation
        if e.tau_iterations <= 0:
            raise ConfigError(f"sim.elongation.tau_iterations must be > 0, got {e.tau_iterations}")
        if not (0.1 <= e.age_factor_min <= 1.0):
            raise ConfigError(
                f"sim.elongation.age_factor_min must be in [0.1, 1.0], got {e.age_factor_min}"
            )
        if e.age_factor_decay < 0:
            raise ConfigError(
                f"sim.elongation.age_factor_decay must be >= 0, got {e.age_factor_decay}"
            )
```

- [ ] **Step 6: Teach the YAML loader to accept `sim.elongation` nested dict**

`SimConfig` already accepts arbitrary fields via `type_(**sec_data)`, but `ElongationConfig` is a nested dataclass, not a scalar. In `src/palubicki/config.py`, modify the `_SECTION_TYPES` loop (around lines 333-339) so that when building `SimConfig` we first convert a nested `elongation` dict into an `ElongationConfig`:

```python
    for name, type_ in _SECTION_TYPES.items():
        sec_data = data.get(name, {}) or {}
        allowed = {f.name for f in fields(type_)}
        unknown = set(sec_data) - allowed
        if unknown:
            raise ConfigError(f"unknown keys in section '{name}': {sorted(unknown)}")
        if name == "sim" and isinstance(sec_data.get("elongation"), dict):
            elong_data = sec_data["elongation"]
            elong_allowed = {f.name for f in fields(ElongationConfig)}
            elong_unknown = set(elong_data) - elong_allowed
            if elong_unknown:
                raise ConfigError(
                    f"unknown keys in section 'sim.elongation': {sorted(elong_unknown)}"
                )
            sec_data = {**sec_data, "elongation": ElongationConfig(**elong_data)}
        sections[name] = type_(**sec_data)
```

- [ ] **Step 7: Run the tests to confirm they pass**

Run: `.venv/bin/pytest tests/test_config.py -k "elongation" -v`
Expected: all 5 tests pass.

- [ ] **Step 8: Run the full config test suite to confirm no regressions**

Run: `.venv/bin/pytest tests/test_config.py tests/test_config_yaml.py tests/test_config_species.py -v`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
feat(config): add ElongationConfig dataclass under SimConfig

Adds enabled / tau_iterations / age_factor_min / age_factor_decay
fields with validation, plus YAML nested-dict loader support.
Disabled by default — no behavior change until presets opt in.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — Add `Node.sag_offset` (zero-init, no consumers yet)

**Files:**
- Modify: `src/palubicki/sim/tree.py:28-34` (add `sag_offset` field to `Node`)
- Modify: `tests/sim/test_tree.py` (add a default-init test)

- [ ] **Step 1: Write failing test for `Node.sag_offset` default**

Append to `tests/sim/test_tree.py`:

```python
def test_node_sag_offset_defaults_to_zero_vector():
    import numpy as np
    from palubicki.sim.tree import Node
    n = Node(position=np.array([1.0, 2.0, 3.0]))
    np.testing.assert_array_equal(n.sag_offset, np.zeros(3))
    assert n.sag_offset.dtype == np.float64
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/pytest tests/sim/test_tree.py -k "sag_offset" -v`
Expected: AttributeError — `sag_offset` does not exist.

- [ ] **Step 3: Add the field to `Node`**

In `src/palubicki/sim/tree.py`, modify the `Node` dataclass (lines 27-34):

```python
@dataclass(eq=False)
class Node:
    position: np.ndarray
    parent_internode: Optional["Internode"] = None
    children_internodes: list["Internode"] = field(default_factory=list)
    terminal_bud: Optional[Bud] = None
    lateral_buds: list[Bud] = field(default_factory=list)
    sag_offset: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
```

- [ ] **Step 4: Run the new test plus existing tree tests**

Run: `.venv/bin/pytest tests/sim/test_tree.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/tree.py tests/sim/test_tree.py
git commit -m "$(cat <<'EOF'
feat(tree): add Node.sag_offset (zero-init np.zeros(3))

Separate visual sag offset from topological position. No consumers yet;
follow-up tasks wire tubes/leaves/sag to use it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — Add `Internode.birth_iteration` + `length_target` fields

**Files:**
- Modify: `src/palubicki/sim/tree.py:36-55` (extend `Internode` dataclass)
- Modify: `tests/sim/test_tree.py` (default test)

- [ ] **Step 1: Write failing test**

Append to `tests/sim/test_tree.py`:

```python
def test_internode_has_birth_iteration_and_length_target_defaults():
    import numpy as np
    from palubicki.sim.tree import Internode, Node
    a = Node(position=np.zeros(3))
    b = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=a, child_node=b, length=1.0, is_main_axis=True)
    assert iod.birth_iteration == 0
    assert iod.length_target == 0.0


def test_internode_accepts_birth_iteration_and_length_target_kwargs():
    import numpy as np
    from palubicki.sim.tree import Internode, Node
    a = Node(position=np.zeros(3))
    b = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(
        parent_node=a, child_node=b, length=0.0, is_main_axis=True,
        birth_iteration=7, length_target=0.42,
    )
    assert iod.birth_iteration == 7
    assert iod.length_target == 0.42
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/pytest tests/sim/test_tree.py -k "birth_iteration or length_target" -v`
Expected: TypeError / AttributeError.

- [ ] **Step 3: Add the fields to `Internode`**

In `src/palubicki/sim/tree.py`, modify the `Internode` dataclass (lines 36-44):

```python
@dataclass(eq=False)
class Internode:
    parent_node: Node
    child_node: Node
    length: float                      # CURRENT effective length (mutated by elongation)
    is_main_axis: bool
    diameter: float = 0.0
    window: int = 5
    birth_iteration: int = 0
    length_target: float = 0.0
    quality_history: deque[float] = field(init=False)
```

(Leave `__post_init__`, `push_quality`, `average_quality` untouched.)

- [ ] **Step 4: Run the new tests + the full tree/sim suite**

Run: `.venv/bin/pytest tests/sim/test_tree.py tests/sim/test_simulator.py tests/sim/test_radii.py tests/sim/test_sag.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/tree.py tests/sim/test_tree.py
git commit -m "$(cat <<'EOF'
feat(tree): add Internode.birth_iteration and length_target

birth_iteration records when the internode was created; length_target
is the final length the sigmoid ramps toward. Both default to safe
zero-equivalents; simulator will populate them in a later task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — Create `sim/elongation.py` with `compute_target_with_age` (TDD)

**Files:**
- Create: `src/palubicki/sim/elongation.py`
- Create: `tests/sim/test_elongation.py`

- [ ] **Step 1: Write failing unit tests for `compute_target_with_age`**

Create `tests/sim/test_elongation.py`:

```python
"""Unit tests for sim/elongation.py — sigmoid ramp + age_factor."""
import math

import pytest

from palubicki.config import ElongationConfig


def test_compute_target_disabled_returns_base():
    from palubicki.sim.elongation import compute_target_with_age
    cfg = ElongationConfig(enabled=False)
    assert compute_target_with_age(0.18, birth_iteration=20, max_iterations=40, cfg=cfg) == 0.18


def test_compute_target_no_age_decay_returns_base():
    from palubicki.sim.elongation import compute_target_with_age
    cfg = ElongationConfig(enabled=True, age_factor_decay=0.0)
    assert compute_target_with_age(0.18, birth_iteration=20, max_iterations=40, cfg=cfg) == 0.18


def test_compute_target_at_birth_zero_is_full_base():
    from palubicki.sim.elongation import compute_target_with_age
    cfg = ElongationConfig(enabled=True, age_factor_min=0.5, age_factor_decay=0.7)
    assert compute_target_with_age(0.20, birth_iteration=0, max_iterations=40, cfg=cfg) == pytest.approx(0.20)


def test_compute_target_at_birth_max_equals_age_factor_min_times_base():
    from palubicki.sim.elongation import compute_target_with_age
    cfg = ElongationConfig(enabled=True, age_factor_min=0.4, age_factor_decay=1.0)
    got = compute_target_with_age(0.20, birth_iteration=40, max_iterations=40, cfg=cfg)
    assert got == pytest.approx(0.20 * 0.4, rel=1e-9)


def test_compute_target_monotonic_decay_with_birth():
    from palubicki.sim.elongation import compute_target_with_age
    cfg = ElongationConfig(enabled=True, age_factor_min=0.3, age_factor_decay=1.0)
    early = compute_target_with_age(0.20, birth_iteration=5, max_iterations=40, cfg=cfg)
    mid = compute_target_with_age(0.20, birth_iteration=20, max_iterations=40, cfg=cfg)
    late = compute_target_with_age(0.20, birth_iteration=35, max_iterations=40, cfg=cfg)
    assert early > mid > late


def test_compute_target_max_iterations_zero_returns_base():
    from palubicki.sim.elongation import compute_target_with_age
    cfg = ElongationConfig(enabled=True)
    assert compute_target_with_age(0.20, birth_iteration=0, max_iterations=0, cfg=cfg) == 0.20


def test_compute_target_birth_past_max_is_clamped():
    """birth_iteration > max_iterations should clamp to t_norm=1 (age_factor_min)."""
    from palubicki.sim.elongation import compute_target_with_age
    cfg = ElongationConfig(enabled=True, age_factor_min=0.4, age_factor_decay=1.0)
    clamped = compute_target_with_age(0.20, birth_iteration=99, max_iterations=40, cfg=cfg)
    at_max = compute_target_with_age(0.20, birth_iteration=40, max_iterations=40, cfg=cfg)
    assert clamped == pytest.approx(at_max)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/pytest tests/sim/test_elongation.py -v`
Expected: ModuleNotFoundError — `palubicki.sim.elongation` doesn't exist.

- [ ] **Step 3: Implement `sim/elongation.py` with `compute_target_with_age`**

Create `src/palubicki/sim/elongation.py`:

```python
"""Progressive internode elongation (S-curve) + age_factor on target length.

Spec: docs/superpowers/specs/2026-05-27-phase2d-temporal-dynamics-design.md (§4.3)

Design compromise: Node.position is fixed at creation to the *final* geometric
location (cur.position + d * length_target). The internode's effective ``length``
ramps from 0 toward ``length_target`` via a sigmoid. Consequence: during the
sim, the rendered tube is shorter than the distance between parent and child
node — visually a transient "gap" that closes as the internode matures. The
post-sim finalization (simulator.py) snaps every length = length_target so the
exported geometry is always fully grown.
"""
from __future__ import annotations

import math

from palubicki.config import ElongationConfig
from palubicki.sim.tree import Tree


def compute_target_with_age(
    base_length: float,
    birth_iteration: int,
    max_iterations: int,
    cfg: ElongationConfig,
) -> float:
    """target_length = base_length × age_factor(birth_iteration).

    age_factor decays exponentially from 1.0 (birth=0) to cfg.age_factor_min
    (birth=max_iterations), with curvature controlled by cfg.age_factor_decay.
    Returns ``base_length`` unchanged if elongation is disabled, decay is zero,
    or max_iterations is non-positive.
    """
    if not cfg.enabled or max_iterations <= 0:
        return base_length
    decay = cfg.age_factor_decay
    if decay <= 0:
        return base_length
    t_norm = min(1.0, birth_iteration / max_iterations)
    base = math.exp(-decay * t_norm)
    base_at_one = math.exp(-decay)
    factor = (
        cfg.age_factor_min
        + (1.0 - cfg.age_factor_min) * (base - base_at_one) / (1.0 - base_at_one)
    )
    return base_length * factor
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv/bin/pytest tests/sim/test_elongation.py -v`
Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/elongation.py tests/sim/test_elongation.py
git commit -m "$(cat <<'EOF'
feat(sim): elongation.compute_target_with_age — age-scaled target length

Hybrid age factor: target_length = base_length × age_factor(birth_iter),
where age_factor decays exponentially from 1.0 to age_factor_min over
[0, max_iterations]. Disabled / decay=0 / max_iter=0 all return base.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 — Add `sim/elongation.update_lengths` (TDD)

**Files:**
- Modify: `src/palubicki/sim/elongation.py`
- Modify: `tests/sim/test_elongation.py`

- [ ] **Step 1: Write failing tests for `update_lengths`**

Append to `tests/sim/test_elongation.py`:

```python
import numpy as np

from palubicki.sim.tree import Internode, Node, Tree


def _single_internode(birth: int, target: float) -> Tree:
    a = Node(position=np.zeros(3))
    b = Node(position=np.array([0.0, target, 0.0]))
    iod = Internode(
        parent_node=a, child_node=b, length=0.0, is_main_axis=True,
        birth_iteration=birth, length_target=target,
    )
    a.children_internodes.append(iod)
    b.parent_internode = iod
    return Tree(root=a, all_internodes=[iod])


def test_update_lengths_disabled_is_noop():
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=0, target=0.5)
    tree.all_internodes[0].length = 0.123
    update_lengths(tree, current_iteration=5, cfg=ElongationConfig(enabled=False))
    assert tree.all_internodes[0].length == 0.123


def test_update_lengths_at_birth_is_small_fraction_of_target():
    """elapsed=0 ⇒ sigma((-tau)/(tau/2)) = sigma(-2) ≈ 0.119, so length ≈ 0.119 * target."""
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=10, target=0.5)
    cfg = ElongationConfig(enabled=True, tau_iterations=3.0, age_factor_decay=0.0)
    update_lengths(tree, current_iteration=10, cfg=cfg)
    assert tree.all_internodes[0].length == pytest.approx(0.5 * (1.0 / (1.0 + math.exp(2.0))), rel=1e-9)


def test_update_lengths_at_tau_is_half_target():
    """elapsed=tau ⇒ sigma(0) = 0.5 ⇒ length = 0.5 * target."""
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=0, target=0.5)
    cfg = ElongationConfig(enabled=True, tau_iterations=3.0)
    update_lengths(tree, current_iteration=3, cfg=cfg)
    assert tree.all_internodes[0].length == pytest.approx(0.25, rel=1e-9)


def test_update_lengths_far_past_tau_approaches_target():
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=0, target=0.5)
    cfg = ElongationConfig(enabled=True, tau_iterations=3.0)
    update_lengths(tree, current_iteration=30, cfg=cfg)
    assert tree.all_internodes[0].length == pytest.approx(0.5, rel=1e-6)


def test_update_lengths_negative_elapsed_clamps_to_zero_elapsed():
    """If current_iteration < birth_iteration (shouldn't happen, but defensive),
    we use elapsed=0 ⇒ same as at-birth behavior."""
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=20, target=0.5)
    cfg = ElongationConfig(enabled=True, tau_iterations=3.0)
    update_lengths(tree, current_iteration=10, cfg=cfg)
    assert tree.all_internodes[0].length == pytest.approx(0.5 * (1.0 / (1.0 + math.exp(2.0))), rel=1e-9)


def test_update_lengths_zero_tau_is_noop():
    """tau<=0 is an invalid runtime state but the function must not crash."""
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=0, target=0.5)
    tree.all_internodes[0].length = 0.123
    update_lengths(tree, current_iteration=5, cfg=ElongationConfig(enabled=True, tau_iterations=0.0))
    assert tree.all_internodes[0].length == 0.123
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/pytest tests/sim/test_elongation.py -k "update_lengths" -v`
Expected: ImportError on `update_lengths`.

- [ ] **Step 3: Implement `update_lengths`**

Append to `src/palubicki/sim/elongation.py`:

```python
def update_lengths(tree: Tree, current_iteration: int, cfg: ElongationConfig) -> None:
    """Recompute Internode.length in-place via sigmoid ramp.

    length(t) = length_target * sigmoid((elapsed - tau) / (tau/2))
    where elapsed = max(0, current_iteration - birth_iteration).

    No-op if cfg.enabled is False or cfg.tau_iterations <= 0.
    """
    if not cfg.enabled:
        return
    tau = cfg.tau_iterations
    if tau <= 0:
        return
    half_tau = tau / 2.0
    for iod in tree.all_internodes:
        elapsed = max(0, current_iteration - iod.birth_iteration)
        x = (elapsed - tau) / half_tau
        sigma = 1.0 / (1.0 + math.exp(-x))
        iod.length = iod.length_target * sigma
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv/bin/pytest tests/sim/test_elongation.py -v`
Expected: all (now 13) tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/elongation.py tests/sim/test_elongation.py
git commit -m "$(cat <<'EOF'
feat(sim): elongation.update_lengths — per-iteration sigmoid ramp

length = length_target * sigmoid((elapsed - tau) / (tau/2)).
Disabled / tau<=0 are no-ops. Negative elapsed clamps to 0.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6 — Extract `update_diameters_incremental` in `sim/radii.py` (idempotent)

**Files:**
- Modify: `src/palubicki/sim/radii.py`
- Modify: `tests/sim/test_radii.py`

- [ ] **Step 1: Write failing tests for the new entry point + idempotence**

Append to `tests/sim/test_radii.py`:

```python
from palubicki.config import GeomConfig
from palubicki.sim.radii import update_diameters_incremental


def test_update_diameters_incremental_matches_compute_radii():
    """update_diameters_incremental is the same pipe model walk, wrapped to
    accept a GeomConfig."""
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

    cfg = GeomConfig(r_tip=0.1, pipe_exponent=2.0)
    update_diameters_incremental(tree, cfg=cfg)
    expected_parent = 2.0 * (0.1**2 + 0.1**2) ** 0.5

    assert iod_mid_left.diameter == 0.2
    assert iod_mid_right.diameter == 0.2
    assert abs(iod_root_mid.diameter - expected_parent) < 1e-9


def test_update_diameters_incremental_idempotent():
    """Calling twice on an unchanged tree yields identical diameters."""
    root = Node(position=np.zeros(3))
    tip = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=root, child_node=tip, length=1.0, is_main_axis=True)
    root.children_internodes.append(iod)
    tree = Tree(root=root, all_internodes=[iod])

    cfg = GeomConfig(r_tip=0.01, pipe_exponent=2.0)
    update_diameters_incremental(tree, cfg=cfg)
    first = iod.diameter
    update_diameters_incremental(tree, cfg=cfg)
    assert iod.diameter == first
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/pytest tests/sim/test_radii.py -k "incremental" -v`
Expected: ImportError on `update_diameters_incremental`.

- [ ] **Step 3: Add the wrapper to `sim/radii.py`**

In `src/palubicki/sim/radii.py`, append (keep `compute_radii` and `_set_radius_iterative` exactly as-is for now — they remain callable for legacy code paths in `sim/light.py`):

```python
from palubicki.config import GeomConfig  # noqa: E402


def update_diameters_incremental(tree: Tree, cfg: GeomConfig) -> None:
    """Pipe-model diameter walk, intended to be called every iteration.

    Mathematically identical to ``compute_radii(tree, r_tip=cfg.r_tip,
    exponent=cfg.pipe_exponent)``; the wrapper exists so the simulator loop
    sees a GeomConfig-shaped API. At the final iteration this produces the
    same result as the old post-sim ``compute_radii`` call — but intermediate
    iterations are now visible, so sag can read up-to-date diameters.
    """
    compute_radii(tree, r_tip=cfg.r_tip, exponent=cfg.pipe_exponent)
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv/bin/pytest tests/sim/test_radii.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/radii.py tests/sim/test_radii.py
git commit -m "$(cat <<'EOF'
feat(radii): add update_diameters_incremental (per-iteration entry point)

Thin GeomConfig wrapper around compute_radii so the simulator loop can
recompute pipe-model diameters every iteration. Old compute_radii stays
for sim/light.py's mid-iteration rebuilds.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7 — Refactor `sim/sag.py` to write `Node.sag_offset` (idempotent)

**Files:**
- Modify: `src/palubicki/sim/sag.py` (rewrite `apply_sag` body + `_rotate_subtree_around` to operate on sag_offset rather than position)
- Modify: `tests/sim/test_sag.py` (existing tests must still pass after we update assertions to look at `position + sag_offset`)

### Design notes

- `apply_sag` MUST reset every `Node.sag_offset` to zero at the start, then walk the tree and accumulate per-node offsets — this is what makes a second call idempotent.
- The algorithm is unchanged conceptually: walk pre-order, compute bend per internode based on `length × diameter²` load, build a Rodrigues rotation, apply it to all descendants. The only change is that "apply" means "rotate the current `(position + sag_offset)` vector around the pivot's bent position" and store the *delta* back into each descendant's `sag_offset`.
- Concretely: each Node has a `bent_position = position + sag_offset`. The pivot's bent_position is `parent.position + parent.sag_offset`. Rotating a descendant's bent_position around that pivot gives a new bent_position; the new `sag_offset = new_bent_position - position`.
- Bud positions/directions are visual decorations consumed by leaves; since leaves will read `node.position + node.sag_offset` (Task 9), we no longer need to rotate bud positions at all. **Remove the bud-rotation code** in `_rotate_subtree_around`. (The leaves placement function uses `bud.position` only for the apex-bud sites; we'll change that in Task 9 to use the node's bent position instead, so this is internally consistent.)

- [ ] **Step 1: Update existing tests to read `position + sag_offset`**

In `tests/sim/test_sag.py`, edit every assertion that currently reads `<node>.position` after `apply_sag` to instead read `<node>.position + <node>.sag_offset`. Concretely:

- `test_horizontal_branch_bends_downward`:

```python
    tip = tree.root.children_internodes[0].child_node.children_internodes[0].child_node.children_internodes[0].child_node
    tip_bent = tip.position + tip.sag_offset
    assert tip_bent[1] < 0.0
    # Bent positions still preserve the original internode length (rigid-body rotation).
    for iod in tree.all_internodes:
        p_bent = iod.parent_node.position + iod.parent_node.sag_offset
        c_bent = iod.child_node.position + iod.child_node.sag_offset
        assert np.linalg.norm(c_bent - p_bent) == pytest.approx(iod.length, rel=1e-9)
```

- `test_vertical_branch_does_not_sag`:

```python
    tip = tree.root.children_internodes[0].child_node.children_internodes[0].child_node
    np.testing.assert_allclose(tip.position + tip.sag_offset, np.array([0.0, 2.0, 0.0]), atol=1e-12)
```

- `test_rigid_axis_order_protects_trunk`:

```python
    child = tree.root.children_internodes[0].child_node
    np.testing.assert_array_equal(child.position + child.sag_offset, np.array([1.0, 0.0, 0.0]))
```

- `test_single_segment_lateral_droops`:

```python
    assert (lateral.position + lateral.sag_offset)[1] < 0.99
```

- `test_near_vertical_branch_sags_less_than_horizontal`:

```python
    horiz_child = horiz.root.children_internodes[0].child_node
    horiz_drop = -float((horiz_child.position + horiz_child.sag_offset)[1])
    ...
    near_child = near.root.children_internodes[0].child_node
    near_tip = near_child.position + near_child.sag_offset
    near_drop = float(near_vert_dir[1] - near_tip[1])
```

- `test_max_bend_caps_thin_tip_runaway`:

```python
    p0_bent = tree.root.position + tree.root.sag_offset
    child = tree.root.children_internodes[0].child_node
    p1_bent = child.position + child.sag_offset
    seg1 = p1_bent - p0_bent
    angle_deg = math.degrees(math.asin(-seg1[1] / np.linalg.norm(seg1)))
    assert angle_deg <= 10.0 + 1e-6
```

- `test_sag_disabled_is_noop`:

```python
    apply_sag(tree, SagConfig(enabled=False, k=10.0))
    child = tree.root.children_internodes[0].child_node
    np.testing.assert_array_equal(child.position + child.sag_offset, before)
```

- [ ] **Step 2: Add two NEW tests for idempotence + position separation**

Append to `tests/sim/test_sag.py`:

```python
def test_apply_sag_idempotent():
    """Calling apply_sag twice gives the same result as calling it once."""
    positions = [
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([2.0, 0.0, 0.0]),
    ]
    tree = _chain_tree(positions, [0.05, 0.05])
    cfg = SagConfig(enabled=True, k=0.5, max_bend_deg=30.0, rigid_axis_order=0)
    apply_sag(tree, cfg)
    once = [n.sag_offset.copy() for n in (
        tree.root,
        tree.root.children_internodes[0].child_node,
        tree.root.children_internodes[0].child_node.children_internodes[0].child_node,
    )]
    apply_sag(tree, cfg)
    twice = [n.sag_offset for n in (
        tree.root,
        tree.root.children_internodes[0].child_node,
        tree.root.children_internodes[0].child_node.children_internodes[0].child_node,
    )]
    for a, b in zip(once, twice):
        np.testing.assert_allclose(a, b, atol=1e-12)


def test_sag_offset_separate_from_position():
    """Node.position must be untouched by apply_sag — only sag_offset moves."""
    positions = [
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
    ]
    tree = _chain_tree(positions, [0.05])
    original_root = tree.root.position.copy()
    original_child = tree.root.children_internodes[0].child_node.position.copy()
    apply_sag(tree, SagConfig(enabled=True, k=0.5, max_bend_deg=30.0, rigid_axis_order=0))
    np.testing.assert_array_equal(tree.root.position, original_root)
    np.testing.assert_array_equal(tree.root.children_internodes[0].child_node.position, original_child)
    # The child got a non-zero sag_offset though.
    assert np.linalg.norm(tree.root.children_internodes[0].child_node.sag_offset) > 0.0
```

- [ ] **Step 3: Run the tests to confirm they fail**

Run: `.venv/bin/pytest tests/sim/test_sag.py -v`
Expected: most existing tests fail because `apply_sag` still mutates `position`, and the new idempotence test fails because a second call doubles the bend.

- [ ] **Step 4: Rewrite `apply_sag` + helpers to operate on sag_offset**

Replace the body of `src/palubicki/sim/sag.py` with this. Keep the module docstring; rewrite from line 37 (`def apply_sag`) downward:

```python
def apply_sag(tree: Tree, cfg: SagConfig) -> None:
    """Idempotent: recompute sag_offset for every Node from scratch.

    Walks the tree pre-order; for each internode computes a bend angle from
    load (length × diameter² × density proxy) and applies the resulting
    rotation to all descendants' *bent* positions (position + sag_offset).
    The result is written back into each descendant's sag_offset.

    Bud positions/directions are NOT rotated — leaves read node bent positions
    directly (geom/leaves.py).

    Requires diameters to be set on all internodes (call update_diameters_incremental
    or compute_radii first).
    """
    # Always reset: a disabled sag must clear any previous offsets, and an
    # enabled sag must compute from scratch (idempotence).
    _reset_offsets(tree)
    if not cfg.enabled:
        return

    g = np.asarray(cfg.direction, dtype=np.float64)
    g_norm = float(np.linalg.norm(g))
    if g_norm < 1e-12:
        return
    g = g / g_norm

    max_bend_rad = math.radians(float(cfg.max_bend_deg))
    rigid_order = int(cfg.rigid_axis_order)
    k = float(cfg.k)

    load_below = _compute_load_below(tree)

    stack: list[tuple[Node, int]] = [(tree.root, 0)]
    while stack:
        parent, parent_order = stack.pop()
        parent_bent = parent.position + parent.sag_offset
        for iod in parent.children_internodes:
            child = iod.child_node
            child_order = parent_order if iod.is_main_axis else parent_order + 1

            if child_order < rigid_order:
                stack.append((child, child_order))
                continue

            child_bent = child.position + child.sag_offset
            old_vec = child_bent - parent_bent
            seg_len = float(np.linalg.norm(old_vec))
            if seg_len < 1e-12:
                stack.append((child, child_order))
                continue
            direction = old_vec / seg_len

            cross = np.cross(direction, g)
            sin_theta = float(np.linalg.norm(cross))
            if sin_theta < 1e-9:
                stack.append((child, child_order))
                continue
            axis = cross / sin_theta

            diameter = max(float(iod.diameter), 1e-4)
            r_iod = 0.5 * float(iod.diameter)
            iod_vol = math.pi * r_iod * r_iod * float(iod.length)
            load = iod_vol + float(load_below.get(id(child), 0.0))
            bend = k * load * sin_theta / (diameter * diameter)
            if bend > max_bend_rad:
                bend = max_bend_rad
            if bend <= 0.0:
                stack.append((child, child_order))
                continue

            R = _rodrigues(axis, bend)
            _rotate_subtree_offsets(child, R, parent_bent)
            stack.append((child, child_order))


def _reset_offsets(tree: Tree) -> None:
    """Zero every Node.sag_offset in the tree (iterative DFS)."""
    stack: list[Node] = [tree.root]
    while stack:
        n = stack.pop()
        n.sag_offset = np.zeros(3, dtype=np.float64)
        for iod in n.children_internodes:
            stack.append(iod.child_node)


def _compute_load_below(tree: Tree) -> dict[int, float]:
    """Wood volume in each node's subtree (sum of every internode growing out
    of it, recursively). Excludes the iod leading INTO the node — callers add
    that contribution inline. Keyed by id(node). Iterative post-order."""
    order: list[Node] = []
    stack: list[Node] = [tree.root]
    while stack:
        n = stack.pop()
        order.append(n)
        for iod in n.children_internodes:
            stack.append(iod.child_node)

    load: dict[int, float] = {}
    for n in reversed(order):
        total = 0.0
        for iod in n.children_internodes:
            child_load = load.get(id(iod.child_node), 0.0)
            r = 0.5 * float(iod.diameter)
            iod_vol = math.pi * r * r * float(iod.length)
            total += iod_vol + child_load
        load[id(n)] = total
    return load


def _rotate_subtree_offsets(
    root: Node, R: np.ndarray, pivot: np.ndarray,
) -> None:
    """For every node in the subtree rooted at ``root`` (including ``root``),
    rotate its current bent position (position + sag_offset) by R around
    ``pivot`` and store the resulting offset back into sag_offset.

    Bud positions/directions are NOT touched — leaves read node bent positions
    in geom/leaves.py.
    """
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        bent = node.position + node.sag_offset
        new_bent = R @ (bent - pivot) + pivot
        node.sag_offset = new_bent - node.position
        for iod in node.children_internodes:
            stack.append(iod.child_node)


def _rodrigues(axis: np.ndarray, angle: float) -> np.ndarray:
    """3×3 rotation matrix around unit ``axis`` by ``angle`` radians."""
    c = math.cos(angle)
    s = math.sin(angle)
    one_c = 1.0 - c
    x, y, z = float(axis[0]), float(axis[1]), float(axis[2])
    return np.array([
        [c + x * x * one_c,     x * y * one_c - z * s, x * z * one_c + y * s],
        [y * x * one_c + z * s, c + y * y * one_c,     y * z * one_c - x * s],
        [z * x * one_c - y * s, z * y * one_c + x * s, c + z * z * one_c    ],
    ], dtype=np.float64)
```

Delete the old `_rotate_subtree_around` (replaced by `_rotate_subtree_offsets`).

- [ ] **Step 5: Run the sag tests to confirm they pass**

Run: `.venv/bin/pytest tests/sim/test_sag.py -v`
Expected: all green (the 7 original tests with updated assertions + the 2 new idempotence/separation tests).

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/sag.py tests/sim/test_sag.py
git commit -m "$(cat <<'EOF'
refactor(sag): apply_sag writes Node.sag_offset, idempotent

Node.position is now untouched; sag is a pure visual offset. Each call
resets offsets to zero before walking, so calling twice yields the same
result and we can run sag mid-simulation safely. Bud positions are no
longer rotated — leaves consume node bent positions in a follow-up task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8 — Update `geom/tubes.py` to consume `position + sag_offset`

**Files:**
- Modify: `src/palubicki/geom/tubes.py` (every read of `node.position` becomes `node.position + node.sag_offset`)
- Modify: `tests/geom/test_tubes.py` (add a sag-aware test)

- [ ] **Step 1: Write a failing test that verifies tube vertices follow sag_offset**

Append to `tests/geom/test_tubes.py` (check the top of the file for existing imports — most likely it already imports `Node`, `Internode`, `Tree`, `numpy as np`; copy whatever pattern is used):

```python
def test_build_bark_primitive_reads_sag_offset():
    """When a node has a non-zero sag_offset, the tube vertices should reflect
    the bent position (position + sag_offset), not the raw topological position."""
    import numpy as np
    from palubicki.geom.mesh import Material
    from palubicki.geom.tubes import build_bark_primitive
    from palubicki.sim.tree import Internode, Node, Tree

    root = Node(position=np.zeros(3))
    tip = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=root, child_node=tip, length=1.0,
                    is_main_axis=True, diameter=0.10)
    root.children_internodes.append(iod)
    tip.parent_internode = iod
    tree = Tree(root=root, all_internodes=[iod])

    mat = Material(name="bark", base_color=(0.3, 0.2, 0.1, 1.0),
                   metallic=0.0, roughness=1.0)
    prim_baseline = build_bark_primitive(tree, ring_sides=6, material=mat)
    baseline_max_y = float(prim_baseline.positions[:, 1].max())

    # Apply a downward sag_offset of -0.5 to the tip and rebuild.
    tip.sag_offset = np.array([0.0, -0.5, 0.0])
    prim_bent = build_bark_primitive(tree, ring_sides=6, material=mat)
    bent_max_y = float(prim_bent.positions[:, 1].max())

    # The tube tip should have moved downward.
    assert bent_max_y < baseline_max_y - 0.3
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/pytest tests/geom/test_tubes.py -k "sag_offset" -v`
Expected: FAIL — vertices ignore sag_offset.

- [ ] **Step 3: Update `_collect_chains` to read bent positions**

In `src/palubicki/geom/tubes.py`, modify the body of `_emit_chain_tube` so it reads bent positions instead of raw positions. Change line 140 from:

```python
    node_positions = np.asarray([n.position for n in chain.nodes], dtype=np.float64)  # (N, 3)
```

to:

```python
    node_positions = np.asarray(
        [n.position + n.sag_offset for n in chain.nodes], dtype=np.float64
    )  # (N, 3)  — bent positions; sag_offset is np.zeros(3) when sag disabled
```

- [ ] **Step 4: Update `_emit_root_cap` similarly**

In `src/palubicki/geom/tubes.py`, change line 212:

```python
    center = chain.nodes[0].position.astype(np.float64)
```

to:

```python
    center = (chain.nodes[0].position + chain.nodes[0].sag_offset).astype(np.float64)
```

- [ ] **Step 5: Run the tube tests to confirm they pass**

Run: `.venv/bin/pytest tests/geom/test_tubes.py -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/geom/tubes.py tests/geom/test_tubes.py
git commit -m "$(cat <<'EOF'
refactor(tubes): consume position + sag_offset for bark vertices

Tube and root-cap geometry now reads each node's bent position
(position + sag_offset). When sag is disabled, sag_offset is zeros(3)
and behavior is unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9 — Update `geom/leaves.py` to consume `position + sag_offset`

**Files:**
- Modify: `src/palubicki/geom/leaves.py` (the apex-bud branch and the parent-internode walk both read raw positions; switch to bent positions)
- Modify: `tests/geom/test_leaves.py` (add a sag-aware test)

### Notes on the change

- Currently `_collect_foliage_sites` does two things:
  1. Loop over `tree.active_buds`, emit one site per active bud where the bud's parent node has no children — uses `bud.position` and `bud.direction`. Since we stopped rotating buds in Task 7, `bud.position` is now equal to the parent node's raw `position` (the bud was initialized with `new_pos.copy()`). We must replace `bud.position` with `bud.parent_node.position + bud.parent_node.sag_offset`.
  2. Walk back through `parent_internode.parent_node` chains, computing the segment direction from `current.position - current.parent_internode.parent_node.position`. Replace both reads with `<node>.position + <node>.sag_offset`.

- [ ] **Step 1: Write a failing test**

Append to `tests/geom/test_leaves.py`:

```python
def test_leaves_follow_sag_offset_at_apex():
    """When the apex node has a downward sag_offset, leaves should be emitted
    at the bent position, not the raw position."""
    import numpy as np
    from palubicki.geom.leaves import build_leaves_primitive
    from palubicki.geom.mesh import Material
    from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree

    root = Node(position=np.zeros(3))
    tip = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=root, child_node=tip, length=1.0,
                    is_main_axis=True, diameter=0.05)
    root.children_internodes.append(iod)
    tip.parent_internode = iod
    tree = Tree(root=root, all_internodes=[iod])
    bud = Bud(position=tip.position.copy(), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=tip)
    tip.terminal_bud = bud
    tree.active_buds = [bud]

    mat = Material(name="leaf", base_color=(0.4, 0.6, 0.2, 1.0),
                   metallic=0.0, roughness=1.0)

    prim_baseline = build_leaves_primitive(tree, leaf_size=0.1, material=mat,
                                           foliage_depth=1)
    baseline_y_mean = float(prim_baseline.positions[:, 1].mean())

    tip.sag_offset = np.array([0.0, -0.5, 0.0])
    prim_bent = build_leaves_primitive(tree, leaf_size=0.1, material=mat,
                                       foliage_depth=1)
    bent_y_mean = float(prim_bent.positions[:, 1].mean())

    assert bent_y_mean < baseline_y_mean - 0.4
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/pytest tests/geom/test_leaves.py -k "follow_sag_offset" -v`
Expected: FAIL.

- [ ] **Step 3: Update `_collect_foliage_sites` to use bent positions**

In `src/palubicki/geom/leaves.py`, rewrite `_collect_foliage_sites`. Replace lines 80-92 (the apex loop) with:

```python
    sites: list[tuple[np.ndarray, np.ndarray]] = []
    apex_nodes: list[Node] = []
    for bud in tree.active_buds:
        if bud.state == BudState.DEAD:
            continue
        node = bud.parent_node
        if len(node.children_internodes) != 0:
            continue
        # Site position = node's bent position (apex tip after sag). Direction
        # stays from the bud (still topological), since it controls leaf
        # orientation, not placement.
        site_pos = np.asarray(node.position + node.sag_offset, dtype=np.float64)
        sites.append((site_pos, np.asarray(bud.direction, dtype=np.float64)))
        apex_nodes.append(node)
```

Replace lines 100-115 (the depth>1 backwalk) with:

```python
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
                parent_node = current.parent_internode.parent_node
                cur_bent = current.position + current.sag_offset
                par_bent = parent_node.position + parent_node.sag_offset
                seg = cur_bent - par_bent
                seg_norm = float(np.linalg.norm(seg))
                direction = seg / seg_norm if seg_norm > 1e-12 else np.array([0.0, 1.0, 0.0])
            else:
                direction = np.array([0.0, 1.0, 0.0])
            site_pos = np.asarray(current.position + current.sag_offset, dtype=np.float64)
            sites.append((site_pos, direction))
```

- [ ] **Step 4: Run the leaves tests to confirm they pass**

Run: `.venv/bin/pytest tests/geom/test_leaves.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/geom/leaves.py tests/geom/test_leaves.py
git commit -m "$(cat <<'EOF'
refactor(leaves): consume node bent positions (position + sag_offset)

Foliage sites now use the node's bent position rather than the bud's
raw position (which sag no longer touches). Backward-walk for
foliage_depth > 1 also reads bent positions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10 — Capture `birth_iteration` + `length_target` on internode creation in simulator

**Files:**
- Modify: `src/palubicki/sim/simulator.py` (the `Internode` construction site at lines 209-218; also place `new_pos` at the *target* position, not the elongation-current one)
- Modify: `tests/sim/test_simulator.py` (verify the captured fields)

### Critical design point (spec §4.6, Site A)

- `length` (the value passed to the simulator's per-internode jitter logic, line 186-193) is the **base** length — call it `base_length`.
- Compute `target = compute_target_with_age(base_length, birth_iteration=iteration, max_iterations=cfg.sim.max_iterations, cfg=cfg.sim.elongation)`.
- **`new_pos = cur.position + d * target`** — the node is placed at the final geometric location. This is the critical compromise: the node sits where the fully-grown tube tip would be.
- Construct the internode with `length = (0.0 if cfg.sim.elongation.enabled else target)` and always set `length_target=target`, `birth_iteration=iteration`.

- [ ] **Step 1: Write a failing test**

Append to `tests/sim/test_simulator.py`:

```python
def test_internodes_record_birth_iteration_and_length_target(tmp_path):
    """Every created internode must carry the iteration it was born in and
    its full target length."""
    from palubicki.config import (
        Config, ElongationConfig, EnvelopeConfig, GeomConfig, LightConfig,
        PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    cfg = Config(
        envelope=EnvelopeConfig(rx=2.0, ry=2.0, rz=2.0, marker_count=500),
        sim=SimConfig(max_iterations=5,
                      elongation=ElongationConfig(enabled=True, tau_iterations=2.0)),
        tropism=TropismConfig(w_orthotropy_main=0.3),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        output=tmp_path / "tree.glb",
        seed=42,
    )
    tree = simulate(cfg)
    assert len(tree.all_internodes) > 0
    for iod in tree.all_internodes:
        assert 0 <= iod.birth_iteration < cfg.sim.max_iterations
        assert iod.length_target > 0.0
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/pytest tests/sim/test_simulator.py -k "birth_iteration_and_length_target" -v`
Expected: FAIL — `length_target` is still 0.0 (the field default).

- [ ] **Step 3: Modify the simulator's internode creation site**

In `src/palubicki/sim/simulator.py`, replace lines 186-218 (the block from `length = cfg.sim.internode_length` through the `tree.all_internodes.append(iod)` line, inclusive) with:

```python
                base_length = cfg.sim.internode_length
                if cfg.sim.internode_length_jitter > 0:
                    ss = np.random.SeedSequence(
                        [cfg.seed, _ILEN_SALT, iteration, state.node_index]
                    )
                    rng = np.random.default_rng(ss.generate_state(1)[0])
                    factor = max(0.5, min(1.5, rng.normal(1.0, cfg.sim.internode_length_jitter)))
                    base_length = cfg.sim.internode_length * factor
                from palubicki.sim.elongation import compute_target_with_age
                target = compute_target_with_age(
                    base_length=base_length,
                    birth_iteration=iteration,
                    max_iterations=cfg.sim.max_iterations,
                    cfg=cfg.sim.elongation,
                )
                # Node placed at the FINAL geometric position. During the sim,
                # Internode.length ramps from 0 toward target (a transient
                # visual gap between parent and child node closes by the
                # finalization snap at the end of simulate()).
                new_pos = cur.position + d * target

                # V3: obstacle blocking
                if forest.obstacles:
                    from palubicki.sim.obstacles import segment_blocked, any_contains
                    if segment_blocked(cur.position, new_pos, forest.obstacles):
                        cur.state = BudState.DORMANT
                        new_active.append(cur)
                        chain.done = True
                        continue
                    if any_contains(new_pos, forest.obstacles):
                        cur.state = BudState.DEAD
                        chain.done = True
                        continue

                new_node = Node(position=new_pos)
                iod = Internode(
                    parent_node=cur.parent_node,
                    child_node=new_node,
                    length=(0.0 if cfg.sim.elongation.enabled else target),
                    is_main_axis=is_main,
                    window=cfg.shedding.window,
                    birth_iteration=iteration,
                    length_target=target,
                )
                cur.parent_node.children_internodes.append(iod)
                new_node.parent_internode = iod
                tree.all_internodes.append(iod)
```

(Lift the `from palubicki.sim.elongation import compute_target_with_age` to the top of the file along with the other imports, then remove the inline import. Keep this small refactor in the same step.)

Move the import: at the top of `src/palubicki/sim/simulator.py`, after the existing imports, add:

```python
from palubicki.sim.elongation import compute_target_with_age, update_lengths
```

(`update_lengths` will be wired in Task 11; importing now is harmless and keeps imports tidy.)

- [ ] **Step 4: Run the new test + the full simulator suite**

Run: `.venv/bin/pytest tests/sim/test_simulator.py -v`
Expected: the new test passes. Existing simulator tests may now show subtle shape drift because new_pos is now `d * target` (= `d * base_length` when elongation is disabled), which is bit-equivalent to the old `d * length` — so behavior should match exactly when `elongation.enabled=False`. If a test fails, double-check the equivalence.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/simulator.py tests/sim/test_simulator.py
git commit -m "$(cat <<'EOF'
feat(simulator): capture birth_iteration + length_target on internode creation

Compute target_length via age_factor at birth; place new node at final
geometric position (cur + d * target). When elongation is enabled,
Internode.length starts at 0 and will ramp via update_lengths each
iteration. When disabled, length == target == base * jitter (legacy).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11 — Call `update_lengths` / `update_diameters_incremental` / `apply_sag` each iteration

**Files:**
- Modify: `src/palubicki/sim/simulator.py` (add a per-iteration dynamics block at the end of `_iteration_step`, just after `shed_low_quality`)
- Modify: `tests/sim/test_simulator.py` (verify lengths ramp during the loop)

- [ ] **Step 1: Write a failing test**

Append to `tests/sim/test_simulator.py`:

```python
def test_internodes_have_progressive_lengths_when_elongation_enabled(tmp_path):
    """At the END of simulate(), young internodes (born late) should have
    length strictly less than length_target — they didn't have time to ramp."""
    from palubicki.config import (
        Config, ElongationConfig, EnvelopeConfig, GeomConfig, LightConfig,
        PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    cfg = Config(
        envelope=EnvelopeConfig(rx=2.0, ry=2.0, rz=2.0, marker_count=500),
        sim=SimConfig(max_iterations=8,
                      elongation=ElongationConfig(enabled=True, tau_iterations=3.0,
                                                  age_factor_decay=0.0)),
        tropism=TropismConfig(w_orthotropy_main=0.3),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        output=tmp_path / "tree.glb",
        seed=42,
    )
    # NOTE: this test inspects mid-simulation state. We run with the new per-
    # iteration update_lengths call but BEFORE the finalization snap (Task 12).
    # After Task 12 lands, finalization will set length == length_target for
    # all internodes, so this test will be rewritten / moved to inspect
    # iteration-N state via a custom hook. For now (after Task 11 only),
    # young internodes should ramp toward but not reach target.
    tree = simulate(cfg)
    # Group internodes by birth_iteration. The latest birth cohort should
    # show length < length_target on at least one internode.
    by_birth = {}
    for iod in tree.all_internodes:
        by_birth.setdefault(iod.birth_iteration, []).append(iod)
    latest_birth = max(by_birth.keys())
    assert any(iod.length < iod.length_target * 0.99 for iod in by_birth[latest_birth])
```

(Yes, this test will need to be replaced in Task 12 — the comment above explains why. Keeping it here forces us to verify the per-iteration update_lengths actually runs and produces non-final lengths before finalization.)

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/pytest tests/sim/test_simulator.py -k "progressive_lengths" -v`
Expected: FAIL — current simulator never ramps `length`; it stays at 0 when elongation is enabled (set in Task 10).

- [ ] **Step 3: Wire per-iteration dynamics into `_iteration_step`**

In `src/palubicki/sim/simulator.py`, locate the end of `_iteration_step` — the existing block:

```python
    for tree in forest.trees:
        shed_low_quality(tree, cfg=cfg.shedding)

    logger.info(...)
    return nodes_created_this_step
```

Replace it with:

```python
    for tree in forest.trees:
        shed_low_quality(tree, cfg=cfg.shedding)

    # --- Phase 2D: per-iteration temporal dynamics ---
    # Order matters: lengths first (sag reads load = length × diameter²),
    # diameters next (sag reads diameter), sag last.
    if cfg.sim.elongation.enabled:
        for tree in forest.trees:
            update_lengths(tree, current_iteration=iteration, cfg=cfg.sim.elongation)
    for tree in forest.trees:
        update_diameters_incremental(tree, cfg=cfg.geom)
    if cfg.sag.enabled:
        for tree in forest.trees:
            apply_sag(tree, cfg=cfg.sag)

    logger.info(
        "[%.1fs] sim/iter %d/%d  trees=%d  nodes_created=%d",
        time.time() - t0,
        iteration + 1, cfg.sim.max_iterations,
        len(forest.trees),
        nodes_created_this_step,
    )
    return nodes_created_this_step
```

Also add the imports at the top of `src/palubicki/sim/simulator.py` (in the import block, after the elongation import added in Task 10):

```python
from palubicki.sim.radii import update_diameters_incremental
from palubicki.sim.sag import apply_sag
```

- [ ] **Step 4: Run the new test to confirm it passes**

Run: `.venv/bin/pytest tests/sim/test_simulator.py -k "progressive_lengths" -v`
Expected: PASS.

- [ ] **Step 5: Run the broader sim suite — light, shedding, forest — to confirm no regressions**

Run: `.venv/bin/pytest tests/sim/ -v`
Expected: all green. (Sag and diameters now run every iteration, but with `elongation.enabled=False` the per-iteration radii recompute is idempotent, and sag is gated on `cfg.sag.enabled`. Effective change for legacy configs: an extra `compute_radii` call per iteration — same diameters as before, just earlier.)

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/simulator.py tests/sim/test_simulator.py
git commit -m "$(cat <<'EOF'
feat(simulator): per-iteration update_lengths + diameters + sag

After shedding each iteration, ramp every internode's length via sigmoid
(elongation), recompute pipe-model diameters from current topology, then
recompute sag offsets. Order matters: lengths feed sag's load term and
diameters feed sag's stiffness term.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12 — Finalization snap (post-loop) + remove builder.py's post-sim calls

**Files:**
- Modify: `src/palubicki/sim/simulator.py` (add finalization block at end of `simulate_forest`)
- Modify: `src/palubicki/geom/builder.py` (remove `compute_radii` and `apply_sag` calls — they're now per-iteration + finalized in the simulator)
- Modify: `tests/sim/test_simulator.py` (replace the Task 11 "young < target" test with a new test asserting finalization: at end of simulate(), all length == length_target)

### Why builder.py stops calling them

Spec §4.6 Site C: the post-sim `compute_radii` and `apply_sag` in `geom/builder.py:16-17` become redundant because the simulator's per-iteration loop already runs them AND the new finalization snap below runs them once more after snapping lengths to targets. Keeping them in builder.py would double-compute (harmless for diameters; harmless for sag because it's idempotent now — but wasteful and confusing).

### Why finalization must replace the Task 11 test

Once the snap sets `length = length_target` for every internode, the "young internodes have length < target" assertion no longer holds. The new test inspects the snap effect directly.

- [ ] **Step 1: Replace the Task 11 test with a finalization assertion**

In `tests/sim/test_simulator.py`, replace `test_internodes_have_progressive_lengths_when_elongation_enabled` with:

```python
def test_finalization_snaps_length_to_target(tmp_path):
    """After simulate() returns, every internode must have length == length_target
    (the finalization pass guarantees the exported geometry is fully grown)."""
    from palubicki.config import (
        Config, ElongationConfig, EnvelopeConfig, GeomConfig, LightConfig,
        PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    cfg = Config(
        envelope=EnvelopeConfig(rx=2.0, ry=2.0, rz=2.0, marker_count=500),
        sim=SimConfig(max_iterations=8,
                      elongation=ElongationConfig(enabled=True, tau_iterations=3.0)),
        tropism=TropismConfig(w_orthotropy_main=0.3),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        output=tmp_path / "tree.glb",
        seed=42,
    )
    tree = simulate(cfg)
    assert len(tree.all_internodes) > 0
    for iod in tree.all_internodes:
        assert iod.length == iod.length_target, (
            f"internode born at {iod.birth_iteration}: length={iod.length}, "
            f"target={iod.length_target}"
        )
```

- [ ] **Step 2: Run to confirm the new test fails**

Run: `.venv/bin/pytest tests/sim/test_simulator.py -k "finalization_snaps_length_to_target" -v`
Expected: FAIL — late-born internodes have length < target.

- [ ] **Step 3: Add finalization to `simulate_forest`**

In `src/palubicki/sim/simulator.py`, modify the body of `simulate_forest` so that just before `return forest`, we run the finalization snap:

```python
        if no_new_streak >= 2:
            break

    # --- Phase 2D finalization ---
    # Snap every internode to its target length, then recompute diameters
    # (no length change ⇒ no diameter change in pipe model, but kept explicit
    # for the case where length influences a future model) and sag offsets
    # (changes because load depends on length).
    if cfg.sim.elongation.enabled:
        for tree in forest.trees:
            for iod in tree.all_internodes:
                iod.length = iod.length_target
    for tree in forest.trees:
        update_diameters_incremental(tree, cfg=cfg.geom)
    if cfg.sag.enabled:
        for tree in forest.trees:
            apply_sag(tree, cfg=cfg.sag)

    return forest
```

- [ ] **Step 4: Remove the post-sim calls in `geom/builder.py`**

In `src/palubicki/geom/builder.py`, delete lines 16-17:

```python
    compute_radii(tree, r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent)
    apply_sag(tree, cfg.sag)
```

Also delete the now-unused imports at the top:

```python
from palubicki.geom.radii import compute_radii
from palubicki.sim.sag import apply_sag
```

Resulting `build_mesh` begins directly with the bark texture resolution.

- [ ] **Step 5: Run the simulator + builder tests**

Run: `.venv/bin/pytest tests/sim/test_simulator.py tests/geom/test_builder.py -v`
Expected: green. The finalization test now passes; existing builder tests are unaffected by removing the post-sim calls because the simulator already produces a fully sagged + diametered tree.

- [ ] **Step 6: Run the full test suite (except goldens) to confirm no regressions**

Run: `.venv/bin/pytest --ignore=tests/golden -v`
Expected: all green. (Goldens will fail — that's expected; we regenerate them in Task 14.)

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/sim/simulator.py src/palubicki/geom/builder.py tests/sim/test_simulator.py
git commit -m "$(cat <<'EOF'
feat(simulator): finalization snap + drop redundant builder.py post-sim calls

After the iteration loop, snap every internode's length to its target
and rerun diameters + sag once. This guarantees the exported geometry is
fully grown regardless of how late an internode was born. The
compute_radii and apply_sag calls in geom/builder.py are now redundant
(simulator owns the lifecycle) and are removed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13 — Update species presets (oak, pine, birch, maple)

**Files:**
- Modify: `src/palubicki/configs/species/oak.yaml`
- Modify: `src/palubicki/configs/species/pine.yaml`
- Modify: `src/palubicki/configs/species/birch.yaml`
- Create or modify: `src/palubicki/configs/species/maple.yaml` (Phase 2C is supposed to have added this — if it's missing, create a stub from the spec defaults; if present, just add the `sim.elongation` block)

### Check for maple.yaml first

- [ ] **Step 1: Determine whether `maple.yaml` exists**

Run: `ls src/palubicki/configs/species/`
- If `maple.yaml` exists, proceed normally (Step 5 will edit it).
- If `maple.yaml` does NOT exist (Phase 2C deferred it), create it now (Step 2) with reasonable defaults so Phase 2D doesn't depend on Phase 2C being complete.

- [ ] **Step 2 (only if `maple.yaml` is missing): Create a minimal maple preset**

Write `src/palubicki/configs/species/maple.yaml`:

```yaml
# Acer saccharum — maple: dense oval crown, opposite phyllotaxy
envelope:
  shape: ellipsoid
  rx: 4.5
  ry: 6.5
  rz: 4.5
  marker_count: 22000
sim:
  internode_length: 0.16
  internode_length_jitter: 0.12
  lambda_apical: 0.80
  alpha_basipetal: 2.0
  max_iterations: 40
  elongation:
    enabled: true
    tau_iterations: 3.0
    age_factor_min: 0.5
    age_factor_decay: 0.7
tropism:
  w_orthotropy_main: 0.32
  w_orthotropy_lateral: 0.05
  w_gravitropism_main: 0.0
  w_gravitropism_lateral: 0.0
  w_phototropism: 0.30
  w_direction_inertia: 0.5
  axis_decay: 0.7
phyllotaxy:
  mode: opposite
  divergence_angle_deg: 180.0
  divergence_jitter_deg: 4.0
  branch_angle_deg: 55
  branch_angle_jitter_deg: 4.0
shedding:
  quality_threshold: 0.12
sag:
  enabled: true
  k: 0.006
  max_bend_deg: 5.0
  rigid_axis_order: 1
light:
  enabled: true
  k_absorption: 0.55
geom:
  ring_sides: 10
  pipe_exponent: 2.3
  r_tip: 0.007
  bark_color: [0.40, 0.30, 0.22]
  leaf_size: 0.12
  leaf_cluster_count: 2
  leaf_aspect: 1.0
  leaf_splay_deg: 25
  foliage_depth: 3
```

(If your repo uses different defaults, prefer the existing pattern.)

- [ ] **Step 3: Add `sim.elongation` to `oak.yaml`**

In `src/palubicki/configs/species/oak.yaml`, append under the existing `sim:` block (before the next top-level key — `tropism:`):

```yaml
  elongation:
    enabled: true
    tau_iterations: 3.0
    age_factor_min: 0.5
    age_factor_decay: 0.8
```

The complete `sim:` block should look like:

```yaml
sim:
  internode_length: 0.18
  internode_length_jitter: 0.12
  lambda_apical: 0.75
  alpha_basipetal: 2.2
  max_iterations: 45
  elongation:
    enabled: true
    tau_iterations: 3.0
    age_factor_min: 0.5
    age_factor_decay: 0.8
```

- [ ] **Step 4: Add `sim.elongation` to `pine.yaml`**

Append to the `sim:` block of `src/palubicki/configs/species/pine.yaml`:

```yaml
  elongation:
    enabled: true
    tau_iterations: 2.5
    age_factor_min: 0.4
    age_factor_decay: 0.7
```

- [ ] **Step 5: Add `sim.elongation` to `birch.yaml`**

Append to the `sim:` block of `src/palubicki/configs/species/birch.yaml`:

```yaml
  elongation:
    enabled: true
    tau_iterations: 2.0
    age_factor_min: 0.6
    age_factor_decay: 0.5
```

- [ ] **Step 6: Add or update `sim.elongation` in `maple.yaml`**

If `maple.yaml` already existed in Step 1, append (or replace the existing block):

```yaml
  elongation:
    enabled: true
    tau_iterations: 3.0
    age_factor_min: 0.5
    age_factor_decay: 0.7
```

If you created `maple.yaml` in Step 2 from the template above, this is already included — skip.

- [ ] **Step 7: Verify each preset loads cleanly**

Run: `.venv/bin/palubicki dump-defaults --species oak`
Expected: prints YAML without error, includes `elongation` under `sim`.

Repeat for `pine`, `birch`, `maple`.

- [ ] **Step 8: Run species-related tests**

Run: `.venv/bin/pytest tests/test_config_species.py tests/sim/test_forest_species.py -v`
Expected: all green. If maple was just added, you may need to extend a parametrized test that enumerates species — check `tests/test_config_species.py` and `tests/sim/test_forest_species.py` for any `["oak", "pine", "birch"]` list and add `"maple"`.

- [ ] **Step 9: Commit**

```bash
git add src/palubicki/configs/species/
git commit -m "$(cat <<'EOF'
feat(presets): enable elongation in oak / pine / birch / maple

Each species gets a tuned (tau, age_factor_min, age_factor_decay) tuple
reflecting its growth rate and the chronological contrast we want
between early-vigorous and late-conservative shoots.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14 — Integration tests: chronology + diameter progression

**Files:**
- Create: `tests/integration/test_elongation_chronology.py`
- Create: `tests/integration/test_diameter_progression.py`

- [ ] **Step 1: Write `test_elongation_chronology.py`**

Create `tests/integration/test_elongation_chronology.py`:

```python
"""Verify the visible chronology: late-born internodes are shorter than early-born."""
import statistics

import pytest

from palubicki.cli import main


@pytest.mark.slow
def test_oak_late_internodes_shorter_than_early(tmp_path):
    """After a 30-iter oak sim with elongation enabled, mean length_target
    of late-cohort internodes (birth >= 20) must be at least 20% smaller
    than early-cohort (birth < 10)."""
    out = tmp_path / "oak.glb"
    rc = main([
        "generate", "--species", "oak",
        "--seed", "42",
        "--marker-count", "2000",
        "--iterations", "30",
        "-o", str(out),
    ])
    assert rc == 0

    # Re-simulate in-process so we can inspect Internode fields directly.
    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate

    cfg = load_config(
        yaml_path=None,
        cli_overrides={
            "seed": 42,
            "envelope.marker_count": 2000,
            "sim.max_iterations": 30,
        },
        output=out,
        species="oak",
    )
    tree = simulate(cfg)

    early = [iod.length_target for iod in tree.all_internodes if iod.birth_iteration < 10]
    late = [iod.length_target for iod in tree.all_internodes if iod.birth_iteration >= 20]
    assert len(early) > 5 and len(late) > 5, (
        f"insufficient samples: early={len(early)} late={len(late)}"
    )
    mean_early = statistics.fmean(early)
    mean_late = statistics.fmean(late)
    assert mean_late < mean_early * 0.8, (
        f"chronology not visible: mean_early={mean_early:.4f}, mean_late={mean_late:.4f}"
    )
```

- [ ] **Step 2: Write `test_diameter_progression.py`**

Create `tests/integration/test_diameter_progression.py`:

```python
"""Verify diameters grow over iterations for old internodes (their subtree expands)."""
import pytest

from palubicki.config import (
    Config, ElongationConfig, EnvelopeConfig, GeomConfig, LightConfig,
    PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.sim.radii import compute_radii, update_diameters_incremental
from palubicki.sim.simulator import simulate_forest


@pytest.mark.slow
def test_diameter_progression_final_matches_post_sim_compute_radii(tmp_path):
    """The per-iteration update_diameters_incremental ends up bit-equivalent
    (modulo float rounding) to a one-shot compute_radii on the final tree —
    pipe model only depends on the topology, so the final iteration's diameter
    pass is the same as the legacy post-sim pass."""
    cfg = Config(
        envelope=EnvelopeConfig(rx=3.0, ry=4.0, rz=3.0, marker_count=2000),
        sim=SimConfig(max_iterations=15,
                      elongation=ElongationConfig(enabled=True, tau_iterations=2.0)),
        tropism=TropismConfig(w_orthotropy_main=0.3, w_phototropism=0.2),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        output=tmp_path / "tree.glb",
        seed=42,
    )
    forest = simulate_forest(cfg)
    tree = forest.trees[0]

    # Snapshot the simulator-produced diameters.
    sim_diam = [iod.diameter for iod in tree.all_internodes]

    # Recompute fresh with the legacy entry point.
    compute_radii(tree, r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent)
    fresh_diam = [iod.diameter for iod in tree.all_internodes]

    assert len(sim_diam) == len(fresh_diam) and len(sim_diam) > 0
    for s, f in zip(sim_diam, fresh_diam):
        assert abs(s - f) < 1e-9
```

- [ ] **Step 3: Run the new integration tests**

Run: `.venv/bin/pytest tests/integration/test_elongation_chronology.py tests/integration/test_diameter_progression.py -v`
Expected: both PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_elongation_chronology.py tests/integration/test_diameter_progression.py
git commit -m "$(cat <<'EOF'
test(integration): elongation chronology + diameter progression

Chronology test asserts late-cohort internodes have ≥20% smaller target
length than early cohort. Diameter test asserts the simulator's
incremental pipe model matches a fresh compute_radii at the final state.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15 — Regenerate goldens (oak, pine, birch, maple)

**Files:**
- Modify: `tests/golden/data/species_oak.sha256`
- Modify: `tests/golden/data/species_pine.sha256`
- Modify: `tests/golden/data/species_birch.sha256`
- Create: `tests/golden/data/species_maple.sha256` (if maple was added in Task 13)
- Modify: `tests/golden/test_species_goldens.py` (extend parametrize to include `"maple"`)
- Possibly modify: `tests/golden/data/ellipsoid.sha256` and `ellipsoid_light.sha256` if the generic envelope goldens shift due to the simulator changes

### Why the generic goldens may also shift

Even though `elongation.enabled=False` by default, the simulator now (a) recomputes diameters every iteration (idempotent, no change) and (b) runs `apply_sag` every iteration when `cfg.sag.enabled=True` (the default SagConfig has `enabled=False` though, so the generic preset is untouched). The generic ellipsoid goldens use `SagConfig(enabled=False)` and `ElongationConfig(enabled=False)` ⇒ should be byte-identical to before. Check anyway.

- [ ] **Step 1: Add `"maple"` to the species golden parametrize (only if maple was added in Task 13)**

In `tests/golden/test_species_goldens.py:32`, change:

```python
@pytest.mark.parametrize("species", ["oak", "pine", "birch"])
```

to:

```python
@pytest.mark.parametrize("species", ["oak", "pine", "birch", "maple"])
```

- [ ] **Step 2: Run goldens without update to see which fail**

Run: `.venv/bin/pytest tests/golden/ -v`
Expected: `species_oak`, `species_pine`, `species_birch`, `species_maple` all fail (changed simulator output). `ellipsoid` and `ellipsoid_light` should pass (no sag, no elongation by default).

- [ ] **Step 3: Regenerate the goldens**

Run: `.venv/bin/pytest tests/golden/ --update-goldens -v`
Expected: each parametrized run writes its sha256 and then skips with "golden written".

- [ ] **Step 4: Re-run goldens normally to confirm they pass**

Run: `.venv/bin/pytest tests/golden/ -v`
Expected: all green.

- [ ] **Step 5: Visually spot-check at least one preset**

Run:

```bash
.venv/bin/palubicki generate --species oak --seed 42 --marker-count 5000 --iterations 30 -o /tmp/oak_phase2d.glb
.venv/bin/palubicki preview /tmp/oak_phase2d.glb -o /tmp/oak_phase2d.png
```

Open `/tmp/oak_phase2d.png` and confirm the tree silhouette is sensible (no obvious gaps, droops look plausible, no degenerate spikes). If something looks wrong, debug and fix BEFORE committing the goldens.

- [ ] **Step 6: Commit**

```bash
git add tests/golden/test_species_goldens.py tests/golden/data/
git commit -m "$(cat <<'EOF'
test(golden): regenerate goldens after Phase 2D temporal dynamics

Progressive elongation + dynamic diameter/sag change the per-iteration
intermediate state and thus the finalized geometry. Visual spot-check
on oak preset confirms shapes are sensible.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16 — Update README and review doc

**Files:**
- Modify: `README.md`
- Modify: `docs/2026-05-27-simulation-review.md`

- [ ] **Step 1: Add a Phase 2D mention to `README.md`**

Open `README.md`, find the introductory paragraphs (around lines 3-5), and after the existing V1 description add:

```markdown
**Phase 2D (temporal dynamics):** every internode tracks its birth iteration
and a target length; effective length ramps via a sigmoid each iteration
while pipe-model diameters and cantilever-bend sag are recomputed live.
A finalization pass snaps lengths to target and recomputes diameters + sag
once more so the exported `.glb` is always fully grown. Enable per species
under `sim.elongation` in any YAML preset.
```

- [ ] **Step 2: Mark suggestions #6 and #7 as addressed in the review doc**

Open `docs/2026-05-27-simulation-review.md`, locate suggestion #6 ("Tropisme par poids (plagiotropisme dynamique)", around line 145-150) and append at the end of its bullet:

```
*Status (Phase 2D, 2026-05-27): addressed in part — sag is now recomputed
every iteration on live diameters and live lengths, giving the
"plagiotropisme dynamique" effect through the mechanical pass rather than
a tropism term. See `sim/sag.py` and the per-iteration loop in
`sim/simulator.py`.*
```

Locate suggestion #7 ("Stochasticité de `internode_length`", around line 153-154) and append:

```
*Status (Phase 1 + Phase 2D, 2026-05-27): addressed. Phase 1 added
`sim.internode_length_jitter` (Gaussian σ, ±10–15% by default in presets);
Phase 2D layers an age-scaled target length so internodes born late are
also shorter (`sim.elongation.age_factor_*`). The combination eliminates
the "constant = AI-readable" tell.*
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/2026-05-27-simulation-review.md
git commit -m "$(cat <<'EOF'
docs(phase2d): README mention + mark review suggestions #6/#7 as addressed

Phase 2D dynamics callout in the README; review doc now records that
the dynamic sag and length stochasticity items are implemented.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 17 — Final verification

**Files:** none — verification only.

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/pytest -v`
Expected: all green.

- [ ] **Step 2: Run the golden suite explicitly (it's gated on a marker)**

Run: `.venv/bin/pytest tests/golden/ -v`
Expected: all green.

- [ ] **Step 3: Smoke-test `palubicki edit` quickly (optional but recommended)**

If the realtime editor is configured locally, start it briefly to verify the schema picks up the new `ElongationConfig` fields:

```bash
.venv/bin/palubicki edit --species oak --no-browser --port 8765 &
sleep 1
curl -s http://127.0.0.1:8765/api/initial | python -m json.tool | grep -A 6 elongation
kill %1
```

Expected: `elongation` block appears with `enabled / tau_iterations / age_factor_min / age_factor_decay`. (If `palubicki edit` is not installed in this checkout, skip.)

- [ ] **Step 4: Confirm spec coverage with a quick checklist**

Compare to spec §2 (Scope · In):
- `Internode.birth_iteration / length_target` — Task 3 ✓
- `Internode.length` now mutable / effective — Tasks 3, 11, 12 ✓
- `SimConfig.elongation: ElongationConfig` — Task 1 ✓
- `sim/elongation.py` with `update_lengths` + `compute_target_with_age` — Tasks 4, 5 ✓
- `sim/radii.py` refactor → `update_diameters_incremental` — Task 6 ✓
- `sim/sag.py` per-iteration + idempotent — Tasks 7, 11 ✓
- `sim/simulator.py` calls all three in the loop + finalization — Tasks 10, 11, 12 ✓
- Presets oak/pine/birch (+ maple) tuned — Task 13 ✓
- Tests + goldens regenerated — Tasks 4, 5, 6, 7, 11, 12, 14, 15 ✓
- README + review-doc updated — Task 16 ✓

If anything in the spec lacks a matching task, address it now before declaring done.

- [ ] **Step 5: Final status report**

No commit. Report task count, total commits, and whether the full suite is green. Hand off to the user for visual review of any presets they want to compare side-by-side against Phase 1.

---

## Reference: spec section ↔ task map

| Spec section | Task(s) |
|---|---|
| §4.1 `ElongationConfig` | 1 |
| §4.2 `Internode` new fields | 2, 3 |
| §4.3 `sim/elongation.py` (`compute_target_with_age`) | 4 |
| §4.3 `sim/elongation.py` (`update_lengths`) | 5 |
| §4.4 `sim/radii.py` incremental refactor | 6 |
| §4.5 `sim/sag.py` idempotent refactor + `Node.sag_offset` | 2, 7, 8, 9 |
| §4.6 simulator Site A (creation site) | 10 |
| §4.6 simulator Site B (per-iter dynamics) | 11 |
| §4.6 simulator Site C (drop builder.py post-sim calls) | 12 |
| §5 presets (oak/pine/birch/maple) | 13 |
| §6.1 unit tests | 1, 4, 5, 6, 7 |
| §6.2 integration tests | 14 |
| §6.3 goldens | 15 |
| §7.1 finalization snap | 12 |
| §7.5 `Node.sag_offset` invariant | 2, 7 |
| §7.6 leaves emitted at final position | 9, 12 |
