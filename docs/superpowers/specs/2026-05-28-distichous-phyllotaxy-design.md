# Distichous phyllotaxis mode — design

**Issue:** [#2](https://github.com/julien-riel/palubicki/issues/2) — `sim/phyllotaxy.py: add explicit distichous mode (single bud, 180° alternate)`
**Branch / PR:** `issue-2-add-explicit-distichous-mode-single-bud` / [#15](https://github.com/julien-riel/palubicki/pull/15)
**Date:** 2026-05-28
**Source motivation:** `docs/botany/simulator-gap-analysis.md` §5 + "Top remaining recommendations" #3.

## Goal

Add `"distichous"` as a named phyllotaxis mode — one bud per node, alternating 180° between successive nodes. Today the pattern is achievable as `mode="alternate"` + `divergence_angle_deg=180`, but no preset uses it and the implicit form is confusing (the same `"alternate"` mode produces *spiral* for oak/birch because their divergence angle is 137.5°).

Additionally: thread a per-axis override so plagiotropic (lateral) axes can be distichous while the orthotropic trunk follows the species mode. This is what makes a conifer's side spray visibly flat/2-ranked instead of spiraling.

**In scope:**
- New `"distichous"` mode value in `PhyllotaxyConfig.mode`.
- New `distichous_on_plagiotropic: bool` field on `PhyllotaxyConfig`.
- New `fir` species preset that exercises the flag.
- Golden test for `fir`.

**Out of scope:**
- Full per-axis mode selection (any-mode-on-any-axis). Bigger design pass.
- Updating any existing preset (oak/birch/pine/maple) to use distichous — acceptance criterion requires their goldens unchanged.
- Reserve-bud distichous behavior — `reserve_bud_directions` doesn't take `axis_order` today; the fir preset sets `dormant_reserve_count: 0` to dodge the question.
- Per-leaf twist / phyllotaxis-via-petiole-rotation (the real-world mechanism for Abies appearing 2-ranked). Distichous here is the simulation shortcut for the visible result.

## Architecture

Two files change; everything else follows by consequence.

### `src/palubicki/config.py` — `PhyllotaxyConfig`

```python
@dataclass(frozen=True)
class PhyllotaxyConfig:
    mode: Literal[
        "alternate", "opposite", "whorled", "decussate", "distichous"
    ] = field(default="alternate", metadata={"ui": {"label": "Mode"}})
    # ... existing fields unchanged ...
    distichous_on_plagiotropic: bool = field(
        default=False,
        metadata={"ui": {"label": "Distichous on lateral axes"}},
    )
```

`divergence_angle_deg` is *ignored* when the effective mode is distichous. Documented in the docstring; no runtime check. Default of 137.5 is fine in non-distichous modes and we can't distinguish "user set it" from "default" on a frozen dataclass.

### `src/palubicki/sim/phyllotaxy.py` — `lateral_bud_directions`

```python
# Effective mode: the flag promotes lateral axes (axis_order > 0) to
# distichous regardless of cfg.mode.
if cfg.distichous_on_plagiotropic and axis_order > 0:
    effective_mode = "distichous"
else:
    effective_mode = cfg.mode

if effective_mode == "alternate":
    k = 1
elif effective_mode == "opposite":
    k = 2
elif effective_mode == "whorled":
    k = max(1, cfg.whorl_count)
elif effective_mode == "decussate":
    k = 2
elif effective_mode == "distichous":
    k = 1
else:
    raise ValueError(f"unknown phyllotaxy mode: {effective_mode!r}")

# base_azimuth selection
if effective_mode == "distichous":
    # Fixed 180° flip per node — divergence_angle_deg is unused here.
    base_azimuth = math.pi * node_index
elif effective_mode == "decussate":
    base_azimuth = (
        math.radians(cfg.divergence_angle_deg) * node_index
        + (math.pi / 2.0) * (node_index % 2)
    )
else:
    base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index
```

Jitter machinery (divergence_jitter_deg, branch_angle_jitter_deg) and the per-axis `branch_angle_by_order` selection both still apply unchanged. Jitter on a distichous node still uses gaussian σ on the 180° base — botanically reasonable.

### Per-axis signal

Already in the call signature: `axis_order: int`. The simulator passes `cur.axis_order` at `simulator.py:284`. `axis_order > 0` ≡ "this bud is being emitted by a lateral axis", same convention `tropisms.py` uses (`is_main_axis = (axis_order == 0)`). No new plumbing at the call site.

### Reserves

`reserve_bud_directions` is not touched. Reserves on a distichous-laterals species would still use `cfg.divergence_angle_deg`. The fir preset sets `dormant_reserve_count: 0` so no reserves are emitted; the issue is sidestepped. A separate issue can pick this up if a preset ever needs both.

## New preset: `src/palubicki/configs/species/fir.yaml`

Minimal sketch — derived from pine's structure, *not* a faithful Abies model. Goal is to demonstrate the flag and lock a new golden.

```yaml
species: fir
geom:
  # cone-ish narrow crown borrowed from pine; tune separately if needed
  ...
phyllotaxy:
  mode: alternate
  divergence_angle_deg: 137.5   # used only on the orthotropic trunk
  branch_angle_by_order: [70.0, 55.0, 40.0, 30.0]
  divergence_jitter_deg: 3.0
  branch_angle_jitter_deg: 3.0
  dormant_reserve_count: 0
  distichous_on_plagiotropic: true
tropisms:
  w_orthotropy_main: 0.6
  w_plagiotropism_lateral: 1.2   # strong — flat sprays
  ...
```

(Exact numeric values determined during implementation by copying pine, swapping the phyllotaxy block, and tuning plagiotropism until the goldens stabilise on something visually sensible. Not part of the spec contract.)

## Tests

### `tests/sim/test_phyllotaxy.py` (new tests)

- `test_distichous_yields_one_direction` — `mode="distichous"`, `axis_order=0` → shape `(1, 3)`, unit length.
- `test_distichous_alternates_180_between_successive_nodes` — call with `node_index=0` and `node_index=1` (zero jitter), assert the perpendicular projections of the two directions onto the growth axis are antiparallel (`cos < -0.999`). Repeat for `node_index=1` and `node_index=2`.
- `test_distichous_ignores_divergence_angle_deg` — two configs, `mode="distichous"` with `divergence_angle_deg=0.0` and `divergence_angle_deg=137.5`, same output (zero jitter).
- `test_distichous_on_plagiotropic_only_affects_lateral_axes` — `mode="alternate"`, `divergence_angle_deg=137.5`, `distichous_on_plagiotropic=True`:
  - `axis_order=0` follows alternate/137.5 (different at successive nodes by ~137.5°).
  - `axis_order=1` follows distichous (180° flip).

### `tests/golden/test_species_goldens.py`

- Add `"fir"` to the `@pytest.mark.parametrize` list at line 32.
- Generate `tests/golden/data/species_fir.sha256` via `pytest --update-goldens`.

### Acceptance-criterion check

- Existing oak/birch/pine/maple goldens unchanged. The new field defaults `False` and the existing presets don't set `mode: distichous`, so the if/elif tree's behavior for them is unchanged. ✓

## Data flow

```
PhyllotaxyConfig (YAML / dataclass)
  └── lateral_bud_directions(growth, cfg, node_index, seed, axis_order)
        ├── effective_mode = "distichous" if (cfg.distichous_on_plagiotropic and axis_order > 0) else cfg.mode
        ├── k = 1 if effective_mode == "distichous"
        ├── base_azimuth = math.pi * node_index   # if distichous
        └── return (k, 3) unit vectors
```

No new call sites, no new threading.

## Error handling

- Unknown mode string → `ValueError` (already raised by the existing `else` branch; covers distichous typos via YAML).
- No new error paths introduced.

## Alternatives considered

- **B. Generalized `lateral_mode: Literal[...] | None`** — any combination of modes per axis. More code, more YAML surface, no consumer beyond distichous today. Speculative.
- **C. Per-call `force_mode` override at the simulator call site** — leaks per-axis policy out of config into the simulator. Worse separation of concerns.

Chosen approach (A: scoped bool flag) is the smallest change that satisfies the issue's "nice to have" without committing to a generalised per-axis system.

## Migration notes

PoC mode, no backward compat (per project memory). All four existing presets continue to work because:
- The new `mode` Literal value is additive.
- The new `distichous_on_plagiotropic` field defaults `False`.
- The new `else if effective_mode == "distichous"` branch is unreachable from any existing preset.
