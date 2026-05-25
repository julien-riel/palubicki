# src/palubicki/sim/tropisms.py
from __future__ import annotations

import numpy as np

from palubicki.config import TropismConfig

_GRAVITY_UP = np.array([0.0, 1.0, 0.0])


def growth_direction(
    *,
    v_perception: np.ndarray,
    current_direction: np.ndarray,
    cfg: TropismConfig,
) -> np.ndarray:
    """Blend perception + gravity + photo + inertia, return unit vector."""
    photo = np.asarray(cfg.photo_direction, dtype=np.float64)
    photo_norm = np.linalg.norm(photo)
    if photo_norm > 1e-12:
        photo = photo / photo_norm

    blend = (
        cfg.w_perception * v_perception
        + cfg.w_gravity * _GRAVITY_UP
        + cfg.w_phototropism * photo
        + cfg.w_direction_inertia * current_direction
    )
    n = np.linalg.norm(blend)
    if n < 1e-12:
        # all weights zero or directions cancel — fall back to current direction
        cd_n = np.linalg.norm(current_direction)
        if cd_n > 1e-12:
            return current_direction / cd_n
        return _GRAVITY_UP.copy()
    return blend / n
