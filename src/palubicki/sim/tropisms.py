# src/palubicki/sim/tropisms.py
from __future__ import annotations

import math

import numpy as np

from palubicki.config import TropismConfig

_UP = np.array([0.0, 1.0, 0.0])
_DOWN = np.array([0.0, -1.0, 0.0])


def spray_plane_normal_from_direction(direction: np.ndarray) -> np.ndarray | None:
    """Normal of the spray plane that contains ``direction`` and is as horizontal
    as possible (#55).

    The plane is spanned by ``direction`` and the horizontal axis perpendicular to
    it; its normal is the component of world-up perpendicular to ``direction``
    (renormalized). For a horizontal direction this returns world-up, so the spray
    plane is the ground plane and laterals fan out flat. Returns ``None`` when
    ``direction`` is degenerate or near-vertical (no well-defined horizontal-ish
    plane — e.g. the trunk), in which case callers fall back to legacy behaviour.
    """
    d = np.asarray(direction, dtype=np.float64)
    dn = float(np.linalg.norm(d))
    if dn < 1e-12:
        return None
    d = d / dn
    n = _UP - float(np.dot(_UP, d)) * d
    nn = float(np.linalg.norm(n))
    if nn < 1e-6:  # direction ~vertical: world-up has no perpendicular component
        return None
    return n / nn


def growth_direction(
    *,
    v_perception: np.ndarray,
    current_direction: np.ndarray,
    cfg: TropismConfig,
    is_main_axis: bool,
    light_gradient: np.ndarray | None = None,
    axis_order: int = 0,
    branch_age_years: float = 0.0,
    spray_plane_normal: np.ndarray | None = None,
) -> np.ndarray:
    """Blend perception + orthotropy (UP) + gravitropy (DOWN) + photo + inertia.

    ``is_main_axis`` selects between main-axis weights (e.g. w_orthotropy_main)
    and lateral-axis weights. Each tropism weight at order k is multiplied by
    ``cfg.axis_decay**k``.

    ``spray_plane_normal`` (#55): when provided, plagiotropism projects
    ``current_direction`` onto the parent axis's spray plane (normal =
    ``spray_plane_normal``) instead of the world-XY plane, and its weight is NOT
    decayed by ``axis_decay`` — so order-2+ branchlets flatten into the parent's
    frond at least as hard as order-1. ``None`` => legacy world-XY projection with
    the usual order decay (bit-identical to pre-#55 behaviour).
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

    # Plagiotropism: project current_direction onto the spray plane (normal
    # ``plane_normal``). Legacy/default target is the world-XY plane (normal = UP);
    # with a parent spray-plane normal (#55) the target is the parent's frond plane.
    # If current_direction is near-parallel to the plane normal (|dot| >= 0.99) the
    # projection is ambiguous; skip the term this iteration. It re-engages once
    # other tropisms tilt the direction off-normal.
    if spray_plane_normal is None:
        plane_normal = _UP
        plagio_decay = decay
    else:
        plane_normal = np.asarray(spray_plane_normal, dtype=np.float64)
        pnn = float(np.linalg.norm(plane_normal))
        plane_normal = plane_normal / pnn if pnn > 1e-12 else _UP
        # In-plane flattening is the whole point of the spray frame; do not let
        # axis_decay weaken it at higher orders (else order-2 climbs out of plane).
        plagio_decay = 1.0
    cd = np.asarray(current_direction, dtype=np.float64)
    cd_norm = float(np.linalg.norm(cd))
    if w_plagio > 0.0 and cd_norm > 1e-12:
        cd_unit = cd / cd_norm
        normal_component = float(np.dot(cd_unit, plane_normal))
        if abs(normal_component) < 0.99:
            v_plagio = cd_unit - normal_component * plane_normal
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
        + (w_plagio * plagio_decay) * v_plagio
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
