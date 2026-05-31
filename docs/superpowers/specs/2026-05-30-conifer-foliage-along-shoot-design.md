# Conifer foliage along the shoot — #36

**Date:** 2026-05-30
**Issue:** #36 (`sim: pine crown is sparse — BH winner-take-all starves laterals`)
**PR:** #51
**Status:** design approved

## Problem (re-diagnosed)

The issue's original root cause — *"Borchert-Honda winner-take-all starves laterals →
~240 internodes, sparse crown"* — **is stale.** Since #36 was filed, #43/#48
recalibrated the presets and enlarged the conifer envelopes ~6.5× with
`marker_count: 18000`. Measured today (seed 1):

| species | nodes | live apices | total_leaf_area |
|---|---|---|---|
| pine | 19,466 | 32,062 | 30.2 |
| fir  | 4,588  | 2,265  | **1.76** |
| oak  | 8,366  | 4,824  | 799 |

Pine is **not** branch-starved — it has more foliage sites than oak. Yet pine renders
as bare brown branches with scattered green tufts, and **fir renders essentially bald.**

The real mechanism is in `geom/leaves.py::_collect_foliage_sites`: foliage is emitted as
a cluster of needles **at each node** (bead-on-a-string), only on the last `foliage_depth`
(=3) internodes behind each living apex. Consequences:

1. Needles only on the outermost ~3 internodes of each tip; older shoot is bare.
   Real white pine holds needles ~2–3 yr, **balsam fir ~7–10 yr** — fir's
   `foliage_depth: 3` is far too shallow → bald.
2. Needles are beaded at nodes, never distributed *along* the shoot. A real conifer
   shoot is clothed in needles over its whole length, radiating outward — point-clusters
   at nodes cannot reproduce that.

This is therefore a **conifer foliage-modeling** problem (geom), not a BH-allocation
problem (`bh.py`). The ticket is refocused accordingly.

## Approach (B, chosen)

Distribute needle clusters *along* each leaf-bearing internode rather than beading one
cluster at its node, plus recalibrate per-species needle retention/density. This attacks
the visible root cause (shoot coverage) with a contained `geom/leaves.py` change and does
**not** build #14's `leaf_age`/`LeafState` system — needle retention stays approximated by
`foliage_depth` (in internode-steps), to be refined by #14 later.

Approaches considered and rejected:
- **A — config-only recalibration.** Bumping `foliage_depth` + density alone leaves needles
  beaded at nodes (lumpy, not continuous) and inflates pine geometry with diminishing
  coverage (apex-path dedup). Doesn't fix the root visual cause.
- **C — full needle-age/retention model tied to the clock.** Most physically grounded but
  overlaps heavily with the not-yet-done #14; building half of it now is scope creep.

B is a foundation for C, not a detour: when #14 lands, the along-shoot placement stays and
the `foliage_depth` retention proxy is swapped for true `leaf_age`.

## Design

### New geom config knob: `needle_cluster_spacing` (float, meters, default `0.0`)

- `0.0` → **legacy behavior, byte-identical**: one cluster at each leaf-bearing node.
  Broadleaves (oak/maple/birch) keep this — they are not touched.
- `> 0` → for each leaf-bearing internode, place clusters spaced every
  `needle_cluster_spacing` meters *along* the segment (parent-node → child-node), each
  oriented to the segment tangent. The shoot is clothed continuously.

### Placement detail

- "Leaf-bearing internode" = an internode within `foliage_depth` steps of a living apex —
  the **same** retention rule as today. Only the *density along* those internodes changes.
- Number of clusters on an internode of length `L`:
  `n = clamp(floor(L / needle_cluster_spacing) + 1, 1, CAP)` with `CAP = 8` to bound
  geometry. The `+1` and `min n = 1` guarantee at least the node-end cluster, so very short
  distal internodes still get one cluster.
- Cluster positions interpolate along the **bent** segment
  (`parent.position + parent.sag_offset` → `node.position + node.sag_offset`).
- `source_internode` for each cluster = that internode (feeds `sun_shade_k` size scaling).
- **Azimuth varied per cluster along the shoot** (e.g. golden-angle increment by site index)
  so needles spiral around the shoot instead of banding in one plane.

### Per-species recalibration (configs only, calibrated empirically)

The render is the acceptance test (`total_leaf_area` is an unbounded relative proxy — there
is no literature bound on it).

- **pine** (`Pinus strobus`): set `needle_cluster_spacing`; keep `foliage_depth` ~3–4
  (needles persist ~2–3 yr); tune cluster density until the crown reads full, not spindly.
- **fir** (`Abies balsamea`): set `needle_cluster_spacing`; raise `foliage_depth`
  substantially (needles persist ~7–10 yr → much deeper retained shoot). This is the bald
  case and needs the most.
- **broadleaves**: untouched (`needle_cluster_spacing` absent/`0.0`).

## Components touched

- `src/palubicki/geom/leaves.py` — `_collect_foliage_sites` (or a sibling) gains the
  along-shoot distribution path gated on `needle_cluster_spacing`; `build_leaves_primitive`
  threads the new param through.
- `src/palubicki/config.py` — `GeomConfig` gains `needle_cluster_spacing: float = 0.0`.
- `src/palubicki/geom/builder.py` — passes `cfg.geom.needle_cluster_spacing` to
  `build_leaves_primitive`.
- `src/palubicki/configs/species/pine.yaml`, `fir.yaml` — recalibrated.

## Testing

- **Regression (broadleaf guard):** with `needle_cluster_spacing == 0.0`, the foliage
  site set is identical to current behavior. Unit test on a small built tree.
- **Along-shoot count:** for a known internode of length `L` and spacing `s`, the emitted
  cluster count equals `clamp(floor(L/s)+1, 1, 8)`. Unit test.
- **Goldens:** pine/fir species goldens re-pinned (geometry changes intentionally);
  oak/maple/birch goldens asserted **unchanged**.
- **Diagnostics:** pine/fir `total_leaf_area` rises markedly; leader/architecture metrics
  (`main_axis_continuation_rate`, `leader_deviation_deg`, height, crown_radius) stay within
  their existing ✓ bounds (no regression).
- **Visual acceptance:** pine and fir renders (seed 1) read as full evergreens, not bare
  branches; no lumpy beading.

## Out of scope

- `leaf_age` / `LeafState` / clock-tied needle shedding — that is **#14**.
- BH allocation / shedding changes — branch count is already healthy.
- Broadleaf foliage — unchanged by design.

## Docs to update at completion (same PR)

- `docs/roadmap.md` — move #36 to "Fait" with PR #51; re-check ordering.
- `docs/botany/simulator-gap-analysis.md` — flip the conifer-foliage row(s); refresh
  "Last reviewed" + verdict.
- Note in the issue/PR that #36's title (BH starves laterals) was superseded by a
  foliage-modeling diagnosis.
