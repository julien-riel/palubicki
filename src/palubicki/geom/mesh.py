# src/palubicki/geom/mesh.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


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


@dataclass
class Mesh:
    primitives: list[Primitive]
