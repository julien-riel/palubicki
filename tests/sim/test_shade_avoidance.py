"""Unit tests for the shade-avoidance break law (#63).

These pin the (pure, RNG-free) probability used by the simulator to demote
laterals to RESERVE in shade; the emergent behaviour is covered by
tests/integration/test_shade_avoidance_initiation.py.
"""
import pytest

from palubicki.sim.shade_avoidance import lateral_break_probability


@pytest.mark.parametrize("strength", [0.0, 0.3, 0.6, 1.0])
def test_full_sun_always_breaks(strength):
    """A fully lit bud (light_factor=1) invests fully at any strength."""
    assert lateral_break_probability(1.0, strength) == 1.0


@pytest.mark.parametrize("light_factor", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_zero_strength_is_exact_identity(light_factor):
    """strength=0 short-circuits to exactly 1.0 (the byte-identical OFF path)."""
    assert lateral_break_probability(light_factor, 0.0) == 1.0


def test_full_shade_full_strength_never_breaks():
    """Deep shade (lf=0) at full strength withholds every lateral."""
    assert lateral_break_probability(0.0, 1.0) == 0.0


def test_full_shade_partial_strength_withholds_that_fraction():
    """At lf=0, p_break = 1 - strength: strength reads as 'fraction withheld'."""
    assert lateral_break_probability(0.0, 0.4) == pytest.approx(0.6)


def test_linear_in_light():
    """p_break = 1 - strength*(1-lf); exact at a known interior point."""
    # strength 0.6, lf 0.5 -> 1 - 0.6*0.5 = 0.7
    assert lateral_break_probability(0.5, 0.6) == pytest.approx(0.7)


def test_monotonic_increasing_in_light():
    ps = [lateral_break_probability(lf / 10.0, 0.8) for lf in range(11)]
    assert ps == sorted(ps)
    assert ps[0] < ps[-1]  # strictly rises from shade to sun


@pytest.mark.parametrize("strength", [0.0, 0.5, 1.0])
@pytest.mark.parametrize("light_factor", [0.0, 0.5, 1.0])
def test_result_in_unit_interval(light_factor, strength):
    p = lateral_break_probability(light_factor, strength)
    assert 0.0 <= p <= 1.0
