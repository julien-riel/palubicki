# tests/sim/test_phyllotaxy.py
import numpy as np
import pytest

from palubicki.config import PhyllotaxyConfig
from palubicki.sim.phyllotaxy import lateral_bud_directions


def test_alternate_yields_one_direction():
    cfg = PhyllotaxyConfig(mode="alternate", branch_angle_deg=45.0, divergence_angle_deg=137.5)
    dirs = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0, seed=0)
    assert dirs.shape == (1, 3)
    assert abs(np.linalg.norm(dirs[0]) - 1.0) < 1e-7


def test_opposite_yields_two_opposing_directions():
    cfg = PhyllotaxyConfig(mode="opposite", branch_angle_deg=45.0, divergence_angle_deg=0.0)
    dirs = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0, seed=0)
    assert dirs.shape == (2, 3)
    # Project onto the plane perpendicular to growth direction
    perp_a = dirs[0] - np.dot(dirs[0], [0, 1, 0]) * np.array([0, 1, 0])
    perp_b = dirs[1] - np.dot(dirs[1], [0, 1, 0]) * np.array([0, 1, 0])
    # Should be opposite
    cos = np.dot(perp_a / np.linalg.norm(perp_a), perp_b / np.linalg.norm(perp_b))
    assert cos < -0.999


def test_whorled_yields_k_directions():
    cfg = PhyllotaxyConfig(mode="whorled", whorl_count=4, branch_angle_deg=45.0)
    dirs = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0, seed=0)
    assert dirs.shape == (4, 3)


def test_branch_angle_respected():
    cfg = PhyllotaxyConfig(mode="alternate", branch_angle_deg=30.0)
    growth = np.array([0, 1, 0])
    dirs = lateral_bud_directions(growth, cfg, node_index=0, seed=0)
    cos = np.dot(dirs[0], growth)
    expected = np.cos(np.radians(30.0))
    assert abs(cos - expected) < 1e-6


def test_alternate_divergence_rotates_between_nodes():
    cfg = PhyllotaxyConfig(mode="alternate", branch_angle_deg=45.0, divergence_angle_deg=137.5)
    d0 = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0, seed=0)[0]
    d1 = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=1, seed=0)[0]
    # Different azimuth (not equal)
    assert not np.allclose(d0, d1, atol=1e-3)


def test_jitter_deterministic_same_seed():
    """Same seed + same node_index → identical jittered direction."""
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_deg=45.0,
        divergence_angle_deg=137.5,
        divergence_jitter_deg=5.0,
        branch_angle_jitter_deg=5.0,
    )
    d_a = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=42)
    d_b = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=42)
    np.testing.assert_array_equal(d_a, d_b)


def test_jitter_different_seeds_differ():
    """Same node_index, different seeds → different jittered directions."""
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_deg=45.0,
        divergence_angle_deg=137.5,
        divergence_jitter_deg=5.0,
        branch_angle_jitter_deg=5.0,
    )
    d_a = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=42)
    d_b = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=43)
    assert not np.allclose(d_a, d_b, atol=1e-6)


def test_jitter_zero_matches_no_jitter():
    """With both sigmas == 0, the result is identical regardless of seed."""
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_deg=45.0,
        divergence_angle_deg=137.5,
        divergence_jitter_deg=0.0,
        branch_angle_jitter_deg=0.0,
    )
    d_a = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=42)
    d_b = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=99)
    np.testing.assert_array_equal(d_a, d_b)


def test_jitter_clamps_branch_angle_in_range():
    """With a huge branch_angle_jitter_deg, the effective angle stays in [0, 90°]."""
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_deg=45.0,
        divergence_angle_deg=137.5,
        divergence_jitter_deg=0.0,
        branch_angle_jitter_deg=500.0,
    )
    growth = np.array([0, 1, 0])
    for ni in range(50):
        d = lateral_bud_directions(growth, cfg, node_index=ni, seed=42)[0]
        cos_with_growth = float(np.dot(d, growth))
        assert -1e-9 <= cos_with_growth <= 1.0 + 1e-9, (
            f"node_index={ni}: cos(growth, d)={cos_with_growth} outside [0, 1]"
        )
