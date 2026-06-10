# src/palubicki/sim/phyllotaxy.py
from __future__ import annotations

import math

import numpy as np

from palubicki.config import PhyllotaxyConfig
from palubicki.sim._vec3 import cross3, norm3

# Salt for SeedSequence to namespace phyllotaxy jitter independently of other
# RNG consumers (light_perception, internode_length jitter).
_PHYLLO_SALT = int.from_bytes(b"phyl", "big")

# Distinct salt so reserve jitter does not collide with lateral jitter for the
# same (seed, node_index).
_RESERVE_SALT = int.from_bytes(b"rsrv", "big")


def _base_azimuth(
    cfg: PhyllotaxyConfig, node_index: int, axis_order: int, effective_mode: str
) -> float:
    """Mode-dependent deterministic seating azimuth (radians) for one node.

    Shared by ``lateral_bud_directions``, ``leaf_azimuths`` and
    ``reserve_bud_directions`` so laterals, leaves and reserves all derive from
    the SAME per-mode base (FIX #2). Decussate/whorled use a pure inter-node
    half-spacing toggle WITHOUT a divergence*node_index spiral term (FIX H): the
    additive spiral corrupts the intended 90deg / 180deg-over-k structure when
    ``divergence_angle_deg`` != 0 (the config default is 137.5). Distichous is a
    fixed 180deg flip per node; alternate/opposite spiral by divergence*node_index.

    ``effective_mode`` is the mode AFTER the distichous_on_plagiotropic promotion
    (callers resolve it). Pure scalar: no jitter (callers add jitter themselves).
    """
    if effective_mode == "decussate":
        return (math.pi / 2.0) * (node_index % 2)
    if effective_mode == "whorled":
        k = max(1, cfg.whorl_count)
        return (math.pi / k) * (node_index % 2)
    if effective_mode == "distichous":
        # Fixed 180° flip per node; divergence_angle_deg is ignored here.
        return math.pi * node_index
    # alternate / opposite -> simple spiral progression
    return math.radians(cfg.divergence_angle_deg) * node_index


def lateral_bud_directions(
    growth_direction: np.ndarray,
    cfg: PhyllotaxyConfig,
    node_index: int,
    *,
    seed: int,
    axis_order: int,
    spray_plane_normal: np.ndarray | None = None,
) -> np.ndarray:
    """Return (K, 3) unit vectors for lateral bud directions at this node.

    The insertion angle is looked up from ``cfg.branch_angle_by_order`` using
    ``axis_order`` (clamped to the last entry if it exceeds the list). Jitter
    on divergence and branch angle is gaussian, deterministic per
    (seed, node_index). The branch angle is hard-clamped to [0deg, 90deg]
    after jitter.

    ``spray_plane_normal`` (#55): when provided, the radial insertion basis is
    aligned to the parent axis's spray plane (azimuth 0/pi splay WITHIN the plane,
    pi/2 splays out of it) so laterals fan into a coherent frond instead of an
    arbitrary perpendicular frame. ``None`` => legacy arbitrary basis.
    """
    g = np.asarray(growth_direction, dtype=np.float64)
    g = g / norm3(g)
    right, up = _insertion_frame(g, spray_plane_normal)

    # Effective mode: the flag promotes lateral axes (axis_order > 0) to
    # distichous regardless of cfg.mode.
    if cfg.distichous_on_plagiotropic and axis_order > 0:
        effective_mode = "distichous"
    else:
        effective_mode = cfg.mode

    if effective_mode == "alternate":
        k = 1
    elif effective_mode == "opposite":
        k = 2
    elif effective_mode == "whorled":
        k = max(1, cfg.whorl_count)
    elif effective_mode == "decussate":
        k = 2
    elif effective_mode == "distichous":
        k = 1
    else:
        raise ValueError(f"unknown phyllotaxy mode: {effective_mode!r}")

    angles = cfg.branch_angle_by_order
    idx = min(int(axis_order), len(angles) - 1)

    base_azimuth = _base_azimuth(cfg, node_index, axis_order, effective_mode)

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


def leaf_azimuths(
    cfg: PhyllotaxyConfig,
    node_index: int,
    *,
    axis_order: int,
    count: int,
) -> list[float]:
    """Phyllotactic seating azimuths (radians) for ``count`` leaves at one node.

    Replicates the per-axis ``base_azimuth`` progression of
    ``lateral_bud_directions`` (so leaves spiral correctly along each axis via the
    #24 ordinal), then fans ``count`` members evenly ``2*pi/count`` apart. Pure
    scalar: the renderer turns (azimuth, render-time stem direction, leaf_splay_deg)
    into blade geometry, keeping the splay area-shear in one place.

    NOTE: the deterministic base azimuth comes from the SHARED ``_base_azimuth``
    helper (same per-mode progression as ``lateral_bud_directions`` /
    ``reserve_bud_directions``), but NOT the jitter: leaves intentionally omit the
    ``divergence_jitter_deg`` / RNG salting that ``lateral_bud_directions`` applies,
    so leaf seating stays pure and deterministic. Do not "sync" jitter in.

    Expects ``count >= 1`` (callers gate on ``leaf_cluster_count > 0``); ``count == 0`` returns ``[]``.
    """
    if cfg.distichous_on_plagiotropic and axis_order > 0:
        mode = "distichous"
    else:
        mode = cfg.mode

    base_azimuth = _base_azimuth(cfg, node_index, axis_order, mode)

    return [base_azimuth + 2.0 * math.pi * i / count for i in range(count)]


def reserve_bud_directions(
    growth_direction: np.ndarray,
    cfg: PhyllotaxyConfig,
    node_index: int,
    *,
    seed: int,
    count: int,
    axis_order: int = 0,
    spray_plane_normal: np.ndarray | None = None,
) -> np.ndarray:
    """Return (count, 3) unit vectors for RESERVE bud directions at this node.

    Reserves are placed on the AZIMUTH HALF-PLANE OPPOSITE to the laterals
    (shared per-mode ``_base_azimuth`` + pi, so reserves stay opposite the
    laterals on decussate/whorled/distichous nodes too — FIX #2) and at a TIGHTER
    branch angle (half the lateral branch_angle for this ``axis_order``, capped at
    30°) so the activated bud emerges in a direction complementary to the lost
    lateral subtree. Jitter is half of lateral jitter.

    ``spray_plane_normal`` (#55): aligns the radial basis to the parent axis's
    spray plane, exactly as ``lateral_bud_directions`` does, so a reactivated
    reserve emerges in the same frond plane. ``None`` => legacy arbitrary basis.

    If ``count == 0`` returns a (0, 3) empty array.
    """
    if count <= 0:
        return np.empty((0, 3), dtype=np.float64)
    g = np.asarray(growth_direction, dtype=np.float64)
    g = g / norm3(g)
    right, up = _insertion_frame(g, spray_plane_normal)

    # Mirror the lateral effective-mode promotion so reserves use the same
    # per-mode base (then offset by pi to sit opposite the laterals).
    if cfg.distichous_on_plagiotropic and axis_order > 0:
        effective_mode = "distichous"
    else:
        effective_mode = cfg.mode

    base_azimuth = _base_azimuth(cfg, node_index, axis_order, effective_mode) + math.pi
    angles = cfg.branch_angle_by_order
    idx = min(int(axis_order), len(angles) - 1)
    branch_angle = min(math.radians(30.0), math.radians(angles[idx]) * 0.5)

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
    right = right / norm3(right)
    up = cross3(d, right)
    return right, up


def _insertion_frame(
    g: np.ndarray, spray_plane_normal: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray]:
    """Radial (right, up) basis perpendicular to axis direction ``g`` (#55).

    Without a spray-plane normal this is the legacy arbitrary perpendicular basis.
    With one, ``right`` is the in-plane radial (``g × n``) and ``up`` is the
    out-of-plane axis (``n`` made perpendicular to ``g``), so azimuth 0/pi place
    laterals WITHIN the parent's spray plane and pi/2 tilts them out of it.
    Falls back to the arbitrary basis if ``g`` is (near-)parallel to ``n``.
    """
    if spray_plane_normal is None:
        return _frame_perpendicular_to(g)
    n = np.asarray(spray_plane_normal, dtype=np.float64)
    nn = norm3(n)
    if nn < 1e-12:
        return _frame_perpendicular_to(g)
    n = n / nn
    right = cross3(g, n)
    rn = norm3(right)
    if rn < 1e-6:  # axis parallel to plane normal: no in-plane radial defined
        return _frame_perpendicular_to(g)
    right = right / rn
    up = n - float(np.dot(n, g)) * g
    un = norm3(up)
    up = up / un if un > 1e-12 else cross3(right, g)
    return right, up
