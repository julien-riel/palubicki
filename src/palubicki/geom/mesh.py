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
    positions: np.ndarray  # (V, 3) float32
    normals: np.ndarray    # (V, 3) float32
    uvs: np.ndarray        # (V, 2) float32
    indices: np.ndarray    # (M,)   uint32
    material: Material


@dataclass
class Mesh:
    primitives: list[Primitive]
