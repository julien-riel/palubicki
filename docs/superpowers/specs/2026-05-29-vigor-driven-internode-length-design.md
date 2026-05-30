# Vigor-driven internode length

**Issue:** #20 — *sim: vigor-driven internode length (replace floor(v) counts +
age_factor with continuous Borchert-Honda flux)*
**PR:** #31
**Date:** 2026-05-29

## Goal

Make internode length *emerge* from the Borchert-Honda (BH) resource allocation
instead of being imposed top-down. Today the BH pass computes a continuous
resource flux `v_b` per bud, then discards the information twice: it floors
`v_b` to an integer count and caps that count at 1 (`n_substeps_max`), so the
fractional surplus is silently lost. Length itself is a fixed constant scaled
by an `age_factor(birth_time)` decay curve — a top-down age clock, not a
consequence of resource scarcity.

This work routes the continuous `v_b` directly into internode length so
vigorous buds extend more and depleted buds extend less, with distal tapering
falling out of marker depletion rather than an age term. It also collapses the
now-redundant substep machinery and couples vigor into diameter growth.

Chosen approach: **issue option 1** (continuous length, 1 segment/bud/iteration),
plus two opted-in extensions confirmed during brainstorming:
- **Hysteresis dormancy** (vs. a bare absolute threshold).
- **Vigor → diameter coupling** via a vigor-seeded pipe-model tip radius.

Calibration target: **realism** — trees should reach physically plausible sizes
and the ~1.5–8.6 cm internode range, not merely preserve current golden scale.

## Non-goals (out of scope)

- Sag feedback into growth (bent positions driving subsequent perception).
- The fold-back / `cos_min_perception` kill heuristic.
- Any time-axis redesign — that is #10. This work *reduces* #10's burden by
  removing the `age_factor` iteration-as-time crutch.

## Current state (what changes)

| Concern | Where | Today | After |
|---|---|---|---|
| Flux floored to counts | `sim/bh.py` (`allocate`, floors at `:93,98,104,134,143`, return type `:16,28`) | `floor(v_b)`; `v_b<1` → DORMANT | continuous `v_b`; no floor |
| One-internode cap | `simulator.py` `_grow_tree`; `SimConfig.n_substeps_max` | surplus above cap lost | each bud emits ≤1 internode/iter (cap removed) |
| Length from age clock | `elongation.py` `compute_target_with_age`; `ElongationConfig.age_factor_*` | `base × age_factor(birth_time)` | `shoot_extension_max·(1−e^(−v_b/vigor_ref))` |
| Substep machinery | `simulator.py` `_SubstepChain`, `_reperceive_substep_terminals`, step-major walk; `SimConfig.re_perceive_per_substep` | exists to grow >1 internode/bud/iter | deleted; single bud-major pass |
| Diameter | `sim/radii.py` pipe model, flat `r_tip` per tip | pure pipe model | pipe model with vigor-seeded tip radius |

## Design

### 1. Length law

`allocate()` returns the continuous `dict[Bud, float]` flux. **All `math.floor()`
calls in `bh.py` are removed** and the return type changes from `dict[Bud, int]`
to `dict[Bud, float]`. The basipetal/acropetal passes are otherwise unchanged.

Each **active** bud emits exactly one internode per iteration. Its target length
is the saturating physiological response:

```
length_raw = shoot_extension_max * (1 - exp(-v_b / vigor_ref))
```

- Small `v_b` → approximately linear: `≈ shoot_extension_max · v_b / vigor_ref`.
- Large `v_b` → asymptotes to `shoot_extension_max` (a finite annual meristem
  rate limit — no arbitrary `min()` clamp). This is what prevents a giant first
  trunk internode when the root perceives the whole envelope at iteration 1.

The existing multiplicative `internode_length_jitter` factor (clamped to
`[0.5, 1.5]`) applies on top of `length_raw`, salted exactly as today by
`(seed, _ILEN_SALT, iteration, node_index)`. The result is the internode's
`length_target`, which still feeds the **unchanged** elongation sigmoid ramp
(`update_lengths`). Only the `age_factor` target-shaping is removed.

`Internode` gains a `vigor: float` field, set at emission to the producing `v_b`.
It feeds both the diameter coupling (§4) and diagnostics (§6).

### 2. Dormancy with hysteresis

`Bud` gains a `recent_vigor: float` field (EMA of its per-iteration `v_b`).
Each iteration, after `v_b` is known for the bud:

```
recent_vigor = (1 - vigor_smoothing) * recent_vigor + vigor_smoothing * v_b
```

A bud is **DORMANT when `recent_vigor < vigor_dormancy`**, ACTIVE otherwise. The
EMA lag is the hysteresis: a single starved iteration no longer flips a
well-fed bud dormant, and a single lucky iteration no longer wakes a starved
one. Dormant buds stay in `active_buds` and are re-perceived each iteration (no
behavior change there), so a genuinely re-vigorated bud wakes naturally once its
smoothed vigor climbs back above `vigor_dormancy`.

The raw per-iteration `v_b` (not the EMA) drives the **length law** in §1; the
EMA governs only the active/dormant decision.

*Rejected alternative:* an explicit two-threshold Schmitt trigger
(`vigor_dormancy` low / `vigor_wake` high). Equivalent flicker resistance but
two knobs and more branching; the EMA-single-threshold is simpler and matches
the issue's "relative to recent vigor" framing.

### 3. Single bud-major pass (collapse substeps)

`_grow_tree` is rewritten as a single pass over `tree.active_buds`:

```
for bud in active_buds:
    v_b = n_by_bud[bud]
    bud.recent_vigor = ema_update(bud.recent_vigor, v_b)
    if bud.recent_vigor < vigor_dormancy or perception is zero:
        bud.state = DORMANT; keep; continue
    d = growth_direction(...)            # tropisms + light + perception
    if U-turn (dot(d, dir) < cos_min_perception): DORMANT; keep; continue
    target = shoot_extension(v_b) * jitter
    new_pos = bud.position + d * target
    if obstacle-blocked: DORMANT / DEAD per existing rules
    emit one node + internode (records vigor=v_b); enqueue new terminal + laterals
```

Deleted: `_SubstepChain`, `_reperceive_substep_terminals`, the `max_n` step
loop, and the two-stage per-level emission. Perception (`res`) and light
(`light_info`) are already computed once per iteration upstream of `_grow_tree`,
so the single pass needs no in-iteration re-perception.

Side benefit: the single pass restores all-of-A-before-B emission ordering, so
the `node_index` interleaving caveat documented at `_grow_tree` (#24) disappears.
`node_index` continues to salt the length-jitter RNG and provide node identity.

**Termination safety.** Each bud still emits ≤1 internode/iteration, so
`nodes_created` per iteration stays bounded by the active-bud count, and the
`no_new_streak >= 2` early stop fires exactly as today once allocation starves
all buds below `vigor_dormancy`. Removing `n_substeps_max` does not change this
because the 1-per-bud rule is retained structurally, not via the cap.

### 4. Vigor → diameter coupling (option a: vigor-seeded tip radius)

The pipe model stays the backbone: `r^n = Σ r_child^n`, post-pass in `radii.py`.
The only change is the **tip seed**. A terminal internode (no descendant
internodes) seeds its radius as:

```
r_seed = r_tip * (1 + vigor_diameter_gain * (iod.vigor / vigor_ref))
```

instead of a flat `r_tip`. Vigorous lineages seed thicker pipes; depleted ones
thinner; the basipetal `Σ r_child^n` accumulation then thickens parents
accordingly. `vigor_diameter_gain = 0` exactly recovers today's pipe model.
`vigor` is read from the internode (recorded at emission), so the coupling is
robust to bud lifecycle (shed/dead tips) at finalization time.

*Rejected alternatives:* (b) per-iteration cambial accumulation replacing the
pipe model — most physical but a large change requiring full `r_tip`/
`pipe_exponent` recalibration across all presets; (c) multiplying pipe radius by
a `v_subtree`-derived scale. Option (a) is the least-invasive coupling that
reuses state we already record.

### 5. Config changes (PoC — no back-compat, no aliases)

**Add to `SimConfig`:**

| Field | Meaning | Provisional default |
|---|---|---|
| `shoot_extension_max` | asymptotic annual shoot extension (length scale) | ~0.3 (tune) |
| `vigor_ref` | flux at which length ≈ 0.632·max (the saturation knee) | ~1.0 (tune) |
| `vigor_dormancy` | smoothed-vigor threshold for dormancy | ~1.0 (≈ today's floor<1) |
| `vigor_smoothing` | EMA weight `s` ∈ (0,1] for `recent_vigor` | ~0.5 (tune) |
| `vigor_diameter_gain` | tip-radius vigor sensitivity (0 = pure pipe model) | tune |

**Remove:**
- `SimConfig.internode_length` — superseded by `shoot_extension_max` as the
  length scale; `internode_length_jitter` becomes a pure multiplicative factor
  on `length_raw` (its σ semantics are unchanged, the "fraction of
  internode_length" wording in the field doc is updated).
- `SimConfig.n_substeps_max`, `SimConfig.re_perceive_per_substep`.
- `ElongationConfig.age_factor_decay`, `ElongationConfig.age_factor_min`.
- `compute_target_with_age` from `elongation.py` (and its import in
  `simulator.py`). `update_lengths` (the sigmoid ramp) stays.

Config validation: `shoot_extension_max > 0`, `vigor_ref > 0`,
`vigor_dormancy >= 0`, `0 < vigor_smoothing <= 1`, `vigor_diameter_gain >= 0`.
Remove the now-dead `age_factor_*` validators.

### 6. Diagnostics

Add an **internode-length-by-axis-order** metric to `sim/diagnostics.py`,
reusing `_axis_orders`: `internode_length_by_order: {order: _stats}`. Plus a
proximal-vs-distal summary (`internode_length_proximal_mean` for the lowest
order(s), `internode_length_distal_mean` for the highest) so the acceptance
criterion "distal internodes measurably shorter than proximal, with no age
term" is machine-checkable. Optionally surface `vigor_by_order` for per-bud
vigor inspection (issue nice-to-have). Wire the new scalars into
`_SCALAR_KEYS`/aggregation and `format_report`.

### 7. Calibration plan (toward realism)

For each of the five presets (`birch/fir/maple/oak/pine.yaml`):
1. Seed `shoot_extension_max` from the old `internode_length` and the old
   `age_factor` ceiling; set `vigor_ref ≈ 1.0` as the starting knee.
2. Run `palubicki diagnose` (multi-seed) and inspect `tree_height`,
   `internode_length_by_order`, `trunk_base_diameter`, Strahler/Horton.
3. Tune `alpha_basipetal` / `vigor_ref` so heights are species-plausible and
   internode lengths land in the ~1.5–8.6 cm range; tune `vigor_diameter_gain`
   so trunk taper looks right.
4. Visual check via `palubicki preview` per species.
5. Drop the removed YAML keys (`internode_length`, `age_factor_*`,
   `n_substeps_max`, `re_perceive_per_substep`) and add the new ones.

Regenerate goldens and update the diagnostics harness assertions/reference
ranges as needed.

## Acceptance criteria

- [ ] `allocate()` returns continuous per-bud flux; no `floor()` remains in `bh.py`.
- [ ] Internode length is a function of `v_b`; `age_factor` removed from
      `elongation.py` and config.
- [ ] `n_substeps_max` / `re_perceive_per_substep` removed; `_SubstepChain` and
      `_reperceive_substep_terminals` gone; each bud emits ≤1 internode/iteration.
- [ ] Dormancy uses the `recent_vigor` EMA against `vigor_dormancy`.
- [ ] Diameter uses the vigor-seeded tip radius; `vigor_diameter_gain=0`
      reproduces the pure pipe model.
- [ ] Five presets recalibrated; `palubicki preview` renders plausible trees for each.
- [ ] Goldens + diagnostics assertions regenerated and green.
- [ ] Distal internodes are measurably shorter than proximal ones with no age
      term (emergent tapering), verified via `internode_length_by_order` in the
      diagnostics harness.

## Risks / open items

- **Calibration is empirical.** Provisional defaults above are starting points;
  final values come from the diagnostics + preview loop.
- **Diameter coupling vs. existing presets.** Several presets tuned
  `pipe_exponent`/`r_tip` against the old flat-tip pipe model; the vigor seed
  shifts taper, so trunk diameters need a recalibration pass alongside heights.
- **`vigor_smoothing` interplay with termination.** A very low `s` slows how
  fast `recent_vigor` decays, which could delay the `no_new_streak` stop; verify
  during calibration that trees still terminate within the year budget.
