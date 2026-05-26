"""Unit tests for mechanical sag."""
import math

import numpy as np
import pytest

from palubicki.config import SagConfig
from palubicki.sim.sag import apply_sag
from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree


def _chain_tree(positions: list[np.ndarray], diameters: list[float]) -> Tree:
    """Build a simple linear chain root → n1 → n2 → ... with all internodes
    on the main axis (axis_order=0 except the last bud which has whatever)."""
    nodes = [Node(position=p.copy()) for p in positions]
    tree = Tree(root=nodes[0])
    for i in range(len(nodes) - 1):
        seg = nodes[i + 1].position - nodes[i].position
        length = float(np.linalg.norm(seg))
        iod = Internode(
            parent_node=nodes[i],
            child_node=nodes[i + 1],
            length=length,
            is_main_axis=True,
            diameter=diameters[i],
        )
        nodes[i].children_internodes.append(iod)
        nodes[i + 1].parent_internode = iod
        tree.all_internodes.append(iod)
    # Attach a terminal bud at the tip so leaves logic stays sane.
    tip = nodes[-1]
    tip.terminal_bud = Bud(
        position=tip.position.copy(),
        direction=np.array([1.0, 0.0, 0.0]),
        axis_order=0,
        parent_node=tip,
    )
    return tree


def test_sag_disabled_is_noop():
    positions = [np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0])]
    tree = _chain_tree(positions, [0.05])
    before = positions[1].copy()
    apply_sag(tree, SagConfig(enabled=False, k=10.0))
    np.testing.assert_array_equal(tree.root.children_internodes[0].child_node.position, before)


def test_horizontal_branch_bends_downward():
    """A horizontal cantilever in +X with gravity -Y should curl downward (y < 0)."""
    positions = [
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([2.0, 0.0, 0.0]),
        np.array([3.0, 0.0, 0.0]),
    ]
    tree = _chain_tree(positions, [0.05, 0.05, 0.05])
    apply_sag(tree, SagConfig(enabled=True, k=0.5, max_bend_deg=30.0, rigid_axis_order=0))
    # Tip should be below the horizon and at smaller x (because the rotations shorten the projection).
    tip = tree.root.children_internodes[0].child_node.children_internodes[0].child_node.children_internodes[0].child_node
    assert tip.position[1] < 0.0
    # All internodes still have their original length (rigid-body rotation preserves it).
    for iod in tree.all_internodes:
        seg = iod.child_node.position - iod.parent_node.position
        assert np.linalg.norm(seg) == pytest.approx(iod.length, rel=1e-9)


def test_vertical_branch_does_not_sag():
    """A pure-up direction with gravity -Y produces zero axis (cross product is zero),
    so the internode shouldn't move."""
    positions = [
        np.array([0.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
        np.array([0.0, 2.0, 0.0]),
    ]
    tree = _chain_tree(positions, [0.05, 0.05])
    apply_sag(tree, SagConfig(enabled=True, k=1.0, max_bend_deg=45.0, rigid_axis_order=0))
    tip = tree.root.children_internodes[0].child_node.children_internodes[0].child_node
    np.testing.assert_allclose(tip.position, np.array([0.0, 2.0, 0.0]), atol=1e-12)


def test_rigid_axis_order_protects_trunk():
    """rigid_axis_order=1 prevents the main-axis trunk (order 0) from bending."""
    positions = [
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
    ]
    tree = _chain_tree(positions, [0.05])
    apply_sag(tree, SagConfig(enabled=True, k=10.0, max_bend_deg=45.0, rigid_axis_order=1))
    # axis_order 0 < rigid_axis_order 1 → no rotation.
    np.testing.assert_array_equal(tree.root.children_internodes[0].child_node.position, np.array([1.0, 0.0, 0.0]))


def test_max_bend_caps_thin_tip_runaway():
    """A tiny-diameter internode with huge load would otherwise bend wildly; max_bend caps it."""
    positions = [
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([2.0, 0.0, 0.0]),
    ]
    # Thin tip
    tree = _chain_tree(positions, [0.05, 0.001])
    apply_sag(tree, SagConfig(enabled=True, k=1000.0, max_bend_deg=10.0, rigid_axis_order=0))
    # The second internode should be rotated by at most 10° from horizontal.
    # First internode rotates by up to 10° too.
    p0 = tree.root.position
    p1 = tree.root.children_internodes[0].child_node.position
    seg1 = p1 - p0
    # Angle of seg1 below horizon should not exceed max_bend (10 deg).
    angle_deg = math.degrees(math.asin(-seg1[1] / np.linalg.norm(seg1)))
    assert angle_deg <= 10.0 + 1e-6
