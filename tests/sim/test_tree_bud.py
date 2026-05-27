import numpy as np

from palubicki.sim.tree import Bud, BudState, Node


def test_bud_has_low_quality_steps_default_zero():
    node = Node(position=np.zeros(3))
    bud = Bud(
        position=np.zeros(3),
        direction=np.array([0.0, 1.0, 0.0]),
        axis_order=0,
        parent_node=node,
    )
    assert bud.low_quality_steps == 0
    assert bud.state is BudState.ACTIVE


def test_bud_low_quality_steps_mutable():
    node = Node(position=np.zeros(3))
    bud = Bud(
        position=np.zeros(3),
        direction=np.array([0.0, 1.0, 0.0]),
        axis_order=0,
        parent_node=node,
    )
    bud.low_quality_steps = 3
    assert bud.low_quality_steps == 3
