# tests/sim/test_envelope.py
import numpy as np
import pytest

from palubicki.config import EnvelopeConfig
from palubicki.sim.envelope import sample_markers


def test_sphere_points_within_radius(rng):
    cfg = EnvelopeConfig(shape="sphere", rx=2.0, ry=2.0, rz=2.0, marker_count=2000)
    pts = sample_markers(cfg, rng)
    assert pts.shape == (2000, 3)
    distances = np.linalg.norm(pts, axis=1)
    assert np.all(distances <= 2.0 + 1e-9)


def test_ellipsoid_points_inside(rng):
    cfg = EnvelopeConfig(shape="ellipsoid", rx=1.0, ry=3.0, rz=2.0, marker_count=2000)
    pts = sample_markers(cfg, rng)
    normalized = pts / np.array([1.0, 3.0, 2.0])
    distances = np.linalg.norm(normalized, axis=1)
    assert np.all(distances <= 1.0 + 1e-9)


def test_cone_apex_at_top(rng):
    cfg = EnvelopeConfig(shape="cone", rx=2.0, ry=4.0, rz=2.0, marker_count=2000)
    pts = sample_markers(cfg, rng)
    assert np.all(pts[:, 1] >= 0 - 1e-9)
    assert np.all(pts[:, 1] <= 4.0 + 1e-9)
    radii = np.sqrt((pts[:, 0] / 2.0) ** 2 + (pts[:, 2] / 2.0) ** 2)
    expected_max_radius = 1.0 - pts[:, 1] / 4.0
    assert np.all(radii <= expected_max_radius + 1e-6)


def test_half_ellipsoid_y_nonneg(rng):
    cfg = EnvelopeConfig(shape="half_ellipsoid", rx=2.0, ry=4.0, rz=2.0, marker_count=1000)
    pts = sample_markers(cfg, rng)
    assert np.all(pts[:, 1] >= 0 - 1e-9)


def test_center_offset_applied(rng):
    cfg = EnvelopeConfig(shape="sphere", rx=1.0, ry=1.0, rz=1.0,
                          center=(10.0, 20.0, 30.0), marker_count=500)
    pts = sample_markers(cfg, rng)
    assert np.linalg.norm(pts.mean(axis=0) - np.array([10.0, 20.0, 30.0])) < 0.1


def test_deterministic_with_same_seed():
    cfg = EnvelopeConfig(shape="ellipsoid", rx=1.0, ry=2.0, rz=1.5, marker_count=500)
    pts_a = sample_markers(cfg, np.random.default_rng(7))
    pts_b = sample_markers(cfg, np.random.default_rng(7))
    np.testing.assert_array_equal(pts_a, pts_b)


def test_unknown_shape_raises():
    cfg = EnvelopeConfig.__new__(EnvelopeConfig)
    object.__setattr__(cfg, "shape", "torus")
    object.__setattr__(cfg, "rx", 1.0); object.__setattr__(cfg, "ry", 1.0); object.__setattr__(cfg, "rz", 1.0)
    object.__setattr__(cfg, "center", (0.0, 0.0, 0.0)); object.__setattr__(cfg, "marker_count", 100)
    with pytest.raises(ValueError, match="torus"):
        sample_markers(cfg, np.random.default_rng(0))
