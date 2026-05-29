# Time / phenology axis — Phase 1 foundation

**Issue:** [#10](https://github.com/julien-riel/palubicki/issues/10)
**Date:** 2026-05-29
**Status:** Approved — ready for implementation plan

## Goal

Introduce a real concept of time into the simulator. Today an iteration is
"+1 internode per active bud" with no temporal unit. This change makes a step
represent a calendar duration so downstream realism features (leaf age,
deciduousness, seasonal dynamics, time-dependent epinasty, flowering) can be
built on a calendar without redesigning the data layer twice.

This is an architectural change: every consumer of "step" semantics must keep
working. The migration keeps iteration-counters and time-deltas explicitly
distinct so it is reviewable.

## Decisions (locked)

1. **Continuous fractional-year clock** (issue option 1) — strictly more
   expressive than a discrete season enum.
2. **Replace `sim.max_iterations`** with `max_simulation_years` + `dt_years`.
   The iteration count is derived. PoC, no back-compat: the old field is
   removed, not aliased.
3. **Remove `Bud.age`** — it is vestigial (only ever reset to 0 in
   `reiteration.py`, never incremented or read). Downstream issues (#4 leaf
   age, #11 flowers) can add a real age field when they have a consumer.
4. **MVP phenology gate only** (`annual_growth_period`). The richer
   `Phenology` struct (`bud_break`, `leaf_out`, `flowering_start`,
   `leaf_drop`) is deferred to downstream issues.

## Architecture

### New module: `src/palubicki/sim/clock.py`

```python
@dataclass
class Clock:
    dt: float              # years per iteration
    t: float = 0.0         # current simulation time, years

    def tick(self) -> None: self.t += self.dt
    def year(self) -> int: return math.floor(self.t)
    def year_fraction(self) -> float: return self.t - math.floor(self.t)
    def in_window(self, lo: float, hi: float) -> bool:
        return lo <= self.year_fraction() < hi
```

`year_fraction ∈ [0, 1)` is the phenology coordinate. `annual_growth_period`
is expressed in those fractions (e.g. `0.25` ≈ April). No `doy()` helper —
nothing needs days yet (YAGNI).

### Config — `SimConfig` (`config.py`)

- **Remove** `max_iterations`.
- **Add**:
  - `dt_years: float = 1.0` — time advance per iteration. UI min 0.1, max 2.0,
    step 0.05.
  - `max_simulation_years: float = 30.0` — simulation budget. UI min 1, max 80,
    step 1. (Default matches the prior `max_iterations=30` at `dt_years=1.0`.)
  - `annual_growth_period: tuple[float, float] = (0.0, 1.0)` — fraction of the
    year during which growth is active. Default spans the whole year (no
    behavioral change).
- **Derived budget** (property on `SimConfig`):
  ```python
  @property
  def num_iterations(self) -> int:
      return round(self.max_simulation_years / self.dt_years)
  ```
- **Validation** (`Config.__post_init__`):
  - `dt_years > 0`
  - `max_simulation_years >= 0`
  - `0.0 <= annual_growth_period[0] < annual_growth_period[1] <= 1.0`
- YAML loader: `annual_growth_period` parsed as a 2-tuple of floats (mirror the
  existing `branch_angle_by_order` tuple-coercion path).

### Config — `ElongationConfig`

- Rename `tau_iterations` → **`tau_years`** (default 3.0, same number).
  Validation: `tau_years > 0`. Docstring updated to "years".

### Data layer — `tree.py`

- `Internode.birth_iteration: int = 0` → **`birth_time: float = 0.0`** (years).
- **Remove** `Bud.age` (and its reset in `reiteration.py`).
- `low_quality_steps` / `low_light_steps` are unchanged — they correctly count
  iterations (steps), not time.

### Simulator — `simulator.py`

- `simulate_forest` builds `Clock(dt=cfg.sim.dt_years)` and loops
  `for iteration in range(cfg.sim.num_iterations)`, setting `clock.t = iteration * dt`
  at the top of each pass.
- **Thread both `iteration: int` and `t: float`.** `iteration` stays where it
  is a step-index: RNG salting (`_internode_target`, light seeds, substep
  seeds), `state.node_index`, and logging. `t` is used everywhere the value
  represents biological time: `Internode.birth_time` and elongation.
- **Growth-window gate lives in the loop**, not inside `_iteration_step`:
  - If `not clock.in_window(*cfg.sim.annual_growth_period)`: run aging only
    (`_apply_temporal_dynamics(forest, cfg, t)`), then `continue` **without**
    touching `no_new_streak`. Dormant seasons must not trip the
    saturation early-stop (`no_new_streak >= 2`).
  - Else: run `_iteration_step` as today.
  - The `if not any active_buds: break` guard stays.
- `_emit_node`: `birth_time=t` (replacing `birth_iteration=iteration`).
- `_internode_target`: keeps `iteration` for the jitter RNG salt; passes
  `birth_time=t` and `total_years=cfg.sim.max_simulation_years` to
  `compute_target_with_age`.
- `_apply_temporal_dynamics(forest, cfg, t)`: calls
  `update_lengths(tree, current_time=t, cfg=...)`.
- Logging line: `%d/%d` uses `cfg.sim.num_iterations`; append the year.

### Elongation — `elongation.py`

- `compute_target_with_age(base_length, birth_time, total_years, cfg)`:
  `t_norm = min(1.0, birth_time / total_years)` (was `birth_iteration / max_iterations`).
- `update_lengths(tree, current_time, cfg)`:
  `elapsed = max(0.0, current_time - iod.birth_time)`, `tau = cfg.tau_years`.

## Invariance argument (why goldens stay green)

With `dt_years = 1.0` and the default window `(0.0, 1.0)`:

- `clock.t = iteration` exactly, so `birth_time == old birth_iteration`.
- `tau_years == tau_iterations` (same default), so the sigmoid is unchanged.
- `year_fraction` is always `0.0`, and `0.0 ∈ [0.0, 1.0)`, so every iteration
  grows — no skipped steps.
- `num_iterations = round(max_simulation_years / 1.0)` reproduces the prior
  iteration count when goldens set `max_simulation_years` to the old
  `max_iterations` value.

The two goldens (`ellipsoid`, `forest_v3`) run with elongation **off**, so the
`birth_iteration → birth_time` rename does not touch their geometry at all;
only the preserved iteration count matters. Species presets (elongation on)
stay green because the elongation math is numerically identical at
`dt_years = 1.0`.

## Ripple / migration

- **CLI** (`cli.py`): `--iterations` → `--years` (maps to
  `sim.max_simulation_years`); add `--dt-years` (maps to `sim.dt_years`).
  `asset_meta` and any diagnose summary use `max_simulation_years` instead of
  `max_iterations`.
- **Species presets** (5: oak, birch, fir, maple, pine): `max_iterations:` →
  `max_simulation_years:`, `elongation.tau_iterations:` → `tau_years:`.
- **Tests** (~16 files + 2 goldens' `SimConfig`): mechanical kwarg rename
  `max_iterations=N` → `max_simulation_years=float(N)`,
  `tau_iterations=` → `tau_years=`, and `--iterations` → `--years` in CLI tests.
  `test_config.py` validation cases re-pointed to the new fields.

## Verification (acceptance criteria)

- `cfg.sim.dt_years` accepted in YAML and schema. ✔ via config + edit-schema tests.
- `Internode.birth_time` (years) replaces `birth_iteration`. ✔
- Elongation produces identical output at `dt_years=1.0`. ✔ via existing goldens
  + species runs.
- New `tests/integration/test_phenology.py`:
  - With `dt_years=0.25`, `annual_growth_period=[0.0, 0.5]`: every internode's
    `birth_time` year-fraction lands in `[0.0, 0.5)`; per-year new-internode
    counts are zero in the dormant half-year.
  - Regression: `dt_years=1.0` with default window grows on every iteration.
- `palubicki generate --species oak --seed 0` still produces a valid `.glb`
  with default settings. ✔ via smoke/CLI test.
- `README.md`: one paragraph documenting the time model (years, `dt_years`,
  `annual_growth_period`).

## Out of scope

- Actual deciduousness, flower induction, leaf age (downstream #4, #11).
- Dormancy of non-bud state (trunk thickening keeps per-iteration behavior).
- Daily resolution (`dt_years < 0.1`).
- Climate / weather input.
- Richer per-species `Phenology` struct (deferred; `annual_growth_period` is
  the MVP gate).
- Diagnostics changes — the per-year bucketing for verification lives in the
  integration test, not in `compute_metrics`.
