import numpy as np

from palubicki.sim.reiteration import activate_reserves_on_shed
from palubicki.sim.tree import Bud, BudState, Node


def _node_with_reserves(k: int) -> Node:
    node = Node(position=np.zeros(3))
    for _ in range(k):
        b = Bud(
            position=np.zeros(3),
            direction=np.array([1.0, 0.0, 0.0]),
            axis_order=1,
            parent_node=node,
            state=BudState.RESERVE,
        )
        b.low_quality_steps = 7
        b.low_light_steps = 5
        b.age = 12
        node.dormant_reserve_buds.append(b)
    return node


def test_activate_returns_empty_when_no_reserves():
    node = _node_with_reserves(0)
    out = activate_reserves_on_shed(node, n_to_activate=2)
    assert out == []
    assert node.lateral_buds == []


def test_activate_pops_n_buds():
    node = _node_with_reserves(3)
    out = activate_reserves_on_shed(node, n_to_activate=2)
    assert len(out) == 2
    assert len(node.dormant_reserve_buds) == 1
    assert len(node.lateral_buds) == 2


def test_activated_buds_change_state_to_active():
    node = _node_with_reserves(2)
    out = activate_reserves_on_shed(node, n_to_activate=2)
    for b in out:
        assert b.state is BudState.ACTIVE
    for b in node.lateral_buds:
        assert b.state is BudState.ACTIVE


def test_activated_buds_have_counters_reset():
    node = _node_with_reserves(1)
    out = activate_reserves_on_shed(node, n_to_activate=1)
    b = out[0]
    assert b.low_quality_steps == 0
    assert b.low_light_steps == 0
    assert b.age == 0


def test_activate_caps_at_available_reserves():
    node = _node_with_reserves(2)
    out = activate_reserves_on_shed(node, n_to_activate=5)
    assert len(out) == 2
    assert node.dormant_reserve_buds == []
    assert len(node.lateral_buds) == 2


def test_activate_zero_or_negative_is_noop():
    node = _node_with_reserves(2)
    assert activate_reserves_on_shed(node, n_to_activate=0) == []
    assert activate_reserves_on_shed(node, n_to_activate=-3) == []
    assert len(node.dormant_reserve_buds) == 2
    assert node.lateral_buds == []
