# src/palubicki/sim/tropisms.py
from __future__ import annotations

import numpy as np

from palubicki.config import TropismConfig

_UP = np.array([0.0, 1.0, 0.0])
_DOWN = np.array([0.0, -1.0, 0.0])


def growth_direction(
    *,
    v_perception: np.ndarray,
    current_direction: np.ndarray,
    cfg: TropismConfig,
    light_gradient: np.ndarray | None = None,
    axis_order: int = 0,
) -> np.ndarray:
    """Blend perception + orthotropy (UP) + gravitropy (DOWN) + photo + inertia.

    When `light_gradient` is provided and non-zero, it replaces `cfg.photo_direction`
    in the phototropism term.

    Each weight is scaled by ``cfg.axis_decay ** axis_order`` so the trunk gets
    full weighting and higher-order branches get attenuated (Fix #2).
    """
    if light_gradient is not None:
        lg = np.asarray(light_gradient, dtype=np.float64)
        lg_norm = float(np.linalg.norm(lg))
        if lg_norm > 1e-12:
            photo = lg / lg_norm
        else:
            photo = np.asarray(cfg.photo_direction, dtype=np.float64)
            pn = np.linalg.norm(photo)
            if pn > 1e-12:
                photo = photo / pn
    else:
        photo = np.asarray(cfg.photo_direction, dtype=np.float64)
        pn = np.linalg.norm(photo)
        if pn > 1e-12:
            photo = photo / pn

    decay = float(cfg.axis_decay) ** int(axis_order)
    blend = (
        cfg.w_perception * v_perception
        + (cfg.w_orthotropy * decay) * _UP
        + (cfg.w_gravitropism * decay) * _DOWN
        + (cfg.w_phototropism * decay) * photo
        + cfg.w_direction_inertia * current_direction
    )
    n = np.linalg.norm(blend)
    if n < 1e-12:
        cd_n = np.linalg.norm(current_direction)
        if cd_n > 1e-12:
            return current_direction / cd_n
        return _UP.copy()
    return blend / n
