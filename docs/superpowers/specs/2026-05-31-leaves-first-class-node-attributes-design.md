# Design — Leaves as first-class `Node` attributes (`Leaf` + `LeafState`)

**Issue:** #14 · **Branch:** `issue-14-leaves-as-first-class-node-attributes` · **PR:** #57
**Date:** 2026-05-31

## Goal

Promote leaves from mesh-time geometry to first-class attributes of `Node`. Today
leaves are synthesized at `build_mesh()` time by walking the tree for apex-proximal
"foliage sites"; they have no identity, age, or state. That blocks every per-leaf
feature: per-leaf age, deciduousness/caducity, marcescence, autumn-color trajectories,
per-leaf phototropism, herbivory. This is the keystone foliage refactor (gap-analysis
§2/§6: "largest single architectural gap").

This issue builds the **foundation only**: `Leaf`/`LeafState`, per-node emission with
phyllotactic seating, and a render/diagnostics path that reads leaves off the tree. The
actual state transitions (caducity, autumn color) are explicit follow-ups.

## Settled decisions (brainstorm)

| Fork | Choice |
|---|---|
| **Retention / render model** | **Parity-preserving.** Leaves are emitted at *every* node and live on `Node`, but the renderer + diagnostics *select* the apex-proximal subset (`foliage_depth` as the selector). Silhouette + leaf-area stay at parity; goldens barely move (vertex positions shift from new seating). When caducity lands, the depth selector is replaced by a `state` filter. Rejected: render-everything-everywhere (botanically wrong without caducity — real trees self-prune inner leaves — and a large perf hit). |
| **Leaf placement** | `position` is **derived** (`parent_node.position + parent_node.sag_offset`), not a frozen world coordinate. Leaves are born mid-sim while node positions are still moving (elongation grows internodes from ~0; sag bends them, every iteration + Phase-2D). A frozen birth-time coordinate would strand the leaf. Stored: `azimuth`, `birth_time`, `state`. |
| **Leaf granularity** | A `Leaf` is a **foliage emission point** (one per `leaf_cluster_count` member per node), carrying its own phyllotactic `azimuth`. The cluster fan moves from render-time to emission-time. `needle_cluster_spacing` (conifer along-shoot) and `n_planes` (cross-blade) stay **render-time expansion** of each leaf. Rejected: one `Leaf` per individual blade/needle (object explosion, no near-term per-blade state need). |
| **Seating representation** | The leaf stores its seating **azimuth** (a scalar, radians), *not* a pre-baked orientation vector. All 5 species set `leaf_splay_deg` 20–30°, whose blade-area shear (`cos(splay)` plane-A factor) must survive for `_total_leaf_area` to stay at parity. The renderer rebuilds the lift basis from the render-time stem direction + `azimuth` + `splay` — exactly today's `_emit_leaf_cluster` math — so area is identical (azimuth-independent) and only the per-node rotation shifts. A pre-baked orthonormal orientation vector would drop the shear and inflate area by `1/cos(splay)`. |

## Data model (`sim/tree.py`)

```python
class LeafState(Enum):
    ACTIVE = auto()
    SENESCENT = auto()    # reserved for caducity follow-up — unused in MVP
    ABSCISSED = auto()    # reserved — unused in MVP

@dataclass(eq=False)
class Leaf:
    parent_node: Node
    azimuth: float            # phyllotactic seating azimuth (radians), fixed at birth
    birth_time: float         # years, from Clock.t
    state: LeafState = LeafState.ACTIVE

    @property
    def position(self) -> np.ndarray:
        # Derived — tracks sag/elongation automatically, mirrors today's placement.
        return self.parent_node.position + self.parent_node.sag_offset

    def age(self, clock) -> float:
        return clock.t - self.birth_time
```

`azimuth` is a scalar (not a vector): the renderer reconstructs the blade basis from the
node's render-time stem direction + this azimuth + `leaf_splay_deg`, preserving today's
splay area-shear exactly (see "Seating representation" above). A future per-leaf
phototropism feature can add a mutable orientation override then; the scalar is the right
MVP unit.

- `Node` gains `leaves: list[Leaf] = field(default_factory=list)`.
- `Tree.all_leaves()` — iterator walking the node graph (same traversal as the existing
  `all_internodes` accessor), yielding every `Leaf`.
- `eq=False` matches `Bud`/`Internode` (identity semantics). `from __future__ import
  annotations` is already in the file → `Node`/`Leaf` forward refs resolve.
- Deferred (YAGNI): stable per-node leaf index.

## Emission (`phyllotaxy.leaf_azimuths` + `simulator._emit_node`)

**New `phyllotaxy.leaf_azimuths(cfg, node_index, *, axis_order, count) -> list[float]`** —
pure scalar azimuths (radians). Replicates `lateral_bud_directions`' `base_azimuth`
switch (spiral / distichous / decussate / whorled, including `distichous_on_plagiotropic`
for `axis_order > 0`), then fans `count = leaf_cluster_count` members at `base + 2πi/count`:

- `node_index` is fed the **per-axis ordinal** (`cur.axis_node_ordinal`) — the #24 fix — so
  leaves spiral correctly along each axis instead of inheriting the scrambled global
  `node_index`.
- It returns only azimuths; the renderer turns `(azimuth, render-time stem direction,
  leaf_splay_deg)` into blade geometry — keeping the splay area-shear (and thus
  `_total_leaf_area` parity) in one place. No `growth_direction`/`seed`/frame needed (the
  base-azimuth switch is pure arithmetic).

The base-azimuth switch is **deliberately duplicated** from `lateral_bud_directions`
(rather than extracted into a shared helper) so the skeleton-driving function is not
touched and its goldens stay bit-exact. A code comment must flag the two must stay in sync.

This moves the cluster fan from render-time to **emission-time**: a node emits
`leaf_cluster_count` `Leaf` objects, each with its own phyllotactic `azimuth` (delivers the
"seating azimuth uses the per-axis ordinal" criterion).

**In `_emit_node`**, after the lateral/reserve buds are created (we already have
`new_node`, `axis_ord = cur.axis_node_ordinal`, `t`):

```python
if cfg.geom.enable_leaves and cfg.geom.leaf_cluster_count > 0:
    for az in leaf_azimuths(
        cfg.phyllotaxy, axis_ord,
        axis_order=cur.axis_order, count=cfg.geom.leaf_cluster_count,
    ):
        new_node.leaves.append(
            Leaf(parent_node=new_node, azimuth=az, birth_time=t,
                 state=LeafState.ACTIVE)
        )
```

Every node gets leaves at birth (parity model — the renderer selects which to draw).
`enable_leaves` currently lives in `cfg.geom` (a render concern) but is read here so
leaves are only *emitted* when they'd be *rendered* — MVP keeps it in `cfg.geom` (no
config migration); split sim-vs-render gating later only if needed.

## Render & diagnostics selection (`geom/leaves.py` + `diagnostics.py`)

A **shared selector** keeps the `.glb` and the diagnostic from drifting (the reason
`compute_effective_leaf_size` was shared):

```python
def selected_leaves(
    tree, *, foliage_depth, needle_cluster_spacing
) -> list[tuple[Leaf, np.ndarray, Internode | None, np.ndarray]]:
    """Apex-proximal, ACTIVE leaves actually rendered this build:
    (leaf, stem_direction, source_internode, render_position) per drawn
    blade-group, expanding needle_cluster_spacing along the shoot."""
```

- Walks `tree.all_leaves()`, keeps `state is ACTIVE`, applies the apex-proximity filter
  via the existing `_leaf_bearing_nodes(tree, foliage_depth)` (kept as the selector; only
  `_collect_foliage_sites` is removed). MVP stand-in for caducity — later the depth filter
  drops and `state` does the work. Takes explicit `foliage_depth`/`needle_cluster_spacing`
  (not `cfg`) so both the renderer (kwarg-driven) and diagnostics call it cleanly.
- `needle_cluster_spacing > 0` (conifers): fan each leaf into up to 8 along-internode
  render positions (today's `_collect_foliage_sites` math, extracted to `_shoot_positions`
  and keyed off the leaf). Broadleaves: one position at `leaf.position`.
- `stem_direction` is the node's render-time direction from `_leaf_bearing_nodes` (apex
  bud direction / segment tangent) — the frame the renderer rebuilds the blade basis in.

**`build_leaves_primitive`** iterates `selected_leaves(...)` and, per record, lifts
`n_planes` blade(s) via a new `_lift_leaf(render_pos, stem_dir, leaf.azimuth, splay_rad,
n_planes, eff_size, …)` — the exact body of today's `_emit_leaf_cluster` inner loop but with
`az = leaf.azimuth` instead of `2πk/count`. `eff_size = compute_effective_leaf_size(
source_iod, …)`. The render-time `cluster_count` fan inside `_emit_leaf_cluster` is removed
(fan is now individual `Leaf`s); `_lift_blade`, `compute_effective_leaf_size`,
`_basis_perpendicular_to` stay.

**`_total_leaf_area`** walks the same `selected_leaves(...)`, summing `pair_area × eff²` per
record (one `pair_area` per leaf, `pair_area = unit_blade_area × (cos(splay) + plane_b)`).
The geometric cross-check `test_leaf_area_matches_geom_helper` (diagnostic area == summed
rendered-triangle area, `rel=1e-5`) remains the live parity guard, now exercising the new
shared path on both sides.

**Parity arithmetic:** old rendered-blade count = `n_sites × cluster_count × n_planes`;
new = `(leaf_bearing_nodes × cluster_count) × needle_positions × n_planes`. Since
`n_sites = leaf_bearing_nodes × needle_positions`, counts match and leaf area
(orientation-independent: `cos(splay)` plane-A + plane-B) is preserved → `_total_leaf_area`
holds within float tolerance. **Vertex positions shift** (phyllotactic seating vs even
fan) → species goldens regenerated in the same PR (PoC mode, allowed).

## Config

No keys removed. `leaf_cluster_count` = leaves per emission point; `foliage_depth` = the
apex-proximity render selector; `needle_cluster_spacing` = conifer along-shoot expansion;
`enable_leaves` gates emission. All retained.

## Testing & verification

**Sim data model:**
- `Leaf.position` derived: assert `== node.position + node.sag_offset`; mutate the node
  position and confirm the leaf follows (anti-staleness guarantee). `LeafState` has three
  members; `Node.leaves` defaults empty; `Tree.all_leaves()` yields every leaf.
- `leaf_azimuths`: returns exactly `count` floats; base azimuth advances with the ordinal
  (ordinal *n* vs *n+1* differ by the divergence step); the `count` members are evenly
  fanned (`2π/count` apart); `distichous_on_plagiotropic` flips lateral axes to the
  180°-per-node progression; pure/deterministic.

**Emission:**
- After a small sim, every node has `leaf_cluster_count` `ACTIVE` leaves with `birth_time`
  = the iteration clock time that created the node.
- `enable_leaves=False` ⇒ no leaves emitted.
- Leaves are inert to growth: node positions identical with leaves on vs off.

**Render + diagnostics parity:**
- `selected_leaves` count == old `_collect_foliage_sites × cluster_count` count on a
  fixture tree (parity arithmetic asserted numerically).
- `build_leaves_primitive` from `node.leaves` returns a valid non-empty primitive for a
  leafy tree, empty when nothing is ACTIVE/selected.
- `_total_leaf_area` (new path) matches the captured pre-refactor value within tolerance:
  **oak seed 0 = 791.24687450** (also birch 9.46838697, maple 111.27648191, pine
  355.28514526, fir 184.64116855), all leaves ACTIVE — the explicit acceptance criterion.
- The geometric cross-check `test_leaf_area_matches_geom_helper` still passes (it now
  cross-checks the new shared path: diagnostic formula vs summed rendered triangles).

**Smoke + goldens:**
- `palubicki generate --species {oak,birch,maple,pine}` produce valid `.glb`s with visible
  foliage.
- Regenerate species goldens + leaf-area diagnostic hashes in the same PR (vertex shift);
  run the full slow golden suite to confirm only foliage-driven hashes moved (skeleton /
  bark / light goldens untouched).

## Acceptance criteria (from #14)

- [ ] `Leaf` dataclass + `LeafState` enum in `sim/tree.py`
- [ ] `Node.leaves: list[Leaf]` field, default empty
- [ ] `Tree.all_leaves()` iterator
- [ ] Leaves emitted in `_iteration_step`/`_emit_node` at every new node, `birth_time = clock.t`
- [ ] Leaf seating azimuth uses the per-axis ordinal (#24), not the global `node_index`
- [ ] `build_leaves_primitive` consumes `tree.all_leaves()` (filtered ACTIVE + apex-proximal selector); no longer calls `_collect_foliage_sites`
- [ ] `_total_leaf_area` matches pre-refactor value within float tolerance, all leaves ACTIVE
- [ ] Four species smoke `.glb`s valid with visible foliage
- [ ] Golden suite passes (goldens regenerated for the seating shift)

## Out of scope

Caducity / marcescence / senescence state transitions (only `ACTIVE` wired) · per-leaf
voxel light sample · autumn-color shader · re-tuning species blade presets (a separate
follow-up after this + #24) · removing `leaf_cluster_count` / `foliage_depth` config keys ·
stable per-node leaf index · splitting `enable_leaves` into sim-vs-render gates.

## Docs to update at finish (per `/work`)

- `docs/roadmap.md` — move #14 to "Fait" (PR #57); re-check ordering (#14 unblocks #6/#5/#7).
- `docs/botany/simulator-gap-analysis.md` — this **does** touch a botanical concept (§6
  Leaves / §2 phytomer): flip the "leaves as first-class node attributes" row, refresh the
  §6 + §2 verdicts and the "Last reviewed" line.
