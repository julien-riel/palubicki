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
