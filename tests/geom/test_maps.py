"""Tests for geom/maps.py — PBR map synthesis (export pipeline P2)."""
import io

import numpy as np
from PIL import Image

from palubicki.geom import maps


def _png_to_array(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)))


def test_flat_height_is_facing_normal():
    """A flat height field encodes the +Z tangent-space normal everywhere:
    (128, 128, 255) ≈ (0, 0, 1) after 2·rgb-1."""
    arr = _png_to_array(maps.height_to_normal_png(np.full((16, 16), 0.5)))
    assert arr.shape == (16, 16, 3)
    assert np.all(np.abs(arr[..., 0].astype(int) - 128) <= 1)
    assert np.all(np.abs(arr[..., 1].astype(int) - 128) <= 1)
    assert np.all(arr[..., 2] >= 250)  # Z ≈ +1


def test_normal_ridge_not_groove():
    """A height field ramping *up* toward +u tilts the normal toward -u (R<128):
    the (-) sign in N=normalize(-dh/du,-dh/dv,1) keeps relief reading as a ridge,
    not an inverted groove (design D9)."""
    h = np.tile(np.linspace(0.0, 1.0, 32)[None, :], (32, 1))  # rises with column/u
    arr = _png_to_array(maps.height_to_normal_png(h, strength=2.0, wrap_x=False))
    interior = arr[8:24, 8:24]
    assert interior[..., 0].mean() < 120     # Nx < 0  → leans away from the rising slope
    assert abs(interior[..., 1].mean() - 128) <= 3  # no v gradient → G ≈ 128
    assert interior[..., 2].mean() > 140     # still mostly facing +Z


def test_flip_y_inverts_green_only():
    h = np.tile(np.linspace(0.0, 1.0, 16)[None, :].T, (1, 16))  # rises with row/v
    og = _png_to_array(maps.height_to_normal_png(h, strength=2.0, wrap_y=False))
    dx = _png_to_array(maps.height_to_normal_png(h, strength=2.0, wrap_y=False, flip_y=True))
    # Green (Y) flips about 128; red/blue unchanged.
    assert np.allclose(og[..., 0], dx[..., 0])
    assert np.allclose(255 - og[..., 1], dx[..., 1], atol=1)
    assert np.allclose(og[..., 2], dx[..., 2])


def test_pack_orm_channel_assignment():
    occ = np.full((8, 8), 0.25)
    rough = np.full((8, 8), 0.50)
    metal = np.full((8, 8), 0.75)
    arr = _png_to_array(maps.pack_orm_png(occ, rough, metal))
    assert abs(int(arr[..., 0].mean()) - round(0.25 * 255)) <= 1  # O → R
    assert abs(int(arr[..., 1].mean()) - round(0.50 * 255)) <= 1  # Rough → G
    assert abs(int(arr[..., 2].mean()) - round(0.75 * 255)) <= 1  # Metal → B


def test_pack_orm_scalar_broadcast():
    arr = _png_to_array(maps.pack_orm_png(1.0, 0.4, np.zeros((4, 4))))
    assert arr.shape == (4, 4, 3)
    assert arr[..., 0].min() == 255 and arr[..., 2].max() == 0


def test_occlusion_darkens_furrows():
    """A furrow (a dark groove) self-occludes (occ < 1) while a flat plateau stays lit."""
    h = np.ones((32, 32))
    h[:, 14:18] = 0.0  # a vertical groove
    occ = maps.occlusion_from_height(h, strength=1.0)
    assert occ[:, 15].mean() < occ[:, 0].mean()
    assert occ.max() <= 1.0 + 1e-6 and occ.min() >= 0.0


def test_translucency_alpha_carries_mask():
    mask = np.linspace(0.0, 1.0, 16)[None, :].repeat(16, axis=0)
    arr = _png_to_array(maps.translucency_png(mask, color=(0.4, 0.6, 0.2)))
    assert arr.shape == (16, 16, 4)
    # Alpha tracks the lamina mask (0 over veins → ~1 over lamina).
    assert arr[0, 0, 3] < 10 and arr[0, -1, 3] > 245
    assert abs(int(arr[..., 1].mean()) - round(0.6 * 255)) <= 1  # RGB = tint
