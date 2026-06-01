# src/palubicki/export/_glb_common.py
"""Low-level glTF buffer/accessor/material builders shared by the single-tree
(`gltf.py`) and forest-instancing (`instancing.py`) export paths.

These were originally private helpers inside ``gltf.py``; they were lifted here
so the instancing path can reuse them without a circular import (``gltf.py``
re-exports ``write_glb_forest`` from ``instancing.py``)."""
from __future__ import annotations

import numpy as np
import pygltflib


class ExportError(RuntimeError):
    pass


_COMPONENT_FLOAT = pygltflib.FLOAT
_COMPONENT_UINT = pygltflib.UNSIGNED_INT
_TYPE_VEC3 = pygltflib.VEC3
_TYPE_VEC2 = pygltflib.VEC2
_TYPE_SCALAR = pygltflib.SCALAR

_TARGET_ARRAY = 34962           # ARRAY_BUFFER
_TARGET_ELEMENT_ARRAY = 34963   # ELEMENT_ARRAY_BUFFER


def _pad4(data: bytearray) -> None:
    while len(data) % 4 != 0:
        data.append(0)


def _add_accessor(
    buffer_data: bytearray,
    buffer_views: list,
    accessors: list,
    array: np.ndarray,
    component_type: int,
    type_str: str,
    target: int | None,
    *,
    with_minmax: bool,
) -> int:
    """Append ``array`` to the binary blob as a new accessor, returning its index.

    ``target`` is the bufferView target (ARRAY_BUFFER / ELEMENT_ARRAY_BUFFER) or
    ``None`` to omit it — the latter is required for ``EXT_mesh_gpu_instancing``
    instance attributes, whose bufferViews must not declare a target."""
    _pad4(buffer_data)
    offset = len(buffer_data)
    raw = array.tobytes()
    buffer_data.extend(raw)
    bv = pygltflib.BufferView(
        buffer=0, byteOffset=offset, byteLength=len(raw), target=target,
    )
    buffer_views.append(bv)
    bv_idx = len(buffer_views) - 1

    count = array.shape[0]
    kwargs = {"bufferView": bv_idx, "componentType": component_type, "count": count, "type": type_str}
    if with_minmax and array.size > 0:
        kwargs["min"] = array.min(axis=0).tolist()
        kwargs["max"] = array.max(axis=0).tolist()
    accessors.append(pygltflib.Accessor(**kwargs))
    return len(accessors) - 1


def _add_material(
    mat,
    buffer_data: bytearray,
    buffer_views: list,
    materials: list,
    textures: list,
    images: list,
    samplers: list,
    *,
    neutralize_base_color: bool = False,
) -> int:
    base_color = (1.0, 1.0, 1.0, 1.0) if neutralize_base_color else list(mat.base_color)
    pbr = pygltflib.PbrMetallicRoughness(
        baseColorFactor=list(base_color),
        metallicFactor=mat.metallic,
        roughnessFactor=mat.roughness,
    )
    if mat.base_color_texture_png is not None:
        tex_idx = _add_texture(mat.base_color_texture_png, buffer_data, buffer_views,
                               textures, images, samplers)
        pbr.baseColorTexture = pygltflib.TextureInfo(index=tex_idx)
    gltf_mat = pygltflib.Material(
        name=mat.name,
        pbrMetallicRoughness=pbr,
        alphaMode=mat.alpha_mode,
        alphaCutoff=mat.alpha_cutoff if mat.alpha_mode == "MASK" else None,
        doubleSided=mat.double_sided,
    )
    materials.append(gltf_mat)
    return len(materials) - 1


def _add_texture(
    png_bytes: bytes,
    buffer_data: bytearray,
    buffer_views: list,
    textures: list,
    images: list,
    samplers: list,
) -> int:
    _pad4(buffer_data)
    offset = len(buffer_data)
    buffer_data.extend(png_bytes)
    bv = pygltflib.BufferView(buffer=0, byteOffset=offset, byteLength=len(png_bytes))
    buffer_views.append(bv)
    bv_idx = len(buffer_views) - 1

    images.append(pygltflib.Image(mimeType="image/png", bufferView=bv_idx))
    img_idx = len(images) - 1

    if not samplers:
        samplers.append(pygltflib.Sampler(
            magFilter=pygltflib.LINEAR,
            minFilter=pygltflib.LINEAR_MIPMAP_LINEAR,
            wrapS=pygltflib.REPEAT,
            wrapT=pygltflib.REPEAT,
        ))
    sampler_idx = 0

    textures.append(pygltflib.Texture(source=img_idx, sampler=sampler_idx))
    return len(textures) - 1
