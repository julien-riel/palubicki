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
_TYPE_VEC4 = pygltflib.VEC4
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


def _add_primitive_attributes(
    prim,
    buffer_data: bytearray,
    buffer_views: list,
    accessors: list,
) -> pygltflib.Attributes:
    """Build the glTF ``Attributes`` for one mesh primitive, data-driven.

    POSITION / NORMAL / TEXCOORD_0 are always emitted; the optional wind/look
    channels follow the P1 portable contract (geom/wind.py) — only emitted when
    present on the ``Primitive``:

        TANGENT    VEC4  (xyz + MikkTSpace handedness)
        COLOR_0    VEC3  (phase, stiffness, leafMask)        ← prim.wind
        COLOR_1    VEC3  tint (autumn / bark age)            ← prim.tint
        TEXCOORD_1 VEC2  (pivot.x, pivot.y)                  ┐ prim.pivot, split
        TEXCOORD_2 VEC2  (pivot.z, wind_tier)                ┘ (TEXCOORD is VEC2-only)

    Custom semantics (``COLOR_1`` / ``TEXCOORD_2``) are set via ``setattr`` —
    pygltflib's ``Attributes`` round-trips arbitrary attribute names.
    """
    v = prim.positions.shape[0]
    attrs = pygltflib.Attributes()
    attrs.POSITION = _add_accessor(buffer_data, buffer_views, accessors, prim.positions,
                                   _COMPONENT_FLOAT, _TYPE_VEC3, _TARGET_ARRAY, with_minmax=True)
    attrs.NORMAL = _add_accessor(buffer_data, buffer_views, accessors, prim.normals,
                                 _COMPONENT_FLOAT, _TYPE_VEC3, _TARGET_ARRAY, with_minmax=False)
    attrs.TEXCOORD_0 = _add_accessor(buffer_data, buffer_views, accessors, prim.uvs,
                                     _COMPONENT_FLOAT, _TYPE_VEC2, _TARGET_ARRAY, with_minmax=False)

    def _ok(arr) -> bool:
        return arr is not None and arr.shape[0] == v

    if _ok(prim.tangents):
        attrs.TANGENT = _add_accessor(buffer_data, buffer_views, accessors,
                                      np.ascontiguousarray(prim.tangents, dtype=np.float32),
                                      _COMPONENT_FLOAT, _TYPE_VEC4, _TARGET_ARRAY, with_minmax=False)
    if _ok(prim.wind):
        attrs.COLOR_0 = _add_accessor(buffer_data, buffer_views, accessors,
                                      np.ascontiguousarray(prim.wind, dtype=np.float32),
                                      _COMPONENT_FLOAT, _TYPE_VEC3, _TARGET_ARRAY, with_minmax=False)
    if _ok(prim.tint):
        attrs.COLOR_1 = _add_accessor(buffer_data, buffer_views, accessors,
                                      np.ascontiguousarray(prim.tint, dtype=np.float32),
                                      _COMPONENT_FLOAT, _TYPE_VEC3, _TARGET_ARRAY, with_minmax=False)
    if _ok(prim.pivot):
        pivot = np.ascontiguousarray(prim.pivot, dtype=np.float32)
        attrs.TEXCOORD_1 = _add_accessor(buffer_data, buffer_views, accessors,
                                         np.ascontiguousarray(pivot[:, :2], dtype=np.float32),
                                         _COMPONENT_FLOAT, _TYPE_VEC2, _TARGET_ARRAY, with_minmax=False)
        tier = (prim.wind_tier if (prim.wind_tier is not None and prim.wind_tier.shape[0] == v)
                else np.zeros(v, dtype=np.float32))
        t2 = np.ascontiguousarray(
            np.column_stack([pivot[:, 2], np.asarray(tier, dtype=np.float32)]), dtype=np.float32)
        attrs.TEXCOORD_2 = _add_accessor(buffer_data, buffer_views, accessors, t2,
                                         _COMPONENT_FLOAT, _TYPE_VEC2, _TARGET_ARRAY, with_minmax=False)
    return attrs


# --------------------------------------------------------------------------- #
# materials (PBR metallic-roughness + P2 maps & extensions)
# --------------------------------------------------------------------------- #

_KHR_TEXTURE_TRANSFORM = "KHR_texture_transform"
_KHR_MATERIALS_SPECULAR = "KHR_materials_specular"
_KHR_MATERIALS_DIFFUSE_TRANSMISSION = "KHR_materials_diffuse_transmission"
_KHR_MATERIALS_VARIANTS = "KHR_materials_variants"


def _texture_transform_ext(mat, extensions_used: set | None):
    """``KHR_texture_transform`` extension dict for this material's atlas window,
    or ``None`` for identity. Registers the extension name when emitted."""
    xf = getattr(mat, "texture_transform", None)
    if xf is None or xf.is_identity():
        return None
    if extensions_used is not None:
        extensions_used.add(_KHR_TEXTURE_TRANSFORM)
    return {_KHR_TEXTURE_TRANSFORM: {
        "offset": [float(xf.offset[0]), float(xf.offset[1])],
        "scale": [float(xf.scale[0]), float(xf.scale[1])],
        "rotation": float(xf.rotation),
    }}


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
    extensions_used: set | None = None,
) -> int:
    """Build one glTF material from ``mat``, emitting every P2 map it carries.

    Base colour rides the sRGB slot; the normal / ORM / occlusion maps ride the
    linear slots (glTF tags colour space by slot). The ORM image, when present,
    is added **once** and referenced by both ``metallicRoughnessTexture`` (G,B)
    and ``occlusionTexture`` (R). Forward-looking + cuticle looks ride material
    extensions; ``extensions_used`` collects every extension name emitted so the
    caller can populate ``gltf.extensionsUsed`` (a Validator requirement)."""
    xf_ext = _texture_transform_ext(mat, extensions_used)

    def _tex(png: bytes) -> int:
        return _add_texture(png, buffer_data, buffer_views, textures, images, samplers)

    def _info(cls, idx, **kw):
        info = cls(index=idx, **kw)
        if xf_ext is not None:
            info.extensions = dict(xf_ext)
        return info

    base_color = (1.0, 1.0, 1.0, 1.0) if neutralize_base_color else list(mat.base_color)
    pbr = pygltflib.PbrMetallicRoughness(
        baseColorFactor=list(base_color),
        metallicFactor=mat.metallic,
        roughnessFactor=mat.roughness,
    )
    if mat.base_color_texture_png is not None:
        pbr.baseColorTexture = _info(pygltflib.TextureInfo, _tex(mat.base_color_texture_png))

    gltf_mat = pygltflib.Material(
        name=mat.name,
        pbrMetallicRoughness=pbr,
        alphaMode=mat.alpha_mode,
        alphaCutoff=mat.alpha_cutoff if mat.alpha_mode == "MASK" else None,
        doubleSided=mat.double_sided,
    )

    orm_png = getattr(mat, "orm_texture_png", None)
    if orm_png is not None:
        orm_idx = _tex(orm_png)  # one image → two slots (ORM packing)
        pbr.metallicRoughnessTexture = _info(pygltflib.TextureInfo, orm_idx)
        gltf_mat.occlusionTexture = _info(
            pygltflib.OcclusionTextureInfo, orm_idx,
            strength=float(getattr(mat, "occlusion_strength", 1.0)),
        )

    normal_png = getattr(mat, "normal_texture_png", None)
    if normal_png is not None:
        gltf_mat.normalTexture = _info(
            pygltflib.NormalMaterialTexture, _tex(normal_png),
            scale=float(getattr(mat, "normal_scale", 1.0)),
        )

    emissive_png = getattr(mat, "emissive_texture_png", None)
    emissive_factor = getattr(mat, "emissive_factor", (0.0, 0.0, 0.0))
    if emissive_png is not None:
        gltf_mat.emissiveTexture = _info(pygltflib.TextureInfo, _tex(emissive_png))
    if any(c > 0.0 for c in emissive_factor):
        gltf_mat.emissiveFactor = [float(c) for c in emissive_factor]

    mat_ext = _material_ext(mat, _tex, _info, extensions_used)
    if mat_ext:
        gltf_mat.extensions = mat_ext

    materials.append(gltf_mat)
    return len(materials) - 1


def _material_ext(mat, add_tex, make_info, extensions_used: set | None) -> dict:
    """Assemble the material-level extension dict: cuticle specular + the
    forward-looking diffuse-transmission back-light (metadata, engine-ignored in
    2026 — design D1)."""
    ext: dict = {}
    spec = getattr(mat, "specular_factor", None)
    if spec is not None:
        if extensions_used is not None:
            extensions_used.add(_KHR_MATERIALS_SPECULAR)
        ext[_KHR_MATERIALS_SPECULAR] = {"specularFactor": float(spec)}

    trans_png = getattr(mat, "transmission_texture_png", None)
    trans_factor = float(getattr(mat, "diffuse_transmission_factor", 0.0))
    if trans_png is not None or trans_factor > 0.0:
        if extensions_used is not None:
            extensions_used.add(_KHR_MATERIALS_DIFFUSE_TRANSMISSION)
        color = getattr(mat, "diffuse_transmission_color", (1.0, 1.0, 1.0))
        dt: dict = {
            "diffuseTransmissionFactor": trans_factor,
            "diffuseTransmissionColorFactor": [float(c) for c in color],
        }
        if trans_png is not None:
            info = make_info(pygltflib.TextureInfo, add_tex(trans_png))
            dt["diffuseTransmissionTexture"] = _info_to_dict(info)
        ext[_KHR_MATERIALS_DIFFUSE_TRANSMISSION] = dt
    return ext


def _info_to_dict(info) -> dict:
    """Serialise a pygltflib TextureInfo to the plain dict an extension expects
    (extensions hold raw JSON, not typed objects)."""
    d: dict = {"index": int(info.index)}
    if getattr(info, "texCoord", None):
        d["texCoord"] = int(info.texCoord)
    if getattr(info, "extensions", None):
        d["extensions"] = info.extensions
    return d


class _VariantRegistry:
    """Ordered, deduped season-variant names for ``KHR_materials_variants``.

    The document declares one ``variants`` list (``index()`` assigns each season a
    stable slot); every primitive's ``mappings`` reference those slots."""

    def __init__(self) -> None:
        self._names: list[str] = []

    def index(self, name: str) -> int:
        if name not in self._names:
            self._names.append(name)
        return self._names.index(name)

    @property
    def names(self) -> list[str]:
        return list(self._names)


def emit_primitive_variants(prim, gltf_prim, registry, add_material, extensions_used: set) -> None:
    """Attach this primitive's ``KHR_materials_variants`` mappings (one material per
    season). The primitive's default ``material`` stays the variant-unaware fallback.
    No-op when the primitive carries no variants."""
    variants = getattr(prim, "material_variants", None)
    if not variants:
        return
    mappings = []
    for name, vmat in variants:
        vidx = registry.index(name)
        midx = add_material(vmat)
        mappings.append({"material": midx, "variants": [vidx]})
    extensions_used.add(_KHR_MATERIALS_VARIANTS)
    existing = dict(gltf_prim.extensions or {})
    existing[_KHR_MATERIALS_VARIANTS] = {"mappings": mappings}
    gltf_prim.extensions = existing


def set_document_variants(gltf, registry, extensions_used: set) -> None:
    """Declare the document-level ``variants`` list once every primitive is built."""
    if not registry.names:
        return
    extensions_used.add(_KHR_MATERIALS_VARIANTS)
    existing = dict(gltf.extensions or {})
    existing[_KHR_MATERIALS_VARIANTS] = {"variants": [{"name": n} for n in registry.names]}
    gltf.extensions = existing


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
