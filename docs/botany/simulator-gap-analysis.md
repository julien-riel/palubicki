# Simulator Gap Analysis vs. Botanical Reference

*Companion to [plant-structure.md](./plant-structure.md). For each concept in sections 1–11 of the reference, this document reports: status in the current simulator, whether it should be modeled, the realism payoff, the performance cost, and a recommendation.*

**Code root:** `src/palubicki/`. Species presets currently shipped: **oak**, **birch**, **pine**, **maple**.

**Last reviewed:** 2026-05-29, after root flare (issue #8), true distichous phyllotaxis (#15), and the diagnostic harness (#13) landed on `main`. Bark variation by trunk radius (#9) is in progress on the current branch.

## What changed since the 2026-05-28 review

All merged to `main` via the issue tracker:

- **Diagnostic / validation harness** (`sim/diagnostics.py`, issue #13) — `compute_metrics` over one or many trees: Strahler/Horton bifurcation ratios, per-order divergence & insertion angles, bud-state histogram, sympodial fork count, height/crown radius, trunk base diameter, total leaf area. Multi-seed aggregation plus literature-range ✓/✗ flagging via `MetricRanges`/`format_report`. This was the highest-priority remaining item in §11.
- **True distichous phyllotaxis** (`sim/phyllotaxy.py` mode `"distichous"`, issue #15) — single bud per node, 180° alternation between successive nodes. The `distichous_on_plagiotropic` flag auto-switches plagiotropic (order > 0) axes to distichous, so conifer side-sprays form a flat 2-ranked plane — the exact fix §5/§10 flagged.
- **Root flare at trunk base** (`geom/tubes.py` + `config.py`, issue #8 / PR #21) — per-vertex radius field at the trunk base, optional azimuthal buttress ridges with a welded seam, per-tree variation; `root_flare_height/factor/falloff`, `root_buttress_count/amplitude`, `root_flare_variation` config fields with per-species defaults. Pure render-time; the sim layer is untouched.
- **Cross-blade leaf fix** (issue #18, follow-up to #4) — cross-blade geometry now only for linear (needle) shapes.
- **Tooling** (PR #19, non-issue) — ruff config + GitHub Actions CI + simulator refactor.

**In progress:** bark variation by trunk radius (issue #9, current branch) — see §8.

## Earlier — Phases 2A–2D (2026-05-28 review)

Phases 2A–2D were merged. Concretely, the following moved from ❌/🟡 to ✅:

- **Parametric leaf blade** (`geom/leaf_blade.py`) — 6 shapes × 4 margins replace cross-quad rectangles. Each species now has a distinct silhouette.
- **Sympodial branching** (`sim/sympodial.py`) — terminal bud failure promotes a lateral.
- **Plagiotropism** (`sim/tropisms.py` `w_plagiotropism_main/_lateral`) — projects direction onto XY plane.
- **Per-branch-order angles** (`phyllotaxy.branch_angle_by_order`).
- **Decussate phyllotaxy** (`sim/phyllotaxy.py` mode `"decussate"` with π/2 alternation between successive pairs).
- **Sun/shade leaf morphology** (`geom.leaf_sun_shade_k` + `Internode.light_factor`).
- **Time-stepped trunk thickening** (`sim/radii.py::update_diameters_incremental`, called per iteration, idempotent).
- **Progressive internode elongation** (`sim/elongation.py` — sigmoid ramp per internode based on `birth_iteration` and `length_target`).
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
| Phytomer = node + internode + leaf(s) + bud(s) as one logical unit | 🟡 | = | `sim/tree.py`: `Node`, `Internode`, `Bud` separate; leaves still synthesized at render time in `geom/leaves.py` | M | L | **IMPROVE** — leaves are still not first-class node attributes. Largest single architectural gap; blocks deciduousness, per-leaf age, and seasonal rendering. Tackle with Phase 1 (seasonal/phenology) — see end of doc. |
| Internode with length + radius | ✅ | 🆕 strengthened | `Internode.length`, `Internode.diameter`; also now `light_factor`, `birth_iteration`, `length_target` (Phase 2D) | — | — | — |
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
| Apical meristem | ✅ | = | terminal bud + `simulator.py:62–71` loop | — | — | — |
| Axillary meristems | ✅ | ⬆ strengthened | richer state machine (Phase 2B) — ACTIVE / DORMANT / DEAD / RESERVE | — | — | — |
| Bud break / release rule | 🟡 | ⬆ strengthened | Activation still implicit through BH allocation, but the lifecycle on the other end is now explicit: `shade_mortality.kill_shaded_buds` (Phase 2B) and `reiteration.activate_reserves_on_shed` (Phase 2B) close the loop on dormancy/death. | M | L | **IMPROVE** — the "missing piece" is now upstream: still no explicit bud-break probability for *initial* activation. Acceptable for now; revisit only if shrub presets need fine control. |
| Reiteration (replacing shed branches from reserves) | ✅ | ⬆ Implemented | `sim/reiteration.py`; activated by `shedding.reactivation_count` | M | L | **DONE** — this also partially substitutes for one role of determinate growth (it lets trees recover from canopy damage). |
| Intercalary meristems (grasses, basal growth) | ❌ | = | — | H (grasses) | L | **LATER** — gates monocots. |
| Lateral / cambium meristem (secondary growth) | ✅ | ⬆ Promoted | `radii.update_diameters_incremental` (Phase 2D) — called each iteration, idempotent. Pipe model with exponent ~2.49. | — | — | **DONE** — thickening now visible during growth; feeds `sag.py` in-flight. |
| Annual rings | ❌ | = | — | L | M | **SKIP** |
| Determinate vs indeterminate growth | ❌ | = | — | M | L | **ADD** when flowers land — gates flowering, fruits, herbaceous forbs, and proper sympodial trees (right now sympodial fires on *quality failure*, not deliberate apex termination). |

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
| Plagiotropy via epinasty (time-dependent bend) | ❌ | = | Current plagiotropism is per-step blend, not "starts vertical then bends down over years" | M | L | **ADD** with Phase 1 (seasonal/time axis) — needs a meaningful concept of branch age. |
| Per-order branching angles | ✅ | ⬆ Promoted | `phyllotaxy.branch_angle_by_order` (Phase 2A) — list indexed by axis order (oak: 60°, 40°, 30°, 25°) | — | — | **DONE** |
| Hallé–Oldeman model selection | ❌ | = | — | L (labels) / H (constraints) | L | **SKIP labels** — current parameter dimensions (mono/sympodial × ortho/plagio × per-order angles) already cover most of what Hallé–Oldeman describes. |

**Verdict.** This section is now the **strongest area of the simulator**. The four landed Phase-2A items (sympodial, plagiotropism, per-order angles, explicit `bud_break_bias`) collectively change what species can be modeled. Only remaining work here: epinasty (couple with seasonal cycles).

---

## §5 — Phyllotaxis

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Distichous (true alternate 2-ranked, 180° with no rotation) | ✅ | ⬆ Implemented | `phyllotaxy.py` mode `"distichous"` (issue #15) — single bud per node, 180° alternation between successive nodes. The `distichous_on_plagiotropic` flag auto-switches plagiotropic (order > 0) axes to distichous, so conifer side-sprays form a flat 2-ranked plane. | — | — | **DONE** — unblocks grass leaves and visibly-correct conifer sprays. |
| Opposite-decussate (pairs at 90° to previous pair) | ✅ | ⬆ Strengthened | `phyllotaxy.py:46–58` mode `"decussate"` (Phase 2C) — pair of buds at 180°, pair rotated by π/2 on alternating nodes | — | — | **DONE** — used by maple preset. The previous "opposite" mode was static 180° without alternation, so this was a real upgrade. |
| Whorled | ✅ | = | `k=whorl_count` (pine: ×5 @ 72°) | — | — | — |
| Spiral / golden angle (137.508°) | ✅ | = | Default `divergence_angle_deg=137.5` (oak, birch) | — | — | — |
| Divergence jitter | ✅ | = | Gaussian σ, clamped | — | — | — |
| Juvenile vs adult phyllotaxis switch | ❌ | = | — | L | L | **SKIP** |

**Verdict.** Complete for the species in scope. True distichous (issue #15) landed and, via `distichous_on_plagiotropic`, fir/pine side-sprays now form a flat 2-ranked plane rather than spiralling. Only the juvenile-vs-adult phyllotaxis switch remains, and it stays **SKIP**.

---

## §6 — Leaves

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Petiole (stalk) | ❌ | = | — | L–M | L | **ADD** — almost free; visible improvement against "leaves stuck to stem" look. |
| Blade with parametric length, width, shape | ✅ | ⬆ Implemented | `geom/leaf_blade.py` (issue #4 / PR #17) — `build_blade(L, W, shape, margin, depth, count)` with 6 shapes × 4 margins. Species presets updated: oak (ovate+lobed), birch (ovate+serrate), maple (palmate), pine/fir (linear). | — | — | **DONE** — leaf silhouettes are now species-distinct. Compound leaves and petiole geometry remain. |
| Simple vs compound leaf (pinnate / palmate / bipinnate) | ❌ | = | All leaves are simple | H (ash, walnut, rose, sumac, mimosa, locust) | L | **ADD** — a compound leaf is a small phytomer chain; reuse the same walker on a leaf-scale subgrammar. Unlocks many broadleaf species. |
| Venation (parallel / pinnate / palmate) | 🟡 | = | Texture-driven | M | L | **IMPROVE** — bake into blade shape parameters; don't model veins as geometry. |
| Margins (serrate, dentate, lobed, entire) | ❌ | = | — | M (oak vs cherry vs willow silhouette) | L | **ADD** — margin function on blade outline. Cheap; very recognizable. |
| Leaf orientation (per-leaf insertion + petiole twist) | 🟡 | = | `leaf_splay_deg` cluster-fan, not per-leaf | M | L | **IMPROVE** with leaves-on-nodes (couples with Phase 1). |
| Leaf clusters at growing tips | ✅ | = | `leaf_cluster_count`, `foliage_depth` | — | — | — |
| Needles / scales / fascicles | 🟡 | = | Pine uses tiny aspect-ratio leaves; no real fascicles (clusters of 2–5 needles from a short shoot) | M (close-up); L (distant) | L | **ADD** — `fascicle: int` parameter on the leaf primitive. Skip if all renders are tree-scale. |
| Sun-leaf vs shade-leaf morphology | ✅ | ⬆ Implemented | `geom.leaf_sun_shade_k` (Phase 2C) — `leaf_size *= 1 + k*(1 - light_factor)`, clamped [0.5×, 2×]. Per-internode `light_factor` captured during sim. | — | — | **DONE** — shade leaves now grow larger, as in real broadleaf trees. |
| Leaf life span | ❌ | = | All leaves permanent | M | L | **ADD with Phase 1 (seasonal cycles)** — `leaf_age` field once leaves move onto nodes. Prerequisite for deciduousness. |
| Deciduous / evergreen / marcescent | ❌ | = | — | H (seasonal scenes) | L | **ADD with Phase 1** — payoff is enormous if seasonal renders matter. |

**Verdict.** Parametric blade + margins (issue #4) and sun/shade morphology (Phase 2C) are in; leaves still aren't first-class node attributes. **In priority order: compound leaves → petiole geometry → (Phase 1: leaves-on-nodes + deciduousness).** The first two don't require seasonal infrastructure.

---

## §7 — Roots

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Below-ground root architecture | ❌ | = | — | L–M (not visible) | L | **LATER** — only worth it if roots are ever rendered. |
| Root flare / buttresses / surface root collar | ✅ | ⬆ Implemented | `geom/tubes.py` per-vertex radius field at the trunk base + optional azimuthal buttress ridges (welded seam) + per-tree variation; `config.py` `root_flare_height/factor/falloff`, `root_buttress_count/amplitude`, `root_flare_variation`; per-species defaults (issue #8 / PR #21). | — | — | **DONE** — pure render-time, sim layer untouched. |
| Tropical buttresses, prop roots, aerial roots | ❌ | = | — | M (niche) | M | **SKIP** unless tropical species are planned. |

**Verdict.** Root flare landed (issue #8) — the high-ROI quick win is banked. Below-ground architecture and tropical buttresses/prop roots stay **LATER/SKIP** until those species or root renders are scoped.

---

## §8 — Stems and secondary growth

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Primary growth (tip elongation) | ✅ | ⬆ Strengthened | `sim/elongation.py` (Phase 2D): each internode has `birth_iteration` and `length_target`; effective length follows a sigmoid ramp `length_target * sigmoid((iter - birth)/τ)`. Earlier-born internodes also have a larger `length_target` via `compute_target_with_age`. | — | — | **DONE** — primary growth is now genuinely temporal: a 5-year-old internode is still elongating until it reaches its target. Big realism win for young trees. |
| Secondary growth (radial thickening over time) | ✅ | ⬆ Promoted | `radii.update_diameters_incremental` (Phase 2D) — recomputed each iteration, idempotent | — | — | **DONE** — trunk thickens visibly as the tree grows; sag responds correctly mid-growth. |
| Pipe model / da Vinci's rule | ✅ | = | `radii.py:6–14` exponent ~2.49 | — | — | — |
| Trunk taper | ✅ | = | from pipe model | — | — | — |
| Sag bending | ✅ | ⬆ Strengthened | `sim/sag.py` now idempotent (Phase 2D), writes to `Node.sag_offset`; can be called mid-iteration after diameter changes | — | — | **DONE** |
| Annual rings | ❌ | = | — | L | M | **SKIP** |
| Bark color / texture | ✅ | = | `GeomConfig.bark_color`, `bark_texture` | — | — | — |
| Bark relief (3D displacement) | ❌ | = | — | M (close-up) | M–H | **LATER** |
| Bark variation by age / radius along trunk | ❌ | = | One texture per species | L–M | L | **IN PROGRESS** (issue #9, current branch) — blend two bark textures by `Internode.diameter` (smooth at tips, cracked at base). Trivial shader work. |

**Verdict.** Phase 2D upgraded this section to **the second-strongest area**. The visible behavior of growth — internodes elongating, trunk thickening, branches sagging in response — now plays out over the iteration sequence rather than being applied once at the end. The last cheap, visible win in this section — `bark variation by age/radius` — is now in flight (issue #9, current branch).

---

## §9 — Reproductive structures

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Flower geometry | ❌ | = | — | H if flowering plants in scope | L–M | **ADD as a bundle** with determinate growth (§3) and inflorescences. |
| Floral formula notation | ❌ | = | — | L (notation, not geometry) | L | **SKIP** |
| Symmetry: actinomorphic vs zygomorphic | ❌ | = | — | M with flowers | L | **ADD with flowers** |
| Inflorescences (raceme, spike, panicle, umbel, capitulum, cyme, corymb) | ❌ | = | — | H with flowers | L | **ADD with flowers** — each is a small grammar over phytomers; capitula reuse golden-angle phyllotaxy already in `phyllotaxy.py`. |
| Cones (gymnosperm) | ❌ | = | — | M (close-up); L (distant) | L | **LATER** — add when close-up conifer renders matter. |
| Fruits | ❌ | = | — | M (apples, cherries, very visible) | L | **ADD** with flowers when fruit species reach the roadmap. |

**Verdict.** Unchanged. The whole reproductive block is still missing. Do **not** start it until determinate growth (§3) is in place; they share infrastructure.

---

## §10 — Plant groups (which categories the simulator can produce)

| Category | Status | Δ | What's missing | Recommendation |
|---|---|---|---|---|
| Deciduous broadleaf trees (oak, birch, **maple**) | ✅ (richer) | ⬆ Strengthened | Leaves-on-nodes, parametric blade, compound leaves, deciduousness. Maple added in Phase 2C with decussate + sympodial + plagiotropism + reiteration + sun/shade leaves. | Polish remaining leaf features before adding more presets. |
| Conifers (pine) | ✅ (richer) | ⬆ Strengthened | Distichous needles on plagiotropic branches landed (issue #15, `distichous_on_plagiotropic`); flat tiered sprays now render correctly. Remaining: fascicles (clusters of 2–5 needles); cones (close-up only). | Add `fascicle` parameter for close-up correctness; cones when close-up conifer renders matter. |
| Grasses (Poaceae) | ❌ | = | Intercalary meristems, tillering, fibrous root, no secondary growth (distichous phyllotaxis now available, issue #15) | **Big gap.** Still requires a tillering/intercalary system architecturally separate from the apical-tip growth currently implemented. |
| Herbaceous forbs (dandelion, sunflower, mint…) | ❌ | = | Determinate growth ending in inflorescence; rosettes (zero-length internodes); no secondary growth | **LATER** — needs determinate + inflorescences + zero-length-internode handling. |
| Shrubs (lilac, dogwood, blueberry) | 🟡 | ⬆ Strengthened | Basitonic bud break now available via `cfg.sim.bud_break_bias.mode="basitonic"` (Phase 2 follow-up). Reiteration from reserves (Phase 2B) already mimics some shrub-like recovery behavior. | **ADD species presets** (lilac / dogwood / blueberry YAML) — the mechanism is in; remaining work is parameter tuning + a preset PR. |
| Vines / lianas | ❌ | = | Climbing strategies, support-finding | **LATER** — substantial new system. |
| Bulbs / rosettes / succulents | ❌ | = | Compressed internodes, photosynthetic stems, spines | **LATER** |

**Verdict.** Coverage of woody dicots has gone from "two similar trees" to "three structurally different presets" (the oak / birch / maple set now spans alternate-spiral / spiral-with-droop / decussate-with-fork). Conifers now render proper flat 2-ranked sprays (plagiotropism + distichous, issue #15); only fascicles and cones remain for close-up correctness. Grasses, forbs, vines remain absent.

---

## §11 — Quantitative patterns

| Topic | Status | Δ | Where | Realism | Perf | Recommendation |
|---|---|---|---|---|---|---|
| Pipe model / da Vinci scaling | ✅ | = | `sim/radii.py` ~2.49 | — | — | — |
| Trunk-diameter / height allometry (`H ∝ D^(2/3)`) | ❌ | = | — | L | L | **SKIP** as a constraint; consequence of mechanics. |
| Strahler / Horton bifurcation ratios | ✅ | ⬆ Implemented | `sim/diagnostics.py::_strahler_metrics` (issue #13) — Horton bifurcation ratio, flagged against the literature range (3.0–5.0) | — | — | **DONE as diagnostic** |
| Fractal dimension of crown | ❌ | = | — | M | L–M | **LATER** |
| Divergence angle | ✅ | = | `phyllotaxy.py` | — | — | — |
| Insertion angle (base) | ✅ | = | `branch_angle_deg` + jitter | — | — | — |
| Insertion angle varying by branch order | ✅ | ⬆ Promoted | `phyllotaxy.branch_angle_by_order` (Phase 2A) | — | — | **DONE** |
| Per-species pipe exponent | ✅ | = | configurable | — | — | — |
| Sympodial fork rate | ✅ | 🆕 | `Node.sympodial_fork` (Phase 2A) lets you count promotions | — | — | Useful diagnostic seed. |
| Validation / diagnostic harness | ✅ | ⬆ Implemented | `sim/diagnostics.py::compute_metrics` (issue #13) over one or many trees — Strahler/Horton ratios, per-order divergence & insertion angles, bud-state histogram, sympodial fork count, height/crown radius, trunk base diameter, total leaf area; multi-seed aggregation; literature-range ✓/✗ flagging via `MetricRanges`/`format_report` | — | — | **DONE** — speeds up all preset tuning. |

**Verdict.** Both the generation axes and the diagnostic side are now covered: `sim/diagnostics.py` (issue #13) emits Strahler/Horton ratios, per-order divergence & insertion angles, bud-state histogram, sympodial fork count and leaf-area density, with literature-range flagging. Nothing high-priority remains here; fractal dimension stays **LATER**.

---

## Top remaining recommendations (ranked by realism-per-effort)

These are the items where the realism payoff is high and the implementation cost is low — the kind of changes worth doing first, **excluding** what Phases 2A–2D and the 2026-05-29 work (root flare #8, distichous #15, diagnostic harness #13) already delivered.

1. **Bark variation by trunk radius** (§8) — blend two bark textures based on `Internode.diameter`. Trivial shader work; visible against young vs. mature stems. **In progress (issue #9, current branch).**
2. **Compound leaves** (§6) — a small phytomer chain at leaf scale. Big species unlock (ash, walnut, rose, sumac, locust…). No dependency.
3. **Shrub species presets** (§10) — now that `bud_break_bias` is in, lilac / dogwood / blueberry YAMLs are mostly parameter-tuning work. Visible payoff for a small PR.
4. **Petiole geometry** (§6) — short stalk between bud site and leaf blade. Cheap, removes the "leaves stuck to twig" look.
5. **Fascicles of needles** (§6) — `fascicle: int` on the leaf primitive. Worth it only for close-up conifer renders.

*Landed since the previous review and removed from this list:* true distichous phyllotaxis (#15), root flare at trunk base (#8), diagnostic/validation harness (#13).

## Phase 1 — Foundation: time / phenology axis *(at the right moment)*

The right moment to do this is **before** adding any of these features, which all need a real concept of time:

- Leaves as first-class node attributes with `leaf_age` (§2, §6)
- Deciduousness, evergreen, marcescence (§6)
- Plagiotropy by epinasty / time-dependent branch reorientation (§4)
- Seasonal bud dormancy windows (proper "release from dormancy" rather than continuous activation)

Today, an iteration is "+1 internode of growth at each active bud" with no temporal unit. Once a step represents a calendar duration (a fraction of a year, or a day), the existing `birth_iteration` and the new `low_quality_steps` / `low_light_steps` counters can be reinterpreted in calendar terms without changing their semantics. **Design pre-work**: pick a clock model (continuous fractional year vs. discrete seasons) and decide whether all species share the same clock or each preset declares its own annual rhythm.

Doing Phase 1 *before* leaves-on-nodes avoids designing `LeafState` twice.

## Larger projects worth planning, not yet building

- **Determinate growth + flowers + inflorescences** (§3, §9) — a coherent block. Gates herbaceous forbs, fruiting trees, and a second sympodial trigger ("apex differentiated to flower → terminate," distinct from today's "apex failed quality threshold"). Best done *after* Phase 1, since flowering is itself a seasonal event.
- **Tillering + intercalary meristems** (§3, §10) — required for any grass. Architecturally orthogonal — a new growth mode, independent of everything above. Add when grasses become a goal.
- **Vines / climbers** (§10) — needs an external "support geometry" the vine reacts to. Substantial new system; only worth it if landscape scenes with structures are in scope.

## Things to consciously skip

- **Annual rings, stipules, root architecture below ground, floral formula notation, fractal-dimension-as-constraint, full Hallé–Oldeman model catalog, tropical buttresses, juvenile-vs-adult phyllotaxis switch** — either invisible at render time, or low value relative to cost.
