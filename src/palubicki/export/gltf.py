# src/palubicki/export/gltf.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import pygltflib

from palubicki.geom.mesh import Material, Mesh


class ExportError(RuntimeError):
    pass


_COMPONENT_FLOAT = pygltflib.FLOAT
_COMPONENT_UINT = pygltflib.UNSIGNED_INT
_TYPE_VEC3 = pygltflib.VEC3
_TYPE_VEC2 = pygltflib.VEC2
_TYPE_SCALAR = pygltflib.SCALAR

_TARGET_ARRAY = 34962           # ARRAY_BUFFER
_TARGET_ELEMENT_ARRAY = 34963   # ELEMENT_ARRAY_BUFFER


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
        idx_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.indices, _COMPONENT_UINT,
                                _TYPE_SCALAR, _TARGET_ELEMENT_ARRAY, with_minmax=False)

        mat_idx = _add_material(prim.material, buffer_data, buffer_views, materials,
                                textures, images, samplers)

        gltf_primitives.append(pygltflib.Primitive(
            attributes=pygltflib.Attributes(
                POSITION=pos_acc, NORMAL=nor_acc, TEXCOORD_0=uv_acc,
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
    target: int,
    *,
    with_minmax: bool,
) -> int:
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
    kwargs = dict(bufferView=bv_idx, componentType=component_type, count=count, type=type_str)
    if with_minmax and array.size > 0:
        kwargs["min"] = array.min(axis=0).tolist()
        kwargs["max"] = array.max(axis=0).tolist()
    accessors.append(pygltflib.Accessor(**kwargs))
    return len(accessors) - 1


def _add_material(
    mat: Material,
    buffer_data: bytearray,
    buffer_views: list,
    materials: list,
    textures: list,
    images: list,
    samplers: list,
) -> int:
    pbr = pygltflib.PbrMetallicRoughness(
        baseColorFactor=list(mat.base_color),
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


def write_glb_forest(forest, cfg, output_path: Path, *, asset_meta: dict) -> None:
    """Write a multi-tree glTF scene: one node per tree + optional 'obstacles' node."""
    from palubicki.geom.builder import build_mesh
    from palubicki.geom.obstacle_geom import build_obstacle_primitive

    # Build per-tree palubicki meshes
    tree_meshes: list[tuple[str, Mesh]] = []
    for i, tree in enumerate(forest.trees):
        per_tree_cfg = forest.per_tree_cfgs[i] if i < len(forest.per_tree_cfgs) else cfg
        tree_meshes.append((f"tree_{i}", build_mesh(tree, per_tree_cfg)))

    # Build obstacle primitive (optional)
    obstacle_primitive = None
    if cfg.forest.export_obstacles_geometry and forest.obstacles:
        obstacle_mat = Material(
            name="obstacle",
            base_color=(0.5, 0.5, 0.55, 0.3),
            metallic=0.0,
            roughness=0.9,
            base_color_texture_png=None,
            alpha_mode="BLEND",
            alpha_cutoff=0.5,
            double_sided=True,
        )
        obstacle_primitive = build_obstacle_primitive(forest.obstacles, obstacle_mat)

    # Sanity: there must be at least one non-empty mesh (trees or obstacles)
    has_geometry = any(
        any(p.positions.shape[0] > 0 for p in m.primitives) for _, m in tree_meshes
    ) or (obstacle_primitive is not None and obstacle_primitive.positions.shape[0] > 0)
    if not has_geometry:
        raise ExportError("empty forest - no trees produced geometry and no obstacles to export")

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

    gltf_meshes: list[pygltflib.Mesh] = []
    gltf_nodes: list[pygltflib.Node] = []

    def _emit_mesh(name: str, primitives_iter) -> None:
        gltf_prims: list[pygltflib.Primitive] = []
        for prim in primitives_iter:
            if prim is None or prim.positions.shape[0] == 0:
                continue
            pos_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.positions,
                                    _COMPONENT_FLOAT, _TYPE_VEC3, _TARGET_ARRAY, with_minmax=True)
            nor_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.normals,
                                    _COMPONENT_FLOAT, _TYPE_VEC3, _TARGET_ARRAY, with_minmax=False)
            uv_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.uvs,
                                   _COMPONENT_FLOAT, _TYPE_VEC2, _TARGET_ARRAY, with_minmax=False)
            idx_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.indices,
                                    _COMPONENT_UINT, _TYPE_SCALAR, _TARGET_ELEMENT_ARRAY, with_minmax=False)
            mat_idx = _add_material(prim.material, buffer_data, buffer_views,
                                    materials, textures, images, samplers)
            gltf_prims.append(pygltflib.Primitive(
                attributes=pygltflib.Attributes(POSITION=pos_acc, NORMAL=nor_acc, TEXCOORD_0=uv_acc),
                indices=idx_acc,
                material=mat_idx,
            ))
        if not gltf_prims:
            return
        gltf_meshes.append(pygltflib.Mesh(primitives=gltf_prims))
        gltf_nodes.append(pygltflib.Node(name=name, mesh=len(gltf_meshes) - 1))

    for name, mesh in tree_meshes:
        _emit_mesh(name, mesh.primitives)

    if obstacle_primitive is not None:
        _emit_mesh("obstacles", [obstacle_primitive])

    gltf.meshes = gltf_meshes
    gltf.nodes = gltf_nodes
    gltf.scenes = [pygltflib.Scene(nodes=list(range(len(gltf_nodes))))]
    gltf.scene = 0
    gltf.bufferViews = buffer_views
    gltf.accessors = accessors
    gltf.materials = materials
    gltf.textures = textures
    gltf.images = images
    gltf.samplers = samplers
    gltf.buffers = [pygltflib.Buffer(byteLength=len(buffer_data))]
    gltf.set_binary_blob(bytes(buffer_data))
    gltf.save_binary(str(output_path))


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
