import pytest

from palubicki.sim.clock import Clock, phenology_activity, phenology_phase


def test_tick_advances_by_dt():
    c = Clock(dt=0.25)
    assert c.t == 0.0
    c.tick()
    assert c.t == pytest.approx(0.25)


def test_year_and_fraction():
    c = Clock(dt=0.25, t=2.5)
    assert c.year() == 2
    assert c.year_fraction() == pytest.approx(0.5)


def test_in_window_inclusive_low_exclusive_high():
    c = Clock(dt=0.25, t=0.0)      # fraction 0.0
    assert c.in_window(0.0, 0.5) is True
    c.t = 0.5                       # fraction 0.5
    assert c.in_window(0.0, 0.5) is False   # high is exclusive
    c.t = 0.75
    assert c.in_window(0.0, 0.5) is False
    c.t = 1.0                       # fraction 0.0 again
    assert c.in_window(0.0, 0.5) is True


def test_full_year_window_always_true():
    for t in (0.0, 1.0, 5.0, 12.0):
        assert Clock(dt=1.0, t=t).in_window(0.0, 1.0) is True


# --- graded phenology (#65) -------------------------------------------------

def test_activity_shoulder_zero_is_exact_legacy_step():
    # shoulder == 0 must be byte-identical to the crisp `lo <= f < hi` gate,
    # returning EXACTLY 1.0 / 0.0 (this is what keeps every default preset's
    # golden unchanged).
    assert phenology_activity(0.0, 0.0, 1.0, 0.0) == 1.0   # default full-year window
    assert phenology_activity(0.5, 0.0, 1.0, 0.0) == 1.0
    assert phenology_activity(0.25, 0.0, 0.5, 0.0) == 1.0
    assert phenology_activity(0.5, 0.0, 0.5, 0.0) == 0.0   # high is exclusive
    assert phenology_activity(0.75, 0.0, 0.5, 0.0) == 0.0


def test_activity_shoulder_zero_matches_in_window_on_a_grid():
    # The growth-stop boundary (activity > 0) equals the legacy window boundary.
    lo, hi = 0.2, 0.85
    for i in range(101):
        f = i / 100.0
        gated = phenology_activity(f, lo, hi, 0.0) > 0.0
        assert gated == (lo <= f < hi), f"mismatch at f={f}"


def test_activity_trapezoid_ramps_and_plateau():
    lo, hi, sh = 0.2, 0.85, 0.1
    # Outside the window.
    assert phenology_activity(0.1, lo, hi, sh) == 0.0
    assert phenology_activity(0.9, lo, hi, sh) == 0.0
    assert phenology_activity(hi, lo, hi, sh) == 0.0          # hi exclusive
    # Rising shoulder: linear from 0 at lo to 1 at lo+shoulder.
    assert phenology_activity(lo, lo, hi, sh) == 0.0
    assert phenology_activity(lo + sh / 2, lo, hi, sh) == pytest.approx(0.5)
    assert phenology_activity(lo + sh, lo, hi, sh) == pytest.approx(1.0)
    # Plateau.
    assert phenology_activity(0.5, lo, hi, sh) == 1.0
    # Falling shoulder: linear from 1 at hi-shoulder to ~0 approaching hi.
    assert phenology_activity(hi - sh, lo, hi, sh) == pytest.approx(1.0)
    assert phenology_activity(hi - sh / 2, lo, hi, sh) == pytest.approx(0.5)


def test_activity_bounded_in_unit_interval():
    lo, hi, sh = 0.2, 0.85, 0.1
    for i in range(101):
        a = phenology_activity(i / 100.0, lo, hi, sh)
        assert 0.0 <= a <= 1.0


def test_phenology_phase_labels():
    lo, hi, sh = 0.2, 0.85, 0.1
    assert phenology_phase(0.05, lo, hi, sh) == "dormant"
    assert phenology_phase(lo + sh / 2, lo, hi, sh) == "bud_break"
    assert phenology_phase(0.5, lo, hi, sh) == "vegetative"
    assert phenology_phase(hi - sh / 2, lo, hi, sh) == "cessation"
    # Default full-year window at dt=1.0 (f=0.0) reads vegetative.
    assert phenology_phase(0.0, 0.0, 1.0, 0.0) == "vegetative"


def test_clock_activity_delegates():
    c = Clock(dt=0.25, t=2.5)            # fraction 0.5
    assert c.activity(0.2, 0.85, 0.1) == 1.0
    assert c.activity(0.0, 0.5, 0.0) == 0.0   # frac 0.5, hi exclusive
    # Delegate agrees with the free function.
    assert c.activity(0.2, 0.85, 0.1) == phenology_activity(0.5, 0.2, 0.85, 0.1)
