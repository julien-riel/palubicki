# tests/sim/test_phyllotaxy.py
import numpy as np
import pytest

from palubicki.config import PhyllotaxyConfig
from palubicki.sim.phyllotaxy import lateral_bud_directions


def test_alternate_yields_one_direction():
    cfg = PhyllotaxyConfig(mode="alternate", branch_angle_deg=45.0, divergence_angle_deg=137.5)
    dirs = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0)
    assert dirs.shape == (1, 3)
    assert abs(np.linalg.norm(dirs[0]) - 1.0) < 1e-7


def test_opposite_yields_two_opposing_directions():
    cfg = PhyllotaxyConfig(mode="opposite", branch_angle_deg=45.0, divergence_angle_deg=0.0)
    dirs = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0)
    assert dirs.shape == (2, 3)
    # Project onto the plane perpendicular to growth direction
    perp_a = dirs[0] - np.dot(dirs[0], [0, 1, 0]) * np.array([0, 1, 0])
    perp_b = dirs[1] - np.dot(dirs[1], [0, 1, 0]) * np.array([0, 1, 0])
    # Should be opposite
    cos = np.dot(perp_a / np.linalg.norm(perp_a), perp_b / np.linalg.norm(perp_b))
    assert cos < -0.999


def test_whorled_yields_k_directions():
    cfg = PhyllotaxyConfig(mode="whorled", whorl_count=4, branch_angle_deg=45.0)
    dirs = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0)
    assert dirs.shape == (4, 3)


def test_branch_angle_respected():
    cfg = PhyllotaxyConfig(mode="alternate", branch_angle_deg=30.0)
    growth = np.array([0, 1, 0])
    dirs = lateral_bud_directions(growth, cfg, node_index=0)
    cos = np.dot(dirs[0], growth)
    expected = np.cos(np.radians(30.0))
    assert abs(cos - expected) < 1e-6


def test_alternate_divergence_rotates_between_nodes():
    cfg = PhyllotaxyConfig(mode="alternate", branch_angle_deg=45.0, divergence_angle_deg=137.5)
    d0 = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0)[0]
    d1 = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=1)[0]
    # Different azimuth (not equal)
    assert not np.allclose(d0, d1, atol=1e-3)
