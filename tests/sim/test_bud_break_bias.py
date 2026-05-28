import pytest

from palubicki.sim.bud_break_bias import position_weight



def test_uniform_returns_one_regardless_of_position_or_strength():
    assert position_weight(0, 5, "uniform", 0.0) == 1.0
    assert position_weight(2, 5, "uniform", 1.0) == 1.0
    assert position_weight(4, 5, "uniform", 0.7) == 1.0


def test_strength_zero_returns_one_for_any_mode():
    for mode in ("acrotonic", "basitonic", "mesotonic", "uniform"):
        for idx in range(5):
            assert position_weight(idx, 5, mode, 0.0) == 1.0, mode


def test_axis_length_one_returns_one_for_any_mode():
    for mode in ("acrotonic", "basitonic", "mesotonic", "uniform"):
        assert position_weight(0, 1, mode, 1.0) == 1.0, mode


def test_acrotonic_tip_full_base_zero_at_strength_one():
    assert position_weight(4, 5, "acrotonic", 1.0) == pytest.approx(1.0)
    assert position_weight(0, 5, "acrotonic", 1.0) == pytest.approx(0.0)
    assert position_weight(2, 5, "acrotonic", 1.0) == pytest.approx(0.5)


def test_basitonic_base_full_tip_zero_at_strength_one():
    assert position_weight(0, 5, "basitonic", 1.0) == pytest.approx(1.0)
    assert position_weight(4, 5, "basitonic", 1.0) == pytest.approx(0.0)
    assert position_weight(2, 5, "basitonic", 1.0) == pytest.approx(0.5)


def test_mesotonic_mid_full_ends_zero_at_strength_one():
    assert position_weight(2, 5, "mesotonic", 1.0) == pytest.approx(1.0)
    assert position_weight(0, 5, "mesotonic", 1.0) == pytest.approx(0.0)
    assert position_weight(4, 5, "mesotonic", 1.0) == pytest.approx(0.0)


def test_acrotonic_monotonic_increasing_with_index():
    weights = [position_weight(i, 10, "acrotonic", 0.6) for i in range(10)]
    assert all(a <= b for a, b in zip(weights, weights[1:]))


def test_basitonic_monotonic_decreasing_with_index():
    weights = [position_weight(i, 10, "basitonic", 0.6) for i in range(10)]
    assert all(a >= b for a, b in zip(weights, weights[1:]))


def test_mesotonic_peak_at_middle():
    weights = [position_weight(i, 10, "mesotonic", 0.6) for i in range(10)]
    peak = max(weights)
    peak_idx = weights.index(peak)
    assert peak_idx in (4, 5)


def test_partial_strength_interpolates_toward_one():
    half = position_weight(0, 5, "acrotonic", 0.5)
    full = position_weight(0, 5, "acrotonic", 1.0)
    assert full == pytest.approx(0.0)
    assert half == pytest.approx(0.5)


def test_invalid_mode_raises():
    with pytest.raises(ValueError, match="mode"):
        position_weight(0, 5, "exotic", 0.5)


import numpy as np

from palubicki.sim.bud_break_bias import compute_axis_positions
from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree


def _linear_chain(length: int) -> Tree:
    """Build a synthetic main-axis chain of ``length`` internodes with one
    lateral bud on every child_node. Returns a Tree whose root has the chain
    attached via is_main_axis=True internodes."""
    root = Node(position=np.zeros(3))
    tree = Tree(root=root)
    prev = root
    for i in range(length):
        child = Node(position=np.array([0.0, float(i + 1), 0.0]))
        iod = Internode(parent_node=prev, child_node=child, length=1.0, is_main_axis=True)
        prev.children_internodes.append(iod)
        child.parent_internode = iod
        tree.all_internodes.append(iod)
        lat = Bud(
            position=child.position.copy(),
            direction=np.array([1.0, 0.0, 0.0]),
            axis_order=1,
            parent_node=child,
        )
        child.lateral_buds.append(lat)
        prev = child
    # Terminal bud at the tip
    term = Bud(
        position=prev.position.copy(),
        direction=np.array([0.0, 1.0, 0.0]),
        axis_order=0,
        parent_node=prev,
    )
    prev.terminal_bud = term
    return tree


def test_compute_axis_positions_assigns_indices_along_trunk():
    tree = _linear_chain(5)  # 5 internodes, 5 child-nodes each with 1 lateral
    pos = compute_axis_positions(tree)
    lateral_pos = sorted(
        ((b.parent_node.position[1], pos[b]) for b in pos),
        key=lambda x: x[0],
    )
    # height 1 → index 0, height 5 → index 4; axis_length = 5 for all
    assert [(idx, L) for _, (idx, L) in lateral_pos] == [
        (0, 5), (1, 5), (2, 5), (3, 5), (4, 5),
    ]


def test_compute_axis_positions_excludes_terminal_buds():
    tree = _linear_chain(3)
    pos = compute_axis_positions(tree)
    # The terminal bud on the tip node should NOT appear in pos.
    tip = tree.all_internodes[-1].child_node
    assert tip.terminal_bud is not None
    assert tip.terminal_bud not in pos


def test_compute_axis_positions_empty_tree_returns_empty():
    root = Node(position=np.zeros(3))
    root.terminal_bud = Bud(
        position=np.zeros(3),
        direction=np.array([0.0, 1.0, 0.0]),
        axis_order=0,
        parent_node=root,
    )
    tree = Tree(root=root)
    pos = compute_axis_positions(tree)
    assert pos == {}


def test_compute_axis_positions_handles_lateral_axis():
    # Build trunk of 3 internodes; from trunk node 1, add a lateral chain of
    # 2 internodes with 1 lateral on each child node.
    tree = _linear_chain(3)
    trunk_node1 = tree.all_internodes[0].child_node
    branch_a = Node(position=np.array([1.0, 1.0, 0.0]))
    iod_a = Internode(parent_node=trunk_node1, child_node=branch_a, length=1.0, is_main_axis=False)
    trunk_node1.children_internodes.append(iod_a)
    branch_a.parent_internode = iod_a
    tree.all_internodes.append(iod_a)
    branch_b = Node(position=np.array([2.0, 1.0, 0.0]))
    iod_b = Internode(parent_node=branch_a, child_node=branch_b, length=1.0, is_main_axis=True)
    branch_a.children_internodes.append(iod_b)
    branch_b.parent_internode = iod_b
    tree.all_internodes.append(iod_b)
    lat_a = Bud(
        position=branch_a.position.copy(),
        direction=np.array([0.0, 0.0, 1.0]),
        axis_order=2,
        parent_node=branch_a,
    )
    branch_a.lateral_buds.append(lat_a)
    lat_b = Bud(
        position=branch_b.position.copy(),
        direction=np.array([0.0, 0.0, 1.0]),
        axis_order=2,
        parent_node=branch_b,
    )
    branch_b.lateral_buds.append(lat_b)

    pos = compute_axis_positions(tree)
    # Trunk laterals: 3 of them, axis_length=3
    assert sum(1 for L in (v[1] for v in pos.values()) if L == 3) == 3
    # Branch laterals: 2 of them on a 2-internode axis, axis_length=2
    assert pos[lat_a] == (0, 2)
    assert pos[lat_b] == (1, 2)
