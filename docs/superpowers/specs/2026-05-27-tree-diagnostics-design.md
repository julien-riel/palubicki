# Tree-diagnostics harness — design

**Issue:** [#1](https://github.com/julien-riel/palubicki/issues/1) — `sim: diagnostic harness for generated tree metrics`
**Branch / PR:** `issue-1-diagnostic-harness-for-generated-tree` / [#13](https://github.com/julien-riel/palubicki/pull/13)
**Date:** 2026-05-27
**Source motivation:** `docs/botany/simulator-gap-analysis.md` §11 + Top remaining recommendations #6.

## Goal

Add a read-only diagnostic pass that, for any generated `Tree`, computes structural metrics and prints them (or writes JSON). Replaces eyeball-the-`.glb` tuning for the four species presets (oak / birch / pine / maple) now that the parameter space (Phases 2A–2D) is too wide for visual inspection.

**Out of scope** (this PR): using metrics as generator constraints; fractal dimension; pipe-model conformance; validation against external datasets.

**In scope** (this PR): all seven minimum-viable metrics from the issue, ✓/✗ literature-range flags, and multi-seed comparison mode (`--seed 0,1,2,3,4`).

## Architecture

Approach **A + C** from brainstorming:

- **A** — single-function `compute_metrics`, internal BFS walker, helper functions per metric, registry-free.
- **C** — extract `compute_effective_leaf_size` from `geom/leaves.py` so the harness and the renderer share one source of truth for sun/shade leaf scaling.

### New module: `src/palubicki/sim/diagnostics.py`

```python
@dataclass
class MetricRanges:
    """Literature-range bounds for ✓/✗ flagging.

    Each field maps to a JSON-path-like key into the compute_metrics dict
    (dotted for nested, ``[N]`` for axis-order subscripts). A path missing
    from MetricRanges = no flag rendered for that metric.
    """
    horton_bifurcation_ratio_mean: tuple[float, float] = (3.0, 5.0)
    # Per-order angle bounds — applied to metrics[path][order]["mean"].
    divergence_angle_deg__order1_mean: tuple[float, float] = (130.0, 145.0)
    insertion_angle_deg_vs_parent__order1_mean: tuple[float, float] = (30.0, 65.0)
    # Renderer / format_report maps field names back to dict paths:
    #   "horton_bifurcation_ratio_mean"            → metrics["horton_bifurcation_ratio_mean"]
    #   "divergence_angle_deg__orderN_mean"        → metrics["divergence_angle_deg"][N]["mean"]
    #   "insertion_angle_deg_vs_parent__orderN_mean" → metrics["insertion_angle_deg_vs_parent"][N]["mean"]

DEFAULT_RANGES = MetricRanges()

def compute_metrics(
    tree: Tree | list[Tree],
    *,
    cfg: Config | None = None,
) -> dict:
    """Overloaded:
      - Tree            → flat dict per the schema below
      - list[Tree]      → aggregated dict (mean / stddev / per_seed at each leaf)
    cfg is optional; only consumed by total_leaf_area (geom params).
    """

def format_report(
    metrics: dict,
    *,
    ranges: MetricRanges = DEFAULT_RANGES,
    seeds: list[int] | None = None,
    species: str | None = None,
) -> str:
    """Pretty-prints the dict from compute_metrics. Auto-detects single vs multi
    by looking for the {"mean", "stddev", "per_seed"} envelope at scalar keys."""
```

### Refactor: `src/palubicki/geom/leaves.py`

Extract the existing inline math into a public helper:

```python
def compute_effective_leaf_size(
    internode: Internode | None,
    leaf_size: float,
    sun_shade_k: float,
) -> float:
    """Same clamping as build_leaves_primitive. Called by both the renderer
    and the diagnostics harness so leaf-area accounting stays consistent."""
```

`build_leaves_primitive` is rewritten to call this helper. **No behaviour change to the .glb path** — guarded by a test that builds the leaves primitive before and after and asserts identical positions array.

### New CLI subcommand: `palubicki diagnose`

```
palubicki diagnose --species oak --seed 0
palubicki diagnose --species oak --seed 0,1,2,3,4    # multi-seed
palubicki diagnose --species oak --seed 0 --json     # machine-readable
palubicki diagnose --config path/to.yaml --seed 0
palubicki diagnose                                     # generic defaults
```

Mirrors `_cmd_generate` for config loading. No `-o/--output` — the report goes to stdout, errors and the seed/species echo banner go to stderr (so `--json > foo.json` produces clean JSON).

### Cost

O(N) per metric (Strahler is O(N) via memoization). All metrics computed in one BFS walk + one Strahler bottom-up pass. No mutation of `Tree` state.

## Metric schema

For a single `Tree`, `compute_metrics` returns:

```python
{
    # Strahler / Horton — operates on the internode tree
    "strahler_order_max": int,
    "strahler_order_histogram": dict[int, int],
    "horton_bifurcation_ratio": dict[int, float],   # {N: count(N)/count(N+1)}
    "horton_bifurcation_ratio_mean": float,         # geometric mean across orders

    # Angles — per child axis_order; observed (computed from internode geometry)
    "insertion_angle_deg_vs_parent": dict[int, {"mean": float, "stddev": float, "n": int}],
    "insertion_angle_deg_vs_main_sibling": dict[int, {"mean": float, "stddev": float, "n": int}],
    "divergence_angle_deg": dict[int, {"mean": float, "stddev": float, "n": int}],

    # Counts
    "sympodial_fork_count": int,
    "bud_state_histogram": dict[str, int],   # "ACTIVE"/"DORMANT"/"DEAD"/"RESERVE" → count

    # Architecture
    "tree_height": float,                    # max y (with sag_offset) over all nodes
    "trunk_base_diameter": float,            # diameter of internode whose parent_node == root
    "crown_radius": float,                   # max sqrt(x²+z²) over nodes with y > 0.4*height
    "total_leaf_area": float,                # sum across foliage sites (per geom/leaves.py)
}
```

For `list[Tree]`, every scalar leaf wraps to `{"mean", "stddev", "per_seed": [...]}`; every per-order dict (insertion/divergence) wraps key-by-key. The `n` value inside angle stats stays as per-seed measurement count (the count of measurements *within* one tree at that order — not the seed count). Axis orders present in some seeds but missing from others get `per_seed: [val, ..., None, ...]`; mean/stddev are computed over the non-None subset. Axis orders missing from all seeds are omitted entirely.

## Semantic rules (locked)

1. **Strahler tree** = internode tree rooted at `tree.root`. Each `Internode` is a node in the Strahler graph; `child_node.children_internodes` defines successors. Leaf internodes get order 1. Parent order = `max(child_orders)` if max is unique; else `max + 1`. Sympodial-promoted bud transfer does not change the Strahler graph (no internodes added/removed by promotion itself).

2. **Bud histogram walks all `Node`s**, BFS from root via `children_internodes`. At each node, collect `terminal_bud`, `lateral_buds`, `dormant_reserve_buds`. `tree.active_buds` is a fast index, not the canonical store; relying on it alone would silently undercount DORMANT / DEAD / RESERVE.

3. **Insertion angle** at child internode L hanging off node N:
   - `vs_parent` = angle between L's tangent and `N.parent_internode`'s tangent. Skipped when `N.parent_internode is None` (L is on the root node).
   - `vs_main_sibling` = angle between L's tangent and the unique sibling C in `N.children_internodes` with `is_main_axis=True` (with L itself excluded from the sibling search). Skipped when no such sibling exists (e.g. terminal-only fork, or sympodial mid-promotion).
   - Both are grouped by **L's `axis_order`**.
   - Tangent for any internode I = `normalize(I.child_node.position - I.parent_node.position)`. Bent positions (with `sag_offset`) are NOT used here — insertion angles are measured against the topological geometry (the simulator's intent), not the post-sag bent geometry. (Sag distortion of angles is a separate concern.)

4. **Divergence angle**: for each axis (maximal chain of internodes sharing one `axis_order`, linked through `is_main_axis=True` continuation), collect the lateral child internodes that hang off the axis in chain order. For each consecutive lateral pair `(L_i, L_{i+1})`:
   - Let `T` = axis tangent at `L_i`'s parent node, computed as the tangent of the incoming internode at that node (or the chain's first-internode tangent if at the chain's base).
   - Build the in-plane basis `(right, up)` via `_frame_perpendicular_to(T)` — the same helper that `sim/phyllotaxy.py` uses to place lateral buds. This guarantees the harness measures angles in the same basis the simulator generated them in.
   - Project each lateral's tangent onto the `(right, up)` plane; compute its azimuth `az_i = atan2(proj · up, proj · right)`.
   - The divergence is `(az_{i+1} − az_i) mod 360°`.
   Group results by **the lateral's `axis_order`**. Axes with fewer than 2 laterals contribute nothing.

5. **Tree height**: `max((node.position + node.sag_offset)[1])` over all nodes. Uses bent positions because that's the rendered height.

6. **Trunk base diameter**: the `Internode` with `parent_node is tree.root`. When multiple exist (rare but possible), takes the max diameter. When the root has no `children_internodes` (degenerate / one-node tree), returns `0.0`.

7. **Total leaf area**: walks `_collect_foliage_sites(tree, cfg.geom.foliage_depth)` from `geom/leaves.py`. Per site:
   - `eff_size = compute_effective_leaf_size(source_internode, cfg.geom.leaf_size, cfg.geom.leaf_sun_shade_k)`
   - per-site area = `2 * cfg.geom.leaf_cluster_count * eff_size² * cfg.geom.leaf_aspect`
     (2 quads per cluster × cluster_count clusters; quad u-dim = `size * aspect`, v-dim = `size`).
   - Sum across sites.
   When `cfg is None`, returns `0.0` and the report shows `total_leaf_area  — (leaf cfg not provided)`.

## Report layout

Single-seed:

```
palubicki diagnose — species: oak, seed: 0
========================================================================

Architecture
  tree_height           5.42 m
  trunk_base_diameter   0.18 m
  crown_radius          2.91 m       (band: y > 2.17 m)
  total_leaf_area       12.4 m²

Strahler / Horton
  order_max             4
  histogram             {1:78, 2:18, 3:5, 4:1}
  bifurcation_ratio     1→2: 4.33   2→3: 3.60   3→4: 5.00
  bif_ratio_mean        4.27  ✓     (expected 3.0–5.0)

Angles (observed, by child axis_order)
  order  insertion (vs parent)   insertion (vs main sib)   divergence
  1      52.1° ± 6.4° (n=18)     48.3° ± 7.1° (n=14)       137.4° ± 9.2° (n=12)  ✓
  2      48.7° ± 9.8° (n=27)     45.1° ± 11.0° (n=21)      135.8° ± 14.6° (n=19) ✓
  3      44.2° ± 12.1° (n=11)    —                          —

Counts
  sympodial_forks       3
  buds                  ACTIVE: 24   DORMANT: 7   DEAD: 12   RESERVE: 5
```

Multi-seed:

```
palubicki diagnose — species: oak, seeds: [0,1,2,3,4]
========================================================================

Architecture                     mean        stddev      ✓/✗
  tree_height                    5.31 m      0.18 m
  trunk_base_diameter            0.17 m      0.01 m
  crown_radius                   2.84 m      0.21 m
  total_leaf_area                11.9 m²     0.8 m²

Strahler / Horton                mean        stddev      ✓/✗
  bif_ratio_mean                 4.18        0.41        ✓

Angles                           mean        stddev      ✓/✗
  insertion_deg (vs parent)
    order 1                      51.7°       1.2°
  divergence_deg
    order 1                      136.9°      2.3°        ✓

Counts                           mean        stddev
  sympodial_forks                3.4         1.1
  buds.DEAD                      11.6        2.1
```

`--json` skips `format_report` and dumps the raw metrics dict via `json.dumps(metrics, indent=2)`.

## Error handling

**Degenerate trees never raise:**
- Root-only tree → all histograms empty, `strahler_order_max=0`, angle dicts empty, `tree_height=root.position[1]`, all other floats `0.0`.
- One-internode tree → `strahler_order_max=1`, histogram `{1:1}`, empty bifurcation_ratio dict, no angles.
- Axis with one lateral → contributes nothing to divergence.
- Axis order absent from any internode → key absent from angle dicts (not `n=0`).

**When `cfg is None`** → `total_leaf_area=0.0` and report shows `— (leaf cfg not provided)`. Other metrics unaffected.

**Reference-range flags**: `✓` if `min ≤ value ≤ max`, `✗` otherwise. NaN / undefined → `—`. For multi-seed, flag computed against the *mean*.

**CLI exit codes** (matches `_cmd_generate`):
- `0` — metrics printed.
- `1` — runtime error during `simulate` or a bug in the harness.
- `2` — config error or invalid CLI argument (`--seed 0,foo`).

**`--seed` parsing**: custom argparse type `_parse_seed_list` accepting `"N"` or `"N,M,…"`. Invalid integers → argparse error (exit 2).

**Stdout vs stderr**: report → stdout. Banner + errors → stderr.

## Testing strategy

### Unit tests on hand-built trees (`tests/sim/test_diagnostics.py`)

Hand-built fixtures (no `simulate`) — expected values are obvious by inspection.

1. `test_strahler_known_small_tree` — Y-shape: orders `{1:2, 2:1}`. Then a deeper pectinate tree where the unique-max rule matters.
2. `test_strahler_single_internode` — `{1:1}`, empty bifurcation dict.
3. `test_strahler_empty_tree` — `order_max=0`, all dicts empty.
4. `test_insertion_angle_vs_parent_at_known_geometry` — trunk +Y, lateral 45° in XZ → mean 45°, stddev 0, n=1.
5. `test_insertion_angle_vs_main_sibling` — main-axis sibling at +Y, lateral 60° off → `vs_main_sibling=60°`, distinct from `vs_parent`.
6. `test_divergence_angle_known_pair` — two laterals at azimuth 0° and 137.5° → `mean=137.5°`.
7. `test_bud_state_histogram_walks_all_nodes` — DORMANT bud on a non-active-list node is counted.
8. `test_sympodial_count_uses_node_flag` — manual `sympodial_fork=True` set on N nodes, assert count.
9. `test_height_uses_sag_offset` — node y=5, sag y=−0.4 → height 4.6.
10. `test_crown_radius_band_only` — wide low node below threshold ignored; narrower high node defines crown_radius.
11. `test_leaf_area_matches_geom_helper` — build the leaves primitive, then sum the actual quad areas directly from its `positions` array (each quad = two triangles, area via cross-product of edge vectors). Independently call `compute_metrics(tree, cfg=cfg)["total_leaf_area"]`. Assert equality to within float epsilon. This is a real cross-check because the test computes area from rendered geometry, not from the same helper the harness uses.
12. `test_compute_metrics_accepts_list_of_trees` — `[t1, t2]` known by hand; assert mean/stddev for one scalar metric.

### Integration / sanity tests

13. `test_bifurcation_ratio_in_sane_range_per_species` (acceptance criterion) — for oak/birch/pine/maple with seed 0, assert `2.5 ≤ horton_bifurcation_ratio_mean ≤ 6.0`.
14. `test_diagnostics_doesnt_mutate_tree` (acceptance criterion) — snapshot internode count, root id, etc., call `compute_metrics`, assert unchanged. Existing goldens still pass untouched (no goldens deleted).
15. `test_compute_effective_leaf_size_extraction_preserves_geom_output` — build leaves primitive before-and-after the C refactor (parametrized over one species); assert identical positions array.

### CLI tests (`tests/test_cli.py`)

16. `test_cli_diagnose_single_seed_runs` — exit 0, stdout contains "tree_height" and "bifurcation_ratio".
17. `test_cli_diagnose_json` — stdout parses as JSON; expected keys present.
18. `test_cli_diagnose_multi_seed` — `--seed 0,1,2` → stdout contains "mean" and "stddev" headers, exit 0.
19. `test_cli_diagnose_bad_seed_list` — `--seed 0,foo` → exit 2.

### No new goldens

Diagnostics is read-only. The only thing that could regress visually is `build_leaves_primitive` after the C extraction; that's covered by test #15.

### TDD order

Each test red → impl → green, in this sequence:
1. Strahler (#1–#3)
2. Angles (#4–#6)
3. Aggregation helpers (#7–#10)
4. `compute_effective_leaf_size` extraction → `total_leaf_area` → #11 + #15
5. Multi-seed (#12)
6. Integration #13–#14
7. CLI #16–#19

## Acceptance-criteria mapping

| Criterion | Covered by |
|---|---|
| `compute_metrics(tree)` returns all minimum-viable keys | Metric schema above + tests #1–#11 |
| `palubicki diagnose --species oak --seed 0` prints all metrics | CLI section + test #16 |
| Strahler unit-tested against a known small tree | Tests #1–#3 |
| Bifurcation ratio in [2.5, 6.0] for each preset | Test #13 |
| No change to `simulate(...)` or any existing golden | Diagnostics is read-only by construction + test #14 + no goldens deleted |
