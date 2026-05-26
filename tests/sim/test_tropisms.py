# tests/sim/test_tropisms.py
import numpy as np
import pytest

from palubicki.config import TropismConfig
from palubicki.sim.tropisms import growth_direction


def test_only_gravity_overrides_to_up():
    cfg = TropismConfig(w_perception=0.0, w_orthotropy=1.0, w_phototropism=0.0, w_direction_inertia=0.0)
    d = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
    )
    np.testing.assert_allclose(d, [0, 1, 0], atol=1e-7)


def test_only_inertia_keeps_current_direction():
    cfg = TropismConfig(w_perception=0.0, w_orthotropy=0.0, w_phototropism=0.0, w_direction_inertia=1.0)
    d = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([0.0, 0.0, 1.0]),
        cfg=cfg,
    )
    np.testing.assert_allclose(d, [0, 0, 1], atol=1e-7)


def test_all_zero_weights_returns_inertia_fallback():
    cfg = TropismConfig(w_perception=0.0, w_orthotropy=0.0, w_phototropism=0.0, w_direction_inertia=0.0)
    d = growth_direction(
        v_perception=np.array([0.0, 0.0, 0.0]),
        current_direction=np.array([0.0, 1.0, 0.0]),
        cfg=cfg,
    )
    np.testing.assert_allclose(d, [0, 1, 0], atol=1e-7)


def test_phototropism_pulls_toward_photo_direction():
    cfg = TropismConfig(
        w_perception=0.0, w_orthotropy=0.0, w_phototropism=1.0, w_direction_inertia=0.0,
        photo_direction=(0.0, 0.0, 1.0),
    )
    d = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
    )
    np.testing.assert_allclose(d, [0, 0, 1], atol=1e-7)


def test_returns_unit_vector():
    cfg = TropismConfig()
    d = growth_direction(
        v_perception=np.array([1.0, 1.0, 0.0]),
        current_direction=np.array([0.0, 1.0, 0.0]),
        cfg=cfg,
    )
    assert abs(np.linalg.norm(d) - 1.0) < 1e-7


def test_zero_weights_zero_current_direction_falls_back_to_gravity():
    """When all weights are zero AND current_direction is zero, return GRAVITY_UP."""
    cfg = TropismConfig(w_perception=0.0, w_orthotropy=0.0, w_phototropism=0.0, w_direction_inertia=0.0)
    d = growth_direction(
        v_perception=np.zeros(3),
        current_direction=np.zeros(3),
        cfg=cfg,
    )
    np.testing.assert_allclose(d, [0, 1, 0], atol=1e-7)


def test_growth_direction_uses_light_gradient_when_provided():
    from palubicki.config import TropismConfig
    from palubicki.sim.tropisms import growth_direction
    cfg = TropismConfig(w_perception=0.0, w_orthotropy=0.0, w_phototropism=1.0, w_direction_inertia=0.0,
                        photo_direction=(0.0, 1.0, 0.0))
    light_grad = np.array([1.0, 0.0, 0.0])  # opposite of photo_direction
    d = growth_direction(
        v_perception=np.zeros(3),
        current_direction=np.array([0.0, 1.0, 0.0]),
        cfg=cfg,
        light_gradient=light_grad,
    )
    # Only phototropism is non-zero; with light_gradient it should override photo_direction
    np.testing.assert_allclose(d, [1.0, 0.0, 0.0], atol=1e-9)


def test_growth_direction_falls_back_to_photo_direction_when_no_gradient():
    from palubicki.config import TropismConfig
    from palubicki.sim.tropisms import growth_direction
    cfg = TropismConfig(w_perception=0.0, w_orthotropy=0.0, w_phototropism=1.0, w_direction_inertia=0.0,
                        photo_direction=(0.0, 1.0, 0.0))
    d = growth_direction(
        v_perception=np.zeros(3),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
        light_gradient=None,
    )
    np.testing.assert_allclose(d, [0.0, 1.0, 0.0], atol=1e-9)


def test_growth_direction_zero_gradient_falls_back_to_photo_direction():
    from palubicki.config import TropismConfig
    from palubicki.sim.tropisms import growth_direction
    cfg = TropismConfig(w_perception=0.0, w_orthotropy=0.0, w_phototropism=1.0, w_direction_inertia=0.0,
                        photo_direction=(0.0, 1.0, 0.0))
    d = growth_direction(
        v_perception=np.zeros(3),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
        light_gradient=np.zeros(3),
    )
    np.testing.assert_allclose(d, [0.0, 1.0, 0.0], atol=1e-9)


def test_growth_direction_v1_signature_still_works():
    """Existing callers that don't pass light_gradient must still work."""
    from palubicki.config import TropismConfig
    from palubicki.sim.tropisms import growth_direction
    cfg = TropismConfig()
    d = growth_direction(
        v_perception=np.array([0.0, 1.0, 0.0]),
        current_direction=np.array([0.0, 1.0, 0.0]),
        cfg=cfg,
    )
    assert np.linalg.norm(d) == pytest.approx(1.0)
