# src/palubicki/export/gltf.py
from __future__ import annotations

from pathlib import Path

import pygltflib

from palubicki.export._glb_common import (
    _COMPONENT_FLOAT,
    _COMPONENT_UINT,
    _TARGET_ARRAY,
    _TARGET_ELEMENT_ARRAY,
    _TYPE_SCALAR,
    _TYPE_VEC2,
    _TYPE_VEC3,
    ExportError,
    _add_accessor,
    _add_material,
)
from palubicki.export.instancing import write_glb_forest  # noqa: F401  (re-export: forest path)
from palubicki.geom.mesh import Mesh

__all__ = ["ExportError", "write_glb", "write_glb_to_bytes", "write_glb_forest"]


def write_glb_to_bytes(mesh: Mesh, *, asset_meta: dict) -> bytes:
    if not mesh.primitives or all(p.positions.shape[0] == 0 for p in mesh.primitives):
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

    for prim in mesh.primitives:
        if prim.positions.shape[0] == 0:
            continue

        pos_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.positions, _COMPONENT_FLOAT,
                                _TYPE_VEC3, _TARGET_ARRAY, with_minmax=True)
        nor_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.normals, _COMPONENT_FLOAT,
                                _TYPE_VEC3, _TARGET_ARRAY, with_minmax=False)
        uv_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.uvs, _COMPONENT_FLOAT,
                               _TYPE_VEC2, _TARGET_ARRAY, with_minmax=False)

        col_acc = None
        if prim.colors is not None and prim.colors.shape[0] == prim.positions.shape[0]:
            col_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.colors,
                                    _COMPONENT_FLOAT, _TYPE_VEC3, _TARGET_ARRAY, with_minmax=False)
        idx_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.indices, _COMPONENT_UINT,
                                _TYPE_SCALAR, _TARGET_ELEMENT_ARRAY, with_minmax=False)

        mat_idx = _add_material(prim.material, buffer_data, buffer_views, materials,
                                textures, images, samplers,
                                neutralize_base_color=col_acc is not None)

        gltf_primitives.append(pygltflib.Primitive(
            attributes=pygltflib.Attributes(
                POSITION=pos_acc, NORMAL=nor_acc, TEXCOORD_0=uv_acc, COLOR_0=col_acc,
            ),
            indices=idx_acc,
            material=mat_idx,
        ))

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
