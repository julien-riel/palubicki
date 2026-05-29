"""Unit tests for mechanical sag."""
import math

import numpy as np
import pytest

from palubicki.config import SagConfig
from palubicki.sim.sag import apply_sag
from palubicki.sim.tree import Bud, Internode, Node, Tree


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
    child = tree.root.children_internodes[0].child_node
    np.testing.assert_array_equal(child.position + child.sag_offset, before)


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
    tip_bent = tip.position + tip.sag_offset
    assert tip_bent[1] < 0.0
    # Bent positions still preserve the original internode length (rigid-body rotation).
    for iod in tree.all_internodes:
        p_bent = iod.parent_node.position + iod.parent_node.sag_offset
        c_bent = iod.child_node.position + iod.child_node.sag_offset
        assert np.linalg.norm(c_bent - p_bent) == pytest.approx(iod.length, rel=1e-9)


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
    np.testing.assert_allclose(tip.position + tip.sag_offset, np.array([0.0, 2.0, 0.0]), atol=1e-12)


def test_rigid_axis_order_protects_trunk():
    """rigid_axis_order=1 prevents the main-axis trunk (order 0) from bending."""
    positions = [
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
    ]
    tree = _chain_tree(positions, [0.05])
    apply_sag(tree, SagConfig(enabled=True, k=10.0, max_bend_deg=45.0, rigid_axis_order=1))
    # axis_order 0 < rigid_axis_order 1 → no rotation.
    child = tree.root.children_internodes[0].child_node
    np.testing.assert_array_equal(child.position + child.sag_offset, np.array([1.0, 0.0, 0.0]))


def test_single_segment_lateral_droops():
    """A single-segment lateral (one iod, no subtree below) must still droop
    under its own weight. Previously the load excluded the iod itself, so
    load_below[tip] = 0 and the segment didn't move at all."""
    nodes = [Node(position=np.array([0.0, 0.0, 0.0])),
             Node(position=np.array([0.0, 1.0, 0.0]))]
    trunk = nodes[1]
    lateral = Node(position=np.array([1.0, 1.0, 0.0]))
    tree = Tree(root=nodes[0])
    # Trunk iod (main axis, order 0 — rigid).
    trunk_iod = Internode(parent_node=nodes[0], child_node=trunk, length=1.0,
                          is_main_axis=True, diameter=0.10)
    nodes[0].children_internodes.append(trunk_iod)
    trunk.parent_internode = trunk_iod
    tree.all_internodes.append(trunk_iod)
    # Single-segment horizontal lateral (order 1).
    lat_iod = Internode(parent_node=trunk, child_node=lateral, length=1.0,
                        is_main_axis=False, diameter=0.05)
    trunk.children_internodes.append(lat_iod)
    lateral.parent_internode = lat_iod
    tree.all_internodes.append(lat_iod)

    apply_sag(tree, SagConfig(enabled=True, k=10.0, max_bend_deg=30.0,
                              rigid_axis_order=1))
    # Lateral tip must have moved downward — the iod's own weight is the load.
    assert (lateral.position + lateral.sag_offset)[1] < 0.99


def test_near_vertical_branch_sags_less_than_horizontal():
    """Bend scales by sin(angle between direction and gravity). A branch tilted
    only 10° off vertical should sag dramatically less than a horizontal one
    with the same load and diameter."""
    # Use k small enough that neither case hits the max-bend cap (otherwise
    # both would bend by the same capped angle and the sin(θ) scaling becomes
    # invisible).
    horiz = _chain_tree(
        [np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0])],
        [0.05],
    )
    apply_sag(horiz, SagConfig(enabled=True, k=0.5, max_bend_deg=45.0,
                               rigid_axis_order=0))
    horiz_child = horiz.root.children_internodes[0].child_node
    horiz_drop = -float((horiz_child.position + horiz_child.sag_offset)[1])

    # Nearly vertical: 10° from vertical → sin(10°) ≈ 0.174 of horizontal.
    near_vert_dir = np.array([math.sin(math.radians(10.0)),
                              math.cos(math.radians(10.0)), 0.0])
    near = _chain_tree(
        [np.array([0.0, 0.0, 0.0]), near_vert_dir.copy()],
        [0.05],
    )
    apply_sag(near, SagConfig(enabled=True, k=0.5, max_bend_deg=45.0,
                              rigid_axis_order=0))
    near_child = near.root.children_internodes[0].child_node
    near_tip = near_child.position + near_child.sag_offset
    near_drop = float(near_vert_dir[1] - near_tip[1])

    assert horiz_drop > 0.0
    assert near_drop > 0.0
    # Strict: vertical-ish branch should drop much less than horizontal.
    assert near_drop < horiz_drop * 0.5


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
    p0_bent = tree.root.position + tree.root.sag_offset
    child = tree.root.children_internodes[0].child_node
    p1_bent = child.position + child.sag_offset
    seg1 = p1_bent - p0_bent
    # Angle of seg1 below horizon should not exceed max_bend (10 deg).
    angle_deg = math.degrees(math.asin(-seg1[1] / np.linalg.norm(seg1)))
    assert angle_deg <= 10.0 + 1e-6


def test_apply_sag_idempotent():
    """Calling apply_sag twice gives the same result as calling it once."""
    positions = [
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([2.0, 0.0, 0.0]),
    ]
    tree = _chain_tree(positions, [0.05, 0.05])
    cfg = SagConfig(enabled=True, k=0.5, max_bend_deg=30.0, rigid_axis_order=0)
    apply_sag(tree, cfg)
    once = [n.sag_offset.copy() for n in (
        tree.root,
        tree.root.children_internodes[0].child_node,
        tree.root.children_internodes[0].child_node.children_internodes[0].child_node,
    )]
    apply_sag(tree, cfg)
    twice = [n.sag_offset for n in (
        tree.root,
        tree.root.children_internodes[0].child_node,
        tree.root.children_internodes[0].child_node.children_internodes[0].child_node,
    )]
    for a, b in zip(once, twice, strict=True):
        np.testing.assert_allclose(a, b, atol=1e-12)


def test_sag_offset_separate_from_position():
    """Node.position must be untouched by apply_sag — only sag_offset moves."""
    positions = [
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
    ]
    tree = _chain_tree(positions, [0.05])
    original_root = tree.root.position.copy()
    original_child = tree.root.children_internodes[0].child_node.position.copy()
    apply_sag(tree, SagConfig(enabled=True, k=0.5, max_bend_deg=30.0, rigid_axis_order=0))
    np.testing.assert_array_equal(tree.root.position, original_root)
    np.testing.assert_array_equal(tree.root.children_internodes[0].child_node.position, original_child)
    # The child got a non-zero sag_offset though.
    assert np.linalg.norm(tree.root.children_internodes[0].child_node.sag_offset) > 0.0
