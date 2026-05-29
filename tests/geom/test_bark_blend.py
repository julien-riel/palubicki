import numpy as np

from palubicki.geom.bark_blend import BarkBlendStops, bark_tint


def _stops():
    return BarkBlendStops(
        d_young=0.02, d_mature=0.10, d_senescent=0.30,
        c_young=(0.45, 0.38, 0.30),
        c_mature=(0.35, 0.22, 0.12),
        c_senescent=(0.22, 0.20, 0.16),
    )


def test_below_young_clamps_to_young():
    out = bark_tint(np.array([0.0, 0.01, 0.02]), _stops())
    assert out.shape == (3, 3)
    assert out.dtype == np.float32
    np.testing.assert_allclose(out, np.tile([0.45, 0.38, 0.30], (3, 1)), atol=1e-6)


def test_above_senescent_clamps_to_senescent():
    out = bark_tint(np.array([0.30, 0.5, 10.0]), _stops())
    np.testing.assert_allclose(out, np.tile([0.22, 0.20, 0.16], (3, 1)), atol=1e-6)


def test_mature_stop_is_exact():
    out = bark_tint(np.array([0.10]), _stops())
    np.testing.assert_allclose(out[0], [0.35, 0.22, 0.12], atol=1e-6)


def test_midpoint_young_to_mature_is_halfway():
    # diameter halfway between d_young (0.02) and d_mature (0.10) = 0.06
    out = bark_tint(np.array([0.06]), _stops())
    expected = 0.5 * np.array([0.45, 0.38, 0.30]) + 0.5 * np.array([0.35, 0.22, 0.12])
    np.testing.assert_allclose(out[0], expected, atol=1e-6)


def test_midpoint_mature_to_senescent_is_halfway():
    # diameter halfway between d_mature (0.10) and d_senescent (0.30) = 0.20
    out = bark_tint(np.array([0.20]), _stops())
    expected = 0.5 * np.array([0.35, 0.22, 0.12]) + 0.5 * np.array([0.22, 0.20, 0.16])
    np.testing.assert_allclose(out[0], expected, atol=1e-6)


def test_degenerate_equal_stops_no_nan():
    stops = BarkBlendStops(
        d_young=0.10, d_mature=0.10, d_senescent=0.10,
        c_young=(0.4, 0.4, 0.4), c_mature=(0.3, 0.3, 0.3), c_senescent=(0.2, 0.2, 0.2),
    )
    out = bark_tint(np.array([0.05, 0.10, 0.20]), stops)
    assert np.isfinite(out).all()
