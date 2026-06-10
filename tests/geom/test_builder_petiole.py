import numpy as np

from palubicki.geom.compound_leaf import build_rachis_primitive
from palubicki.geom.leaves_instanced import (
    build_petioles_instanced,
    quat_to_matrix,
)
from palubicki.geom.mesh import Material
from palubicki.sim.tree import Bud, BudState, Internode, Leaf, LeafState, Node, Tree


def _mat(name="petiole"):
    return Material(name=name, base_color=(1, 1, 1, 1), metallic=0.0, roughness=1.0,
                    base_color_texture_png=None, alpha_mode="OPAQUE",
                    alpha_cutoff=0.5, double_sided=False)


def _single_leaf_tree():
    """One internode root->child apex, one ACTIVE leaf, one terminal bud.

    Mirrors the working fixture _tree_one_apex_with_internode in
    tests/geom/test_leaves.py (selected_leaves walks tree.active_buds to find
    leaf-bearing apex nodes, so the Bud is required).
    """
    root = Node(position=np.zeros(3))
    child = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=root, child_node=child, length=1.0,
                    is_main_axis=True, light_factor=1.0)
    root.children_internodes.append(iod)
    child.parent_internode = iod
    bud = Bud(position=child.position.copy(), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=child, state=BudState.ACTIVE)
    child.terminal_bud = bud
    child.leaves.append(
        Leaf(parent_node=child, azimuth=0.0, birth_time=0.0, state=LeafState.ACTIVE)
    )
    tree = Tree(root=root)
    tree.active_buds.append(bud)
    tree.all_internodes.append(iod)
    return tree


# ratios (leaf-size multiples), exactly as builder.py builds them for simple leaves
_SIMPLE_PETIOLE_SPECS = {
    "leaflet_count": 1, "leaflet_pair_count": 0, "terminal_leaflet": False,
    "rachis_length": 0.0, "petiole_length": 0.3, "rachis_radius": 0.02,
    "petiole_taper": 0.6,
}


def test_simple_petiole_tube_has_expected_vertices():
    prim = build_rachis_primitive(
        _single_leaf_tree(), material=_mat(), leaf_size=0.1, foliage_depth=1,
        leaf_kind="simple", leaflet_specs=_SIMPLE_PETIOLE_SPECS, ring_sides=4,
    )
    # one tapered tube for one leaf: 2 * ring_sides vertices
    assert prim.positions.shape[0] == 8


def test_zero_petiole_tube_is_empty():
    specs = dict(_SIMPLE_PETIOLE_SPECS, petiole_length=0.0)
    prim = build_rachis_primitive(
        _single_leaf_tree(), material=_mat(), leaf_size=0.1, foliage_depth=1,
        leaf_kind="simple", leaflet_specs=specs, ring_sides=4,
    )
    assert prim.positions.shape[0] == 0


# ── GPU-instanced petioles (geom/leaves_instanced.py) ──────────────────────────

_PINNATE_SPECS = {
    "leaflet_count": 5, "leaflet_pair_count": 2, "terminal_leaflet": True,
    "rachis_length": 0.7, "petiole_length": 0.2, "rachis_radius": 0.02,
    "petiole_taper": 1.0,
}


def _multi_leaf_tree():
    """Single apex node bearing three leaves at distinct azimuths, so the
    instanced placement (T/R/S) is exercised across differing leaf frames."""
    tree = _single_leaf_tree()
    apex = tree.active_buds[0].parent_node
    apex.leaves.clear()
    for az in (0.0, 2.0, 4.0):
        apex.leaves.append(
            Leaf(parent_node=apex, azimuth=az, birth_time=0.0, state=LeafState.ACTIVE)
        )
    return tree


def _reconstruct(inst):
    """World (positions, normals, tangent.xyz) of one InstancedPrimitive, in
    instance order: ``T + R @ (scale * canonical)`` for positions, ``R @ dir`` for
    directions (uniform scale leaves directions unchanged)."""
    cp = inst.canonical.positions.astype(np.float64)
    cn = inst.canonical.normals.astype(np.float64)
    ct = inst.canonical.tangents[:, :3].astype(np.float64)
    pos, nrm, tan = [], [], []
    for t, q, s in zip(inst.translations, inst.rotations, inst.scales, strict=True):
        r = quat_to_matrix(q.astype(np.float64))
        pos.append(t.astype(np.float64)[None, :] + (s.astype(np.float64) * cp) @ r.T)
        nrm.append(cn @ r.T)
        tan.append(ct @ r.T)
    return np.concatenate(pos), np.concatenate(nrm), np.concatenate(tan)


def _assert_instanced_matches_baked(tree, *, leaf_kind, specs, ring_sides):
    """The instanced petioles reconstruct the baked rachis primitive exactly.

    Baked vertex order is per-leaf ``[seg0, seg1, ...]``; instanced groups by
    segment (``[seg0 over all leaves], [seg1 over all leaves], ...``). Both iterate
    ``selected_leaves`` in the same order, so re-interleaving the per-segment
    instanced blocks recovers the baked order for an element-wise comparison."""
    kw = {"material": _mat(), "leaf_size": 0.1, "foliage_depth": 1,
          "leaf_kind": leaf_kind, "leaflet_specs": specs, "ring_sides": ring_sides}
    baked = build_rachis_primitive(tree, **kw)
    insts = build_petioles_instanced(tree, **kw)
    assert insts, "expected at least one instanced petiole segment"

    ring2 = 2 * ring_sides
    n_seg = len(insts)
    n_leaf = insts[0].translations.shape[0]
    assert baked.positions.shape[0] == n_seg * n_leaf * ring2

    seg = [_reconstruct(i) for i in insts]
    rec_pos = np.empty_like(baked.positions, dtype=np.float64)
    rec_nrm = np.empty_like(baked.normals, dtype=np.float64)
    rec_tan = np.empty((baked.tangents.shape[0], 3), dtype=np.float64)
    for li in range(n_leaf):
        for j in range(n_seg):
            dst = (li * n_seg + j) * ring2
            src = li * ring2
            rec_pos[dst:dst + ring2] = seg[j][0][src:src + ring2]
            rec_nrm[dst:dst + ring2] = seg[j][1][src:src + ring2]
            rec_tan[dst:dst + ring2] = seg[j][2][src:src + ring2]

    np.testing.assert_allclose(baked.positions, rec_pos, atol=1e-4)
    np.testing.assert_allclose(baked.normals, rec_nrm, atol=1e-4)
    np.testing.assert_allclose(baked.tangents[:, :3], rec_tan, atol=1e-4)
    # The tube frame [right|forward|axis] is right-handed, so R is a proper rotation
    # and the MikkTSpace handedness is preserved (baked writes +1).
    for i in insts:
        assert np.all(i.canonical.tangents[:, 3] == 1.0)


def test_instanced_simple_petiole_matches_baked():
    _assert_instanced_matches_baked(
        _multi_leaf_tree(), leaf_kind="simple",
        specs=_SIMPLE_PETIOLE_SPECS, ring_sides=5,
    )


def test_instanced_pinnate_rachis_matches_baked():
    _assert_instanced_matches_baked(
        _multi_leaf_tree(), leaf_kind="pinnate",
        specs=_PINNATE_SPECS, ring_sides=4,
    )


def test_instanced_petioles_empty_when_no_rachis():
    # simple leaf with no petiole -> no rachis segments -> no instanced primitives.
    specs = dict(_SIMPLE_PETIOLE_SPECS, petiole_length=0.0)
    insts = build_petioles_instanced(
        _multi_leaf_tree(), material=_mat(), leaf_size=0.1, foliage_depth=1,
        leaf_kind="simple", leaflet_specs=specs, ring_sides=4,
    )
    assert insts == []


def test_instanced_simple_petiole_instance_count():
    insts = build_petioles_instanced(
        _multi_leaf_tree(), material=_mat(), leaf_size=0.1, foliage_depth=1,
        leaf_kind="simple", leaflet_specs=_SIMPLE_PETIOLE_SPECS, ring_sides=5,
    )
    # one segment (petiole), one instance per leaf (three leaves).
    assert len(insts) == 1
    assert insts[0].translations.shape[0] == 3
    assert insts[0].rotations.shape == (3, 4)
    assert insts[0].scales.shape == (3, 3)
