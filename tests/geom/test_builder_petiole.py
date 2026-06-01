import numpy as np

from palubicki.geom.compound_leaf import build_rachis_primitive
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
