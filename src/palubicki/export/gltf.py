# src/palubicki/export/gltf.py
from __future__ import annotations

from pathlib import Path

import pygltflib

from palubicki.export._glb_common import (
    _COMPONENT_UINT,
    _TARGET_ELEMENT_ARRAY,
    _TYPE_SCALAR,
    ExportError,
    _add_accessor,
    _add_material,
    _add_primitive_attributes,
    _VariantRegistry,
    emit_primitive_variants,
    set_document_variants,
)
from palubicki.export.instancing import write_glb_forest  # noqa: F401  (re-export: forest path)
from palubicki.geom.mesh import Mesh

__all__ = ["ExportError", "write_glb", "write_glb_to_bytes", "write_glb_forest"]


def write_glb_to_bytes(mesh: Mesh, *, asset_meta: dict) -> bytes:
    if not mesh.primitives or all(
        p.positions.shape[0] == 0 or p.indices.shape[0] == 0 for p in mesh.primitives
    ):
        raise ExportError("empty mesh - simulation produced no geometry")

    gltf = pygltflib.GLTF2()
    gltf.asset = pygltflib.Asset(
        version="2.0",
        generator="palubicki",
        extras=dict(asset_meta) if asset_meta else None,
    )

    buffer_data = bytearray()
    buffer_views: list[pygltflib.BufferView] = []
    accessors: list[pygltflib.Accessor] = []
    materials: list[pygltflib.Material] = []
    textures: list[pygltflib.Texture] = []
    images: list[pygltflib.Image] = []
    samplers: list[pygltflib.Sampler] = []
    gltf_primitives: list[pygltflib.Primitive] = []
    extensions_used: set[str] = set()
    variants = _VariantRegistry()

    for prim in mesh.primitives:
        # Skip degenerate primitives: no verts, or verts but no triangles (e.g. a
        # tiny tree whose bark is just the root-cap point). A 0-count indices/vertex
        # accessor is invalid glTF (Validator VALUE_NOT_IN_RANGE).
        if prim.positions.shape[0] == 0 or prim.indices.shape[0] == 0:
            continue

        attributes = _add_primitive_attributes(prim, buffer_data, buffer_views, accessors)
        idx_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.indices, _COMPONENT_UINT,
                                _TYPE_SCALAR, _TARGET_ELEMENT_ARRAY, with_minmax=False)

        # COLOR_0 now carries wind data, so base-color neutralization keys on the
        # tint stream (COLOR_1) — the per-vertex bark/autumn colour — not on COLOR_0.
        has_tint = prim.tint is not None and prim.tint.shape[0] == prim.positions.shape[0]

        def _add_mat(material, *, neutralize=has_tint):
            return _add_material(material, buffer_data, buffer_views, materials,
                                 textures, images, samplers,
                                 neutralize_base_color=neutralize,
                                 extensions_used=extensions_used)

        mat_idx = _add_mat(prim.material)
        gltf_prim = pygltflib.Primitive(
            attributes=attributes,
            indices=idx_acc,
            material=mat_idx,
        )
        # Season variants carry their own base colour (the autumn hue), so they are
        # never neutralized — unlike the COLOR_1-tinted default material.
        emit_primitive_variants(prim, gltf_prim, variants,
                                lambda m: _add_mat(m, neutralize=False), extensions_used)
        gltf_primitives.append(gltf_prim)

    set_document_variants(gltf, variants, extensions_used)
    if extensions_used:
        gltf.extensionsUsed = sorted(extensions_used)
    gltf.meshes = [pygltflib.Mesh(primitives=gltf_primitives)]
    gltf.nodes = [pygltflib.Node(name="tree_root", mesh=0)]
    gltf.scenes = [pygltflib.Scene(nodes=[0])]
    gltf.scene = 0
    gltf.bufferViews = buffer_views
    gltf.accessors = accessors
    gltf.materials = materials
    gltf.textures = textures
    gltf.images = images
    gltf.samplers = samplers
    gltf.buffers = [pygltflib.Buffer(byteLength=len(buffer_data))]
    gltf.set_binary_blob(bytes(buffer_data))
    return b"".join(gltf.save_to_bytes())


def write_glb(mesh: Mesh, output_path: Path, *, asset_meta: dict) -> None:
    data = write_glb_to_bytes(mesh, asset_meta=asset_meta)
    Path(output_path).write_bytes(data)
