# src/palubicki/sim/tropisms.py
from __future__ import annotations

import math

import numpy as np

from palubicki.config import TropismConfig

_UP = np.array([0.0, 1.0, 0.0])
_DOWN = np.array([0.0, -1.0, 0.0])


def growth_direction(
    *,
    v_perception: np.ndarray,
    current_direction: np.ndarray,
    cfg: TropismConfig,
    is_main_axis: bool,
    light_gradient: np.ndarray | None = None,
    axis_order: int = 0,
    branch_age_years: float = 0.0,
) -> np.ndarray:
    """Blend perception + orthotropy (UP) + gravitropy (DOWN) + photo + inertia.

    ``is_main_axis`` selects between main-axis weights (e.g. w_orthotropy_main)
    and lateral-axis weights. Each tropism weight at order k is multiplied by
    ``cfg.axis_decay**k``.
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
    w_ortho = cfg.w_orthotropy_main if is_main_axis else cfg.w_orthotropy_lateral
    w_gravi = cfg.w_gravitropism_main if is_main_axis else cfg.w_gravitropism_lateral
    w_plagio = cfg.w_plagiotropism_main if is_main_axis else cfg.w_plagiotropism_lateral
    if cfg.epinasty_enabled and cfg.epinasty_tau_years > 0.0:
        ramp = 1.0 - math.exp(-max(0.0, branch_age_years) / cfg.epinasty_tau_years)
        w_plagio = w_plagio * ramp

    # Plagiotropism: project current_direction onto the XY plane (horizontal).
    # If current_direction is near-vertical (|dot(UP)| >= 0.99) the projection
    # is ambiguous; skip the term this iteration. It re-engages once other
    # tropisms tilt the direction off-vertical.
    cd = np.asarray(current_direction, dtype=np.float64)
    cd_norm = float(np.linalg.norm(cd))
    if w_plagio > 0.0 and cd_norm > 1e-12:
        cd_unit = cd / cd_norm
        vertical_component = float(np.dot(cd_unit, _UP))
        if abs(vertical_component) < 0.99:
            v_plagio = cd_unit - vertical_component * _UP
            n_plagio = float(np.linalg.norm(v_plagio))
            if n_plagio > 1e-12:
                v_plagio = v_plagio / n_plagio
            else:
                v_plagio = np.zeros(3)
        else:
            v_plagio = np.zeros(3)
    else:
        v_plagio = np.zeros(3)

    blend = (
        cfg.w_perception * v_perception
        + (w_ortho * decay) * _UP
        + (w_gravi * decay) * _DOWN
        + (w_plagio * decay) * v_plagio
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
