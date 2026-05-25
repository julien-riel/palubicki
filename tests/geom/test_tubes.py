# tests/geom/test_tubes.py
import numpy as np

from palubicki.geom.mesh import Material
from palubicki.geom.tubes import build_bark_primitive
from palubicki.sim.tree import Internode, Node, Tree


def _vertical_chain(n=5, length=1.0, r=0.05):
    root = Node(position=np.zeros(3))
    prev = root
    iods = []
    for i in range(n):
        child = Node(position=np.array([0.0, float(i + 1) * length, 0.0]))
        iod = Internode(parent_node=prev, child_node=child, length=length, is_main_axis=True)
        iod.diameter = 2 * r
        prev.children_internodes.append(iod)
        child.parent_internode = iod
        iods.append(iod)
        prev = child
    return Tree(root=root, all_internodes=iods)


def _mat():
    return Material(name="bark", base_color=(1, 1, 1, 1), metallic=0.0, roughness=1.0,
                    base_color_texture_png=None, alpha_mode="OPAQUE",
                    alpha_cutoff=0.5, double_sided=False)


def test_vertical_chain_vertex_count():
    tree = _vertical_chain(n=4)
    prim = build_bark_primitive(tree, ring_sides=8, material=_mat())
    # 5 rings (root + 4 children), each 9 columns (8 sides + 1 seam dup) = 45 vertices for tube
    # Plus root cap fan = 8 fan triangles + 1 center vertex = 9 extra vertices
    assert prim.positions.shape[1] == 3
    assert prim.positions.dtype == np.float32
    assert prim.positions.shape[0] >= 45


def test_no_nan_or_inf():
    tree = _vertical_chain(n=3)
    prim = build_bark_primitive(tree, ring_sides=6, material=_mat())
    assert np.isfinite(prim.positions).all()
    assert np.isfinite(prim.normals).all()
    assert np.isfinite(prim.uvs).all()


def test_normals_radial_for_vertical_chain():
    tree = _vertical_chain(n=2)
    prim = build_bark_primitive(tree, ring_sides=8, material=_mat())
    # all tube normals should be perpendicular to +Y (i.e., y-component near 0)
    n_y = prim.normals[:, 1]
    # cap may have y normal; check only first 18 (2 rings * 9 cols) tube vertices
    tube_normals_y = n_y[:18]
    assert np.all(np.abs(tube_normals_y) < 1e-5)


def test_indices_within_bounds_and_uint32():
    tree = _vertical_chain(n=3)
    prim = build_bark_primitive(tree, ring_sides=6, material=_mat())
    assert prim.indices.dtype == np.uint32
    assert prim.indices.max() < prim.positions.shape[0]


def _tree_with_lateral(main_n=2, lat_n=2, r=0.05):
    """Build a tree with one lateral branch: trunk of main_n internodes, one lateral at junction."""
    root = Node(position=np.zeros(3))
    prev = root
    iods = []
    for i in range(main_n):
        child = Node(position=np.array([0.0, float(i + 1), 0.0]))
        iod = Internode(parent_node=prev, child_node=child, length=1.0, is_main_axis=True)
        iod.diameter = 2 * r
        prev.children_internodes.append(iod)
        child.parent_internode = iod
        iods.append(iod)
        prev = child
    # Attach a lateral chain at the junction node (root's direct child)
    junction = root.children_internodes[0].child_node
    lat_prev = junction
    for j in range(lat_n):
        lat_child = Node(position=np.array([float(j + 1), 1.0, 0.0]))
        lat_iod = Internode(parent_node=lat_prev, child_node=lat_child, length=1.0, is_main_axis=False)
        lat_iod.diameter = 2 * r * 0.5
        lat_prev.children_internodes.append(lat_iod)
        lat_child.parent_internode = lat_iod
        iods.append(lat_iod)
        lat_prev = lat_child
    return Tree(root=root, all_internodes=iods)


def test_lateral_chain_produces_valid_primitive():
    """Lateral branches create additional chains; mesh should be finite and index-valid."""
    tree = _tree_with_lateral(main_n=2, lat_n=2)
    prim = build_bark_primitive(tree, ring_sides=6, material=_mat())
    assert np.isfinite(prim.positions).all()
    assert np.isfinite(prim.normals).all()
    assert prim.indices.max() < prim.positions.shape[0]


def test_single_node_tree_no_crash():
    """A tree with only a root node produces a valid primitive without error."""
    root = Node(position=np.zeros(3))
    tree = Tree(root=root, all_internodes=[])
    prim = build_bark_primitive(tree, ring_sides=6, material=_mat())
    # _emit_chain_tube returns early (len < 2), only root cap center vertex emitted
    assert prim.positions.shape[1] == 3
    assert np.isfinite(prim.positions).all()
