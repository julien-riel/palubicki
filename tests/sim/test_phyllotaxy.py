# tests/sim/test_phyllotaxy.py
import numpy as np
import pytest

from palubicki.config import PhyllotaxyConfig
from palubicki.sim.phyllotaxy import lateral_bud_directions, reserve_bud_directions


def test_alternate_yields_one_direction():
    cfg = PhyllotaxyConfig(mode="alternate", branch_angle_by_order=(45.0,), divergence_angle_deg=137.5)
    dirs = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0, seed=0, axis_order=0)
    assert dirs.shape == (1, 3)
    assert abs(np.linalg.norm(dirs[0]) - 1.0) < 1e-7


def test_opposite_yields_two_opposing_directions():
    cfg = PhyllotaxyConfig(mode="opposite", branch_angle_by_order=(45.0,), divergence_angle_deg=0.0)
    dirs = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0, seed=0, axis_order=0)
    assert dirs.shape == (2, 3)
    perp_a = dirs[0] - np.dot(dirs[0], [0, 1, 0]) * np.array([0, 1, 0])
    perp_b = dirs[1] - np.dot(dirs[1], [0, 1, 0]) * np.array([0, 1, 0])
    cos = np.dot(perp_a / np.linalg.norm(perp_a), perp_b / np.linalg.norm(perp_b))
    assert cos < -0.999


def test_whorled_yields_k_directions():
    cfg = PhyllotaxyConfig(mode="whorled", whorl_count=4, branch_angle_by_order=(45.0,))
    dirs = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0, seed=0, axis_order=0)
    assert dirs.shape == (4, 3)


def test_branch_angle_respected():
    cfg = PhyllotaxyConfig(mode="alternate", branch_angle_by_order=(30.0,))
    growth = np.array([0, 1, 0])
    dirs = lateral_bud_directions(growth, cfg, node_index=0, seed=0, axis_order=0)
    cos = np.dot(dirs[0], growth)
    expected = np.cos(np.radians(30.0))
    assert abs(cos - expected) < 1e-6


def test_alternate_divergence_rotates_between_nodes():
    cfg = PhyllotaxyConfig(mode="alternate", branch_angle_by_order=(45.0,), divergence_angle_deg=137.5)
    d0 = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0, seed=0, axis_order=0)[0]
    d1 = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=1, seed=0, axis_order=0)[0]
    assert not np.allclose(d0, d1, atol=1e-3)


def test_jitter_deterministic_same_seed():
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_by_order=(45.0,),
        divergence_angle_deg=137.5,
        divergence_jitter_deg=5.0,
        branch_angle_jitter_deg=5.0,
    )
    d_a = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=42, axis_order=0)
    d_b = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=42, axis_order=0)
    np.testing.assert_array_equal(d_a, d_b)


def test_jitter_different_seeds_differ():
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_by_order=(45.0,),
        divergence_angle_deg=137.5,
        divergence_jitter_deg=5.0,
        branch_angle_jitter_deg=5.0,
    )
    d_a = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=42, axis_order=0)
    d_b = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=43, axis_order=0)
    assert not np.allclose(d_a, d_b, atol=1e-6)


def test_jitter_zero_matches_no_jitter():
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_by_order=(45.0,),
        divergence_angle_deg=137.5,
        divergence_jitter_deg=0.0,
        branch_angle_jitter_deg=0.0,
    )
    d_a = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=42, axis_order=0)
    d_b = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=99, axis_order=0)
    np.testing.assert_array_equal(d_a, d_b)


def test_jitter_clamps_branch_angle_in_range():
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_by_order=(45.0,),
        divergence_angle_deg=137.5,
        divergence_jitter_deg=0.0,
        branch_angle_jitter_deg=500.0,
    )
    growth = np.array([0, 1, 0])
    for ni in range(50):
        d = lateral_bud_directions(growth, cfg, node_index=ni, seed=42, axis_order=0)[0]
        cos_with_growth = float(np.dot(d, growth))
        assert -1e-9 <= cos_with_growth <= 1.0 + 1e-9, (
            f"node_index={ni}: cos(growth, d)={cos_with_growth} outside [0, 1]"
        )


def test_branch_angle_by_order_lookup_first():
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_by_order=(30.0, 60.0, 80.0),
        divergence_angle_deg=0.0,
    )
    growth = np.array([0, 1, 0])
    d = lateral_bud_directions(growth, cfg, node_index=0, seed=0, axis_order=0)[0]
    cos = float(np.dot(d, growth))
    assert abs(cos - np.cos(np.radians(30.0))) < 1e-6


def test_branch_angle_by_order_lookup_clamps_above_len():
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_by_order=(30.0, 60.0),
        divergence_angle_deg=0.0,
    )
    growth = np.array([0, 1, 0])
    d = lateral_bud_directions(growth, cfg, node_index=0, seed=0, axis_order=10)[0]
    cos = float(np.dot(d, growth))
    assert abs(cos - np.cos(np.radians(60.0))) < 1e-6


def test_branch_angle_by_order_single_element_same_for_all_orders():
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_by_order=(45.0,),
        divergence_angle_deg=0.0,
    )
    growth = np.array([0, 1, 0])
    d0 = lateral_bud_directions(growth, cfg, node_index=0, seed=0, axis_order=0)[0]
    d5 = lateral_bud_directions(growth, cfg, node_index=0, seed=0, axis_order=5)[0]
    cos0 = float(np.dot(d0, growth))
    cos5 = float(np.dot(d5, growth))
    assert abs(cos0 - cos5) < 1e-9


def test_reserve_directions_count():
    cfg = PhyllotaxyConfig(mode="alternate", branch_angle_by_order=(45.0,), dormant_reserve_count=3)
    dirs = reserve_bud_directions(
        np.array([0.0, 1.0, 0.0]), cfg,
        node_index=0, seed=0, count=3,
    )
    assert dirs.shape == (3, 3)
    for d in dirs:
        assert abs(np.linalg.norm(d) - 1.0) < 1e-7


def test_reserve_directions_count_zero_returns_empty():
    cfg = PhyllotaxyConfig(mode="alternate", branch_angle_by_order=(45.0,))
    dirs = reserve_bud_directions(
        np.array([0.0, 1.0, 0.0]), cfg,
        node_index=0, seed=0, count=0,
    )
    assert dirs.shape == (0, 3)


def test_reserve_directions_opposite_to_laterals():
    """Reserves point to the opposite azimuth half-plane from laterals."""
    cfg = PhyllotaxyConfig(
        mode="alternate", branch_angle_by_order=(45.0,), divergence_angle_deg=0.0,
        dormant_reserve_count=1,
    )
    growth = np.array([0.0, 1.0, 0.0])
    lateral = lateral_bud_directions(growth, cfg, node_index=0, seed=0, axis_order=0)[0]
    reserve = reserve_bud_directions(growth, cfg, node_index=0, seed=0, count=1)[0]
    # Project onto plane perpendicular to growth.
    lat_perp = lateral - np.dot(lateral, growth) * growth
    res_perp = reserve - np.dot(reserve, growth) * growth
    lat_perp = lat_perp / np.linalg.norm(lat_perp)
    res_perp = res_perp / np.linalg.norm(res_perp)
    # Approximately opposite azimuth (cos ≈ -1, jitter aside).
    assert float(np.dot(lat_perp, res_perp)) < -0.9


def test_reserve_branch_angle_tighter_than_laterals():
    """Reserves emerge at a tighter angle (closer to growth axis)."""
    cfg = PhyllotaxyConfig(
        mode="alternate", branch_angle_by_order=(60.0,),
        dormant_reserve_count=1,
    )
    growth = np.array([0.0, 1.0, 0.0])
    lateral = lateral_bud_directions(growth, cfg, node_index=0, seed=0, axis_order=0)[0]
    reserve = reserve_bud_directions(growth, cfg, node_index=0, seed=0, count=1)[0]
    # Tighter = larger dot product with growth direction.
    assert float(np.dot(reserve, growth)) > float(np.dot(lateral, growth))


def test_reserve_directions_deterministic():
    cfg = PhyllotaxyConfig(
        mode="alternate", branch_angle_by_order=(45.0,),
        divergence_jitter_deg=5.0, branch_angle_jitter_deg=5.0,
        dormant_reserve_count=2,
    )
    d_a = reserve_bud_directions(np.array([0, 1, 0]), cfg, node_index=7, seed=42, count=2)
    d_b = reserve_bud_directions(np.array([0, 1, 0]), cfg, node_index=7, seed=42, count=2)
    np.testing.assert_array_equal(d_a, d_b)


def test_decussate_two_buds_per_node():
    cfg = PhyllotaxyConfig(mode="decussate", branch_angle_by_order=(45.0,), divergence_angle_deg=0.0)
    dirs = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0, seed=0, axis_order=0)
    assert dirs.shape == (2, 3)
    assert abs(np.linalg.norm(dirs[0]) - 1.0) < 1e-7
    assert abs(np.linalg.norm(dirs[1]) - 1.0) < 1e-7


def test_decussate_alternates_90_per_node():
    cfg = PhyllotaxyConfig(mode="decussate", branch_angle_by_order=(45.0,), divergence_angle_deg=0.0)
    growth = np.array([0.0, 1.0, 0.0])
    d_even = lateral_bud_directions(growth, cfg, node_index=0, seed=0, axis_order=0)[0]
    d_odd = lateral_bud_directions(growth, cfg, node_index=1, seed=0, axis_order=0)[0]
    proj_even = d_even - np.dot(d_even, growth) * growth
    proj_odd = d_odd - np.dot(d_odd, growth) * growth
    proj_even = proj_even / np.linalg.norm(proj_even)
    proj_odd = proj_odd / np.linalg.norm(proj_odd)
    cos_angle = float(np.dot(proj_even, proj_odd))
    assert abs(cos_angle) < 1e-6


def test_decussate_with_nonzero_divergence():
    cfg = PhyllotaxyConfig(mode="decussate", branch_angle_by_order=(45.0,), divergence_angle_deg=10.0)
    growth = np.array([0.0, 1.0, 0.0])
    d0 = lateral_bud_directions(growth, cfg, node_index=0, seed=0, axis_order=0)[0]
    d2 = lateral_bud_directions(growth, cfg, node_index=2, seed=0, axis_order=0)[0]
    p0 = d0 - np.dot(d0, growth) * growth
    p2 = d2 - np.dot(d2, growth) * growth
    p0 = p0 / np.linalg.norm(p0)
    p2 = p2 / np.linalg.norm(p2)
    cos_angle = float(np.dot(p0, p2))
    expected = np.cos(np.radians(20.0))
    assert abs(cos_angle - expected) < 1e-6


def test_distichous_yields_one_direction():
    cfg = PhyllotaxyConfig(mode="distichous", branch_angle_by_order=(45.0,))
    dirs = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0, seed=0, axis_order=0)
    assert dirs.shape == (1, 3)
    assert abs(np.linalg.norm(dirs[0]) - 1.0) < 1e-7


def test_distichous_alternates_180_between_successive_nodes():
    cfg = PhyllotaxyConfig(mode="distichous", branch_angle_by_order=(45.0,))
    g = np.array([0.0, 1.0, 0.0])

    def perp(v):
        p = v - np.dot(v, g) * g
        return p / np.linalg.norm(p)

    d0 = lateral_bud_directions(g, cfg, node_index=0, seed=0, axis_order=0)[0]
    d1 = lateral_bud_directions(g, cfg, node_index=1, seed=0, axis_order=0)[0]
    d2 = lateral_bud_directions(g, cfg, node_index=2, seed=0, axis_order=0)[0]
    assert np.dot(perp(d0), perp(d1)) < -0.999
    assert np.dot(perp(d1), perp(d2)) < -0.999


def test_distichous_ignores_divergence_angle_deg():
    cfg_a = PhyllotaxyConfig(mode="distichous", branch_angle_by_order=(45.0,), divergence_angle_deg=0.0)
    cfg_b = PhyllotaxyConfig(mode="distichous", branch_angle_by_order=(45.0,), divergence_angle_deg=137.5)
    g = np.array([0.0, 1.0, 0.0])
    d_a = lateral_bud_directions(g, cfg_a, node_index=1, seed=0, axis_order=0)
    d_b = lateral_bud_directions(g, cfg_b, node_index=1, seed=0, axis_order=0)
    np.testing.assert_allclose(d_a, d_b, atol=1e-10)
