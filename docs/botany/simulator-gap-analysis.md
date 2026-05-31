# Simulator Gap Analysis vs. Botanical Reference

*Companion to [plant-structure.md](./plant-structure.md). For each concept in sections 1–11 of the reference, this document reports: status in the current simulator, whether it should be modeled, the realism payoff, the performance cost, and a recommendation.*

*Primary literature (download links + code mapping): [sources.md](./sources.md).*

**Code root:** `src/palubicki/`. Species presets currently shipped: **oak**, **birch**, **pine**, **maple**.

**Last reviewed:** 2026-05-30, after the **geometric leader-verticality metric** ([#48](https://github.com/julien-riel/palubicki/issues/48)) added the leader-orientation guard to the diagnostic net (§11) and the species golden test was moved to representative marker density (the #43 "conifer-leader regression" was an artifact of the golden's 1000-marker proxy under-sampling #43's enlarged conifer envelopes ~18×, not a preset defect — at design density the leaders stand upright). Prior review 2026-05-30, after the **main-axis continuation / excurrent-index metric** ([#40](https://github.com/julien-riel/palubicki/issues/40)) added the leader-dominance guard to the diagnostic net (§11). Prior review 2026-05-29, after root flare ([issue #8](https://github.com/julien-riel/palubicki/issues/8)), true distichous phyllotaxis ([#15](https://github.com/julien-riel/palubicki/issues/15)), the diagnostic harness ([#13](https://github.com/julien-riel/palubicki/issues/13)), bark variation by `Internode.diameter` ([#9](https://github.com/julien-riel/palubicki/issues/9)), and the **time / phenology foundation** ([#10](https://github.com/julien-riel/palubicki/issues/10)) all landed on `main`.

> **Cross-cutting review (2026-05-29, [../2026-05-29-codebase-review.md](../2026-05-29-codebase-review.md)).** Surfaced a **phyllotaxis per-axis delivery defect**: the divergence azimuth was keyed on a *global* `node_index` shared across all bud chains, so successive-node divergence was scrambled on the real tree even though each mode was correct in the function. **Fixed** ([#24](https://github.com/julien-riel/palubicki/issues/24)) — divergence is now driven by a per-axis ordinal (`Bud.axis_node_ordinal`), with the per-axis regression test ([#25](https://github.com/julien-riel/palubicki/issues/25)) landing alongside it as `tests/sim/test_phyllotaxy_per_axis.py`. See §5. (The review also filed the software-side [#26](https://github.com/julien-riel/palubicki/issues/26) — recursive config loader, **landed** in [PR #30] — out of scope for this botanical doc.)

> **Botanical + engineering evaluation (2026-05-29).** First audit of the `geom→render→export` layer. Two botanical items filed: **epinasty / time-dependent plagiotropic reorientation** ([#34](https://github.com/julien-riel/palubicki/issues/34), §4) and a **whorled inter-whorl rotation defect** ([#35](https://github.com/julien-riel/palubicki/issues/35), §5 — pine's whorls stack into 5 vertical ranks instead of interleaving; **since fixed**, PR #39). A third, geometry-side finding is tracked separately, out of scope for this botanical doc: **inverted triangle winding** ([#33](https://github.com/julien-riel/palubicki/issues/33)) — every tube/obstacle face winds opposite to its outward normal, so the single-sided bark back-faces out and is culled by any conformant glTF viewer (confirmed on `pine2.glb`: 23 312 / 23 320 bark faces inward).

## What changed since the 2026-05-28 review

All merged to `main` via the issue tracker:

- **Time / phenology axis — Phase 1 foundation** (`sim/clock.py` + `config.py` + `sim/simulator.py` + `sim/elongation.py` + `sim/tree.py`, [issue #10](https://github.com/julien-riel/palubicki/issues/10) / [PR #23](https://github.com/julien-riel/palubicki/pull/23)) — the simulator now advances in fractional years instead of bare iterations. A `Clock` (`dt_years`, `t`) threads through the forest loop; `sim.max_iterations` is replaced by `dt_years` + `max_simulation_years` (with a derived `num_iterations`); `Internode.birth_iteration` → `birth_time` (years) and `ElongationConfig.tau_iterations` → `tau_years`; the vestigial `Bud.age` was removed. A per-species `sim.annual_growth_period = [lo, hi)` (year fractions) gates growth to a window — outside it the tree only ages (elongation/diameters/sag), emits nothing, and does not trip the saturation early-stop. The `iteration`-vs-`t` split keeps integer `iteration` for RNG seeding/identity and float `t` for biological time, so at `dt_years=1.0` trees are bit-identical (all goldens, incl. the pinned bit-exact RNG test, unchanged). **This is the foundation the deciduousness / leaf-age / epinasty / flowering work was waiting on.**
- **Bark variation by `Internode.diameter`** (`geom/bark_blend.py` + `config.py` + `export/gltf.py`, [issue #9](https://github.com/julien-riel/palubicki/issues/9) / [PR #22](https://github.com/julien-riel/palubicki/pull/22)) — three-way bark tint (young → mature → senescent) carried as a per-vertex `COLOR_0` blend over the single bark texture, driven solely by `Internode.diameter`: pale smooth bark on thin twigs, dark fissured bark on thick limbs. Stops calibrated to the sim's actual internode-diameter scale (~1.5–8.6 cm). Presence-gated (off ⇒ byte-identical output); on by default for all five species, with mature tint = each species' prior `bark_color`.
- **Diagnostic / validation harness** (`sim/diagnostics.py`, [issue #13](https://github.com/julien-riel/palubicki/issues/13)) — `compute_metrics` over one or many trees: Strahler/Horton bifurcation ratios, per-order divergence & insertion angles, bud-state histogram, sympodial fork count, height/crown radius, trunk base diameter, total leaf area. Multi-seed aggregation plus literature-range ✓/✗ flagging via `MetricRanges`/`format_report`. This was the highest-priority remaining item in §11.
- **True distichous phyllotaxis** (`sim/phyllotaxy.py` mode `"distichous"`, [issue #15](https://github.com/julien-riel/palubicki/issues/15)) — single bud per node, 180° alternation between successive nodes. The `distichous_on_plagiotropic` flag auto-switches plagiotropic (order > 0) axes to distichous, so conifer side-sprays form a flat 2-ranked plane — the exact fix §5/§10 flagged.
- **Root flare at trunk base** (`geom/tubes.py` + `config.py`, [issue #8](https://github.com/julien-riel/palubicki/issues/8) / [PR #21](https://github.com/julien-riel/palubicki/pull/21)) — per-vertex radius field at the trunk base, optional azimuthal buttress ridges with a welded seam, per-tree variation; `root_flare_height/factor/falloff`, `root_buttress_count/amplitude`, `root_flare_variation` config fields with per-species defaults. Pure render-time; the sim layer is untouched.
- **Cross-blade leaf fix** ([issue #18](https://github.com/julien-riel/palubicki/issues/18), follow-up to [#4](https://github.com/julien-riel/palubicki/issues/4)) — cross-blade geometry now only for linear (needle) shapes.
- **Tooling** ([PR #19](https://github.com/julien-riel/palubicki/pull/19), non-issue) — ruff config + GitHub Actions CI + simulator refactor.


## Earlier — Phases 2A–2D (2026-05-28 review)

Phases 2A–2D were merged. Concretely, the following moved from ❌/🟡 to ✅:

- **Parametric leaf blade** (`geom/leaf_blade.py`) — 6 shapes × 4 margins replace cross-quad rectangles. Each species now has a distinct silhouette.
- **Sympodial branching** (`sim/sympodial.py`) — terminal bud failure promotes a lateral.
- **Plagiotropism** (`sim/tropisms.py` `w_plagiotropism_main/_lateral`) — projects direction onto XY plane.
- **Per-branch-order angles** (`phyllotaxy.branch_angle_by_order`).
- **Decussate phyllotaxy** (`sim/phyllotaxy.py` mode `"decussate"` with π/2 alternation between successive pairs).
- **Sun/shade leaf morphology** (`geom.leaf_sun_shade_k` + `Internode.light_factor`).
- **Time-stepped trunk thickening** (`sim/radii.py::update_diameters_incremental`, called per iteration, idempotent).
- **Progressive internode elongation** (`sim/elongation.py` — sigmoid ramp per internode based on `birth_time` and `length_target`; `birth_iteration` was renamed to `birth_time` in years by Phase 1 [#10](https://github.com/julien-riel/palubicki/issues/10)).
- **Idempotent sag** (`sim/sag.py` writing `Node.sag_offset`).
- **Bud lifecycle**: `BudState.RESERVE`, `Bud.low_quality_steps`, `Bud.low_light_steps`, shade mortality (`sim/shade_mortality.py`), reiteration from reserves (`sim/reiteration.py`).
- **Maple** species preset (decussate + sympodial + reiteration + plagiotropism + sun/shade leaves).

Items still pending are explicitly called out in each section's table and re-aggregated at the end.

---

**Legend**

| Symbol | Status |
|---|---|
| ✅ | Present and used |
| 🟡 | Partial / weak / present only as approximation |
| ❌ | Absent |

| Δ column | Meaning |
|---|---|
| ⬆ Implemented | Was ❌ in v1, now ✅ |
| ⬆ Promoted | Was 🟡 in v1, now ✅ |
| ⬆ Strengthened | Was 🟡 in v1, still 🟡 but materially improved |
| 🆕 Added | New field or subtopic that didn't exist in v1 |
| = | Unchanged since v1 |

| Field | Meaning |
|---|---|
| **Realism gain** | Visible impact on a generated tree if added/fixed. H/M/L. |
| **Perf cost** | Runtime/memory cost of doing it well. L/M/H. |
| **Recommendation** | `ADD`, `IMPROVE`, `SKIP`, `LATER`, or `DONE`. |

---

## §1 — Conceptual framework (modularity, recursion, local rules)

Still nothing to do — the simulator follows all three principles. **Reinforced** by Phase 2D: the per-iteration recomputation of radii, lengths, and sag now genuinely treats each step as a local re-application of rules, no global passes.

---

## §2 — The modular body plan: the phytomer

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Phytomer = node + internode + leaf(s) + bud(s) as one logical unit | 🟡 | = | `sim/tree.py`: `Node`, `Internode`, `Bud` separate; leaves still synthesized at render time in `geom/leaves.py` | M | L | **IMPROVE** ([#14](https://github.com/julien-riel/palubicki/issues/14)) — leaves are still not first-class node attributes. Largest single architectural gap; blocks deciduousness, per-leaf age, and seasonal rendering. Phase 1 (time/phenology, [#10](https://github.com/julien-riel/palubicki/issues/10)) **landed**, so `LeafState` can now be designed on a real calendar (`leaf_age` in years) the first time — see end of doc. |
| Internode with length + radius | ✅ | 🆕 strengthened | `Internode.length`, `Internode.diameter`; also now `light_factor`, `birth_time` (years, Phase 1 [#10](https://github.com/julien-riel/palubicki/issues/10)), `length_target` (Phase 2D) | — | — | — |
| Axillary buds in axils | ✅ | ⬆ strengthened | `Node.lateral_buds`; states now `ACTIVE`, `DORMANT`, `DEAD`, `RESERVE` (Phase 2B); also `Bud.low_quality_steps`, `low_light_steps` | — | — | — |
| Terminal/apical bud | ✅ | = | `Node.terminal_bud` | — | — | — |
| Dormant reserve buds (preformed) | ✅ | 🆕 | `Node.dormant_reserve_buds: List[Bud]` (Phase 2B) — separate from active laterals, activated by `reiteration.py` | M | L | — |
| Stipules | ❌ | = | — | L | L | **SKIP** |
| Phytomer wrapper object | ❌ | = | — | L | L | **SKIP** |

**Verdict.** Skeleton is correct and now richer (per-internode time/light state, RESERVE buds). The single unresolved gap is still **leaves not living on the structure** — every realism feature for foliage (per-leaf age, abscission, marcescence, autumn color) is blocked until that lands. Best done jointly with seasonal cycles.

---

## §3 — Meristems: the engines of growth

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Apical meristem | ✅ | = | terminal bud + the `Clock`-driven `simulate_forest` loop (`simulator.py`, `range(cfg.sim.num_iterations)`) | — | — | — |
| Axillary meristems | ✅ | ⬆ strengthened | richer state machine (Phase 2B) — ACTIVE / DORMANT / DEAD / RESERVE | — | — | — |
| Bud break / release rule | 🟡 | ⬆ strengthened | Activation still implicit through BH allocation, but the lifecycle on the other end is now explicit: `shade_mortality.kill_shaded_buds` (Phase 2B) and `reiteration.activate_reserves_on_shed` (Phase 2B) close the loop on dormancy/death. | M | L | **IMPROVE** — the "missing piece" is now upstream: still no explicit bud-break probability for *initial* activation. Acceptable for now; revisit only if shrub presets need fine control. |
| Reiteration (replacing shed branches from reserves) | ✅ | ⬆ Implemented | `sim/reiteration.py`; activated by `shedding.reactivation_count` | M | L | **DONE** — this also partially substitutes for one role of determinate growth (it lets trees recover from canopy damage). |
| Intercalary meristems (grasses, basal growth) | ❌ | = | — | H (grasses) | L | **LATER** — gates monocots. |
| Lateral / cambium meristem (secondary growth) | ✅ | ⬆ Promoted | `radii.update_diameters_incremental` (Phase 2D) — called each iteration, idempotent. Pipe model with exponent ~2.49. | — | — | **DONE** — thickening now visible during growth; feeds `sag.py` in-flight. |
| Annual rings | ❌ | = | — | L | M | **SKIP** |
| Determinate vs indeterminate growth | ❌ | = | — | M | L | **ADD** ([#11](https://github.com/julien-riel/palubicki/issues/11)) when flowers land — gates flowering, fruits, herbaceous forbs, and proper sympodial trees (right now sympodial fires on *quality failure*, not deliberate apex termination). |

**Verdict.** Big win in this section: cambium and reiteration both landed. The two remaining gaps are (a) **intercalary meristems for grasses** (no urgency until monocots are scoped) and (b) **determinate growth** (couple it with the flower bundle).

---

## §4 — Branching architecture

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Monopodial branching | ✅ | = | `Internode.is_main_axis` | — | — | — |
| Sympodial branching | ✅ | ⬆ Implemented | `sim/sympodial.py::promote_lateral_if_failing` (Phase 2A) — when terminal bud `low_quality_steps` ≥ threshold, the best lateral is promoted to terminal, axis_order inherited. `Node.sympodial_fork` flag records each event. | — | — | **DONE** (with caveat) — current trigger is *quality failure*, not deliberate apex termination. Adequate for broadleaf woody trees; will need a second pathway (`apex differentiated to flower → terminate`) when flowering lands. |
| Apical dominance | ✅ | = | `sim/bh.py` Borchert–Honda; `lambda_apical` per species | — | — | — |
| Acrotony (apex-favoring bud break) | ✅ | ⬆ Implemented | `sim/bud_break_bias.py::position_weight` + `cfg.sim.bud_break_bias` (mode + strength). Default `uniform`/`strength=0` is a no-op; `acrotonic` linearly boosts tip-side lateral quality before BH allocation. | — | — | **DONE** — tunable per species. |
| Basitony (base-favoring) | ✅ | ⬆ Implemented | Same `bud_break_bias` axis, `mode="basitonic"`. Linearly boosts base-side lateral quality. Mesotonic mode (midpoint peak) also available. | — | — | **DONE** — gates shrub presets; lilac / dogwood / blueberry can land as a follow-up species PR. |
| Orthotropy | ✅ | = | `sim/tropisms.py` `w_orthotropy_main/_lateral` with `axis_decay^order` | — | — | — |
| Plagiotropy (horizontal lateral axis) | ✅ | ⬆ Promoted | `sim/tropisms.py:44–67` `w_plagiotropism_main/_lateral` (Phase 2A) — projects current direction onto XY plane, blends, safely skipped near-vertical | — | — | **DONE** — true plagiotropic horizontal sprays now possible (key for maple-like crowns, fir-like flat tiers). |
| Plagiotropy via epinasty (time-dependent bend) | ❌ | ⬆ unblocked, filed | Current plagiotropism is a per-step fixed-weight blend (`sim/tropisms.py:46,54-73`), not "starts near the parent axis then arches toward horizontal over years"; `growth_direction` isn't even passed an age | M | L | **ADD** ([#34](https://github.com/julien-riel/palubicki/issues/34)) — the Phase 1 time axis ([#10](https://github.com/julien-riel/palubicki/issues/10)) landed, so branch age in years (`t - birth_time`, `sim/tree.py:64`) is now available; ramp the effective plagiotropism weight over an `epinasty_tau_years`. **Filed** as [#34](https://github.com/julien-riel/palubicki/issues/34) (2026-05-29 eval). |
| Per-order branching angles | ✅ | ⬆ Promoted | `phyllotaxy.branch_angle_by_order` (Phase 2A) — list indexed by axis order (oak: 60°, 40°, 30°, 25°) | — | — | **DONE** |
| Hallé–Oldeman model selection | ❌ | = | — | L (labels) / H (constraints) | L | **SKIP labels** — current parameter dimensions (mono/sympodial × ortho/plagio × per-order angles) already cover most of what Hallé–Oldeman describes. |

**Verdict.** This section is now the **strongest area of the simulator**. The four landed Phase-2A items (sympodial, plagiotropism, per-order angles, explicit `bud_break_bias`) collectively change what species can be modeled. Only remaining work here: epinasty — and the Phase 1 time axis ([#10](https://github.com/julien-riel/palubicki/issues/10)) it depended on is now in place, so it is ready to build (**filed** as [#34](https://github.com/julien-riel/palubicki/issues/34)).

---

## §5 — Phyllotaxis

> ✅ **Per-axis delivery fixed (2026-05-29, [#24](https://github.com/julien-riel/palubicki/issues/24)).** Each mode was already correct *inside* `lateral_bud_directions`, but its azimuth used to be driven by a **global `node_index`** interleaved across all bud chains, so successive-node divergence was not delivered per-axis on the real tree (spiral scrambled; decussate/distichous parity collapsed). Divergence is now keyed on a **per-axis ordinal** (`Bud.axis_node_ordinal`, set in `_emit_node`), so the ✅ in this table now hold *on the real tree*, not just in the function. Guarded by `tests/sim/test_phyllotaxy_per_axis.py` ([#25](https://github.com/julien-riel/palubicki/issues/25)).

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Distichous (true alternate 2-ranked, 180° with no rotation) | ✅ | ⬆ Implemented | `phyllotaxy.py` mode `"distichous"` ([issue #15](https://github.com/julien-riel/palubicki/issues/15)) — single bud per node, 180° alternation between successive nodes. The `distichous_on_plagiotropic` flag auto-switches plagiotropic (order > 0) axes to distichous, so conifer side-sprays form a flat 2-ranked plane. | — | — | **DONE** — unblocks grass leaves and visibly-correct conifer sprays. |
| Opposite-decussate (pairs at 90° to previous pair) | ✅ | ⬆ Strengthened | `phyllotaxy.py:46–58` mode `"decussate"` (Phase 2C) — pair of buds at 180°, pair rotated by π/2 on alternating nodes | — | — | **DONE** — used by maple preset. The previous "opposite" mode was static 180° without alternation, so this was a real upgrade. |
| Whorled | ✅ | ⬆ Fixed | `k=whorl_count` (pine: ×5 @ 72°). Inter-whorl rotation added (`phyllotaxy.py`): `base_azimuth += (π/k)·(node_index % 2)`, mirroring the decussate half-step — even/odd whorls land on two grids offset by 180°/k, so pine's `divergence=72°=360/5` interleaves into 2k azimuths instead of stacking onto 5 ranks | M | L | **DONE** ([#35](https://github.com/julien-riel/palubicki/issues/35), PR #39) — bud-level fix; see verdict for the rendered-geometry caveat |
| Spiral / golden angle (137.508°) | ✅ | = | Default `divergence_angle_deg=137.5` (oak, birch) | — | — | — |
| Divergence jitter | ✅ | = | Gaussian σ, clamped | — | — | — |
| **Per-axis delivery of the above modes** (azimuth advances correctly *along each axis*) | ✅ | ⬆ Fixed | per-axis ordinal `Bud.axis_node_ordinal` set in `_emit_node` (terminal=parent+1, laterals/reserves=0, sympodial promotion inherits parent axis); replaces the global `node_index` for divergence | — | — | **DONE** ([#24](https://github.com/julien-riel/palubicki/issues/24)) — regression test `tests/sim/test_phyllotaxy_per_axis.py` ([#25](https://github.com/julien-riel/palubicki/issues/25)) |
| Juvenile vs adult phyllotaxis switch | ❌ | = | — | L | L | **SKIP** |

**Verdict.** Both phyllotaxis defects surfaced across the recent reviews are now **fixed**. The cross-cutting per-axis delivery defect ([#24](https://github.com/julien-riel/palubicki/issues/24)): divergence advances per-axis via `Bud.axis_node_ordinal`, so spiral, decussate and distichous are all delivered correctly along each axis on the real tree (guarded by [#25](https://github.com/julien-riel/palubicki/issues/25)). With true distichous ([issue #15](https://github.com/julien-riel/palubicki/issues/15)) + `distichous_on_plagiotropic` giving flat 2-ranked conifer sprays, those modes read correctly. The **`whorled` inter-whorl rotation** defect ([#35](https://github.com/julien-riel/palubicki/issues/35), PR #39) is also fixed: a `(π/k)·(node_index % 2)` half-step offset (mirroring decussate) makes successive whorls interleave onto two grids instead of stacking onto 5 ranks. **Caveat worth recording:** this corrects the phyllotaxis *primitive* and the dormant-bud directions (the per-axis test goes 5→10 distinct azimuths), but it does **not** change pine's rendered silhouette — pine grows as a recursive mass of laterals (the `is_main_axis` trunk is only ~2 internodes, so there are no global whorl "ranks" to interleave) and grown azimuths are governed by space perception (`w_perception=1.0`), not the phyllotaxis seed. Lowering perception to expose the interleaving was investigated and rejected (it densifies the crown without revealing ranks, and would force a golden re-pin for an invisible effect); the pine golden is byte-identical. The juvenile-vs-adult phyllotaxis switch stays **SKIP**.

---

## §6 — Leaves

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Petiole (stalk) | ❌ | = | — | L–M | L | **ADD** ([#5](https://github.com/julien-riel/palubicki/issues/5)) — almost free; visible improvement against "leaves stuck to stem" look. |
| Blade with parametric length, width, shape | ✅ | ⬆ Implemented | `geom/leaf_blade.py` ([issue #4](https://github.com/julien-riel/palubicki/issues/4) / [PR #17](https://github.com/julien-riel/palubicki/pull/17)) — `build_blade(L, W, shape, margin, depth, count)` with 6 shapes × 4 margins. Species presets updated: oak (ovate+lobed), birch (ovate+serrate), maple (palmate), pine/fir (linear). | — | — | **DONE** — leaf silhouettes are now species-distinct. Compound leaves and petiole geometry remain. |
| Simple vs compound leaf (pinnate / palmate / bipinnate) | ❌ | = | All leaves are simple | H (ash, walnut, rose, sumac, mimosa, locust) | L | **ADD** ([#6](https://github.com/julien-riel/palubicki/issues/6)) — a compound leaf is a small phytomer chain; reuse the same walker on a leaf-scale subgrammar. Unlocks many broadleaf species. |
| Venation (parallel / pinnate / palmate) | 🟡 | = | Texture-driven | M | L | **IMPROVE** — bake into blade shape parameters; don't model veins as geometry. |
| Margins (serrate, dentate, lobed, entire) | ✅ | ⬆ Implemented | `geom/leaf_blade.py` — 4 margin functions (entire / serrate / dentate / lobed) on the blade outline ([issue #4](https://github.com/julien-riel/palubicki/issues/4)) | — | — | **DONE** — delivered with the parametric blade. |
| Leaf orientation (per-leaf insertion + petiole twist) | 🟡 | = | `leaf_splay_deg` cluster-fan, not per-leaf | M | L | **IMPROVE** ([#14](https://github.com/julien-riel/palubicki/issues/14)) with leaves-on-nodes (Phase 1 time foundation [#10](https://github.com/julien-riel/palubicki/issues/10) already landed). |
| Leaf clusters at growing tips | ✅ | = | `leaf_cluster_count`, `foliage_depth` | — | — | — |
| Needles / scales / fascicles | 🟡 | = | Pine uses tiny aspect-ratio leaves; no real fascicles (clusters of 2–5 needles from a short shoot) | M (close-up); L (distant) | L | **ADD** ([#7](https://github.com/julien-riel/palubicki/issues/7)) — `fascicle: int` parameter on the leaf primitive. Skip if all renders are tree-scale. |
| Sun-leaf vs shade-leaf morphology | ✅ | ⬆ Implemented | `geom.leaf_sun_shade_k` (Phase 2C) — `leaf_size *= 1 + k*(1 - light_factor)`, clamped [0.5×, 2×]. Per-internode `light_factor` captured during sim. | — | — | **DONE** — shade leaves now grow larger, as in real broadleaf trees. |
| Leaf life span | ❌ | ⬆ unblocked | All leaves permanent | M | L | **ADD** ([#14](https://github.com/julien-riel/palubicki/issues/14)) — Phase 1 ([#10](https://github.com/julien-riel/palubicki/issues/10)) landed, so `leaf_age` in years is now expressible once leaves move onto nodes. Prerequisite for deciduousness. |
| Deciduous / evergreen / marcescent | ❌ | ⬆ unblocked | — | H (seasonal scenes) | L | **ADD** — Phase 1 foundation ([#10](https://github.com/julien-riel/palubicki/issues/10)) landed (`birth_time` + `annual_growth_period`); build on leaves-on-nodes ([#14](https://github.com/julien-riel/palubicki/issues/14)). Payoff is enormous if seasonal renders matter. |

**Verdict.** Parametric blade + margins ([issue #4](https://github.com/julien-riel/palubicki/issues/4)) and sun/shade morphology (Phase 2C) are in; leaves still aren't first-class node attributes. The Phase 1 time foundation ([#10](https://github.com/julien-riel/palubicki/issues/10)) has now landed, so leaves-on-nodes + deciduousness can be designed against a real calendar. **In priority order: compound leaves → petiole geometry → leaves-on-nodes ([#14](https://github.com/julien-riel/palubicki/issues/14)) + deciduousness.** The first two don't require the seasonal infrastructure.

---

## §7 — Roots

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Below-ground root architecture | ❌ | = | — | L–M (not visible) | L | **LATER** — only worth it if roots are ever rendered. |
| Root flare / buttresses / surface root collar | ✅ | ⬆ Implemented | `geom/tubes.py` per-vertex radius field at the trunk base + optional azimuthal buttress ridges (welded seam) + per-tree variation; `config.py` `root_flare_height/factor/falloff`, `root_buttress_count/amplitude`, `root_flare_variation`; per-species defaults ([issue #8](https://github.com/julien-riel/palubicki/issues/8) / [PR #21](https://github.com/julien-riel/palubicki/pull/21)). | — | — | **DONE** — pure render-time, sim layer untouched. |
| Tropical buttresses, prop roots, aerial roots | ❌ | = | — | M (niche) | M | **SKIP** unless tropical species are planned. |

**Verdict.** Root flare landed ([issue #8](https://github.com/julien-riel/palubicki/issues/8)) — the high-ROI quick win is banked. Below-ground architecture and tropical buttresses/prop roots stay **LATER/SKIP** until those species or root renders are scoped.

---

## §8 — Stems and secondary growth

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Primary growth (tip elongation) | ✅ | ⬆ Strengthened | `sim/elongation.py` (Phase 2D, time-based since Phase 1 [#10](https://github.com/julien-riel/palubicki/issues/10)): each internode has `birth_time` (years) and `length_target`; effective length follows a sigmoid ramp `length_target * sigmoid((t - birth_time)/τ)` with `τ = tau_years`. Earlier-born internodes also have a larger `length_target` via `compute_target_with_age(birth_time, total_years)`. | — | — | **DONE** — primary growth is now genuinely temporal: a 5-year-old internode is still elongating until it reaches its target. Big realism win for young trees. |
| Secondary growth (radial thickening over time) | ✅ | ⬆ Promoted | `radii.update_diameters_incremental` (Phase 2D) — recomputed each iteration, idempotent | — | — | **DONE** — trunk thickens visibly as the tree grows; sag responds correctly mid-growth. |
| Pipe model / da Vinci's rule | ✅ | = | `radii.py:6–14` exponent ~2.49 | — | — | — |
| Trunk taper | ✅ | = | from pipe model | — | — | — |
| Sag bending | ✅ | ⬆ Strengthened | `sim/sag.py` now idempotent (Phase 2D), writes to `Node.sag_offset`; can be called mid-iteration after diameter changes | — | — | **DONE** |
| Annual rings | ❌ | = | — | L | M | **SKIP** |
| Bark color / texture | ✅ | = | `GeomConfig.bark_color`, `bark_texture` | — | — | — |
| Bark relief (3D displacement) | ❌ | = | — | M (close-up) | M–H | **LATER** |
| Bark variation by age / radius along trunk | ✅ | ⬆ Implemented | `geom/bark_blend.py` — three-way `COLOR_0` tint (young → mature → senescent) over the single bark texture, blended by `Internode.diameter`; `config.py` `bark_tint_young/mature/senescent` + `bark_blend_diameter_*`; also written into glTF export (`export/gltf.py`). Stops calibrated to the ~1.5–8.6 cm internode scale; on by default for all five species ([issue #9](https://github.com/julien-riel/palubicki/issues/9) / [PR #22](https://github.com/julien-riel/palubicki/pull/22)). | — | — | **DONE** — pale smooth twigs → dark fissured trunk; presence-gated, render-time only. |

**Verdict.** Phase 2D upgraded this section to **the second-strongest area**. The visible behavior of growth — internodes elongating, trunk thickening, branches sagging in response — now plays out over the iteration sequence rather than being applied once at the end. The last cheap, visible win in this section — `bark variation by age/radius` — also landed ([issue #9](https://github.com/julien-riel/palubicki/issues/9)): a diameter-driven three-way `COLOR_0` tint takes twigs from pale smooth bark to dark fissured trunk. Only `bark relief` (3D displacement) remains in this section, and it stays **LATER**.

---

## §9 — Reproductive structures

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Flower geometry | ❌ | = | — | H if flowering plants in scope | L–M | **ADD as a bundle** ([#11](https://github.com/julien-riel/palubicki/issues/11)) with determinate growth (§3) and inflorescences. |
| Floral formula notation | ❌ | = | — | L (notation, not geometry) | L | **SKIP** |
| Symmetry: actinomorphic vs zygomorphic | ❌ | = | — | M with flowers | L | **ADD with flowers** ([#11](https://github.com/julien-riel/palubicki/issues/11)) |
| Inflorescences (raceme, spike, panicle, umbel, capitulum, cyme, corymb) | ❌ | = | — | H with flowers | L | **ADD with flowers** ([#11](https://github.com/julien-riel/palubicki/issues/11)) — each is a small grammar over phytomers; capitula reuse golden-angle phyllotaxy already in `phyllotaxy.py`. |
| Cones (gymnosperm) | ❌ | = | — | M (close-up); L (distant) | L | **LATER** — add when close-up conifer renders matter. |
| Fruits | ❌ | = | — | M (apples, cherries, very visible) | L | **ADD** ([#11](https://github.com/julien-riel/palubicki/issues/11)) with flowers when fruit species reach the roadmap. |

**Verdict.** Unchanged. The whole reproductive block is still missing. Do **not** start it until determinate growth (§3) is in place; they share infrastructure.

---

## §10 — Plant groups (which categories the simulator can produce)

| Category | Status | Δ | What's missing | Recommendation |
|---|---|---|---|---|
| Deciduous broadleaf trees (oak, birch, **maple**) | ✅ (richer) | ⬆ Strengthened | Leaves-on-nodes, parametric blade, compound leaves, deciduousness. Maple added in Phase 2C with decussate + sympodial + plagiotropism + reiteration + sun/shade leaves. | Polish remaining leaf features before adding more presets. |
| Conifers (pine) | ✅ (richer) | ⬆ Strengthened | Distichous needles on plagiotropic branches landed ([issue #15](https://github.com/julien-riel/palubicki/issues/15), `distichous_on_plagiotropic`); flat tiered sprays now render correctly. Remaining: fascicles (clusters of 2–5 needles); cones (close-up only). | Add `fascicle` parameter for close-up correctness; cones when close-up conifer renders matter. |
| Grasses (Poaceae) | ❌ | = | Intercalary meristems, tillering, fibrous root, no secondary growth (distichous phyllotaxis now available, [issue #15](https://github.com/julien-riel/palubicki/issues/15)) | **Big gap.** Still requires a tillering/intercalary system architecturally separate from the apical-tip growth currently implemented. |
| Herbaceous forbs (dandelion, sunflower, mint…) | ❌ | = | Determinate growth ending in inflorescence; rosettes (zero-length internodes); no secondary growth | **LATER** — needs determinate + inflorescences + zero-length-internode handling. |
| Shrubs (lilac, dogwood, blueberry) | 🟡 | ⬆ Strengthened | Basitonic bud break now available via `cfg.sim.bud_break_bias.mode="basitonic"` (Phase 2 follow-up). Reiteration from reserves (Phase 2B) already mimics some shrub-like recovery behavior. | **ADD species presets** (lilac / dogwood / blueberry YAML) — the mechanism is in; remaining work is parameter tuning + a preset PR. |
| Vines / lianas | ❌ | = | Climbing strategies, support-finding | **LATER** — substantial new system. |
| Bulbs / rosettes / succulents | ❌ | = | Compressed internodes, photosynthetic stems, spines | **LATER** |

**Verdict.** Coverage of woody dicots has gone from "two similar trees" to "three structurally different presets" (the oak / birch / maple set now spans alternate-spiral / spiral-with-droop / decussate-with-fork). Conifers now render proper flat 2-ranked sprays (plagiotropism + distichous, [issue #15](https://github.com/julien-riel/palubicki/issues/15)); only fascicles and cones remain for close-up correctness. Grasses, forbs, vines remain absent.

---

## §11 — Quantitative patterns

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Pipe model / da Vinci scaling | ✅ | = | `sim/radii.py` ~2.49 | — | — | — |
| Trunk-diameter / height allometry (`H ∝ D^(2/3)`) | ❌ | = | — | L | L | **SKIP** as a constraint; consequence of mechanics. |
| Strahler / Horton bifurcation ratios | ✅ | ⬆ Implemented | `sim/diagnostics.py::_strahler_metrics` ([issue #13](https://github.com/julien-riel/palubicki/issues/13)) — Horton bifurcation ratio, flagged against the literature range (3.0–5.0, **hardcoded, uncited** → to be sourced per-species via [#32](https://github.com/julien-riel/palubicki/issues/32)) | — | — | **DONE as diagnostic** |
| Fractal dimension of crown | ❌ | = | — | M | L–M | **LATER** |
| Divergence angle | ✅ | = | `phyllotaxy.py` | — | — | — |
| Insertion angle (base) | ✅ | = | `branch_angle_deg` + jitter | — | — | — |
| Insertion angle varying by branch order | ✅ | ⬆ Promoted | `phyllotaxy.branch_angle_by_order` (Phase 2A) | — | — | **DONE** |
| Per-species pipe exponent | ✅ | = | configurable | — | — | — |
| Sympodial fork rate | ✅ | 🆕 | `Node.sympodial_fork` (Phase 2A) lets you count promotions | — | — | Useful diagnostic seed. |
| Main-axis continuation / excurrent form | ✅ | 🆕 | `sim/diagnostics.py::_main_axis_continuation_rate` ([#40](https://github.com/julien-riel/palubicki/issues/40)) — leader length / longest root→leaf path, both in internodes. 1.0 = monopodial leader IS the deepest axis; collapses to ~0.03 when the leader is decapitated and a lateral takes over. Per-species ✓/✗ bound in `configs/literature.yaml` (excurrent conifers 0.5–0.6 floor, decurrent maple 0.2). | — | — | **DONE** ([#40](https://github.com/julien-riel/palubicki/issues/40)) — closes the net hole that let a dead-leader conifer pass `diagnose`. |
| Leader verticality / excurrent geometry | ✅ | 🆕 | `sim/diagnostics.py::_leader_deviation_deg` ([#48](https://github.com/julien-riel/palubicki/issues/48)) — *unweighted* mean angle of the leader's internode tangents from vertical. The **geometric** companion to `main_axis_continuation_rate`: that metric is topological (a leaning/arched leader stays the deepest axis, so it reads ~1.0), this one catches a leader that stands as the main axis but tilts or arches toward horizontal. Per-species ✓/✗ bound in `configs/literature.yaml` (excurrent fir/pine ≤20°, decurrent maple ≤45°). | — | — | **DONE** ([#48](https://github.com/julien-riel/palubicki/issues/48)) — closes the orientation hole #40 left open; surfaced #43's sparse-proxy conifer-leader arch. |
| Validation / diagnostic harness | ✅ | ⬆ Implemented | `sim/diagnostics.py::compute_metrics` ([issue #13](https://github.com/julien-riel/palubicki/issues/13)) over one or many trees — Strahler/Horton ratios, per-order divergence & insertion angles, bud-state histogram, sympodial fork count, **main-axis continuation rate** ([#40](https://github.com/julien-riel/palubicki/issues/40)), height/crown radius, trunk base diameter, total leaf area; multi-seed aggregation; literature-range ✓/✗ flagging via `MetricRanges`/`format_report` | — | — | **DONE** — speeds up all preset tuning. |
| Literature ranges sourced & per-species | ✅ | ⬆ Implemented | Bounds moved to the cited `configs/literature.yaml` manifest (per-species + global fallback) with `MetricRanges.from_species` ([#32](https://github.com/julien-riel/palubicki/issues/32), PR #43). [#40](https://github.com/julien-riel/palubicki/issues/40) adds the per-species `main_axis_continuation_rate` bound (excurrent vs decurrent). | — | — | **DONE** — the ✓/✗ flag is now traceable; per-species recalibration loop is self-consistent. |

**Verdict.** Both the generation axes and the diagnostic side are now covered: `sim/diagnostics.py` ([issue #13](https://github.com/julien-riel/palubicki/issues/13)) emits Strahler/Horton ratios, per-order divergence & insertion angles, bud-state histogram, sympodial fork count, **main-axis continuation rate** ([#40](https://github.com/julien-riel/palubicki/issues/40)) and leaf-area density, all flagged against a cited per-species manifest (`configs/literature.yaml`, [#32](https://github.com/julien-riel/palubicki/issues/32) PR #43). The provenance gap is closed: the bounds driving the empirical recalibration loop now rest on real, traceable values, and the net catches a decapitated leader (`main_axis_continuation_rate ✗`) — the specific failure that previously slipped through every test. [#48](https://github.com/julien-riel/palubicki/issues/48) adds the geometric companion `leader_deviation_deg`: `main_axis_continuation_rate` is topological, so a leader that leans or arches toward horizontal while remaining the deepest axis reads ~1.0 and slips through; the deviation metric flags that orientation defect (it surfaced #43's sparse-proxy conifer-leader arch, invisible to #40). Fractal dimension stays **LATER**.

---

## Top remaining recommendations (ranked by realism-per-effort)

These are the items where the realism payoff is high and the implementation cost is low — the kind of changes worth doing first, **excluding** what Phases 2A–2D and the 2026-05-29 work (root flare [#8](https://github.com/julien-riel/palubicki/issues/8), distichous [#15](https://github.com/julien-riel/palubicki/issues/15), diagnostic harness [#13](https://github.com/julien-riel/palubicki/issues/13), bark variation [#9](https://github.com/julien-riel/palubicki/issues/9), time/phenology foundation [#10](https://github.com/julien-riel/palubicki/issues/10)) already delivered.

1. **Compound leaves** (§6, [#6](https://github.com/julien-riel/palubicki/issues/6)) — a small phytomer chain at leaf scale. Big species unlock (ash, walnut, rose, sumac, locust…). No dependency.
2. **Shrub species presets** (§10) — now that `bud_break_bias` is in, lilac / dogwood / blueberry YAMLs are mostly parameter-tuning work. Visible payoff for a small PR.
3. **Petiole geometry** (§6, [#5](https://github.com/julien-riel/palubicki/issues/5)) — short stalk between bud site and leaf blade. Cheap, removes the "leaves stuck to twig" look.
4. **Fascicles of needles** (§6, [#7](https://github.com/julien-riel/palubicki/issues/7)) — `fascicle: int` on the leaf primitive. Worth it only for close-up conifer renders.

*Landed since the previous review and removed from this list:* true distichous phyllotaxis ([#15](https://github.com/julien-riel/palubicki/issues/15)), root flare at trunk base ([#8](https://github.com/julien-riel/palubicki/issues/8)), diagnostic/validation harness ([#13](https://github.com/julien-riel/palubicki/issues/13)), bark variation by `Internode.diameter` ([#9](https://github.com/julien-riel/palubicki/issues/9)), time/phenology foundation ([#10](https://github.com/julien-riel/palubicki/issues/10)).

## Phase 1 — Foundation: time / phenology axis ([#10](https://github.com/julien-riel/palubicki/issues/10)) — ✅ LANDED

**Status: done** ([PR #23](https://github.com/julien-riel/palubicki/pull/23)). The simulator now advances in fractional years rather than bare iterations:

- `sim/clock.py` — a `Clock(dt, t)` with `tick()` / `year()` / `year_fraction()` / `in_window(lo, hi)`, threaded through the forest loop.
- `sim.max_iterations` → `dt_years` + `max_simulation_years`, with a derived `num_iterations` property (`round(max_simulation_years / dt_years)`).
- `Internode.birth_iteration` → `birth_time` (years); `ElongationConfig.tau_iterations` → `tau_years`; elongation reads time deltas (`t - birth_time`, `birth_time / total_years`).
- `sim.annual_growth_period = [lo, hi)` (year fractions) gates growth to a seasonal window — outside it the tree only ages (elongation/diameters/sag) and emits nothing, without tripping the no-growth early-stop.
- Vestigial `Bud.age` removed. The integer `iteration` is retained only for RNG seeding / `node_index` / logging; biological time flows through float `t`, so at `dt_years=1.0` trees are bit-identical (all goldens, incl. the pinned bit-exact RNG test, unchanged).

This was deliberately done **before** leaves-on-nodes so `LeafState` is designed against a real calendar exactly once. The features it now unblocks:

- Leaves as first-class node attributes with `leaf_age` (§2, §6 — [#14](https://github.com/julien-riel/palubicki/issues/14))
- Deciduousness, evergreen, marcescence (§6)
- Plagiotropy by epinasty / time-dependent branch reorientation (§4)
- Seasonal bud dormancy windows (proper "release from dormancy" — the `annual_growth_period` gate is the first step; per-bud release probability is the next)

The existing `low_quality_steps` / `low_light_steps` counters were correctly **kept** as step-counts (they count iterations, not time); only the values that represent time switched to years.

## Larger projects worth planning, not yet building

- **Determinate growth + flowers + inflorescences** (§3, §9 — [#11](https://github.com/julien-riel/palubicki/issues/11)) — a coherent block. Gates herbaceous forbs, fruiting trees, and a second sympodial trigger ("apex differentiated to flower → terminate," distinct from today's "apex failed quality threshold"). Phase 1 ([#10](https://github.com/julien-riel/palubicki/issues/10)) has now landed, so the temporal prerequisite is satisfied (flowering is itself a seasonal event) — this is the next of the larger projects to schedule.
- **Tillering + intercalary meristems** (§3, §10 — [#12](https://github.com/julien-riel/palubicki/issues/12)) — required for any grass. Architecturally orthogonal — a new growth mode, independent of everything above. Add when grasses become a goal.
- **Vines / climbers** (§10) — needs an external "support geometry" the vine reacts to. Substantial new system; only worth it if landscape scenes with structures are in scope.

## Things to consciously skip

- **Annual rings, stipules, root architecture below ground, floral formula notation, fractal-dimension-as-constraint, full Hallé–Oldeman model catalog, tropical buttresses, juvenile-vs-adult phyllotaxis switch** — either invisible at render time, or low value relative to cost.
