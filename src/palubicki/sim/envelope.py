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


def points_inside(cfg: EnvelopeConfig, pts: np.ndarray) -> np.ndarray:
    """Boolean mask: which of ``pts`` (N, 3) lie inside the translated envelope ``cfg``.

    The inequalities mirror ``sample_markers`` exactly (with a tiny epsilon to absorb
    float round-trips through scale + translate), so a marker is always counted as
    inside the envelope that sampled it. Used to flatten the marker density of
    overlapping envelopes to a uniform union (see ``forest.build_forest``)."""
    pts = np.asarray(pts, dtype=np.float64)
    if len(pts) == 0:
        return np.zeros(0, dtype=bool)
    d = pts - np.asarray(cfg.center, dtype=np.float64)
    eps = 1e-9
    if cfg.shape == "sphere":
        return np.einsum("ij,ij->i", d, d) <= (cfg.rx * cfg.rx) * (1.0 + eps)
    if cfg.shape in ("ellipsoid", "half_ellipsoid"):
        r = np.array([cfg.rx, cfg.ry, cfg.rz], dtype=np.float64)
        inside = np.einsum("ij,ij->i", d / r, d / r) <= 1.0 + eps
        if cfg.shape == "half_ellipsoid":
            inside &= d[:, 1] >= -eps
        return inside
    if cfg.shape == "cone":
        dy = d[:, 1]
        rf = 1.0 - dy / cfg.ry
        in_height = (dy >= -eps) & (dy <= cfg.ry + eps)
        safe_rf = np.where(rf > eps, rf, np.inf)  # apex: radial must be ~0 → big denom
        rx = cfg.rx * safe_rf
        rz = cfg.rz * safe_rf
        radial = (d[:, 0] / rx) ** 2 + (d[:, 2] / rz) ** 2
        return in_height & (radial <= 1.0 + eps)
    raise ValueError(f"unknown envelope shape: {cfg.shape!r}")


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
