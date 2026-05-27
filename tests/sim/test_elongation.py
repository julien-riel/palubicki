"""Unit tests for sim/elongation.py — sigmoid ramp + age_factor."""
import math

import pytest

from palubicki.config import ElongationConfig


def test_compute_target_disabled_returns_base():
    from palubicki.sim.elongation import compute_target_with_age
    cfg = ElongationConfig(enabled=False)
    assert compute_target_with_age(0.18, birth_iteration=20, max_iterations=40, cfg=cfg) == 0.18


def test_compute_target_no_age_decay_returns_base():
    from palubicki.sim.elongation import compute_target_with_age
    cfg = ElongationConfig(enabled=True, age_factor_decay=0.0)
    assert compute_target_with_age(0.18, birth_iteration=20, max_iterations=40, cfg=cfg) == 0.18


def test_compute_target_at_birth_zero_is_full_base():
    from palubicki.sim.elongation import compute_target_with_age
    cfg = ElongationConfig(enabled=True, age_factor_min=0.5, age_factor_decay=0.7)
    assert compute_target_with_age(0.20, birth_iteration=0, max_iterations=40, cfg=cfg) == pytest.approx(0.20)


def test_compute_target_at_birth_max_equals_age_factor_min_times_base():
    from palubicki.sim.elongation import compute_target_with_age
    cfg = ElongationConfig(enabled=True, age_factor_min=0.4, age_factor_decay=1.0)
    got = compute_target_with_age(0.20, birth_iteration=40, max_iterations=40, cfg=cfg)
    assert got == pytest.approx(0.20 * 0.4, rel=1e-9)


def test_compute_target_monotonic_decay_with_birth():
    from palubicki.sim.elongation import compute_target_with_age
    cfg = ElongationConfig(enabled=True, age_factor_min=0.3, age_factor_decay=1.0)
    early = compute_target_with_age(0.20, birth_iteration=5, max_iterations=40, cfg=cfg)
    mid = compute_target_with_age(0.20, birth_iteration=20, max_iterations=40, cfg=cfg)
    late = compute_target_with_age(0.20, birth_iteration=35, max_iterations=40, cfg=cfg)
    assert early > mid > late


def test_compute_target_max_iterations_zero_returns_base():
    from palubicki.sim.elongation import compute_target_with_age
    cfg = ElongationConfig(enabled=True)
    assert compute_target_with_age(0.20, birth_iteration=0, max_iterations=0, cfg=cfg) == 0.20


def test_compute_target_birth_past_max_is_clamped():
    from palubicki.sim.elongation import compute_target_with_age
    cfg = ElongationConfig(enabled=True, age_factor_min=0.4, age_factor_decay=1.0)
    clamped = compute_target_with_age(0.20, birth_iteration=99, max_iterations=40, cfg=cfg)
    at_max = compute_target_with_age(0.20, birth_iteration=40, max_iterations=40, cfg=cfg)
    assert clamped == pytest.approx(at_max)


import numpy as np

from palubicki.sim.tree import Internode, Node, Tree


def _single_internode(birth: int, target: float) -> Tree:
    a = Node(position=np.zeros(3))
    b = Node(position=np.array([0.0, target, 0.0]))
    iod = Internode(
        parent_node=a, child_node=b, length=0.0, is_main_axis=True,
        birth_iteration=birth, length_target=target,
    )
    a.children_internodes.append(iod)
    b.parent_internode = iod
    return Tree(root=a, all_internodes=[iod])


def test_update_lengths_disabled_is_noop():
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=0, target=0.5)
    tree.all_internodes[0].length = 0.123
    update_lengths(tree, current_iteration=5, cfg=ElongationConfig(enabled=False))
    assert tree.all_internodes[0].length == 0.123


def test_update_lengths_at_birth_is_small_fraction_of_target():
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=10, target=0.5)
    cfg = ElongationConfig(enabled=True, tau_iterations=3.0, age_factor_decay=0.0)
    update_lengths(tree, current_iteration=10, cfg=cfg)
    assert tree.all_internodes[0].length == pytest.approx(0.5 * (1.0 / (1.0 + math.exp(2.0))), rel=1e-9)


def test_update_lengths_at_tau_is_half_target():
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=0, target=0.5)
    cfg = ElongationConfig(enabled=True, tau_iterations=3.0)
    update_lengths(tree, current_iteration=3, cfg=cfg)
    assert tree.all_internodes[0].length == pytest.approx(0.25, rel=1e-9)


def test_update_lengths_far_past_tau_approaches_target():
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=0, target=0.5)
    cfg = ElongationConfig(enabled=True, tau_iterations=3.0)
    update_lengths(tree, current_iteration=30, cfg=cfg)
    assert tree.all_internodes[0].length == pytest.approx(0.5, rel=1e-6)


def test_update_lengths_negative_elapsed_clamps_to_zero_elapsed():
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=20, target=0.5)
    cfg = ElongationConfig(enabled=True, tau_iterations=3.0)
    update_lengths(tree, current_iteration=10, cfg=cfg)
    assert tree.all_internodes[0].length == pytest.approx(0.5 * (1.0 / (1.0 + math.exp(2.0))), rel=1e-9)


def test_update_lengths_zero_tau_is_noop():
    from palubicki.sim.elongation import update_lengths
    tree = _single_internode(birth=0, target=0.5)
    tree.all_internodes[0].length = 0.123
    update_lengths(tree, current_iteration=5, cfg=ElongationConfig(enabled=True, tau_iterations=0.0))
    assert tree.all_internodes[0].length == 0.123
