# src/palubicki/export/instancing.py
"""Forest export: unit-tree-at-origin meshes + per-instance transforms.

Replaces the old world-baked ``write_glb_forest`` (which built full geometry per
tree and emitted one node per tree with ``node.translation`` unused — every tree
rooted at its world position, so world-space vertices were baked in place,
defeating instancing / batching / Nanite-HISM and bloating the file linearly
with tree count).

The fix: each tree's geometry is **localized** so its root collar sits at the
local origin ``(0, 0, 0)``; placement is carried by a transform instead of baked
vertices. Two emission granularities, per the design (docs/export-pipeline-design.md §6.2):

- **instance-of-one** — a tree whose localized geometry is unique in the forest
  becomes a plain ``Node`` carrying just its world transform
  (``node.translation`` = collar world position ``(x, 0, z)``). This is the
  common case: every forest tree is seeded distinctly (``cfg.seed + index``), so
  its topology — and, under competition, its grown form — differs. Plain node
  TRS is read by every engine *and* by trimesh, so the round-trip places it.
- **shared mesh** — trees whose localized geometry is identical (within a
  tolerance that absorbs float round-trip noise but rejects cm-scale
  competition differences) share **one** mesh and a single node bearing
  ``EXT_mesh_gpu_instancing`` with a flat per-instance ``TRANSLATION`` buffer,
  plus ``EXT_instance_features`` feature IDs carrying ``_SPECIES`` / ``_SEED``.
  This is where instancing pays off: geometry is stored once, so file size grows
  sub-linearly with repeated trees.

Sharing is decided by the **actual resulting geometry**, not by config keys:
two same-seed trees at different positions in a competitive forest grow
*differently* (neighbour shading / marker depletion), so a config-key dedup would
wrongly merge them. We instead localize every tree, bucket by a cheap signature
(per-primitive vertex/index counts + material), and within a bucket cluster trees
whose localized vertex data matches within ``_GEOM_ATOL``. Genuine duplicates
(same seed, no competition) merge; everything else falls to instance-of-one.

``sim/`` is never mutated: localization subtracts the (read-only) collar anchor
from a *copy* of the built vertex array.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pygltflib

from palubicki.export._glb_common import (
    _COMPONENT_FLOAT,
    _COMPONENT_UINT,
    _TARGET_ELEMENT_ARRAY,
    _TYPE_SCALAR,
    _TYPE_VEC3,
    ExportError,
    _add_accessor,
    _add_material,
    _add_primitive_attributes,
)
from palubicki.geom.mesh import Material, Mesh, Primitive

_GPU_INSTANCING = "EXT_mesh_gpu_instancing"
_INSTANCE_FEATURES = "EXT_instance_features"

# Localized vertex data of two trees is treated as the same geometry when every
# attribute matches within this absolute tolerance. ~1e-4 m (0.1 mm) sits far
# above the ~1e-6 float32 noise of the world->local subtraction yet far below the
# centimetre-scale form differences competition produces, so it merges genuine
# duplicates without ever merging visibly-different trees.
_GEOM_ATOL = 1e-4


@dataclass
class _Cluster:
    """One emitted mesh + the trees that instance it."""
    rep_prims: list[Primitive]          # localized geometry (the representative tree)
    rep_index: int                      # tree index that defined the geometry
    members: list[int] = field(default_factory=list)
    anchors: list[np.ndarray] = field(default_factory=list)
    species: list[str] = field(default_factory=list)
    seeds: list[int] = field(default_factory=list)


def write_glb_forest(forest, cfg, output_path: Path, *, asset_meta: dict) -> None:
    """Write a multi-tree glTF scene as unit-trees-at-origin + per-instance transforms.

    Each tree is localized to its collar; unique trees become plain TRS nodes and
    geometrically-identical trees share one ``EXT_mesh_gpu_instancing`` node. An
    optional world-space ``obstacles`` node is appended unchanged.
    """
    clusters = _cluster_forest(forest, cfg)
    obstacle_prim = _build_obstacle_primitive(forest, cfg)

    if not clusters and obstacle_prim is None:
        raise ExportError("empty forest - no trees produced geometry and no obstacles to export")

    species_table = _species_table(clusters)

    gltf = pygltflib.GLTF2()
    buffer_data = bytearray()
    buffer_views: list[pygltflib.BufferView] = []
    accessors: list[pygltflib.Accessor] = []
    materials: list[pygltflib.Material] = []
    textures: list[pygltflib.Texture] = []
    images: list[pygltflib.Image] = []
    samplers: list[pygltflib.Sampler] = []
    meshes: list[pygltflib.Mesh] = []
    nodes: list[pygltflib.Node] = []
    used_instancing = False

    def _emit_mesh(prims: list[Primitive]) -> int:
        gltf_prims: list[pygltflib.Primitive] = []
        for prim in prims:
            attributes = _add_primitive_attributes(prim, buffer_data, buffer_views, accessors)
            idx_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.indices,
                                    _COMPONENT_UINT, _TYPE_SCALAR, _TARGET_ELEMENT_ARRAY, with_minmax=False)
            # COLOR_0 is wind data — neutralize base colour on the tint stream (COLOR_1).
            has_tint = prim.tint is not None and prim.tint.shape[0] == prim.positions.shape[0]
            mat_idx = _add_material(prim.material, buffer_data, buffer_views,
                                    materials, textures, images, samplers,
                                    neutralize_base_color=has_tint)
            gltf_prims.append(pygltflib.Primitive(
                attributes=attributes,
                indices=idx_acc,
                material=mat_idx,
            ))
        meshes.append(pygltflib.Mesh(primitives=gltf_prims))
        return len(meshes) - 1

    for cluster in clusters:
        mesh_idx = _emit_mesh(cluster.rep_prims)
        if len(cluster.members) == 1:
            # instance-of-one: plain node carrying just its world transform.
            anchor = cluster.anchors[0]
            nodes.append(pygltflib.Node(
                name=f"tree_{cluster.rep_index}",
                mesh=mesh_idx,
                translation=[float(anchor[0]), float(anchor[1]), float(anchor[2])],
                extras={
                    "species": cluster.species[0],
                    "seed": int(cluster.seeds[0]),
                    "tree_index": cluster.rep_index,
                },
            ))
        else:
            # shared mesh: one EXT_mesh_gpu_instancing node for all members.
            used_instancing = True
            n = len(cluster.members)
            translations = np.asarray(cluster.anchors, dtype=np.float32).reshape(n, 3)
            species_ids = np.asarray([species_table[s] for s in cluster.species],
                                     dtype=np.float32).reshape(n)
            seed_ids = np.asarray(cluster.seeds, dtype=np.float32).reshape(n)
            # Instance-attribute bufferViews MUST NOT declare a target -> target=None.
            t_acc = _add_accessor(buffer_data, buffer_views, accessors, translations,
                                  _COMPONENT_FLOAT, _TYPE_VEC3, None, with_minmax=True)
            sp_acc = _add_accessor(buffer_data, buffer_views, accessors, species_ids,
                                   _COMPONENT_FLOAT, _TYPE_SCALAR, None, with_minmax=False)
            seed_acc = _add_accessor(buffer_data, buffer_views, accessors, seed_ids,
                                     _COMPONENT_FLOAT, _TYPE_SCALAR, None, with_minmax=False)
            nodes.append(pygltflib.Node(
                name=f"tree_{cluster.rep_index}",
                mesh=mesh_idx,
                extensions={
                    _GPU_INSTANCING: {
                        "attributes": {
                            "TRANSLATION": t_acc,
                            "_FEATURE_ID_0": sp_acc,
                            "_FEATURE_ID_1": seed_acc,
                        },
                    },
                    _INSTANCE_FEATURES: {
                        "featureIds": [
                            {"featureCount": n, "attribute": 0, "label": "species"},
                            {"featureCount": n, "attribute": 1, "label": "seed"},
                        ],
                    },
                },
                extras={
                    "tree_indices": [int(m) for m in cluster.members],
                    "instance_count": n,
                    "species": cluster.species,
                    "seeds": [int(s) for s in cluster.seeds],
                },
            ))

    if obstacle_prim is not None:
        obs_mesh_idx = _emit_mesh([obstacle_prim])
        nodes.append(pygltflib.Node(name="obstacles", mesh=obs_mesh_idx))

    extras = dict(asset_meta) if asset_meta else {}
    extras["instancing"] = {
        "n_instances": sum(len(c.members) for c in clusters),
        "n_meshes": len(clusters),
        "n_instanced_nodes": sum(1 for c in clusters if len(c.members) > 1),
        "n_singleton_nodes": sum(1 for c in clusters if len(c.members) == 1),
        "species_table": species_table,
    }

    gltf.asset = pygltflib.Asset(version="2.0", generator="palubicki", extras=extras or None)
    gltf.meshes = meshes
    gltf.nodes = nodes
    gltf.scenes = [pygltflib.Scene(nodes=list(range(len(nodes))))]
    gltf.scene = 0
    gltf.bufferViews = buffer_views
    gltf.accessors = accessors
    gltf.materials = materials
    gltf.textures = textures
    gltf.images = images
    gltf.samplers = samplers
    if used_instancing:
        gltf.extensionsUsed = [_GPU_INSTANCING, _INSTANCE_FEATURES]
    gltf.buffers = [pygltflib.Buffer(byteLength=len(buffer_data))]
    gltf.set_binary_blob(bytes(buffer_data))
    gltf.save_binary(str(output_path))


# --------------------------------------------------------------------------- #
# clustering
# --------------------------------------------------------------------------- #

def _cluster_forest(forest, cfg) -> list[_Cluster]:
    """Build every tree's localized mesh and group geometrically-identical ones."""
    from palubicki.geom.builder import build_mesh

    trees = forest.trees
    per_tree_cfgs = getattr(forest, "per_tree_cfgs", None) or []
    buckets: dict[tuple, list[int]] = {}
    clusters: list[_Cluster] = []

    for i, tree in enumerate(trees):
        ptc = per_tree_cfgs[i] if i < len(per_tree_cfgs) else cfg
        mesh = build_mesh(tree, ptc)
        anchor = np.asarray(tree.root.position, dtype=np.float64).reshape(3)
        prims = _localized_primitives(mesh, anchor)
        if not prims:
            continue  # tree produced no geometry; no node, no instance

        species = _tree_species(forest, i)
        seed = _tree_seed(forest, cfg, i)
        key = _bucket_key(prims)

        match = None
        for ci in buckets.get(key, ()):
            if _geom_close(clusters[ci].rep_prims, prims):
                match = ci
                break

        if match is None:
            clusters.append(_Cluster(rep_prims=prims, rep_index=i, members=[i],
                                     anchors=[anchor], species=[species], seeds=[seed]))
            buckets.setdefault(key, []).append(len(clusters) - 1)
        else:
            cluster = clusters[match]
            cluster.members.append(i)
            cluster.anchors.append(anchor)
            cluster.species.append(species)
            cluster.seeds.append(seed)

    return clusters


def _localized_primitives(mesh: Mesh, anchor: np.ndarray) -> list[Primitive]:
    """Return the mesh's non-empty primitives with positions shifted so the tree's
    collar anchor lands at the local origin. The wind ``pivot`` is also a position,
    so it is shifted by the same anchor (keeping vertex - pivot intact under the
    per-instance transform); directions/scalars (normals, tangents, wind, tint,
    wind_tier) are shared by reference (read-only). ``sim/`` is untouched —
    positions/pivot are fresh arrays."""
    out: list[Primitive] = []
    for prim in mesh.primitives:
        # Skip degenerate primitives (no verts, or verts but no triangles) — a
        # 0-count accessor is invalid glTF and a triangle-less prim renders nothing.
        if prim.positions.shape[0] == 0 or prim.indices.shape[0] == 0:
            continue
        local_pos = (prim.positions.astype(np.float64) - anchor).astype(np.float32)
        local_pivot = None
        if prim.pivot is not None:
            local_pivot = (prim.pivot.astype(np.float64) - anchor).astype(np.float32)
        out.append(Primitive(
            positions=local_pos,
            normals=prim.normals,
            uvs=prim.uvs,
            indices=prim.indices,
            material=prim.material,
            tint=prim.tint,
            wind=prim.wind,
            pivot=local_pivot,
            wind_tier=prim.wind_tier,
            tangents=prim.tangents,
        ))
    return out


def _material_sig(mat: Material) -> tuple:
    tex = hashlib.sha1(mat.base_color_texture_png).hexdigest() if mat.base_color_texture_png else None
    return (
        mat.name,
        tuple(round(float(c), 6) for c in mat.base_color),
        round(float(mat.metallic), 6),
        round(float(mat.roughness), 6),
        mat.alpha_mode,
        round(float(mat.alpha_cutoff), 6),
        bool(mat.double_sided),
        tex,
    )


def _bucket_key(prims: list[Primitive]) -> tuple:
    """Cheap hashable signature: a fast reject before the per-vertex comparison.
    Trees that differ in primitive count, vertex/index counts, or materials can
    never be the same geometry, so they land in different buckets."""
    return tuple(
        (int(p.positions.shape[0]), int(p.indices.shape[0]), _material_sig(p.material))
        for p in prims
    )


def _geom_close(a: list[Primitive], b: list[Primitive]) -> bool:
    """True if two localized primitive lists are the same geometry within tolerance.
    Callers guarantee ``a`` and ``b`` share a bucket (same counts + materials)."""
    if len(a) != len(b):
        return False
    for pa, pb in zip(a, b, strict=True):
        if pa.positions.shape != pb.positions.shape or pa.indices.shape != pb.indices.shape:
            return False
        if not np.array_equal(pa.indices, pb.indices):
            return False
        if not np.allclose(pa.positions, pb.positions, rtol=0.0, atol=_GEOM_ATOL):
            return False
        if not np.allclose(pa.normals, pb.normals, rtol=0.0, atol=_GEOM_ATOL):
            return False
        if not np.allclose(pa.uvs, pb.uvs, rtol=0.0, atol=_GEOM_ATOL):
            return False
        # Wind/look attributes are derived deterministically from the geometry, so
        # matching positions implies matching wind — but compare them anyway so a
        # shared mesh can never silently flatten differing per-vertex streams.
        for attr in ("tint", "wind", "pivot", "wind_tier", "tangents"):
            va, vb = getattr(pa, attr), getattr(pb, attr)
            if (va is None) != (vb is None):
                return False
            if va is not None and not np.allclose(va, vb, rtol=0.0, atol=_GEOM_ATOL):
                return False
    return True


def _species_table(clusters: list[_Cluster]) -> dict[str, int]:
    names: set[str] = set()
    for cluster in clusters:
        names.update(cluster.species)
    return {name: idx for idx, name in enumerate(sorted(names))}


def _tree_species(forest, i: int) -> str:
    seeds = getattr(forest, "seeds", None)
    if seeds and i < len(seeds):
        sp = getattr(seeds[i], "species", None)
        if sp:
            return str(sp)
    return "default"


def _tree_seed(forest, cfg, i: int) -> int:
    per_tree_cfgs = getattr(forest, "per_tree_cfgs", None)
    if per_tree_cfgs and i < len(per_tree_cfgs):
        s = getattr(per_tree_cfgs[i], "seed", None)
        if s is not None:
            return int(s)
    return int(getattr(cfg, "seed", 0) or 0)


def _build_obstacle_primitive(forest, cfg) -> Primitive | None:
    if not (cfg.forest.export_obstacles_geometry and forest.obstacles):
        return None
    from palubicki.geom.obstacle_geom import build_obstacle_primitive
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
    prim = build_obstacle_primitive(forest.obstacles, obstacle_mat)
    if prim is None or prim.positions.shape[0] == 0:
        return None
    return prim
