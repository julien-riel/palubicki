"""Tests for geom/leaf_blade3d.py — curved hero blade (export pipeline P2)."""
import numpy as np

from palubicki.geom.leaf_blade import build_blade
from palubicki.geom.leaf_blade3d import build_curved_blade, displace_blade, tangent_frame


def _flat_blade(shape="ovate", aspect=0.8):
    pos, _, uv, idx = build_blade(length=1.0, width=aspect, shape=shape, margin="entire")
    return pos, uv, idx, aspect


def test_zero_fold_curl_is_flat():
    pos, uv, idx, aspect = _flat_blade()
    z = displace_blade(pos, fold_deg=0.0, curl=0.0, aspect=aspect)
    assert np.allclose(z, 0.0)


def test_flat_blade_frame_is_canonical():
    """A flat blade's recomputed frame matches the legacy convention: N=+z, T=+x,
    handedness +1 — so enabling/​disabling the hero path can't flip shading."""
    pos, uv, idx, aspect = _flat_blade()
    pos3d, normals, tangents = build_curved_blade(pos, uv, idx, fold_deg=0.0, curl=0.0, aspect=aspect)
    assert np.allclose(pos3d[:, 2], 0.0)
    assert np.allclose(normals, np.array([0.0, 0.0, 1.0]), atol=1e-5)
    assert np.allclose(tangents[:, :3], np.array([1.0, 0.0, 0.0]), atol=1e-5)
    assert np.allclose(tangents[:, 3], 1.0)


def test_fold_lifts_lamina_off_midrib():
    """The midrib keel lifts the lamina out of plane proportional to |u|, leaving
    the midrib column (u≈0) on the plane."""
    pos, uv, idx, aspect = _flat_blade()
    z = displace_blade(pos, fold_deg=25.0, curl=0.0, aspect=aspect)
    u = pos[:, 0]
    near_midrib = np.abs(u) < 0.02
    off_midrib = np.abs(u) > 0.2 * aspect
    assert np.all(z[near_midrib] < 1e-3)
    assert z[off_midrib].max() > 0.02  # lamina clearly raised


def test_curl_recurves_tip_below_base():
    pos, uv, idx, aspect = _flat_blade()
    z = displace_blade(pos, fold_deg=0.0, curl=0.3, aspect=aspect)
    v = pos[:, 1]
    base = z[v < 0.05]
    tip = z[v > 0.9]
    assert tip.mean() < base.mean()  # tip dips below the base plane
    assert tip.min() < -0.05


def test_curved_footprint_preserved():
    """Displacement only adds z — the projected (u, v) footprint is untouched, so
    leaf_area_records (light grid) never drifts when the hero blade is enabled."""
    pos, uv, idx, aspect = _flat_blade()
    pos3d, _, _ = build_curved_blade(pos, uv, idx, fold_deg=20.0, curl=0.2, aspect=aspect)
    assert np.allclose(pos3d[:, :2], pos[:, :2])


def test_curved_tangent_frame_orthonormal():
    pos, uv, idx, aspect = _flat_blade()
    _, normals, tangents = build_curved_blade(pos, uv, idx, fold_deg=20.0, curl=0.15, aspect=aspect)
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0, atol=1e-4)
    assert np.allclose(np.linalg.norm(tangents[:, :3], axis=1), 1.0, atol=1e-4)
    # Tangent ⟂ normal (NormalTangentMirrorTest health) and handedness is ±1.
    dots = np.sum(normals * tangents[:, :3], axis=1)
    assert np.max(np.abs(dots)) < 1e-3
    assert np.all(np.isin(np.round(tangents[:, 3]), (-1.0, 1.0)))


def test_tangent_frame_flat_winding_faces_up():
    """A hand-built CCW quad in the (u,v) plane recomputes N=+z (matching the fan
    winding's front face)."""
    pos = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64)
    uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
    idx = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
    normals, tangents = tangent_frame(pos, uv, idx)
    assert np.allclose(normals, np.array([0.0, 0.0, 1.0]), atol=1e-6)
    assert np.allclose(tangents[:, 3], 1.0)
