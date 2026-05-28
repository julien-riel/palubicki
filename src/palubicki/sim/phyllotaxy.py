# src/palubicki/sim/phyllotaxy.py
from __future__ import annotations

import math

import numpy as np

from palubicki.config import PhyllotaxyConfig


# Salt for SeedSequence to namespace phyllotaxy jitter independently of other
# RNG consumers (light_perception, internode_length jitter).
_PHYLLO_SALT = int.from_bytes(b"phyl", "big")

# Distinct salt so reserve jitter does not collide with lateral jitter for the
# same (seed, node_index).
_RESERVE_SALT = int.from_bytes(b"rsrv", "big")


def lateral_bud_directions(
    growth_direction: np.ndarray,
    cfg: PhyllotaxyConfig,
    node_index: int,
    *,
    seed: int,
    axis_order: int,
) -> np.ndarray:
    """Return (K, 3) unit vectors for lateral bud directions at this node.

    The insertion angle is looked up from ``cfg.branch_angle_by_order`` using
    ``axis_order`` (clamped to the last entry if it exceeds the list). Jitter
    on divergence and branch angle is gaussian, deterministic per
    (seed, node_index). The branch angle is hard-clamped to [0deg, 90deg]
    after jitter.
    """
    g = np.asarray(growth_direction, dtype=np.float64)
    g = g / np.linalg.norm(g)
    right, up = _frame_perpendicular_to(g)

    if cfg.mode == "alternate":
        k = 1
    elif cfg.mode == "opposite":
        k = 2
    elif cfg.mode == "whorled":
        k = max(1, cfg.whorl_count)
    elif cfg.mode == "decussate":
        k = 2
    else:
        raise ValueError(f"unknown phyllotaxy mode: {cfg.mode!r}")

    angles = cfg.branch_angle_by_order
    idx = min(int(axis_order), len(angles) - 1)

    if cfg.mode == "decussate":
        base_azimuth = (
            math.radians(cfg.divergence_angle_deg) * node_index
            + (math.pi / 2.0) * (node_index % 2)
        )
    else:
        base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index

    branch_angle = math.radians(angles[idx])

    if cfg.divergence_jitter_deg > 0 or cfg.branch_angle_jitter_deg > 0:
        ss = np.random.SeedSequence([seed, _PHYLLO_SALT, node_index])
        rng = np.random.default_rng(ss.generate_state(1)[0])
        if cfg.divergence_jitter_deg > 0:
            base_azimuth += math.radians(rng.normal(0.0, cfg.divergence_jitter_deg))
        if cfg.branch_angle_jitter_deg > 0:
            branch_angle += math.radians(rng.normal(0.0, cfg.branch_angle_jitter_deg))
            branch_angle = max(0.0, min(math.pi / 2, branch_angle))

    cos_b = math.cos(branch_angle)
    sin_b = math.sin(branch_angle)

    out = np.empty((k, 3), dtype=np.float64)
    for i in range(k):
        az = base_azimuth + 2.0 * math.pi * i / k
        radial = math.cos(az) * right + math.sin(az) * up
        out[i] = cos_b * g + sin_b * radial
    return out


def reserve_bud_directions(
    growth_direction: np.ndarray,
    cfg: PhyllotaxyConfig,
    node_index: int,
    *,
    seed: int,
    count: int,
) -> np.ndarray:
    """Return (count, 3) unit vectors for RESERVE bud directions at this node.

    Reserves are placed on the AZIMUTH HALF-PLANE OPPOSITE to the laterals
    (base_azimuth + pi) and at a TIGHTER branch angle (half the lateral
    branch_angle, capped at 30°) so the activated bud emerges in a direction
    complementary to the lost lateral subtree. Jitter is half of lateral jitter.

    If ``count == 0`` returns a (0, 3) empty array.
    """
    if count <= 0:
        return np.empty((0, 3), dtype=np.float64)
    g = np.asarray(growth_direction, dtype=np.float64)
    g = g / np.linalg.norm(g)
    right, up = _frame_perpendicular_to(g)

    base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index + math.pi
    branch_angle = min(math.radians(30.0), math.radians(cfg.branch_angle_by_order[0]) * 0.5)

    div_jitter = cfg.divergence_jitter_deg * 0.5
    ang_jitter = cfg.branch_angle_jitter_deg * 0.5
    if div_jitter > 0 or ang_jitter > 0:
        ss = np.random.SeedSequence([seed, _RESERVE_SALT, node_index])
        rng = np.random.default_rng(ss.generate_state(1)[0])
        if div_jitter > 0:
            base_azimuth += math.radians(rng.normal(0.0, div_jitter))
        if ang_jitter > 0:
            branch_angle += math.radians(rng.normal(0.0, ang_jitter))
            branch_angle = max(0.0, min(math.pi / 2, branch_angle))

    cos_b = math.cos(branch_angle)
    sin_b = math.sin(branch_angle)

    out = np.empty((count, 3), dtype=np.float64)
    for i in range(count):
        az = base_azimuth + 2.0 * math.pi * i / count
        radial = math.cos(az) * right + math.sin(az) * up
        out[i] = cos_b * g + sin_b * radial
    return out


# Keep in sync with sim/diagnostics.py:_frame_perpendicular_to (duplicated
# for in-plane basis consistency with the diagnostics harness).
def _frame_perpendicular_to(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return any (right, up) orthonormal basis perpendicular to unit vector d."""
    canonical = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    right = canonical - np.dot(canonical, d) * d
    right = right / np.linalg.norm(right)
    up = np.cross(d, right)
    return right, up
