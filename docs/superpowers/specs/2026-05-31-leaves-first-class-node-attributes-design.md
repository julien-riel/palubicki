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
| **Leaf placement** | `position` is **derived** (`parent_node.position + parent_node.sag_offset`), not a frozen world coordinate. Leaves are born mid-sim while node positions are still moving (elongation grows internodes from ~0; sag bends them, every iteration + Phase-2D). A frozen birth-time coordinate would strand the leaf. Stored: `orientation`, `birth_time`, `state`. |
| **Leaf granularity** | A `Leaf` is a **foliage emission point** (one per `leaf_cluster_count` member per node), carrying its own phyllotactic `orientation`. The cluster fan moves from render-time to emission-time. `needle_cluster_spacing` (conifer along-shoot) and `n_planes` (cross-blade) stay **render-time expansion** of each leaf. Rejected: one `Leaf` per individual blade/needle (object explosion, no near-term per-blade state need). |

## Data model (`sim/tree.py`)

```python
class LeafState(Enum):
    ACTIVE = auto()
    SENESCENT = auto()    # reserved for caducity follow-up — unused in MVP
    ABSCISSED = auto()    # reserved — unused in MVP

@dataclass(eq=False)
class Leaf:
    parent_node: Node
    orientation: np.ndarray   # blade seating vector (unit), fixed at birth
    birth_time: float         # years, from Clock.t
    state: LeafState = LeafState.ACTIVE

    @property
    def position(self) -> np.ndarray:
        # Derived — tracks sag/elongation automatically, mirrors today's placement.
        return self.parent_node.position + self.parent_node.sag_offset

    def age(self, clock) -> float:
        return clock.t - self.birth_time
```

- `Node` gains `leaves: list[Leaf] = field(default_factory=list)`.
- `Tree.all_leaves()` — iterator walking the node graph (same traversal as the existing
  `all_internodes` accessor), yielding every `Leaf`.
- `eq=False` matches `Bud`/`Internode` (identity semantics). `from __future__ import
  annotations` is already in the file → `Node`/`Leaf` forward refs resolve.
- Deferred (YAGNI): stable per-node leaf index.

## Emission (`phyllotaxy.leaf_directions` + `simulator._emit_node`)

**New `phyllotaxy.leaf_directions(growth_direction, cfg, node_index, *, seed, axis_order,
count, splay_deg) -> (count, 3)`** unit seating vectors. Reuses `lateral_bud_directions`'
per-axis `base_azimuth` progression (spiral / distichous / decussate / whorled), but:

- `node_index` is fed the **per-axis ordinal** (`cur.axis_node_ordinal`) — the #24 fix —
  so leaves spiral correctly along each axis instead of inheriting the scrambled global
  `node_index`.
- inclination is the **leaf insertion angle** from `leaf_splay_deg` (not
  `branch_angle_by_order`); emits `count = leaf_cluster_count` members fanned at
  `2πi/count` around the base azimuth, each `cos(splay)·g + sin(splay)·radial`.

This moves the cluster fan from render-time to **emission-time**: a node emits
`leaf_cluster_count` `Leaf` objects, each with its own phyllotactically-seated
`orientation` (delivers the "seating azimuth uses the per-axis ordinal" criterion).

**In `_emit_node`**, after the lateral/reserve buds are created (we already have `d`,
`new_node`, `axis_ord = cur.axis_node_ordinal`, `t`, `cfg.seed`):

```python
if cfg.geom.enable_leaves and cfg.geom.leaf_cluster_count > 0:
    leaf_dirs = leaf_directions(
        d, cfg.phyllotaxy, node_index=axis_ord, seed=cfg.seed,
        axis_order=cur.axis_order, count=cfg.geom.leaf_cluster_count,
        splay_deg=cfg.geom.leaf_splay_deg,
    )
    for ld in leaf_dirs:
        new_node.leaves.append(
            Leaf(parent_node=new_node, orientation=ld, birth_time=t,
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
def selected_leaves(tree, cfg) -> list[tuple[Leaf, Internode | None, np.ndarray]]:
    """Apex-proximal, ACTIVE leaves actually rendered this build.
    (leaf, source_internode, render_position) per drawn blade-group,
    expanding needle_cluster_spacing along the shoot."""
```

- Walks `tree.all_leaves()`, keeps `state is ACTIVE`, applies the apex-proximity filter
  via the existing `_leaf_bearing_nodes(tree, foliage_depth)` (kept as the selector; only
  `_collect_foliage_sites` is removed). MVP stand-in for caducity — later the depth filter
  drops and `state` does the work.
- `needle_cluster_spacing > 0` (conifers): fan each leaf into up to 8 along-internode
  render positions (today's logic, keyed off the leaf). Broadleaves: one position at
  `leaf.position`.

**`build_leaves_primitive`** iterates `selected_leaves(...)` and lifts `n_planes` blade(s)
along `leaf.orientation`, scaled by `compute_effective_leaf_size(source_iod, …)`, reusing
`_lift_blade`. The render-time `cluster_count` fan inside `_emit_leaf_cluster` goes away
(fan is now individual `Leaf`s); `_lift_blade`, `compute_effective_leaf_size`,
`_basis_perpendicular_to` stay.

**`_total_leaf_area`** walks the same `selected_leaves(...)`, summing `pair_area × eff²`.

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
- `leaf_directions`: returns exactly `count` unit vectors; base azimuth advances with the
  ordinal (ordinal *n* vs *n+1* → rotated seatings); inclination tracks `leaf_splay_deg`;
  deterministic per `(seed, ordinal)`.

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
- `_total_leaf_area` (new path) matches a captured pre-refactor value within float
  tolerance on a fixed seed/species, all leaves ACTIVE — the explicit acceptance criterion.

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
