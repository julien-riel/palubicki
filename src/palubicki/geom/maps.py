# src/palubicki/geom/maps.py
"""PBR map synthesis for the photoreal master (export pipeline P2, design §6.3).

Bakes the texture maps a standard glTF 2.0 metallic-roughness material needs
*beyond* base colour, from **clean** procedural source fields (never from a lit
photo — design §6.3: "Sobel/Scharr, jamais depuis une photo éclairée"):

- :func:`height_to_normal_png` — tangent-space normal map from a height field via
  Sobel, ``N = normalize(-strength·dh/du, -strength·dh/dv, 1)`` encoded
  OpenGL-style (+Y up, green **not** flipped — the glTF 2.0 §3.9.3 convention).
  The leading ``(-)`` keeps crests reading as ridges, not grooves (design D9);
  ``strength`` is the bump depth (mirrored at runtime by ``normalTexture.scale``).
- :func:`pack_orm_png` — occlusion→R, roughness→G, metal→B, the de-facto ORM
  packing whose single image feeds **both** ``occlusionTexture`` (R) and
  ``metallicRoughnessTexture`` (G, B). Linear data, never sRGB (design D9).
- :func:`occlusion_from_height` — cheap cavity AO so furrow bottoms self-shadow;
  fed into the ORM ``O`` channel (NOT baked into baseColor — design §6.3 warns
  the double-darkening that produces).
- :func:`translucency_png` — the leaf back-light mask: white lamina, dark
  veins / midrib / petiole base, carried in the **alpha** channel. Consumed by
  the per-engine subsurface paths (Unreal *Two-Sided Foliage*, Unity HDRP
  *Translucent*) and emitted forward as the
  ``KHR_materials_diffuse_transmission`` texture (RC, engine-ignored in 2026 —
  design correction #1).

Color management (design D9): only baseColor / emissive are sRGB; **everything
this module produces is linear** and must ride the linear texture slots. glTF
does not tag colour space per image — it is implied by the slot — so correctness
here means emitting these maps into ``normalTexture`` /
``metallicRoughnessTexture`` / ``occlusionTexture``, never ``baseColorTexture``.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image
from scipy import ndimage

# Sobel kernel weights sum to 8 in magnitude; dividing the convolution by 8
# turns it into a unit-spacing central-difference derivative estimate. The exact
# scale is absorbed by ``strength`` downstream, but normalising here keeps
# ``strength`` interpretable as "bump slope" rather than a kernel-dependent magic
# number.
_SOBEL_NORM = 8.0


def _field(x, shape: tuple[int, int] | None) -> np.ndarray:
    """Coerce a scalar or 2D array to a float64 ``(H, W)`` field.

    A scalar broadcasts to ``shape`` (which must then be given); an array is
    returned as float64 unchanged (and ``shape``, if given, is asserted)."""
    a = np.asarray(x, dtype=np.float64)
    if a.ndim == 0:
        if shape is None:
            raise ValueError("scalar field needs an explicit shape")
        return np.full(shape, float(a), dtype=np.float64)
    if a.ndim != 2:
        raise ValueError(f"field must be scalar or 2D, got ndim={a.ndim}")
    if shape is not None and a.shape != shape:
        raise ValueError(f"field shape {a.shape} != expected {shape}")
    return a


def _to_png(arr: np.ndarray, mode: str) -> bytes:
    """Encode a uint8 ``(H, W[, C])`` array as PNG bytes."""
    buf = io.BytesIO()
    Image.fromarray(arr, mode=mode).save(buf, format="PNG")
    return buf.getvalue()


def height_to_normal_png(
    height,
    *,
    strength: float = 1.0,
    wrap_x: bool = True,
    wrap_y: bool = True,
    flip_y: bool = False,
) -> bytes:
    """Tangent-space normal map (OpenGL +Y) PNG from a height field via Sobel.

    ``height`` is an ``(H, W)`` field (any scale; the gradient is what matters).
    ``strength`` scales the in-plane gradient → larger = deeper-looking relief.
    ``wrap_x`` / ``wrap_y`` use a wrapping Sobel so a horizontally- (and/or
    vertically-) tiling source produces a seamless normal map under a REPEAT
    sampler. ``flip_y`` inverts the green channel for a DirectX (-Y) target;
    the default (False) is the OpenGL +Y convention glTF mandates.

    Encoding: ``N = normalize(-strength·dh/du, -strength·dh/dv, 1)`` then
    ``rgb = N·0.5 + 0.5``. The ``(-)`` on the in-plane terms makes a local height
    *maximum* push its neighbouring normals *outward* (a ridge), not inward (a
    groove).
    """
    h = _field(height, None)
    mode_x = "wrap" if wrap_x else "nearest"
    mode_y = "wrap" if wrap_y else "nearest"
    # axis=1 is along columns (u / image-x); axis=0 along rows (v / image-y).
    gx = ndimage.sobel(h, axis=1, mode=mode_x) / _SOBEL_NORM
    gy = ndimage.sobel(h, axis=0, mode=mode_y) / _SOBEL_NORM
    nx = -strength * gx
    ny = -strength * gy
    if flip_y:
        ny = -ny
    nz = np.ones_like(h)
    inv_len = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    nx *= inv_len
    ny *= inv_len
    nz *= inv_len
    rgb = np.empty(h.shape + (3,), dtype=np.uint8)
    rgb[..., 0] = np.clip(np.rint((nx * 0.5 + 0.5) * 255.0), 0, 255)
    rgb[..., 1] = np.clip(np.rint((ny * 0.5 + 0.5) * 255.0), 0, 255)
    rgb[..., 2] = np.clip(np.rint((nz * 0.5 + 0.5) * 255.0), 0, 255)
    return _to_png(rgb, "RGB")


def occlusion_from_height(height, *, radius: int = 4, strength: float = 1.0) -> np.ndarray:
    """Cheap cavity ambient occlusion from a height field, in ``[0, 1]``.

    A texel sitting below its local mean is in a furrow and self-occludes:
    ``occ = 1 - strength·clamp(localmean - h, 0, 1)``. Crests stay at 1 (lit),
    furrow bottoms darken. Returned as a float field for :func:`pack_orm_png`'s
    ``O`` channel — never baked into baseColor (that double-darkens, design §6.3).
    """
    h = _field(height, None)
    span = float(h.max() - h.min())
    if span > 1e-9:
        h = (h - h.min()) / span  # normalise so ``strength`` reads consistently
    local = ndimage.uniform_filter(h, size=2 * radius + 1, mode="wrap")
    cavity = np.clip(local - h, 0.0, 1.0)
    return np.clip(1.0 - strength * cavity, 0.0, 1.0)


def pack_orm_png(occlusion, roughness, metallic, *, shape: tuple[int, int] | None = None) -> bytes:
    """Pack occlusion→R, roughness→G, metallic→B into one linear ORM PNG.

    Each argument is a scalar (broadcast to ``shape``) or an ``(H, W)`` field;
    at least one must be an array (or ``shape`` given) to fix the size. This is
    the glTF ORM convention: ``metallicRoughnessTexture`` reads G (roughness) and
    B (metallic); ``occlusionTexture`` reads R — so one image serves both slots.
    """
    if shape is None:
        for cand in (occlusion, roughness, metallic):
            a = np.asarray(cand)
            if a.ndim == 2:
                shape = a.shape
                break
    occ = np.clip(_field(occlusion, shape), 0.0, 1.0)
    rough = np.clip(_field(roughness, shape), 0.0, 1.0)
    met = np.clip(_field(metallic, shape), 0.0, 1.0)
    rgb = np.empty(occ.shape + (3,), dtype=np.uint8)
    rgb[..., 0] = np.rint(occ * 255.0)
    rgb[..., 1] = np.rint(rough * 255.0)
    rgb[..., 2] = np.rint(met * 255.0)
    return _to_png(rgb, "RGB")


def translucency_png(lamina_mask, *, color: tuple[float, float, float] = (0.5, 0.62, 0.22)) -> bytes:
    """Leaf back-light / thickness mask as an RGBA PNG.

    ``lamina_mask`` is an ``(H, W)`` field in ``[0, 1]``: 1 over thin translucent
    lamina, →0 over the opaque veins / midrib / petiole base. It is written to
    the **alpha** channel (the modulation the per-engine subsurface paths and
    ``KHR_materials_diffuse_transmission``'s ``diffuseTransmissionTexture`` both
    read); ``color`` fills RGB with the warm transmitted tint.
    """
    a = np.clip(_field(lamina_mask, None), 0.0, 1.0)
    rgba = np.empty(a.shape + (4,), dtype=np.uint8)
    rgba[..., 0] = round(color[0] * 255.0)
    rgba[..., 1] = round(color[1] * 255.0)
    rgba[..., 2] = round(color[2] * 255.0)
    rgba[..., 3] = np.rint(a * 255.0)
    return _to_png(rgba, "RGBA")
