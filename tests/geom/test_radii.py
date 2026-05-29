import numpy as np
import pytest

from palubicki.geom.radii import compute_radii
from palubicki.sim.tree import Internode, Node, Tree


def _two_segments_linear():
    root = Node(position=np.zeros(3))
    mid = Node(position=np.array([0, 1, 0]))
    tip = Node(position=np.array([0, 2, 0]))
    iod_a = Internode(parent_node=root, child_node=mid, length=1.0, is_main_axis=True)
    iod_b = Internode(parent_node=mid, child_node=tip, length=1.0, is_main_axis=True)
    root.children_internodes.append(iod_a)
    mid.parent_internode = iod_a
    mid.children_internodes.append(iod_b)
    tip.parent_internode = iod_b
    return Tree(root=root, all_internodes=[iod_a, iod_b]), iod_a, iod_b


def _fork():
    root = Node(position=np.zeros(3))
    mid = Node(position=np.array([0, 1, 0]))
    tip_a = Node(position=np.array([1, 2, 0]))
    tip_b = Node(position=np.array([-1, 2, 0]))
    iod_main = Internode(parent_node=root, child_node=mid, length=1.0, is_main_axis=True)
    iod_a = Internode(parent_node=mid, child_node=tip_a, length=1.4, is_main_axis=True)
    iod_b = Internode(parent_node=mid, child_node=tip_b, length=1.4, is_main_axis=False)
    root.children_internodes.append(iod_main)
    mid.parent_internode = iod_main
    mid.children_internodes.extend([iod_a, iod_b])
    tip_a.parent_internode = iod_a
    tip_b.parent_internode = iod_b
    return Tree(root=root, all_internodes=[iod_main, iod_a, iod_b]), iod_main, iod_a, iod_b


def test_terminal_internode_gets_r_tip():
    tree, iod_a, iod_b = _two_segments_linear()
    compute_radii(tree, r_tip=0.01, exponent=2.0)
    assert iod_b.diameter == pytest.approx(0.02)


def test_root_diameter_grows_with_two_tips():
    tree, iod_main, iod_a, iod_b = _fork()
    r_tip = 0.01
    compute_radii(tree, r_tip=r_tip, exponent=2.0)
    expected_main_r = (2 * r_tip**2) ** 0.5
    assert iod_main.diameter == pytest.approx(2 * expected_main_r, abs=1e-9)


def test_exponent_three_gives_smaller_root():
    tree2, iod_m2, _, _ = _fork()
    tree3, iod_m3, _, _ = _fork()
    r_tip = 0.01
    compute_radii(tree2, r_tip=r_tip, exponent=2.0)
    compute_radii(tree3, r_tip=r_tip, exponent=3.0)
    assert iod_m3.diameter < iod_m2.diameter
