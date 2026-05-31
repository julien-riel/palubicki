# Leaves as First-Class Node Attributes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote leaves from mesh-time synthesis to first-class `Node` attributes — a `Leaf`/`LeafState` data model, per-node emission with phyllotactic seating (#24 ordinal), and a render/diagnostics path that reads leaves off the tree — so future per-leaf features (caducity, age, autumn color) have a foundation.

**Architecture:** Leaves are emitted at *every* node during the sim (`_emit_node`) and live on `Node.leaves`. A shared `selected_leaves(...)` selector picks the apex-proximal `ACTIVE` subset (the `foliage_depth` filter is the MVP stand-in for caducity), and both the renderer and `_total_leaf_area` consume it. Each `Leaf` stores a scalar seating **azimuth**; the renderer rebuilds the blade basis from the render-time stem direction + azimuth + `leaf_splay_deg`, preserving today's splay area-shear so leaf-area stays at exact parity. Vertex positions shift (phyllotactic seating vs even fan) → species goldens are regenerated.

**Tech Stack:** Python (NumPy), pytest, glTF mesh pipeline.

**Spec:** `docs/superpowers/specs/2026-05-31-leaves-first-class-node-attributes-design.md`

**Pre-refactor leaf-area pins (seed 0):** oak `791.24687450`, birch `9.46838697`, maple `111.27648191`, pine `355.28514526`, fir `184.64116855`.

---

## File structure

| File | Responsibility |
|---|---|
| `src/palubicki/sim/tree.py` (modify) | `LeafState` enum, `Leaf` dataclass (`azimuth`/`birth_time`/`state` + derived `position`, `age`), `Node.leaves`, `Tree.all_leaves()`. |
| `src/palubicki/sim/phyllotaxy.py` (modify) | `leaf_azimuths(...)` — pure scalar seating azimuths reusing the per-axis base-azimuth progression. |
| `src/palubicki/sim/simulator.py` (modify) | Emit `leaf_cluster_count` leaves per new node in `_emit_node`. |
| `src/palubicki/geom/leaves.py` (modify) | `selected_leaves(...)` selector + `_shoot_positions`, `_lift_leaf`; rewrite `build_leaves_primitive` to consume leaves; remove `_collect_foliage_sites` + `_emit_leaf_cluster` + the `cluster_count` kwarg. |
| `src/palubicki/geom/builder.py` (modify) | Drop the `cluster_count=` kwarg from the `build_leaves_primitive` call. |
| `src/palubicki/sim/diagnostics.py` (modify) | `_total_leaf_area` walks `selected_leaves(...)`. |
| `tests/sim/test_leaf.py` (create) | Data model + `leaf_azimuths` unit tests. |
| `tests/sim/test_simulator.py` (modify) | Emission tests. |
| `tests/geom/test_leaves_from_nodes.py` (create) | Renderer-from-leaves + selector tests. |
| `tests/sim/test_diagnostics.py` (modify) | Leaf-area pin + adapt the existing cross-check call. |
| `tests/golden/data/*` (regenerate) | Species GLB hashes shift from seating. |

---

## Task 1: `Leaf` / `LeafState` data model

**Files:**
- Modify: `src/palubicki/sim/tree.py`
- Test: `tests/sim/test_leaf.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_leaf.py`:

```python
import numpy as np

from palubicki.sim.tree import Leaf, LeafState, Node, Tree


def test_leafstate_has_three_members():
    assert {s.name for s in LeafState} == {"ACTIVE", "SENESCENT", "ABSCISSED"}


def test_node_leaves_defaults_empty():
    n = Node(position=np.zeros(3))
    assert n.leaves == []


def test_leaf_position_is_derived_and_tracks_node():
    n = Node(position=np.array([1.0, 2.0, 3.0]))
    n.sag_offset = np.array([0.0, -0.5, 0.0])
    leaf = Leaf(parent_node=n, azimuth=0.0, birth_time=1.0)
    assert np.allclose(leaf.position, [1.0, 1.5, 3.0])
    # Moving the node moves the leaf (no frozen world coordinate).
    n.position = np.array([10.0, 0.0, 0.0])
    assert np.allclose(leaf.position, [10.0, -0.5, 0.0])
    assert leaf.state is LeafState.ACTIVE


def test_leaf_age_uses_clock():
    from palubicki.sim.clock import Clock
    n = Node(position=np.zeros(3))
    leaf = Leaf(parent_node=n, azimuth=0.0, birth_time=2.0)
    clock = Clock(dt=1.0)
    clock.t = 5.0
    assert leaf.age(clock) == 3.0


def test_tree_all_leaves_walks_graph():
    root = Node(position=np.zeros(3))
    leaf = Leaf(parent_node=root, azimuth=0.0, birth_time=0.0)
    root.leaves.append(leaf)
    tree = Tree(root=root)
    assert list(tree.all_leaves()) == [leaf]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/sim/test_leaf.py -v`
Expected: FAIL with `ImportError: cannot import name 'Leaf'`.

- [ ] **Step 3: Add the data model**

In `src/palubicki/sim/tree.py`, add `LeafState` near `BudState` (after the `BudState` enum):

```python
class LeafState(Enum):
    ACTIVE = auto()
    SENESCENT = auto()   # reserved for caducity follow-up — unused in MVP
    ABSCISSED = auto()   # reserved — unused in MVP
```

Add the `Leaf` dataclass after the `Bud` dataclass (Leaf references `Node`, which is
defined below — `from __future__ import annotations` at the top of the file makes the
forward reference resolve):

```python
@dataclass(eq=False)
class Leaf:
    parent_node: Node
    azimuth: float            # phyllotactic seating azimuth (radians), fixed at birth
    birth_time: float         # years, from Clock.t
    state: LeafState = LeafState.ACTIVE

    @property
    def position(self) -> np.ndarray:
        # Derived — tracks sag/elongation automatically, mirrors mesh-time placement.
        return self.parent_node.position + self.parent_node.sag_offset

    def age(self, clock) -> float:
        return clock.t - self.birth_time
```

In the `Node` dataclass, add the field (next to `dormant_reserve_buds`):

```python
    leaves: list[Leaf] = field(default_factory=list)
```

In the `Tree` dataclass, add the iterator method:

```python
    def all_leaves(self):
        """Yield every Leaf in the tree (pre-order walk from root)."""
        stack = [self.root]
        while stack:
            node = stack.pop()
            yield from node.leaves
            for iod in node.children_internodes:
                stack.append(iod.child_node)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/sim/test_leaf.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/tree.py tests/sim/test_leaf.py
git commit -m "sim/tree: add Leaf + LeafState + Node.leaves + Tree.all_leaves (#14)"
```

---

## Task 2: `phyllotaxy.leaf_azimuths`

**Files:**
- Modify: `src/palubicki/sim/phyllotaxy.py`
- Test: `tests/sim/test_leaf.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_leaf.py`:

```python
import math

from palubicki.config import PhyllotaxyConfig
from palubicki.sim.phyllotaxy import leaf_azimuths


def test_leaf_azimuths_returns_count_floats():
    cfg = PhyllotaxyConfig(mode="alternate", divergence_angle_deg=137.5)
    az = leaf_azimuths(cfg, node_index=0, axis_order=0, count=3)
    assert len(az) == 3
    assert all(isinstance(a, float) for a in az)
    # count members fanned evenly 2*pi/count apart from the base.
    assert math.isclose(az[1] - az[0], 2 * math.pi / 3, rel_tol=1e-9)
    assert math.isclose(az[2] - az[1], 2 * math.pi / 3, rel_tol=1e-9)


def test_leaf_azimuths_advance_with_ordinal():
    cfg = PhyllotaxyConfig(mode="alternate", divergence_angle_deg=137.5)
    a0 = leaf_azimuths(cfg, node_index=0, axis_order=0, count=1)[0]
    a1 = leaf_azimuths(cfg, node_index=1, axis_order=0, count=1)[0]
    assert math.isclose(a1 - a0, math.radians(137.5), rel_tol=1e-9)


def test_leaf_azimuths_distichous_on_plagiotropic_lateral():
    cfg = PhyllotaxyConfig(mode="alternate", distichous_on_plagiotropic=True)
    # axis_order>0 with the flag -> distichous: 180 deg per node.
    a0 = leaf_azimuths(cfg, node_index=0, axis_order=1, count=1)[0]
    a1 = leaf_azimuths(cfg, node_index=1, axis_order=1, count=1)[0]
    assert math.isclose(a1 - a0, math.pi, rel_tol=1e-9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/sim/test_leaf.py -k azimuths -v`
Expected: FAIL with `ImportError: cannot import name 'leaf_azimuths'`.

- [ ] **Step 3: Implement `leaf_azimuths`**

In `src/palubicki/sim/phyllotaxy.py`, add (after `lateral_bud_directions`):

```python
def leaf_azimuths(
    cfg: PhyllotaxyConfig,
    node_index: int,
    *,
    axis_order: int,
    count: int,
) -> list[float]:
    """Phyllotactic seating azimuths (radians) for ``count`` leaves at one node.

    Replicates the per-axis ``base_azimuth`` progression of
    ``lateral_bud_directions`` (so leaves spiral correctly along each axis via the
    #24 ordinal), then fans ``count`` members evenly ``2*pi/count`` apart. Pure
    scalar: the renderer turns (azimuth, render-time stem direction, leaf_splay_deg)
    into blade geometry, keeping the splay area-shear in one place.

    NOTE: the base-azimuth switch below is deliberately duplicated from
    ``lateral_bud_directions`` rather than shared, so that skeleton-driving function
    stays byte-for-byte untouched. Keep the two in sync if the progression changes.
    """
    if cfg.distichous_on_plagiotropic and axis_order > 0:
        mode = "distichous"
    else:
        mode = cfg.mode

    if mode == "decussate":
        base = (
            math.radians(cfg.divergence_angle_deg) * node_index
            + (math.pi / 2.0) * (node_index % 2)
        )
    elif mode == "whorled":
        k = max(1, cfg.whorl_count)
        base = (
            math.radians(cfg.divergence_angle_deg) * node_index
            + (math.pi / k) * (node_index % 2)
        )
    elif mode == "distichous":
        base = math.pi * node_index
    else:  # alternate / opposite -> simple spiral progression
        base = math.radians(cfg.divergence_angle_deg) * node_index

    return [base + 2.0 * math.pi * i / count for i in range(count)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/sim/test_leaf.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/phyllotaxy.py tests/sim/test_leaf.py
git commit -m "sim/phyllotaxy: add leaf_azimuths (per-axis phyllotactic leaf seating) (#14)"
```

---

## Task 3: Emit leaves in `_emit_node`

**Files:**
- Modify: `src/palubicki/sim/simulator.py`
- Test: `tests/sim/test_simulator.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_simulator.py`:

```python
def test_every_node_emits_leaves(tmp_path):
    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate
    from palubicki.sim.tree import LeafState
    cfg = load_config(
        yaml_path=None,
        cli_overrides={"envelope.marker_count": 200, "sim.max_simulation_years": 5,
                       "seed": 3, "geom.leaf_cluster_count": 3},
        output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)
    # Every node that has a parent internode (i.e. every emitted node) carries
    # leaf_cluster_count ACTIVE leaves with a non-negative birth_time.
    n_nodes = 0
    stack = [tree.root]
    while stack:
        node = stack.pop()
        if node.parent_internode is not None:
            n_nodes += 1
            assert len(node.leaves) == 3
            assert all(lf.state is LeafState.ACTIVE for lf in node.leaves)
            assert all(lf.birth_time >= 0.0 for lf in node.leaves)
        for iod in node.children_internodes:
            stack.append(iod.child_node)
    assert n_nodes > 0
    assert len(list(tree.all_leaves())) == n_nodes * 3


def test_enable_leaves_false_emits_no_leaves(tmp_path):
    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate
    cfg = load_config(
        yaml_path=None,
        cli_overrides={"envelope.marker_count": 200, "sim.max_simulation_years": 5,
                       "seed": 3, "geom.enable_leaves": False},
        output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)
    assert list(tree.all_leaves()) == []


def test_leaves_do_not_perturb_skeleton(tmp_path):
    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate
    import numpy as np

    def sig(tree):
        out = []
        stack = [tree.root]
        while stack:
            node = stack.pop()
            out.append(tuple(np.round(node.position, 6).tolist()))
            for iod in node.children_internodes:
                stack.append(iod.child_node)
        return sorted(out)

    base = {"envelope.marker_count": 200, "sim.max_simulation_years": 5, "seed": 3}
    on = simulate(load_config(yaml_path=None, cli_overrides={**base, "geom.enable_leaves": True}, output=tmp_path / "a.glb"))
    off = simulate(load_config(yaml_path=None, cli_overrides={**base, "geom.enable_leaves": False}, output=tmp_path / "b.glb"))
    assert sig(on) == sig(off)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/sim/test_simulator.py::test_every_node_emits_leaves -v`
Expected: FAIL with `assert 0 == 3` (no leaves emitted yet).

- [ ] **Step 3: Wire emission into `_emit_node`**

In `src/palubicki/sim/simulator.py`:

(a) Extend the phyllotaxy import (the line `from palubicki.sim.phyllotaxy import lateral_bud_directions, reserve_bud_directions`):

```python
from palubicki.sim.phyllotaxy import (
    lateral_bud_directions,
    leaf_azimuths,
    reserve_bud_directions,
)
```

(b) Extend the tree import (the line `from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree`):

```python
from palubicki.sim.tree import Bud, BudState, Internode, Leaf, LeafState, Node, Tree
```

(c) In `_emit_node`, immediately before the final `cur.state = BudState.DEAD` line, insert:

```python
    # Leaves (#14): emit leaf_cluster_count leaves at this node, seated by the
    # per-axis phyllotactic azimuth (same #24 ordinal that drives lateral buds).
    # The renderer selects which leaves to draw (apex-proximity) and turns the
    # stored azimuth into blade geometry.
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

(`axis_ord` and `t` are already in scope in `_emit_node`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_simulator.py -k "leaves or skeleton" -v`
Expected: PASS (emission + enable-false + skeleton-unperturbed).

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/simulator.py tests/sim/test_simulator.py
git commit -m "sim: emit per-node leaves with phyllotactic seating in _emit_node (#14)"
```

---

## Task 4: Render leaves from `Node.leaves`

**Files:**
- Modify: `src/palubicki/geom/leaves.py`, `src/palubicki/geom/builder.py`
- Test: `tests/geom/test_leaves_from_nodes.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/geom/test_leaves_from_nodes.py`:

```python
from pathlib import Path

import numpy as np

from palubicki.config import load_config
from palubicki.geom.leaves import selected_leaves, build_leaves_primitive
from palubicki.geom.mesh import Material
from palubicki.sim.simulator import simulate
from palubicki.sim.tree import LeafState


def _mat():
    return Material(name="leaf", base_color=(0.4, 0.6, 0.2, 1.0), metallic=0.0,
                    roughness=0.85, base_color_texture_png=None, alpha_mode="MASK",
                    alpha_cutoff=0.5, double_sided=True)


def _oak_tree(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={"seed": 0},
                      output=tmp_path / "t.glb", species="oak")
    return simulate(cfg), cfg


def test_selected_leaves_only_active(tmp_path):
    tree, cfg = _oak_tree(tmp_path)
    g = cfg.geom
    recs = selected_leaves(tree, foliage_depth=g.foliage_depth,
                           needle_cluster_spacing=g.needle_cluster_spacing)
    assert len(recs) > 0
    assert all(leaf.state is LeafState.ACTIVE for leaf, _d, _s, _p in recs)
    # Marking a leaf senescent drops it from selection.
    first_leaf = recs[0][0]
    first_leaf.state = LeafState.SENESCENT
    recs2 = selected_leaves(tree, foliage_depth=g.foliage_depth,
                            needle_cluster_spacing=g.needle_cluster_spacing)
    assert len(recs2) < len(recs)


def test_build_leaves_primitive_nonempty(tmp_path):
    tree, cfg = _oak_tree(tmp_path)
    g = cfg.geom
    prim = build_leaves_primitive(
        tree, leaf_size=g.leaf_size, material=_mat(), aspect=g.leaf_aspect,
        splay_deg=g.leaf_splay_deg, foliage_depth=g.foliage_depth,
        needle_cluster_spacing=g.needle_cluster_spacing, sun_shade_k=g.leaf_sun_shade_k,
        leaf_shape=g.leaf_shape, leaf_margin=g.leaf_margin,
        leaf_margin_depth=g.leaf_margin_depth, leaf_margin_count=g.leaf_margin_count,
    )
    assert prim.positions.shape[0] > 0
    assert prim.indices.shape[0] % 3 == 0


def test_build_leaves_primitive_empty_when_no_active(tmp_path):
    tree, cfg = _oak_tree(tmp_path)
    g = cfg.geom
    for leaf in tree.all_leaves():
        leaf.state = LeafState.ABSCISSED
    prim = build_leaves_primitive(
        tree, leaf_size=g.leaf_size, material=_mat(), aspect=g.leaf_aspect,
        splay_deg=g.leaf_splay_deg, foliage_depth=g.foliage_depth,
        needle_cluster_spacing=g.needle_cluster_spacing, sun_shade_k=g.leaf_sun_shade_k,
        leaf_shape=g.leaf_shape, leaf_margin=g.leaf_margin,
        leaf_margin_depth=g.leaf_margin_depth, leaf_margin_count=g.leaf_margin_count,
    )
    assert prim.positions.shape[0] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/geom/test_leaves_from_nodes.py -v`
Expected: FAIL with `ImportError: cannot import name 'selected_leaves'`.

- [ ] **Step 3: Rewrite `geom/leaves.py`**

In `src/palubicki/geom/leaves.py`:

(a) Update the import line `from palubicki.sim.tree import BudState, Internode, Node, Tree` to add `Leaf, LeafState`:

```python
from palubicki.sim.tree import BudState, Internode, Leaf, LeafState, Node, Tree
```

(b) Add `selected_leaves` (after `_leaf_bearing_nodes`, replacing the role of `_collect_foliage_sites`):

```python
def selected_leaves(
    tree: Tree, *, foliage_depth: int, needle_cluster_spacing: float = 0.0
) -> list[tuple[Leaf, np.ndarray, Internode | None, np.ndarray]]:
    """The apex-proximal, ACTIVE leaves actually rendered this build.

    Returns (leaf, stem_direction, source_internode, render_position) per drawn
    blade-group. Shared by the renderer and sim/diagnostics so the .glb and the
    leaf-area metric cannot drift. The foliage_depth apex filter is the MVP
    stand-in for caducity; when caducity lands it is dropped and the ACTIVE
    state filter does the work alone.

    needle_cluster_spacing > 0 (conifers) fans each leaf into up to
    _MAX_CLUSTERS_PER_INTERNODE positions along the (bent) parent segment, using
    the segment tangent as the stem direction (matching the legacy along-shoot
    placement). Broadleaves render one group at the node tip.
    """
    if foliage_depth < 1:
        return []
    out: list[tuple[Leaf, np.ndarray, Internode | None, np.ndarray]] = []
    for node, direction, source_iod in _leaf_bearing_nodes(tree, foliage_depth):
        active = [lf for lf in node.leaves if lf.state is LeafState.ACTIVE]
        if not active:
            continue
        node_pos = np.asarray(node.position + node.sag_offset, dtype=np.float64)
        node_dir = np.asarray(direction, dtype=np.float64)
        if needle_cluster_spacing > 0.0 and source_iod is not None:
            par = source_iod.parent_node
            par_pos = np.asarray(par.position + par.sag_offset, dtype=np.float64)
            seg = node_pos - par_pos
            seg_len = float(np.linalg.norm(seg))
            if seg_len < 1e-12:
                positions = [(node_pos, node_dir)]
            else:
                seg_dir = seg / seg_len
                n = int(seg_len / needle_cluster_spacing) + 1
                n = max(1, min(_MAX_CLUSTERS_PER_INTERNODE, n))
                positions = [(par_pos + ((k + 1) / n) * seg, seg_dir) for k in range(n)]
        else:
            positions = [(node_pos, node_dir)]
        for leaf in active:
            for pos, stem_dir in positions:
                out.append((leaf, stem_dir, source_iod, pos))
    return out
```

(c) Delete `_collect_foliage_sites` entirely (lines 167-202 in the current file).

(d) Replace `build_leaves_primitive` (the whole function) with:

```python
def build_leaves_primitive(
    tree: Tree,
    *,
    leaf_size: float,
    material: Material,
    aspect: float = 1.0,
    splay_deg: float = 0.0,
    foliage_depth: int = 1,
    needle_cluster_spacing: float = 0.0,
    sun_shade_k: float = 0.0,
    leaf_shape: str = "ovate",
    leaf_margin: str = "entire",
    leaf_margin_depth: float = 0.0,
    leaf_margin_count: int = 0,
) -> Primitive:
    """Triangulate every selected (apex-proximal, ACTIVE) leaf on the tree.

    Each Leaf already encodes one phyllotactically-seated cluster member (the fan
    moved to emission time, #14), so there is no render-time cluster_count fan.
    ``n_planes`` is 2 (cross-blade) for linear needles, 1 otherwise. Blade size
    scales by compute_effective_leaf_size(source_internode, ...).
    """
    records = selected_leaves(
        tree, foliage_depth=foliage_depth,
        needle_cluster_spacing=needle_cluster_spacing,
    )
    if not records:
        return Primitive(
            positions=np.zeros((0, 3), dtype=np.float32),
            normals=np.zeros((0, 3), dtype=np.float32),
            uvs=np.zeros((0, 2), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
            material=material,
        )

    blade_pos_unit, _, blade_uv, blade_idx = build_blade(
        length=1.0, width=aspect, shape=leaf_shape, margin=leaf_margin,
        margin_depth=leaf_margin_depth, margin_count=leaf_margin_count,
    )
    blade_v_count = blade_pos_unit.shape[0]
    blade_i_count = blade_idx.shape[0]
    n_planes = 2 if leaf_shape == "linear" else 1

    verts_per_leaf = n_planes * blade_v_count
    idx_per_leaf = n_planes * blade_i_count
    n = len(records)
    positions = np.empty((n * verts_per_leaf, 3), dtype=np.float32)
    normals = np.empty((n * verts_per_leaf, 3), dtype=np.float32)
    uvs = np.empty((n * verts_per_leaf, 2), dtype=np.float32)
    indices = np.empty((n * idx_per_leaf,), dtype=np.uint32)

    splay_rad = math.radians(splay_deg)
    for i, (leaf, stem_dir, source_iod, render_pos) in enumerate(records):
        eff_size = compute_effective_leaf_size(source_iod, leaf_size, sun_shade_k)
        v_start = i * verts_per_leaf
        i_start = i * idx_per_leaf
        _lift_leaf(
            render_pos, stem_dir, leaf.azimuth, eff_size, splay_rad, n_planes,
            blade_pos_unit, blade_uv, blade_idx,
            positions[v_start : v_start + verts_per_leaf],
            normals[v_start : v_start + verts_per_leaf],
            uvs[v_start : v_start + verts_per_leaf],
            indices[i_start : i_start + idx_per_leaf],
            v_start,
        )
    return Primitive(positions=positions, normals=normals, uvs=uvs, indices=indices, material=material)
```

(e) Replace `_emit_leaf_cluster` (the whole function) with `_lift_leaf`:

```python
def _lift_leaf(center, direction, azimuth, size, splay_rad, n_planes,
               blade_pos_unit, blade_uv, blade_idx,
               out_pos, out_norm, out_uv, out_idx, base):
    """Lift one phyllotactically-seated leaf (n_planes blades) at ``center``.

    Reconstructs the blade basis from the render-time stem ``direction`` + the
    leaf ``azimuth`` + ``splay_rad`` — identical math to the legacy per-cluster-
    member lift, so blade area (cos(splay) plane-A shear) is preserved exactly;
    only the azimuth now carries the phyllotactic seating.
    """
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    right, forward = _basis_perpendicular_to(d)

    blade_v_count = blade_pos_unit.shape[0]
    blade_i_count = blade_idx.shape[0]
    leaf_center = np.asarray(center, dtype=np.float64)

    rot_axis_u = math.cos(azimuth) * right + math.sin(azimuth) * forward
    rot_axis_w = -math.sin(azimuth) * right + math.cos(azimuth) * forward
    leaf_up = math.cos(splay_rad) * d + math.sin(splay_rad) * rot_axis_u

    # Plane A: basis_u = rot_axis_u, basis_v = leaf_up, normal = rot_axis_w
    _lift_blade(
        blade_pos_unit, blade_uv, blade_idx,
        leaf_center, rot_axis_u, leaf_up, rot_axis_w, size,
        out_pos[0:blade_v_count], out_norm[0:blade_v_count],
        out_uv[0:blade_v_count], out_idx[0:blade_i_count], base,
    )
    if n_planes == 2:
        slot_b = blade_v_count
        idx_b = blade_i_count
        _lift_blade(
            blade_pos_unit, blade_uv, blade_idx,
            leaf_center, rot_axis_w, leaf_up, rot_axis_u, size,
            out_pos[slot_b : slot_b + blade_v_count],
            out_norm[slot_b : slot_b + blade_v_count],
            out_uv[slot_b : slot_b + blade_v_count],
            out_idx[idx_b : idx_b + blade_i_count],
            base + slot_b,
        )
```

Keep `compute_effective_leaf_size`, `_leaf_bearing_nodes`, `_lift_blade`,
`_basis_perpendicular_to` unchanged. The `cluster_count` parameter is gone from
`build_leaves_primitive`.

(f) In `src/palubicki/geom/builder.py`, delete the `cluster_count=cfg.geom.leaf_cluster_count,` line from the `build_leaves_primitive(...)` call (lines 60).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/geom/test_leaves_from_nodes.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/geom/leaves.py src/palubicki/geom/builder.py tests/geom/test_leaves_from_nodes.py
git commit -m "geom/leaves: render from Node.leaves via selected_leaves; drop foliage-site synthesis (#14)"
```

---

## Task 5: Diagnostics `_total_leaf_area` from leaves + parity pin

**Files:**
- Modify: `src/palubicki/sim/diagnostics.py`, `tests/sim/test_diagnostics.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_diagnostics.py`:

```python
def test_total_leaf_area_matches_pre_refactor_pin():
    """Leaf area is preserved across the #14 refactor (azimuth seating keeps the
    cos(splay) shear). Pin captured on main before the refactor, seed 0."""
    from pathlib import Path
    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate
    from palubicki.sim.diagnostics import compute_metrics
    pins = {"oak": 791.24687450, "birch": 9.46838697, "maple": 111.27648191}
    for sp, expected in pins.items():
        cfg = load_config(yaml_path=None, cli_overrides={"seed": 0},
                          output=Path("t.glb"), species=sp)
        m = compute_metrics(simulate(cfg), cfg=cfg)
        assert m["total_leaf_area"] == pytest.approx(expected, rel=1e-6), sp
```

Also **update the existing** `test_leaf_area_matches_geom_helper` in this file: remove the
`cluster_count=g.leaf_cluster_count,` kwarg from its `build_leaves_primitive(...)` call (the
parameter no longer exists). Leave the rest of that test unchanged.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_total_leaf_area_matches_pre_refactor_pin -v`
Expected: FAIL (old `_total_leaf_area` still calls `_collect_foliage_sites`, now removed → `ImportError`/`AttributeError`).

- [ ] **Step 3: Rewrite `_total_leaf_area`**

In `src/palubicki/sim/diagnostics.py`, replace the body of `_total_leaf_area` with:

```python
def _total_leaf_area(tree: Tree, cfg: Config) -> float:
    """Sum of rendered leaf surface areas across the selected leaves.

    Each selected leaf renders one blade-group: ``pair_area`` = unit_blade_area *
    (cos(splay) [plane A] + 1 if cross-blade [plane B]). The fan that used to
    multiply by cluster_count is now expressed as cluster_count separate Leaf
    objects per node, so the per-leaf sum reproduces the pre-refactor total.
    """
    from palubicki.geom.leaf_blade import build_blade
    from palubicki.geom.leaves import compute_effective_leaf_size, selected_leaves

    g = cfg.geom
    records = selected_leaves(
        tree, foliage_depth=g.foliage_depth,
        needle_cluster_spacing=g.needle_cluster_spacing,
    )
    if not records:
        return 0.0

    blade_pos, _, _, blade_idx = build_blade(
        length=1.0, width=g.leaf_aspect, shape=g.leaf_shape,
        margin=g.leaf_margin, margin_depth=g.leaf_margin_depth,
        margin_count=g.leaf_margin_count,
    )
    pos2d = blade_pos.astype(np.float64)
    tris = blade_idx.reshape(-1, 3)
    e1 = pos2d[tris[:, 1]] - pos2d[tris[:, 0]]
    e2 = pos2d[tris[:, 2]] - pos2d[tris[:, 0]]
    unit_blade_area = float(0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum())

    splay_rad = math.radians(g.leaf_splay_deg)
    n_planes = 2 if g.leaf_shape == "linear" else 1
    plane_b_factor = 1.0 if n_planes == 2 else 0.0
    pair_area = unit_blade_area * (math.cos(splay_rad) + plane_b_factor)

    total = 0.0
    for _leaf, _stem_dir, source_iod, _pos in records:
        eff = compute_effective_leaf_size(source_iod, g.leaf_size, g.leaf_sun_shade_k)
        total += pair_area * (eff * eff)
    return total
```

(`math` is already imported at the top of `diagnostics.py` — the old `_total_leaf_area`
used `math.radians`/`math.cos` — so no new import is needed.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -k "leaf_area" -v`
Expected: PASS (the pin matches within `rel=1e-6`, and the geometric cross-check still holds).

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/sim/diagnostics.py tests/sim/test_diagnostics.py
git commit -m "sim/diagnostics: total_leaf_area from selected_leaves; pin pre-refactor parity (#14)"
```

---

## Task 6: Regenerate goldens, smoke test, full suite

**Files:** `tests/golden/data/*` (regenerated)

- [ ] **Step 1: Confirm the leaf-bearing suites are green**

Run: `.venv/bin/pytest tests/sim/test_leaf.py tests/geom/test_leaves_from_nodes.py tests/sim/test_diagnostics.py -q`
Expected: PASS.

- [ ] **Step 2: Smoke-test the four species produce valid GLBs with foliage**

Run:
```bash
for s in oak birch maple pine; do .venv/bin/palubicki generate --species $s --seed 42 --years 10 -o /tmp/$s.glb && echo "$s $(stat -f%z /tmp/$s.glb) bytes"; done
```
Expected: each exits 0 and prints a non-trivial byte count.

- [ ] **Step 3: Run the full non-slow suite**

Run: `.venv/bin/pytest -q -m "not slow"`
Expected: PASS. Any failure outside the leaf/diagnostics area is a regression — investigate before regenerating goldens.

- [ ] **Step 4: Regenerate the species goldens (seating shifted vertex positions)**

Run: `.venv/bin/pytest tests/golden -m slow --update-goldens -q`
Then inspect what changed:
Run: `git status --porcelain tests/golden/data`
Expected: only `species_*.sha256` files change. If a non-species golden (skeleton / bark / light / forest-position hash) changed, STOP — the refactor perturbed something it shouldn't (leaves must be inert to the skeleton); investigate before committing.

- [ ] **Step 5: Re-run the slow suite clean to confirm the new goldens pin**

Run: `.venv/bin/pytest -q -m slow`
Expected: PASS.

- [ ] **Step 6: Lint**

Run: `.venv/bin/ruff check src tests`
Expected: All checks passed.

- [ ] **Step 7: Commit**

```bash
git add tests/golden/data
git commit -m "test(golden): regenerate species goldens for phyllotactic leaf seating (#14)"
```

---

## Task 7: Docs

**Files:** `docs/roadmap.md`, `docs/botany/simulator-gap-analysis.md`

- [ ] **Step 1: Move #14 to "Fait" in `docs/roadmap.md`**

Remove the `#14 → #6, #5, #7 — foliage` item from "À faire (dans l'ordre)" (it is the first
item) and renumber the rest. The follow-ups #6/#5/#7 remain — add a short note that #14
(their blocker) has landed. Add a row to the "Fait" table:

```markdown
| #14 | Feuilles en attributs de `Node` (`Leaf`/`LeafState`) : émission par nœud avec azimut phyllotactique (ordinal par-axe #24), rendu via `selected_leaves` (sous-ensemble apex-proximal `ACTIVE`, `foliage_depth` comme sélecteur — futur état caducité). Position dérivée (suit sag/élongation) ; `total_leaf_area` à parité exacte (cisaillement `cos(splay)` préservé). Débloque #5/#6/#7 + future caducité/couleur d'automne. Goldens d'espèce repassés (siège phyllotactique décale les sommets) | #57 |
```

- [ ] **Step 2: Update `docs/botany/simulator-gap-analysis.md`**

This touches a botanical concept (§2 phytomer / §6 leaves). Flip the "leaves as first-class
node attributes" row from ❌ to ✅ (foundation; note state transitions remain a follow-up),
and refresh the §2 + §6 **Verdict** lines to state leaves are now first-class `Node`
attributes with per-leaf age/state (caducity wired but only `ACTIVE` in production). Update
the "Last reviewed" line at the top to `2026-05-31, after leaves-as-first-class-node-
attributes (#14)` with a one-sentence summary, and refresh the "Top remaining
recommendations" if leaves were on it.

- [ ] **Step 3: Commit**

```bash
git add docs/roadmap.md docs/botany/simulator-gap-analysis.md
git commit -m "docs: #14 leaves-on-nodes landed — roadmap + gap-analysis (#57)"
```

---

## Self-review notes

- **Spec coverage:** `Leaf`/`LeafState` (T1) · `Node.leaves` (T1) · `Tree.all_leaves` (T1) ·
  emission at every node with `birth_time` (T3) · seating azimuth via per-axis ordinal (T2/T3) ·
  `build_leaves_primitive` consumes `all_leaves` via the `selected_leaves` selector, no
  `_collect_foliage_sites` (T4) · `_total_leaf_area` parity within tolerance (T5) · 4-species
  smoke (T6) · golden suite regenerated (T6) · docs incl. gap-analysis (T7). All nine
  acceptance criteria mapped.
- **Parity:** `_total_leaf_area` pinned to the captured pre-refactor values (oak 791.24687450
  etc.) at `rel=1e-6`, plus the geometric cross-check `test_leaf_area_matches_geom_helper`
  (now exercising the shared path). Skeleton/bark/light goldens must NOT move (T6 step 4
  gate).
- **Name consistency:** `LeafState`, `Leaf.azimuth`/`position`/`age`, `Node.leaves`,
  `Tree.all_leaves`, `leaf_azimuths(cfg, node_index, *, axis_order, count)`,
  `selected_leaves(tree, *, foliage_depth, needle_cluster_spacing)`, `_lift_leaf`,
  `_shoot_positions` logic inlined in `selected_leaves` — consistent across tasks. The
  `cluster_count` kwarg is removed from `build_leaves_primitive` in T4 and every caller
  (builder.py T4, the diagnostics cross-check test T5) is updated in the same task that
  removes it.
- **Deferred (out of scope, no task):** caducity transitions, per-leaf light, autumn color,
  preset re-tuning, config-key removal, per-node leaf index, sim/render gate split.
