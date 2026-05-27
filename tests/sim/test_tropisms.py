# tests/sim/test_tropisms.py
import numpy as np
import pytest

from palubicki.config import TropismConfig
from palubicki.sim.tropisms import growth_direction


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


def test_growth_direction_zero_gradient_falls_back_to_photo_direction():
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
    np.testing.assert_allclose(d, [0.0, 1.0, 0.0], atol=1e-9)


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
