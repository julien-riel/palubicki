import numpy as np

from palubicki.sim.radii import compute_radii
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
