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
