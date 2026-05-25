# src/palubicki/sim/phyllotaxy.py
from __future__ import annotations

import math

import numpy as np

from palubicki.config import PhyllotaxyConfig


def lateral_bud_directions(
    growth_direction: np.ndarray,
    cfg: PhyllotaxyConfig,
    node_index: int,
) -> np.ndarray:
    """Return (K, 3) unit vectors for lateral bud directions at this node."""
    g = np.asarray(growth_direction, dtype=np.float64)
    g = g / np.linalg.norm(g)
    right, up = _frame_perpendicular_to(g)

    if cfg.mode == "alternate":
        k = 1
    elif cfg.mode == "opposite":
        k = 2
    elif cfg.mode == "whorled":
        k = max(1, cfg.whorl_count)
    else:
        raise ValueError(f"unknown phyllotaxy mode: {cfg.mode!r}")

    base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index
    branch_angle = math.radians(cfg.branch_angle_deg)
    cos_b = math.cos(branch_angle)
    sin_b = math.sin(branch_angle)

    out = np.empty((k, 3), dtype=np.float64)
    for i in range(k):
        az = base_azimuth + 2.0 * math.pi * i / k
        radial = math.cos(az) * right + math.sin(az) * up
        out[i] = cos_b * g + sin_b * radial
    return out


def _frame_perpendicular_to(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return any (right, up) orthonormal basis perpendicular to unit vector d."""
    canonical = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    right = canonical - np.dot(canonical, d) * d
    right = right / np.linalg.norm(right)
    up = np.cross(d, right)
    return right, up
