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
