"""Unit tests for sim/elongation.py — shoot_extension + sigmoid ramp."""
import math

import pytest

from palubicki.config import ElongationConfig
from palubicki.sim.elongation import shoot_extension


def test_shoot_extension_zero_vigor_is_zero():
    assert shoot_extension(0.0, shoot_extension_max=0.3, vigor_ref=1.0) == 0.0


def test_shoot_extension_saturates_below_max():
    # exp(-100/1.0) underflows to 0.0 in IEEE 754; result is indistinguishable from max
    got = shoot_extension(100.0, shoot_extension_max=0.3, vigor_ref=1.0)
    assert got <= 0.3
    assert got == pytest.approx(0.3, abs=1e-6)


def test_shoot_extension_knee_at_vigor_ref():
    got = shoot_extension(1.0, shoot_extension_max=0.3, vigor_ref=1.0)
    assert got == pytest.approx(0.3 * (1.0 - math.exp(-1.0)))


def test_shoot_extension_monotonic_in_vigor():
    a = shoot_extension(0.5, shoot_extension_max=0.3, vigor_ref=1.0)
    b = shoot_extension(1.5, shoot_extension_max=0.3, vigor_ref=1.0)
    assert b > a


def test_shoot_extension_near_linear_for_small_vigor():
    got = shoot_extension(0.01, shoot_extension_max=0.3, vigor_ref=1.0)
    assert got == pytest.approx(0.3 * 0.01, rel=1e-2)


import numpy as np

from palubicki.sim.tree import Internode, Node, Tree


def _single_internode(birth: int, target: float) -> Tree:
    a = Node(position=np.zeros(3))
    b = Node(position=np.array([0.0, target, 0.0]))
    iod = Internode(
        parent_node=a, child_node=b, length=0.0, is_main_axis=True,
        birth_time=float(birth), length_target=target,
    )
    a.children_internodes.append(iod)
    b.parent_internode = iod
    return Tree(root=a, all_internodes=[iod])


def test_update_lengths_disabled_is_noop():
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=0, target=0.5)
    tree.all_internodes[0].length = 0.123
    update_lengths(tree, current_time=5.0, cfg=ElongationConfig(enabled=False))
    assert tree.all_internodes[0].length == 0.123


def test_update_lengths_at_birth_is_small_fraction_of_target():
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=10, target=0.5)
    cfg = ElongationConfig(enabled=True, tau_years=3.0)
    update_lengths(tree, current_time=10.0, cfg=cfg)
    assert tree.all_internodes[0].length == pytest.approx(0.5 * (1.0 / (1.0 + math.exp(2.0))), rel=1e-9)


def test_update_lengths_at_tau_is_half_target():
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=0, target=0.5)
    cfg = ElongationConfig(enabled=True, tau_years=3.0)
    update_lengths(tree, current_time=3.0, cfg=cfg)
    assert tree.all_internodes[0].length == pytest.approx(0.25, rel=1e-9)


def test_update_lengths_far_past_tau_approaches_target():
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=0, target=0.5)
    cfg = ElongationConfig(enabled=True, tau_years=3.0)
    update_lengths(tree, current_time=30.0, cfg=cfg)
    assert tree.all_internodes[0].length == pytest.approx(0.5, rel=1e-6)


def test_update_lengths_negative_elapsed_clamps_to_zero_elapsed():
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=20, target=0.5)
    cfg = ElongationConfig(enabled=True, tau_years=3.0)
    update_lengths(tree, current_time=10.0, cfg=cfg)
    assert tree.all_internodes[0].length == pytest.approx(0.5 * (1.0 / (1.0 + math.exp(2.0))), rel=1e-9)


def test_update_lengths_zero_tau_is_noop():
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=0, target=0.5)
    tree.all_internodes[0].length = 0.123
    update_lengths(tree, current_time=5.0, cfg=ElongationConfig(enabled=True, tau_years=0.0))
    assert tree.all_internodes[0].length == 0.123
