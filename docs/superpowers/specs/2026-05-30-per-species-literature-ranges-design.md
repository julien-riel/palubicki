# Per-species literature ranges + config tuning — design

**Issue:** #32 (extension) · **Date:** 2026-05-30 · **Branch:** `issue-32-metricranges-literature-manifest`

## Goal

Close the loop **cited manifest → per-species diagnostic → config tuning →
re-diagnose** so each `src/palubicki/configs/species/*.yaml` generates a tree
whose *measured* metrics fall inside literature-sourced bounds. Today only
`maple` has a single per-species bound (decussate divergence); the rest of
`ranges.species` is empty.

## Scope

In: the 5 existing species (`birch fir maple oak pine`), realigned to North
American taxa. Bounds are filled by **real extraction** (CSV exports the user
drops in + public-domain PDF tables the fetch script downloads). Configs are
tuned until `diagnose --species X` is mostly ✓ on the *measured* metrics.

Out: extending `compute_metrics` to measure leaves/mechanics (separate issue).
Leaf + mechanical/environmental data enter the manifest as cited **reference**
data (not flagged) for manual tuning.

## Key constraint discovered

`diagnose` can only flag a bound when `compute_metrics` actually produces the
metric. Live audit of `compute_metrics` output keys:

| Category | Measured? | Metrics |
|---|---|---|
| Angles & phyllotaxy | ✅ | `divergence_angle_deg`, `insertion_angle_deg_vs_parent`, `insertion_angle_deg_vs_main_sibling` (by order) |
| Architecture | ✅ | `tree_height`, `trunk_base_diameter`, `crown_radius`, `internode_length_*`, `strahler_order_max`, `horton_bifurcation_ratio_mean` |
| Leaves | ⚠️ partial | only `total_leaf_area`; length/width/shape/arrangement are config *inputs*, not measured outputs |
| Mechanics/environment | ❌ | none (no MOE, wood density, climate in `compute_metrics`) |

→ Flagged bounds = angles + architecture only. Leaves/mechanics = `reference:`.

## Species realignment (EU → NA)

To match the best free PDF sources (Silvics of North America, Wood Handbook):

| config | was (EU) | now (NA) |
|---|---|---|
| birch | Betula pendula | **Betula papyrifera** |
| oak | Quercus robur | **Quercus rubra** |
| pine | Pinus sylvestris | **Pinus strobus** |
| maple | Acer campestre | **Acer saccharum** |
| fir | Abies (vague) | **Abies balsamea** |

The config→latin map lives in the manifest under `species_latin:` as the single
source of truth shared by fetch/extract and docs. Header comments in each
`species/*.yaml` updated to the NA name.

## Architecture / data flow

```
Sources (CSV the user drops in cache + PDF Silvics/Wood Handbook fetched)
   │  extract_botany_values.py  (filter by latin name → percentile band)
   ▼
literature.yaml  ranges.species.{birch,fir,maple,oak,pine}
   │  MetricRanges.from_species(name)   [already in place]
   ▼
diagnose --species X  →  ✓/✗ per metric
   │  (manual config tuning via metric→lever map below)
   ▼
species/X.yaml  →  re-simulate  →  re-diagnose  →  converge
```

## Manifest schema

```yaml
species_latin:
  oak: "Quercus rubra"
  # ...the 5 mappings

ranges:
  global: { ... }                 # unchanged defaults
  species:
    oak:                          # Quercus rubra
      # flagged bounds — keys are MetricRanges fields, measured by compute_metrics
      divergence_angle_deg__order1_mean: {value: [130,145], source: abop, page: "..."}
      tree_height:                       {value: [18,28],   source: silvics, page: "..."}
      trunk_base_diameter:               {value: [0.3,0.9], source: silvics, page: "..."}
      crown_radius:                      {value: [6,12],    source: silvics, page: "..."}
      # cited reference — NOT flagged (leaves, mechanics, environment)
      reference:
        leaf_length_cm:    {value: [10,20],   source: flora_na,      page: "..."}
        leaf_width_cm:     {value: [8,15],    source: flora_na,      page: "..."}
        wood_density_g_cm3:{value: [0.56,0.66],source: wood_density,  page: "..."}
        moe_gpa:           {value: [9,13],    source: wood_handbook, page: "Table 5-3a"}
        hardiness_zone:    {value: [3,8],     source: silvics,       page: "..."}
```

- `reference:` is inert in `from_species` — the merge already keeps only keys
  that are `MetricRanges` fields. No code change needed for it to stay ignored.
- `tree_height` / `trunk_base_diameter` / `crown_radius` become flaggeable:
  `format_report` already reads them via `_bounds_for(ranges, k)` (diagnostics.py
  ~line 656), so the only code change is **adding these 3 fields to the
  `MetricRanges` dataclass** (optional bounds, default `None`). No `format_report`
  change.
- Units are explicit in `reference` keys (`_cm`, `_g_cm3`, `_gpa`).

## Extractors

`extract_botany_values.py` gains a registry of extractors per (source × metric),
each filtering by latin name and reducing to a percentile band:

```python
def _extract_<source>(cache, species_latin) -> list[Proposal]:
    rows = _read_csv / _read_pdf_table(...)
    for cfg_name, latin in species_latin.items():
        vals = [obs for rows matching latin]
        lo, hi = range_from_values(vals, lo_pct=10, hi_pct=90)
        yield Proposal(field, species=cfg_name, value=(lo, hi), source, page)
```

| Source | Access | Metrics → manifest field |
|---|---|---|
| wood_density (CSV) | user drops in cache | `reference.wood_density_g_cm3` |
| wood_handbook (PDF) | fetch downloads | `reference.moe_gpa` (Table 5-3) |
| silvics (PDF/HTML) | fetch downloads | `tree_height`, `crown_radius`, `trunk_base_diameter`, `reference.hardiness_zone` |
| baad (CSV) | user drops in cache | `tree_height`, `crown_radius` (corroborate) |
| flora_na (semi-structured) | manual/hand | `reference.leaf_length_cm`, `leaf_width_cm` |
| abop / phyllotaxy | already cited | `divergence_angle_deg__order1_mean` by mode |

Guardrails: `--only <source>` runs extractors as CSVs arrive; a missing source
returns `[]` and `log`s what was skipped (no silent cap). Divergence-by-mode is a
botanical constant (decussate ~90°, spiral ~137.5°, distichous ~180°, whorled per
`whorl_count`), cited to ABOP — not a fake file extractor.

## Metric → config-lever map (tuning guide, not a solver)

| Metric (measured) | Primary config lever(s) | Direction |
|---|---|---|
| `tree_height` | `envelope.ry`, `sim.max_simulation_years`, `shoot_extension_max`, `vigor_ref` | envelope caps height; years/vigor fill it |
| `crown_radius` | `envelope.rx`/`rz` | horizontal envelope radius |
| `trunk_base_diameter` | `geom.pipe_exponent`, `sim.vigor_diameter_gain` | pipe-model exponent → cumulative diameter |
| `divergence_angle__order1` | `phyllotaxy.mode` + `divergence_angle_deg` | decussate/spiral/distichous |
| `insertion_angle__order1` | `phyllotaxy.branch_angle_by_order[0]` | first-order insertion angle |
| `internode_length_*` | `shoot_extension_max`, `vigor_ref`, `elongation.tau_years` | Borchert-Honda flux |
| `horton_bifurcation_ratio` | `lambda_apical`, `alpha_basipetal`, `shedding.*` | apical dominance / pruning |

This map goes in this doc + a header comment in each `species/*.yaml`. Tuning is
manual: read ✗ → adjust lever → re-simulate → repeat.

Caveat: `crown_radius` follows the envelope, so calibrating it to Silvics mostly
means **sizing the envelope from literature** — legitimate and on-goal, but these
bounds validate envelope realism rather than an emergent property.

## Tests (TDD)

- `range_from_values` with latin filter: synthetic multi-species CSV → correct
  per-species percentile band.
- `MetricRanges` new fields: `from_species("oak")` returns bounded
  `tree_height`/`crown_radius`/`trunk_base_diameter`; `reference:` stays ignored.
- Each `species/*.yaml` loads and has a `ranges.species.<name>` entry.
- Regression: `not slow` suite stays green.

## Deliverables

1. `MetricRanges` + 3 architectural fields.
2. `literature.yaml`: `species_latin:`, 5 NA species, flagged bounds + `reference:`.
3. `extract_botany_values.py`: per-source extractor registry, latin filter.
4. 5 tuned `species/*.yaml` + lever-map header comment; NA header names.
5. This design doc + `sources.md` update.

## Success criteria

Angles + height/crown mostly ✓ across the 5 species; `bifurcation_ratio`
"in-band or justified". Final diagnostic is honest about what does not converge.

## Known dependency

Structured DBs have no stable direct-file URL (BAAD via R package, wood-density
via Dryad file API, TRY via data request). The user supplies CSV exports into
`docs/botany/sources/`; the script codes the extractors and runs them for real.
PDF sources (Silvics, Wood Handbook) are fetchable directly.
