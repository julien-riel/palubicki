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


def test_vertical_chain_geometric_pin():
    """Hand-computed pin test: catches any drift in vertex layout, UVs, or index order
    during refactors of _emit_chain_tube / _emit_root_cap.

    Geometry derivation for _vertical_chain(n=3, length=1.0, r=0.05), ring_sides=4:
      - 4 nodes at (0, i, 0), i=0..3; tangent constant = (0, 1, 0)
      - Frame: right=(1,0,0), up=cross((0,1,0),(1,0,0))=(0,0,-1) — constant (no rotation)
      - columns = ring_sides + 1 = 5; total tube vertices = 4 × 5 = 20
      - Plus 1 root-cap center vertex = 21 total
      - Per-ring layout (k=0..4): angles 0, π/2, π, 3π/2, 0 (seam)
    """
    tree = _vertical_chain(n=3, length=1.0, r=0.05)
    prim = build_bark_primitive(tree, ring_sides=4, material=_mat())

    assert prim.positions.shape == (21, 3)
    assert prim.normals.shape == (21, 3)
    assert prim.uvs.shape == (21, 2)
    # tube: 3 segs × 4 sides × 6 = 72; cap: 4 tris × 3 = 12; total 84
    assert prim.indices.shape == (84,)
    assert prim.indices.dtype == np.uint32

    # --- Ring 0 (node at y=0) ---
    assert np.allclose(prim.positions[0], [0.05, 0.0, 0.0], atol=1e-6)
    assert np.allclose(prim.normals[0],   [1.0,  0.0, 0.0], atol=1e-6)
    assert np.allclose(prim.uvs[0],       [0.0,  0.0],      atol=1e-6)

    assert np.allclose(prim.positions[1], [0.0,  0.0, -0.05], atol=1e-6)
    assert np.allclose(prim.normals[1],   [0.0,  0.0, -1.0],  atol=1e-6)
    assert np.allclose(prim.uvs[1],       [0.25, 0.0],        atol=1e-6)

    assert np.allclose(prim.positions[2], [-0.05, 0.0, 0.0], atol=1e-6)
    assert np.allclose(prim.normals[2],   [-1.0,  0.0, 0.0], atol=1e-6)

    assert np.allclose(prim.positions[3], [0.0, 0.0, 0.05], atol=1e-6)
    assert np.allclose(prim.normals[3],   [0.0, 0.0, 1.0], atol=1e-6)

    # Seam vertex (k=4): same 3D as k=0, UV at u=1.0
    assert np.allclose(prim.positions[4], prim.positions[0], atol=1e-12)
    assert np.allclose(prim.normals[4],   prim.normals[0],   atol=1e-12)
    assert np.allclose(prim.uvs[4],       [1.0, 0.0],        atol=1e-6)

    # --- Ring 1 (node at y=1): same XZ layout, y=1, v=1.0 ---
    assert np.allclose(prim.positions[5], [0.05, 1.0, 0.0], atol=1e-6)
    assert np.allclose(prim.uvs[5],       [0.0,  1.0],      atol=1e-6)

    # --- Ring 3 (last node, y=3, v=3.0) ---
    assert np.allclose(prim.positions[15], [0.05, 3.0, 0.0], atol=1e-6)
    assert np.allclose(prim.uvs[15],       [0.0,  3.0],      atol=1e-6)

    # --- Root cap center vertex (last appended) at (0,0,0) ---
    assert np.allclose(prim.positions[20], [0.0, 0.0, 0.0], atol=1e-12)

    # --- Tube indices (segment 0, k=0..3 → 24 ints) ---
    # k=0: a=0,b=5,c=6,d=1  → [0,5,6, 0,6,1]
    # k=1: a=1,b=6,c=7,d=2  → [1,6,7, 1,7,2]
    # k=2: a=2,b=7,c=8,d=3  → [2,7,8, 2,8,3]
    # k=3: a=3,b=8,c=9,d=4  → [3,8,9, 3,9,4]
    expected_seg0 = [0,5,6,0,6,1, 1,6,7,1,7,2, 2,7,8,2,8,3, 3,8,9,3,9,4]
    assert prim.indices[:24].tolist() == expected_seg0

    # --- Cap indices: [center=20, ring0[k+1], ring0[k]] for k=0..3 ---
    assert prim.indices[72:75].tolist() == [20, 1, 0]
    assert prim.indices[75:78].tolist() == [20, 2, 1]
    assert prim.indices[78:81].tolist() == [20, 3, 2]
    assert prim.indices[81:84].tolist() == [20, 4, 3]


def test_build_bark_primitive_reads_sag_offset():
    """When a node has a non-zero sag_offset, the tube vertices should reflect
    the bent position (position + sag_offset), not the raw topological position."""
    import numpy as np
    from palubicki.geom.mesh import Material
    from palubicki.geom.tubes import build_bark_primitive
    from palubicki.sim.tree import Internode, Node, Tree

    root = Node(position=np.zeros(3))
    tip = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=root, child_node=tip, length=1.0,
                    is_main_axis=True, diameter=0.10)
    root.children_internodes.append(iod)
    tip.parent_internode = iod
    tree = Tree(root=root, all_internodes=[iod])

    mat = Material(name="bark", base_color=(0.3, 0.2, 0.1, 1.0),
                   metallic=0.0, roughness=1.0, base_color_texture_png=None,
                   alpha_mode="OPAQUE", alpha_cutoff=0.5, double_sided=False)
    prim_baseline = build_bark_primitive(tree, ring_sides=6, material=mat)
    baseline_max_y = float(prim_baseline.positions[:, 1].max())

    # Apply a downward sag_offset of -0.5 to the tip and rebuild.
    tip.sag_offset = np.array([0.0, -0.5, 0.0])
    prim_bent = build_bark_primitive(tree, ring_sides=6, material=mat)
    bent_max_y = float(prim_bent.positions[:, 1].max())

    # The tube tip should have moved downward.
    assert bent_max_y < baseline_max_y - 0.3
