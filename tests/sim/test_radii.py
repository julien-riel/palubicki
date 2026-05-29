import numpy as np

from palubicki.sim.radii import compute_radii, update_diameters_incremental
from palubicki.sim.tree import Internode, Node, Tree


def test_compute_radii_single_tip():
    """A tree with one internode → tip radius = r_tip; internode diameter = 2·r_tip."""
    root = Node(position=np.zeros(3))
    tip = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=root, child_node=tip, length=1.0, is_main_axis=True)
    root.children_internodes.append(iod)
    tree = Tree(root=root, all_internodes=[iod])

    compute_radii(tree, r_tip=0.01, exponent=2.0)

    assert iod.diameter == 0.02


def test_compute_radii_pipe_model_two_children():
    """Parent radius² = r_left² + r_right² (n=2). Both tips at r_tip = 0.1 → parent = sqrt(0.02) → diameter = 2·sqrt(0.02)."""
    root = Node(position=np.zeros(3))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    left = Node(position=np.array([-1.0, 2.0, 0.0]))
    right = Node(position=np.array([1.0, 2.0, 0.0]))
    iod_root_mid = Internode(parent_node=root, child_node=mid, length=1.0, is_main_axis=True)
    iod_mid_left = Internode(parent_node=mid, child_node=left, length=1.0, is_main_axis=False)
    iod_mid_right = Internode(parent_node=mid, child_node=right, length=1.0, is_main_axis=True)
    root.children_internodes.append(iod_root_mid)
    mid.children_internodes.extend([iod_mid_left, iod_mid_right])
    tree = Tree(root=root, all_internodes=[iod_root_mid, iod_mid_left, iod_mid_right])

    compute_radii(tree, r_tip=0.1, exponent=2.0)

    assert iod_mid_left.diameter == 0.2
    assert iod_mid_right.diameter == 0.2
    expected_parent_radius = (0.1**2 + 0.1**2) ** 0.5
    assert abs(iod_root_mid.diameter - 2.0 * expected_parent_radius) < 1e-9


def test_update_diameters_incremental_idempotent():
    """Calling update_diameters_incremental twice on the same unchanged tree
    yields bit-identical diameters."""
    root = Node(position=np.zeros(3))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    left = Node(position=np.array([-1.0, 2.0, 0.0]))
    right = Node(position=np.array([1.0, 2.0, 0.0]))
    iod_root_mid = Internode(parent_node=root, child_node=mid, length=1.0, is_main_axis=True)
    iod_mid_left = Internode(parent_node=mid, child_node=left, length=1.0, is_main_axis=False)
    iod_mid_right = Internode(parent_node=mid, child_node=right, length=1.0, is_main_axis=True)
    root.children_internodes.append(iod_root_mid)
    mid.children_internodes.extend([iod_mid_left, iod_mid_right])
    tree = Tree(root=root, all_internodes=[iod_root_mid, iod_mid_left, iod_mid_right])

    update_diameters_incremental(tree, r_tip=0.005, exponent=2.49)
    first = [iod.diameter for iod in tree.all_internodes]
    update_diameters_incremental(tree, r_tip=0.005, exponent=2.49)
    second = [iod.diameter for iod in tree.all_internodes]
    assert first == second


def _two_tip_tree(vigor_a: float, vigor_b: float):
    root = Node(position=np.zeros(3))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    trunk = Internode(parent_node=root, child_node=mid, length=1.0, is_main_axis=True)
    root.children_internodes.append(trunk)
    mid.parent_internode = trunk
    a_node = Node(position=np.array([0.5, 2.0, 0.0]))
    b_node = Node(position=np.array([-0.5, 2.0, 0.0]))
    ia = Internode(parent_node=mid, child_node=a_node, length=1.0, is_main_axis=True, vigor=vigor_a)
    ib = Internode(parent_node=mid, child_node=b_node, length=1.0, is_main_axis=False, vigor=vigor_b)
    mid.children_internodes.extend([ia, ib])
    a_node.parent_internode = ia
    b_node.parent_internode = ib
    tree = Tree(root=root, all_internodes=[trunk, ia, ib])
    return tree, ia, ib


def test_gain_zero_recovers_pure_pipe_model():
    tree, ia, ib = _two_tip_tree(5.0, 0.1)
    compute_radii(tree, r_tip=0.01, exponent=2.0, vigor_ref=1.0, vigor_diameter_gain=0.0)
    assert ia.diameter == ib.diameter  # vigor ignored


def test_higher_vigor_tip_is_thicker():
    tree, ia, ib = _two_tip_tree(5.0, 0.1)
    compute_radii(tree, r_tip=0.01, exponent=2.0, vigor_ref=1.0, vigor_diameter_gain=1.0)
    assert ia.diameter > ib.diameter
