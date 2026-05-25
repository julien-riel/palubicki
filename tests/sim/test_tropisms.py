# tests/sim/test_tropisms.py
import numpy as np

from palubicki.config import TropismConfig
from palubicki.sim.tropisms import growth_direction


def test_only_gravity_overrides_to_up():
    cfg = TropismConfig(w_perception=0.0, w_gravity=1.0, w_phototropism=0.0, w_direction_inertia=0.0)
    d = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
    )
    np.testing.assert_allclose(d, [0, 1, 0], atol=1e-7)


def test_only_inertia_keeps_current_direction():
    cfg = TropismConfig(w_perception=0.0, w_gravity=0.0, w_phototropism=0.0, w_direction_inertia=1.0)
    d = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([0.0, 0.0, 1.0]),
        cfg=cfg,
    )
    np.testing.assert_allclose(d, [0, 0, 1], atol=1e-7)


def test_all_zero_weights_returns_inertia_fallback():
    cfg = TropismConfig(w_perception=0.0, w_gravity=0.0, w_phototropism=0.0, w_direction_inertia=0.0)
    d = growth_direction(
        v_perception=np.array([0.0, 0.0, 0.0]),
        current_direction=np.array([0.0, 1.0, 0.0]),
        cfg=cfg,
    )
    np.testing.assert_allclose(d, [0, 1, 0], atol=1e-7)


def test_phototropism_pulls_toward_photo_direction():
    cfg = TropismConfig(
        w_perception=0.0, w_gravity=0.0, w_phototropism=1.0, w_direction_inertia=0.0,
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
