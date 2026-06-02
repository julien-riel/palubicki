# tests/sim/test_tropisms.py
import numpy as np
import pytest

from palubicki.config import TropismConfig
from palubicki.sim.tropisms import (
    growth_direction,
    spray_plane_normal_from_direction,
)


def test_only_gravity_overrides_to_up():
    cfg = TropismConfig(w_perception=0.0, w_orthotropy_main=1.0, w_phototropism=0.0, w_direction_inertia=0.0)
    d = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
        is_main_axis=True,
    )
    np.testing.assert_allclose(d, [0, 1, 0], atol=1e-7)


def test_only_inertia_keeps_current_direction():
    cfg = TropismConfig(w_perception=0.0, w_orthotropy_main=0.0, w_phototropism=0.0, w_direction_inertia=1.0)
    d = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([0.0, 0.0, 1.0]),
        cfg=cfg,
        is_main_axis=True,
    )
    np.testing.assert_allclose(d, [0, 0, 1], atol=1e-7)


def test_all_zero_weights_returns_inertia_fallback():
    cfg = TropismConfig(w_perception=0.0, w_orthotropy_main=0.0, w_phototropism=0.0, w_direction_inertia=0.0)
    d = growth_direction(
        v_perception=np.array([0.0, 0.0, 0.0]),
        current_direction=np.array([0.0, 1.0, 0.0]),
        cfg=cfg,
        is_main_axis=True,
    )
    np.testing.assert_allclose(d, [0, 1, 0], atol=1e-7)


def test_phototropism_pulls_toward_photo_direction():
    cfg = TropismConfig(
        w_perception=0.0, w_orthotropy_main=0.0, w_phototropism=1.0, w_direction_inertia=0.0,
        photo_direction=(0.0, 0.0, 1.0),
    )
    d = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
        is_main_axis=True,
    )
    np.testing.assert_allclose(d, [0, 0, 1], atol=1e-7)


def test_returns_unit_vector():
    cfg = TropismConfig()
    d = growth_direction(
        v_perception=np.array([1.0, 1.0, 0.0]),
        current_direction=np.array([0.0, 1.0, 0.0]),
        cfg=cfg,
        is_main_axis=True,
    )
    assert abs(np.linalg.norm(d) - 1.0) < 1e-7


def test_zero_weights_zero_current_direction_falls_back_to_gravity():
    """When all weights are zero AND current_direction is zero, return GRAVITY_UP."""
    cfg = TropismConfig(w_perception=0.0, w_orthotropy_main=0.0, w_phototropism=0.0, w_direction_inertia=0.0)
    d = growth_direction(
        v_perception=np.zeros(3),
        current_direction=np.zeros(3),
        cfg=cfg,
        is_main_axis=True,
    )
    np.testing.assert_allclose(d, [0, 1, 0], atol=1e-7)


def test_growth_direction_uses_light_gradient_when_provided():
    from palubicki.config import TropismConfig
    from palubicki.sim.tropisms import growth_direction
    cfg = TropismConfig(w_perception=0.0, w_orthotropy_main=0.0, w_phototropism=1.0, w_direction_inertia=0.0,
                        photo_direction=(0.0, 1.0, 0.0))
    light_grad = np.array([1.0, 0.0, 0.0])  # opposite of photo_direction
    d = growth_direction(
        v_perception=np.zeros(3),
        current_direction=np.array([0.0, 1.0, 0.0]),
        cfg=cfg,
        is_main_axis=True,
        light_gradient=light_grad,
    )
    # Only phototropism is non-zero; with light_gradient it should override photo_direction
    np.testing.assert_allclose(d, [1.0, 0.0, 0.0], atol=1e-9)


def test_growth_direction_falls_back_to_photo_direction_when_no_gradient():
    from palubicki.config import TropismConfig
    from palubicki.sim.tropisms import growth_direction
    cfg = TropismConfig(w_perception=0.0, w_orthotropy_main=0.0, w_phototropism=1.0, w_direction_inertia=0.0,
                        photo_direction=(0.0, 1.0, 0.0))
    d = growth_direction(
        v_perception=np.zeros(3),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
        is_main_axis=True,
        light_gradient=None,
    )
    np.testing.assert_allclose(d, [0.0, 1.0, 0.0], atol=1e-9)


def test_growth_direction_zero_gradient_contributes_no_phototropism():
    """FIX E: a present-but-uniform light gradient (norm ~0) must contribute ZERO
    phototropism, NOT fall back to cfg.photo_direction (which would smuggle a
    spurious +Y/orthotropic pull under w_phototropism). With every other weight
    zeroed, the blend is empty and the direction holds at current_direction."""
    from palubicki.config import TropismConfig
    from palubicki.sim.tropisms import growth_direction
    cfg = TropismConfig(w_perception=0.0, w_orthotropy_main=0.0, w_phototropism=1.0, w_direction_inertia=0.0,
                        photo_direction=(0.0, 1.0, 0.0))
    d = growth_direction(
        v_perception=np.zeros(3),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
        is_main_axis=True,
        light_gradient=np.zeros(3),
    )
    np.testing.assert_allclose(d, [1.0, 0.0, 0.0], atol=1e-9)


def test_growth_direction_minimal_kwargs():
    """Existing callers that don't pass light_gradient must still work."""
    from palubicki.config import TropismConfig
    from palubicki.sim.tropisms import growth_direction
    cfg = TropismConfig()
    d = growth_direction(
        v_perception=np.array([0.0, 1.0, 0.0]),
        current_direction=np.array([0.0, 1.0, 0.0]),
        cfg=cfg,
        is_main_axis=True,
    )
    assert np.linalg.norm(d) == pytest.approx(1.0)


def test_main_axis_uses_main_orthotropy_weight():
    """With w_orthotropy_main=1.0 and w_orthotropy_lateral=0.0, a main axis
    should be pulled UP; a lateral axis should ignore orthotropy entirely."""
    cfg = TropismConfig(
        w_perception=0.0,
        w_orthotropy_main=1.0,
        w_orthotropy_lateral=0.0,
        w_phototropism=0.0,
        w_direction_inertia=0.0,
    )
    # main axis: orthotropy pulls UP
    d_main = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
        is_main_axis=True,
    )
    np.testing.assert_allclose(d_main, [0, 1, 0], atol=1e-7)

    # lateral axis: no orthotropy → use inertia (current_direction)
    cfg2 = TropismConfig(
        w_perception=0.0,
        w_orthotropy_main=1.0,
        w_orthotropy_lateral=0.0,
        w_phototropism=0.0,
        w_direction_inertia=1.0,
    )
    d_lat = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg2,
        is_main_axis=False,
    )
    np.testing.assert_allclose(d_lat, [1, 0, 0], atol=1e-7)


def test_lateral_axis_uses_lateral_gravitropism_weight():
    """With w_gravitropism_lateral=1.0 (pendula-like), a lateral axis is pulled DOWN."""
    cfg = TropismConfig(
        w_perception=0.0,
        w_orthotropy_main=0.0,
        w_orthotropy_lateral=0.0,
        w_gravitropism_main=0.0,
        w_gravitropism_lateral=1.0,
        w_direction_inertia=0.0,
    )
    d_lat = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
        is_main_axis=False,
    )
    np.testing.assert_allclose(d_lat, [0, -1, 0], atol=1e-7)


def test_plagiotropism_pulls_horizontal():
    cfg = TropismConfig(
        w_perception=0.0,
        w_orthotropy_main=0.0,
        w_orthotropy_lateral=0.0,
        w_gravitropism_main=0.0,
        w_gravitropism_lateral=0.0,
        w_plagiotropism_lateral=1.0,
        w_phototropism=0.0,
        w_direction_inertia=0.0,
    )
    cur = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
    d = growth_direction(
        v_perception=np.zeros(3),
        current_direction=cur,
        cfg=cfg,
        is_main_axis=False,
    )
    assert abs(float(np.dot(d, [0.0, 1.0, 0.0]))) < 1e-6
    assert d[0] > 0.99


def test_plagiotropism_skipped_when_near_vertical():
    cfg = TropismConfig(
        w_perception=0.0,
        w_orthotropy_main=0.0,
        w_orthotropy_lateral=0.0,
        w_gravitropism_main=0.0,
        w_gravitropism_lateral=0.0,
        w_plagiotropism_lateral=10.0,
        w_phototropism=0.0,
        w_direction_inertia=1.0,
    )
    cur = np.array([0.0, 1.0, 0.0])
    d = growth_direction(
        v_perception=np.zeros(3),
        current_direction=cur,
        cfg=cfg,
        is_main_axis=False,
    )
    np.testing.assert_allclose(d, [0.0, 1.0, 0.0], atol=1e-7)


def test_plagiotropism_main_vs_lateral():
    cfg = TropismConfig(
        w_perception=0.0,
        w_orthotropy_main=0.0,
        w_orthotropy_lateral=0.0,
        w_gravitropism_main=0.0,
        w_gravitropism_lateral=0.0,
        w_plagiotropism_main=0.0,
        w_plagiotropism_lateral=1.0,
        w_phototropism=0.0,
        w_direction_inertia=0.0,
    )
    cur = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
    d_main = growth_direction(
        v_perception=np.zeros(3),
        current_direction=cur,
        cfg=cfg,
        is_main_axis=True,
    )
    np.testing.assert_allclose(d_main, cur, atol=1e-7)
    d_lat = growth_direction(
        v_perception=np.zeros(3),
        current_direction=cur,
        cfg=cfg,
        is_main_axis=False,
    )
    assert abs(float(np.dot(d_lat, [0.0, 1.0, 0.0]))) < 1e-6


def test_epinasty_disabled_matches_constant_weight():
    """Default (disabled) epinasty leaves plagiotropism at full strength
    regardless of branch_age_years."""
    cfg = TropismConfig(
        w_perception=0.0, w_orthotropy_main=0.0, w_orthotropy_lateral=0.0,
        w_gravitropism_main=0.0, w_gravitropism_lateral=0.0,
        w_plagiotropism_main=0.0, w_plagiotropism_lateral=1.0,
        w_phototropism=0.0, w_direction_inertia=0.0,
    )
    cur = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
    base = growth_direction(v_perception=np.zeros(3), current_direction=cur,
                            cfg=cfg, is_main_axis=False)
    for age in (0.0, 5.0, 50.0):
        d = growth_direction(v_perception=np.zeros(3), current_direction=cur,
                             cfg=cfg, is_main_axis=False, branch_age_years=age)
        np.testing.assert_allclose(d, base, atol=1e-12)


def test_epinasty_young_branch_ignores_plagiotropism():
    """Epinasty on, age 0: ramp=0 disables the horizontal pull; only inertia
    remains, so the lateral keeps its current direction."""
    cfg = TropismConfig(
        w_perception=0.0, w_orthotropy_main=0.0, w_orthotropy_lateral=0.0,
        w_gravitropism_main=0.0, w_gravitropism_lateral=0.0,
        w_plagiotropism_main=0.0, w_plagiotropism_lateral=1.0,
        w_phototropism=0.0, w_direction_inertia=1.0,
        epinasty_enabled=True, epinasty_tau_years=8.0,
    )
    cur = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
    d = growth_direction(v_perception=np.zeros(3), current_direction=cur,
                         cfg=cfg, is_main_axis=False, branch_age_years=0.0)
    np.testing.assert_allclose(d, cur, atol=1e-7)


def test_epinasty_old_branch_recovers_full_plagiotropism():
    """Epinasty on, age >> tau: result approaches the full-strength horizontal
    pull (the disabled result)."""
    common = {
        "w_perception": 0.0, "w_orthotropy_main": 0.0, "w_orthotropy_lateral": 0.0,
        "w_gravitropism_main": 0.0, "w_gravitropism_lateral": 0.0,
        "w_plagiotropism_main": 0.0, "w_plagiotropism_lateral": 1.0,
        "w_phototropism": 0.0, "w_direction_inertia": 0.0,
    }
    cur = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
    full = growth_direction(v_perception=np.zeros(3), current_direction=cur,
                            cfg=TropismConfig(**common), is_main_axis=False)
    cfg_on = TropismConfig(**common, epinasty_enabled=True, epinasty_tau_years=8.0)
    d_old = growth_direction(v_perception=np.zeros(3), current_direction=cur,
                             cfg=cfg_on, is_main_axis=False, branch_age_years=80.0)
    np.testing.assert_allclose(d_old, full, atol=1e-3)
    assert abs(float(np.dot(d_old, [0.0, 1.0, 0.0]))) < 1e-3  # near-zero vertical component


def test_spray_normal_horizontal_direction_is_up():
    """A horizontal axis's spray plane is the ground plane (normal = world-up)."""
    n = spray_plane_normal_from_direction(np.array([1.0, 0.0, 0.3]))
    assert n is not None
    np.testing.assert_allclose(n, [0.0, 1.0, 0.0], atol=1e-9)


def test_spray_normal_vertical_direction_is_none():
    """A near-vertical axis (the trunk) has no horizontal-ish plane."""
    assert spray_plane_normal_from_direction(np.array([0.0, 1.0, 0.0])) is None
    assert spray_plane_normal_from_direction(np.zeros(3)) is None


def test_spray_normal_is_perpendicular_to_direction():
    d = np.array([1.0, 0.7, -0.4])
    n = spray_plane_normal_from_direction(d)
    assert n is not None
    assert abs(float(np.dot(n, d / np.linalg.norm(d)))) < 1e-9
    assert abs(np.linalg.norm(n) - 1.0) < 1e-9


def test_spray_plane_normal_none_matches_world_xy():
    """Passing spray_plane_normal=None is bit-identical to the legacy XY path."""
    cfg = TropismConfig(
        w_perception=0.0, w_orthotropy_main=0.0, w_orthotropy_lateral=0.0,
        w_gravitropism_main=0.0, w_gravitropism_lateral=0.0,
        w_plagiotropism_main=0.0, w_plagiotropism_lateral=1.0,
        w_phototropism=0.0, w_direction_inertia=0.3,
    )
    cur = np.array([1.0, 1.0, 0.5])
    base = growth_direction(v_perception=np.zeros(3), current_direction=cur,
                            cfg=cfg, is_main_axis=False)
    same = growth_direction(v_perception=np.zeros(3), current_direction=cur,
                            cfg=cfg, is_main_axis=False, spray_plane_normal=None)
    np.testing.assert_allclose(same, base, atol=1e-12)


def test_plagiotropism_flattens_into_given_spray_plane():
    """With a spray-plane normal, plagiotropism removes the out-of-plane
    component of current_direction instead of the world-vertical one."""
    cfg = TropismConfig(
        w_perception=0.0, w_orthotropy_main=0.0, w_orthotropy_lateral=0.0,
        w_gravitropism_main=0.0, w_gravitropism_lateral=0.0,
        w_plagiotropism_main=0.0, w_plagiotropism_lateral=1.0,
        w_phototropism=0.0, w_direction_inertia=0.0,
    )
    # Spray plane = the X=0 plane (normal +X). A direction with an X component
    # should be flattened onto that plane (x -> 0), NOT onto world-XY.
    n = np.array([1.0, 0.0, 0.0])
    cur = np.array([0.5, 0.0, 1.0])
    d = growth_direction(v_perception=np.zeros(3), current_direction=cur,
                         cfg=cfg, is_main_axis=False, spray_plane_normal=n)
    assert abs(float(np.dot(d, n))) < 1e-9          # lies in the spray plane
    np.testing.assert_allclose(d, [0.0, 0.0, 1.0], atol=1e-7)


def test_spray_plane_plagiotropism_skipped_when_parallel_to_normal():
    """current_direction (near-)parallel to the plane normal is ambiguous and
    the flattening term is skipped that iteration."""
    cfg = TropismConfig(
        w_perception=0.0, w_orthotropy_main=0.0, w_orthotropy_lateral=0.0,
        w_gravitropism_main=0.0, w_gravitropism_lateral=0.0,
        w_plagiotropism_main=0.0, w_plagiotropism_lateral=10.0,
        w_phototropism=0.0, w_direction_inertia=1.0,
    )
    n = np.array([1.0, 0.0, 0.0])
    cur = np.array([1.0, 0.0, 0.0])
    d = growth_direction(v_perception=np.zeros(3), current_direction=cur,
                         cfg=cfg, is_main_axis=False, spray_plane_normal=n)
    np.testing.assert_allclose(d, [1.0, 0.0, 0.0], atol=1e-7)


def test_spray_plane_plagiotropism_not_decayed_by_axis_order():
    """In-plane flattening keeps full strength at higher orders (axis_decay is
    applied to the world-XY path but NOT the spray-plane path)."""
    cfg = TropismConfig(
        w_perception=0.0, w_orthotropy_main=0.0, w_orthotropy_lateral=0.0,
        w_gravitropism_main=0.0, w_gravitropism_lateral=0.0,
        w_plagiotropism_main=0.0, w_plagiotropism_lateral=1.0,
        w_phototropism=0.0, w_direction_inertia=0.0,
        axis_decay=0.5,
    )
    n = np.array([1.0, 0.0, 0.0])
    cur = np.array([0.5, 0.0, 1.0])
    d0 = growth_direction(v_perception=np.zeros(3), current_direction=cur,
                          cfg=cfg, is_main_axis=False, axis_order=0, spray_plane_normal=n)
    d3 = growth_direction(v_perception=np.zeros(3), current_direction=cur,
                          cfg=cfg, is_main_axis=False, axis_order=3, spray_plane_normal=n)
    np.testing.assert_allclose(d3, d0, atol=1e-12)
    assert abs(float(np.dot(d3, n))) < 1e-9


def test_epinasty_monotone_in_age():
    """The horizontal (x) component grows monotonically with branch age."""
    cfg = TropismConfig(
        w_perception=0.0, w_orthotropy_main=0.0, w_orthotropy_lateral=0.0,
        w_gravitropism_main=0.0, w_gravitropism_lateral=0.0,
        w_plagiotropism_main=0.0, w_plagiotropism_lateral=1.0,
        w_phototropism=0.0, w_direction_inertia=1.0,
        epinasty_enabled=True, epinasty_tau_years=8.0,
    )
    cur = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
    horiz = []
    for age in (0.0, 4.0, 8.0, 16.0, 32.0):
        d = growth_direction(v_perception=np.zeros(3), current_direction=cur,
                             cfg=cfg, is_main_axis=False, branch_age_years=age)
        horiz.append(float(d[0]))
    assert all(b >= a - 1e-9 for a, b in zip(horiz, horiz[1:], strict=False))
