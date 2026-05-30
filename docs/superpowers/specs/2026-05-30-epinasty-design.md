# Epinasty — time-dependent plagiotropic branch reorientation

Issue: #34 · Branch: `issue-34-epinasty-time-dependent-plagiotropic`
Date: 2026-05-30

## Problem

Real lateral branches don't start horizontal. They emerge near the parent's
angle and **arch toward horizontal over several years** (epinasty /
gravimorphism). Today plagiotropism is applied at full strength from node one
(`sim/tropisms.py` — a constant `w_plagiotropism_lateral` weight projecting the
growth direction onto the horizontal plane every iteration, with no notion of
age). The result: crowns reach their final branch geometry instantly and read as
young/stiff. The mature arching oak/maple limb and the swept conifer branch are
both missing.

## Mechanism

Scale the existing plagiotropism term in `growth_direction` by an age-dependent
ramp instead of applying it at full strength. Nothing else in the tropism blend
changes.

```
ramp(age) = 1 - exp(-age / tau)          # 0 at birth -> 1 asymptotically
w_plagio_eff = w_plagio * ramp(age)      # replaces the constant w_plagio
```

Reference values: `ramp(0)=0.00`, `ramp(tau)=0.63`, `ramp(2*tau)=0.86`,
`ramp(3*tau)=0.95`. The `1 - exp` form (matching `shoot_extension`'s saturating
style in `elongation.py`) is chosen over a logistic because it is exactly 0 at
birth, the truest fit to the "insertion direction at birth is close to the
parent axis" acceptance criterion.

When `epinasty_enabled` is `False`, `ramp` is identically `1.0`, so the blend is
**bit-for-bit identical** to the current behaviour. This is the default.

### Age source

```
age = t - bud.parent_node.parent_internode.birth_time
```

`t` is the clock time already threaded into the per-bud loop
(`simulator.py`, the `_grow`/emission loop, where `growth_direction` is called).
`birth_time` (years) already exists on `Internode` (`sim/tree.py`). The age used
is the age of the **wood the bud is attached to**, not the bud's own age:

- A lateral breaking from **old proximal wood** -> `ramp ~ 1` -> arches toward
  horizontal.
- A lateral on **fresh distal wood** -> `ramp ~ 0` -> stays near the parent
  axis (steep).

That is precisely the "young distal laterals steeper than old proximal ones"
gradient the diagnostics acceptance criterion asks for. Direction inertia
(`w_direction_inertia`, default 0.4) smooths each emission step so the axis
curves into an arch rather than kinking.

If `parent_internode is None` (the trunk-base buds at the root node), `age` falls
back to `0.0`. This is irrelevant in practice: those buds are main-axis, and
`w_plagiotropism_main` defaults to 0.

### Per-internode, not rigid reorient

This resolves the issue's open question. The ramp composes with the existing
per-bud emission loop: each newly emitted internode uses the age-appropriate
plagiotropism weight. Already-placed internodes are not retro-actively bent
(consistent with `elongation.py`'s fixed-node-position model). The arch emerges
from new growth off aging wood, not from a `sag`-style post-process pass.

## Changes

1. **`src/palubicki/config.py`** — add two fields to `TropismConfig`
   (frozen dataclass, same `field(... metadata={"ui": ...})` style as siblings):
   - `epinasty_enabled: bool = False`
   - `epinasty_tau_years: float = 8.0`

   Default-off means the `tau` value cannot affect any golden while disabled.

2. **`src/palubicki/sim/tropisms.py`** — `growth_direction` gains a keyword-only
   `branch_age_years: float = 0.0`. When `cfg.epinasty_enabled` and
   `cfg.epinasty_tau_years > 0`, compute `ramp = 1 - exp(-branch_age_years /
   tau)` and use `w_plagio * ramp` in place of `w_plagio`. The near-vertical skip
   guard and renormalisation are untouched. When disabled (or tau <= 0), `ramp`
   is `1.0`.

3. **`src/palubicki/sim/simulator.py`** — at the `growth_direction` call site,
   compute `branch_age_years` from `bud.parent_node.parent_internode` (guarding
   `None` -> `0.0`) and pass it.

4. **Tests** — see below.

## Out of scope (deferred, per issue)

- **Epinastic droop**: a separate sub-horizontal set-point for pendulous
  laterals (distinct from gravitropism). File separately if wanted.
- **Active re-straightening / reaction-wood recovery**: a branch springing back
  toward a set-point as it stiffens. Distinct mechanism.
- **Per-axis-order tau**: a single global `tau` suffices for the MVP; the
  age gradient already falls out of `axis_decay**order` plus per-internode age.

## Tests / acceptance criteria

- **Unit (`tests/sim/test_tropisms.py`)**:
  - `ramp(0) == 0`, monotonically increasing, asymptotes to 1.
  - With `epinasty_enabled=False`, the effective plagiotropism equals the
    constant-weight behaviour (the existing `test_plagiotropism_*` cases stay
    green unchanged).
  - With `epinasty_enabled=True`, a young branch (`age=0`) ignores plagiotropism
    (direction follows inertia/parent); an old branch (`age >> tau`) reproduces
    the full-strength horizontal pull.
- **Goldens**: disabled-default reproduces existing goldens bit-for-bit.
- **Integration**: on a grown tree with epinasty enabled, a lateral's insertion
  direction at birth is close to the parent axis, and by age ~= 2*tau it has
  arched to the configured plagiotropic angle. The insertion-angle-by-order
  diagnostic reflects the age gradient.

## Non-goals / honesty note

No per-age branch-angle dataset exists in the repo (`literature.yaml` carries
diagnostic metric ranges, not an angle-vs-age curve). The default `tau = 8 years`
is a botanically-plausible choice, not a fitted value. No calibration claim is
made beyond that.
