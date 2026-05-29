from __future__ import annotations

from dataclasses import dataclass

import numpy as np

RGB = tuple[float, float, float]


@dataclass(frozen=True)
class BarkBlendStops:
    """Three-stop diameter->color gradient for bark tinting.

    Requires d_young <= d_mature <= d_senescent. Equal adjacent stops collapse
    that segment without dividing by zero (the lower color wins at the boundary).
    """
    d_young: float
    d_mature: float
    d_senescent: float
    c_young: RGB
    c_mature: RGB
    c_senescent: RGB


def _lerp_segment(
    d: np.ndarray, lo: float, hi: float, c_lo: np.ndarray, c_hi: np.ndarray
) -> np.ndarray:
    """Per-element lerp of c_lo->c_hi by (d-lo)/(hi-lo), clamped to [0,1].
    Degenerate lo==hi yields t=0 (c_lo)."""
    span = hi - lo
    if span <= 0.0:
        t = np.zeros_like(d)
    else:
        t = np.clip((d - lo) / span, 0.0, 1.0)
    return c_lo[None, :] + t[:, None] * (c_hi - c_lo)[None, :]


def bark_tint(diameter: np.ndarray, stops: BarkBlendStops) -> np.ndarray:
    """Map per-vertex diameter to (N, 3) float32 RGB via a 3-stop gradient.

    d <= d_young            -> c_young
    d_young..d_mature       -> lerp c_young -> c_mature
    d_mature..d_senescent   -> lerp c_mature -> c_senescent
    d >= d_senescent        -> c_senescent
    """
    d = np.asarray(diameter, dtype=np.float64).reshape(-1)
    c_young = np.asarray(stops.c_young, dtype=np.float64)
    c_mature = np.asarray(stops.c_mature, dtype=np.float64)
    c_senescent = np.asarray(stops.c_senescent, dtype=np.float64)

    lower = _lerp_segment(d, stops.d_young, stops.d_mature, c_young, c_mature)
    upper = _lerp_segment(d, stops.d_mature, stops.d_senescent, c_mature, c_senescent)

    use_upper = (d >= stops.d_mature)[:, None]
    out = np.where(use_upper, upper, lower)
    return out.astype(np.float32)
