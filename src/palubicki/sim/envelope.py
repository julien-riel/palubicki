# src/palubicki/sim/envelope.py
from __future__ import annotations

import numpy as np

from palubicki.config import EnvelopeConfig


def sample_markers(cfg: EnvelopeConfig, rng: np.random.Generator) -> np.ndarray:
    """Return (N, 3) array of marker positions inside the envelope."""
    n = cfg.marker_count
    if cfg.shape == "sphere":
        pts = _sample_unit_ball(rng, n) * cfg.rx
    elif cfg.shape == "ellipsoid":
        unit = _sample_unit_ball(rng, n)
        pts = unit * np.array([cfg.rx, cfg.ry, cfg.rz])
    elif cfg.shape == "half_ellipsoid":
        unit = _sample_unit_ball(rng, n)
        unit[:, 1] = np.abs(unit[:, 1])
        pts = unit * np.array([cfg.rx, cfg.ry, cfg.rz])
    elif cfg.shape == "cone":
        pts = _sample_cone(rng, n, cfg.rx, cfg.ry, cfg.rz)
    else:
        raise ValueError(f"unknown envelope shape: {cfg.shape!r}")
    return pts + np.array(cfg.center)


def _sample_unit_ball(rng: np.random.Generator, n: int) -> np.ndarray:
    """Uniform sampling in the unit sphere via rejection."""
    out = np.empty((n, 3), dtype=np.float64)
    filled = 0
    while filled < n:
        batch = rng.uniform(-1.0, 1.0, size=(max(n - filled, 64) * 2, 3))
        inside = batch[np.einsum("ij,ij->i", batch, batch) <= 1.0]
        take = min(len(inside), n - filled)
        out[filled : filled + take] = inside[:take]
        filled += take
    return out


def _sample_cone(rng: np.random.Generator, n: int, rx: float, h: float, rz: float) -> np.ndarray:
    """Cone apex at (0, h, 0), base radius (rx, rz) at y=0. Inverse-CDF on y, then disk."""
    out = np.empty((n, 3), dtype=np.float64)
    filled = 0
    while filled < n:
        m = max(n - filled, 64) * 2
        u = rng.uniform(0.0, 1.0, size=m)
        y = h * (1.0 - np.cbrt(1.0 - u))
        radius_factor = 1.0 - y / h
        theta = rng.uniform(0.0, 2.0 * np.pi, size=m)
        r = np.sqrt(rng.uniform(0.0, 1.0, size=m))
        x = r * np.cos(theta) * rx * radius_factor
        z = r * np.sin(theta) * rz * radius_factor
        pts = np.column_stack([x, y, z])
        take = min(len(pts), n - filled)
        out[filled : filled + take] = pts[:take]
        filled += take
    return out
