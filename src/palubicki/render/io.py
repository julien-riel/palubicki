# src/palubicki/render/io.py
"""Persistence helpers: .glb -> palubicki.Mesh, ndarray -> PNG file."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from palubicki.geom.mesh import Material, Mesh, Primitive
from palubicki.render.errors import RenderError


def save_png(image: np.ndarray, path: Path) -> None:
    """Persist an (H, W, 4) uint8 RGBA ndarray as a PNG file."""
    if image.dtype != np.uint8:
        raise ValueError(f"image must be dtype uint8, got {image.dtype}")
    if image.ndim != 3 or image.shape[2] != 4:
        raise ValueError(f"image must have shape (H, W, 4), got {image.shape}")
    from PIL import Image
    Image.fromarray(image, mode="RGBA").save(Path(path), format="PNG")


def _glb_to_mesh(path: Path, *, drop_leaves: bool = False) -> Mesh:
    """Load a .glb via trimesh and convert to palubicki.Mesh.

    Concatenates all scene nodes into a single Mesh with one Primitive per
    source geometry instance. Each node's world transform is applied to
    positions and normals. Textures are discarded (diagnostic mode); only
    base_color is kept.

    If drop_leaves=True, filter out primitives whose base_color is dominantly
    green (g > r and g > b and g > 0.3). This works around the glTF->trimesh
    roundtrip losing alpha_mode='MASK'.
    """
    try:
        import trimesh
    except ImportError as e:
        # trimesh is a core dep; if it's missing, the install is broken.
        raise RenderError(f"trimesh import failed: {e}") from e

    p = Path(path)
    if not p.exists():
        raise RenderError(f"could not load glTF: {p} (file not found)")

    try:
        loaded = trimesh.load(str(p), force="scene")
    except (ValueError, OSError) as e:
        raise RenderError(f"could not load glTF: {p}: {e}") from e
    if loaded is None or not hasattr(loaded, "geometry") or not loaded.geometry:
        raise RenderError(f"could not load glTF: {p} (empty scene)")

    primitives: list[Primitive] = []
    # Iterate scene graph nodes; loaded.graph[node_name] yields
    # (transform 4x4, geometry_name or None).
    for node_name in loaded.graph.nodes:
        try:
            transform, geom_name = loaded.graph[node_name]
        except (KeyError, ValueError):
            continue
        if geom_name is None or geom_name not in loaded.geometry:
            continue
        geom = loaded.geometry[geom_name]
        if not hasattr(geom, "faces") or geom.faces is None or len(geom.faces) == 0:
            continue

        # Apply world transform (4x4) to vertices and normals.
        M = np.asarray(transform, dtype=np.float64)
        verts = np.asarray(geom.vertices, dtype=np.float32)
        verts_h = np.concatenate(
            [verts, np.ones((verts.shape[0], 1), dtype=np.float32)], axis=1
        )
        verts_w = (verts_h @ M.T)[:, :3].astype(np.float32)

        # For normals, transform with inverse-transpose of upper 3x3.
        R = M[:3, :3]
        try:
            R_inv_t = np.linalg.inv(R).T.astype(np.float32)
        except np.linalg.LinAlgError:
            R_inv_t = R.astype(np.float32)
        if hasattr(geom, "vertex_normals") and geom.vertex_normals is not None:
            norms = np.asarray(geom.vertex_normals, dtype=np.float32) @ R_inv_t.T
        else:
            # Trimesh computes them lazily; fall back to a default up vector.
            norms = np.tile(np.array([0, 1, 0], dtype=np.float32), (verts.shape[0], 1))

        faces = np.asarray(geom.faces, dtype=np.uint32).reshape(-1)

        # Material baseColor: try the trimesh visual.material.baseColorFactor;
        # fall back to gray.
        base_color = (0.7, 0.7, 0.7, 1.0)
        visual = getattr(geom, "visual", None)
        mat = getattr(visual, "material", None) if visual is not None else None
        if mat is not None and hasattr(mat, "baseColorFactor") and mat.baseColorFactor is not None:
            bc = np.asarray(mat.baseColorFactor, dtype=np.float32)
            if bc.max() > 1.5:
                bc = bc / 255.0
            if bc.shape == (3,):
                base_color = (float(bc[0]), float(bc[1]), float(bc[2]), 1.0)
            elif bc.shape == (4,):
                base_color = tuple(float(x) for x in bc)

        # Drop-leaves heuristic
        if drop_leaves:
            r, g, b, _ = base_color
            if g > r and g > b and g > 0.3:
                continue

        material = Material(
            name=str(geom_name),
            base_color=base_color,
            metallic=0.0,
            roughness=1.0,
            base_color_texture_png=None,
            alpha_mode="OPAQUE",
            alpha_cutoff=0.5,
            double_sided=False,
        )
        primitives.append(Primitive(
            positions=verts_w,
            normals=norms.astype(np.float32),
            uvs=np.zeros((verts_w.shape[0], 2), dtype=np.float32),
            indices=faces,
            material=material,
        ))

    if not primitives:
        raise RenderError(f"glTF loaded but no usable primitives: {p}")
    return Mesh(primitives=primitives)
