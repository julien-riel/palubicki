# src/palubicki/geom/mesh.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass(frozen=True)
class TextureTransform:
    """``KHR_texture_transform`` window applied to every texture of a material
    (atlas placement, design D8). ``offset``/``scale`` are in UV units, ``rotation``
    in radians CCW. Identity (the default) is never emitted."""
    offset: tuple[float, float] = (0.0, 0.0)
    scale: tuple[float, float] = (1.0, 1.0)
    rotation: float = 0.0

    def is_identity(self) -> bool:
        return (self.offset == (0.0, 0.0) and self.scale == (1.0, 1.0)
                and self.rotation == 0.0)


@dataclass
class Material:
    name: str
    base_color: tuple[float, float, float, float]
    metallic: float
    roughness: float
    base_color_texture_png: bytes | None
    alpha_mode: Literal["OPAQUE", "MASK", "BLEND"]
    alpha_cutoff: float
    double_sided: bool
    # ── PBR texture maps (export pipeline P2, geom/maps.py). Every map below is
    #    LINEAR data and rides a linear glTF slot; only base_color/emissive are
    #    sRGB (design D9). glTF tags colour space by *slot*, not per image, so
    #    correctness == emitting each map into the right slot. ──
    # Tangent-space normal map (OpenGL +Y); strength via normalTexture.scale.
    normal_texture_png: bytes | None = None
    normal_scale: float = 1.0
    # ORM packed occlusion→R / roughness→G / metal→B: one image feeds BOTH the
    # metallicRoughnessTexture (G,B) and occlusionTexture (R) slots.
    orm_texture_png: bytes | None = None
    occlusion_strength: float = 1.0
    emissive_texture_png: bytes | None = None
    emissive_factor: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # Leaf back-light: white-lamina / dark-vein mask in the alpha channel. Emitted
    # via KHR_materials_diffuse_transmission (forward-looking metadata — RC,
    # engine-ignored in 2026, design D1) + read by per-engine subsurface paths.
    transmission_texture_png: bytes | None = None
    diffuse_transmission_factor: float = 0.0
    diffuse_transmission_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    # KHR_materials_specular cuticle/dielectric specular strength; None = omit.
    specular_factor: float | None = None
    # KHR_texture_transform atlas window for all this material's textures; None
    # (or identity) emits nothing.
    texture_transform: TextureTransform | None = None


@dataclass
class Primitive:
    positions: np.ndarray  # (V, 3) float32   POSITION
    normals: np.ndarray    # (V, 3) float32   NORMAL
    uvs: np.ndarray        # (V, 2) float32   TEXCOORD_0
    indices: np.ndarray    # (M,)   uint32
    material: Material
    # ── Wind authoring + look attributes (export pipeline P1, geom/wind.py). ──
    # All ride portable COLOR_n / TEXCOORD_n channels (never `_underscore`, which
    # three.js / Unity drop). None on any field = that channel is omitted.
    tint: np.ndarray | None = None       # (V, 3) f32  COLOR_1 — autumn / bark age tint
    wind: np.ndarray | None = None       # (V, 3) f32  COLOR_0 — (phase, stiffness, leafMask)
    pivot: np.ndarray | None = None      # (V, 3) f32  branch pivot (a position; localized with POSITION)
    wind_tier: np.ndarray | None = None  # (V,)  f32  per-vertex tier {0,1,2}
    tangents: np.ndarray | None = None   # (V, 4) f32  TANGENT (xyz + MikkTSpace handedness w)
    # pivot + wind_tier are packed at export into TEXCOORD_1=(pivot.x,pivot.y),
    # TEXCOORD_2=(pivot.z, wind_tier) — glTF restricts TEXCOORD accessors to VEC2.
    # ── Seasons (export pipeline P2): KHR_materials_variants alternative materials,
    #    (variant_name, Material) per season, sharing this primitive's geometry. The
    #    default `material` stays the fallback for variant-unaware viewers. None = no
    #    variants emitted (byte-identical to a single-material primitive). ──
    material_variants: list[tuple[str, Material]] | None = None


@dataclass
class Mesh:
    primitives: list[Primitive]
