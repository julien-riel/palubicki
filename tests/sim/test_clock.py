import pytest

from palubicki.sim.clock import Clock


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
