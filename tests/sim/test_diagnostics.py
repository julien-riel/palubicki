from __future__ import annotations

import math

import numpy as np
import pytest

from palubicki.sim.diagnostics import compute_metrics
from palubicki.sim.tree import Internode, Node, Tree


def _link(parent: Node, child: Node, *, is_main_axis: bool = True) -> Internode:
    """Create + bidirectionally link an internode between parent and child."""
    iod = Internode(
        parent_node=parent, child_node=child,
        length=float(np.linalg.norm(child.position - parent.position)),
        is_main_axis=is_main_axis,
    )
    parent.children_internodes.append(iod)
    child.parent_internode = iod
    return iod


def _make_tree_y_shape() -> Tree:
    """Trunk + two equal leaf branches:

           c1     c2
            \\   /
             m
             |
             root
    """
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    c1 = Node(position=np.array([0.5, 1.5, 0.0]))
    c2 = Node(position=np.array([-0.5, 1.5, 0.0]))
    tree = Tree(root=root)
    trunk = _link(root, mid, is_main_axis=True)
    # Two laterals at the fork — neither marked main axis (terminal fork).
    b1 = _link(mid, c1, is_main_axis=False)
    b2 = _link(mid, c2, is_main_axis=False)
    tree.all_internodes.extend([trunk, b1, b2])
    return tree


def test_strahler_y_shape():
    tree = _make_tree_y_shape()
    m = compute_metrics(tree)
    assert m["strahler_order_max"] == 2
    assert m["strahler_order_histogram"] == {1: 2, 2: 1}
    # Bifurcation ratio: count(1) / count(2) = 2 / 1 = 2.0
    assert m["horton_bifurcation_ratio"] == {1: 2.0}
    assert m["horton_bifurcation_ratio_mean"] == pytest.approx(2.0)


def _make_pectinate_3level() -> Tree:
    """A pectinate-style tree:

              g
             /
            f---leaf3
           /
          e---leaf2
         /
        d---leaf1
        |
        root

    Three forks; each non-leaf has children of orders (1, k) where
    k grows from 1 → 2 → 3 → ... Strahler order at root = 2
    (the unique-max rule keeps each internal node at max+0 since
    the higher-order child is unique at every fork).
    """
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    d = Node(position=np.array([0.0, 1.0, 0.0]))
    leaf1 = Node(position=np.array([0.5, 1.0, 0.0]))
    e = Node(position=np.array([0.0, 2.0, 0.0]))
    leaf2 = Node(position=np.array([0.5, 2.0, 0.0]))
    f = Node(position=np.array([0.0, 3.0, 0.0]))
    leaf3 = Node(position=np.array([0.5, 3.0, 0.0]))
    g = Node(position=np.array([0.0, 4.0, 0.0]))

    tree = Tree(root=root)
    trunk = _link(root, d, is_main_axis=True)
    l1 = _link(d, leaf1, is_main_axis=False)
    main1 = _link(d, e, is_main_axis=True)
    l2 = _link(e, leaf2, is_main_axis=False)
    main2 = _link(e, f, is_main_axis=True)
    l3 = _link(f, leaf3, is_main_axis=False)
    main3 = _link(f, g, is_main_axis=True)
    tree.all_internodes.extend([trunk, l1, main1, l2, main2, l3, main3])
    return tree


def test_strahler_pectinate_unique_max_rule():
    tree = _make_pectinate_3level()
    m = compute_metrics(tree)
    # main3, l3, l2, l1 are all leaves (order 1). main2 has children
    # (main3, l3): both order 1 → tie → main2 is order 2. main1's children
    # (main2, l2): main2=2, l2=1 → unique max → main1 is order 2. trunk's
    # children (main1, l1): main1=2, l1=1 → unique max → trunk is order 2.
    assert m["strahler_order_max"] == 2
    assert m["strahler_order_histogram"] == {1: 4, 2: 3}
    # ratio 1→2 = 4/3
    assert m["horton_bifurcation_ratio"][1] == pytest.approx(4.0 / 3.0)


def test_strahler_single_internode():
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    child = Node(position=np.array([0.0, 1.0, 0.0]))
    tree = Tree(root=root)
    iod = _link(root, child, is_main_axis=True)
    tree.all_internodes.append(iod)
    m = compute_metrics(tree)
    assert m["strahler_order_max"] == 1
    assert m["strahler_order_histogram"] == {1: 1}
    assert m["horton_bifurcation_ratio"] == {}
    assert math.isnan(m["horton_bifurcation_ratio_mean"])


def test_strahler_empty_tree():
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    tree = Tree(root=root)
    m = compute_metrics(tree)
    assert m["strahler_order_max"] == 0
    assert m["strahler_order_histogram"] == {}
    assert m["horton_bifurcation_ratio"] == {}
    assert math.isnan(m["horton_bifurcation_ratio_mean"])


def _make_trunk_with_lateral(branch_dir: np.ndarray,
                              branch_is_main_axis: bool = False) -> Tree:
    """Trunk along +Y; one lateral at the trunk's child node, pointing in
    `branch_dir` (any non-zero vector — gets normalized to position the
    lateral end node 1 unit from mid)."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    branch_dir = np.asarray(branch_dir, dtype=np.float64)
    branch_dir = branch_dir / np.linalg.norm(branch_dir)
    lat_end = mid.position + branch_dir
    lat_node = Node(position=lat_end)
    tree = Tree(root=root)
    trunk = _link(root, mid, is_main_axis=True)
    lat = _link(mid, lat_node, is_main_axis=branch_is_main_axis)
    tree.all_internodes.extend([trunk, lat])
    return tree


def test_insertion_angle_vs_parent_45():
    tree = _make_trunk_with_lateral(
        branch_dir=np.array([math.sin(math.radians(45.0)),
                              math.cos(math.radians(45.0)), 0.0]),
    )
    m = compute_metrics(tree)
    assert 1 in m["insertion_angle_deg_vs_parent"]
    stats = m["insertion_angle_deg_vs_parent"][1]
    assert stats["mean"] == pytest.approx(45.0, abs=1e-6)
    assert stats["stddev"] == pytest.approx(0.0, abs=1e-9)
    assert stats["n"] == 1


def test_insertion_angle_vs_main_sibling_60():
    """Trunk +Y up to mid; mid has a main-axis continuation also at +Y, plus
    a lateral at 60° from that direction. Angle vs parent = 60°, and angle
    vs main_sibling = 60° (parent and main_sibling happen to be colinear)."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    top = Node(position=np.array([0.0, 2.0, 0.0]))
    angle = math.radians(60.0)
    lat_dir = np.array([math.sin(angle), math.cos(angle), 0.0])
    lat_node = Node(position=mid.position + lat_dir)

    tree = Tree(root=root)
    trunk = _link(root, mid, is_main_axis=True)
    cont = _link(mid, top, is_main_axis=True)
    lat = _link(mid, lat_node, is_main_axis=False)
    tree.all_internodes.extend([trunk, cont, lat])

    m = compute_metrics(tree)
    p_stats = m["insertion_angle_deg_vs_parent"][1]
    s_stats = m["insertion_angle_deg_vs_main_sibling"][1]
    assert p_stats["mean"] == pytest.approx(60.0, abs=1e-6)
    assert p_stats["n"] == 1
    assert s_stats["mean"] == pytest.approx(60.0, abs=1e-6)
    assert s_stats["n"] == 1


def test_insertion_angle_vs_main_sibling_differs_from_vs_parent():
    """Trunk +Y; main-sibling at 30° in +X half-plane; lateral at 30° in -X
    half-plane → 60° vs main-sibling, but 30° vs parent (trunk)."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    a30 = math.radians(30.0)
    main_dir = np.array([math.sin(a30), math.cos(a30), 0.0])
    lat_dir = np.array([-math.sin(a30), math.cos(a30), 0.0])
    top = Node(position=mid.position + main_dir)
    lat_node = Node(position=mid.position + lat_dir)

    tree = Tree(root=root)
    trunk = _link(root, mid, is_main_axis=True)
    cont = _link(mid, top, is_main_axis=True)
    lat = _link(mid, lat_node, is_main_axis=False)
    tree.all_internodes.extend([trunk, cont, lat])

    m = compute_metrics(tree)
    assert m["insertion_angle_deg_vs_parent"][1]["mean"] == pytest.approx(30.0, abs=1e-6)
    assert m["insertion_angle_deg_vs_main_sibling"][1]["mean"] == pytest.approx(60.0, abs=1e-6)
