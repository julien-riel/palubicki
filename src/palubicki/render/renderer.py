# src/palubicki/render/renderer.py
from __future__ import annotations

import io
import logging
import time
from pathlib import Path

import numpy as np

from palubicki.geom.mesh import Mesh
from palubicki.render.camera import Camera
from palubicki.render.errors import RenderDependencyError, RenderError

_LOG = logging.getLogger("palubicki.render")
_MAX_PIXELS = 50_000_000  # guard against --size 99999x99999


def _flatten(mesh: Mesh) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Concatenate all primitives into flat arrays for rendering.

    Returns:
        tri:   (T, 3, 3) float32 — T triangles, each as 3 vertices in 3D
        norm:  (T, 3)    float32 — unit-length face normal per triangle
        col:   (T, 3)    float32 — RGB face color from primitive's base_color
    """
    tris: list[np.ndarray] = []
    norms: list[np.ndarray] = []
    cols: list[np.ndarray] = []

    for p in mesh.primitives:
        idx = p.indices.reshape(-1, 3)
        # Triangle vertex positions
        tris.append(p.positions[idx].astype(np.float32, copy=False))
        # Face normal = mean of vertex normals, then renormalized
        n = p.normals[idx].astype(np.float32, copy=False).mean(axis=1)
        n /= np.linalg.norm(n, axis=1, keepdims=True).clip(1e-9)
        norms.append(n)
        # Face color: mean of triangle's vertex colors when present, else primitive base_color.
        if p.colors is not None and p.colors.shape[0] == p.positions.shape[0]:
            face_rgb = p.colors[idx].astype(np.float32, copy=False).mean(axis=1)
            cols.append(face_rgb)
        else:
            rgb = np.asarray(p.material.base_color[:3], dtype=np.float32)
            cols.append(np.broadcast_to(rgb, (idx.shape[0], 3)).copy())

    if not tris:
        # Empty mesh — caller should have caught this earlier.
        empty = np.zeros((0, 3, 3), dtype=np.float32)
        return empty, np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.float32)

    return np.concatenate(tris), np.concatenate(norms), np.concatenate(cols)


def _shade(
    normals: np.ndarray,
    face_colors: np.ndarray,
    light_dir: tuple[float, float, float],
) -> np.ndarray:
    """Flat Lambert shading with implicit double-sided faces.

    intensity = abs(n · -L)        # abs() = both sides of leaf quads light up
    factor    = ambient + (1 - ambient) * intensity
    output    = clip(color * factor, 0, 1)
    """
    L = np.asarray(light_dir, dtype=np.float32)
    L /= np.linalg.norm(L).clip(1e-9)
    intensity = np.abs(normals @ -L).clip(0, 1)
    ambient = 0.25
    factor = ambient + (1.0 - ambient) * intensity
    return (face_colors * factor[:, None]).clip(0, 1)


def _validate_size(size: tuple[int, int]) -> None:
    w, h = size
    if w <= 0 or h <= 0:
        raise ValueError(f"size must be positive, got {size}")
    if w * h > _MAX_PIXELS:
        raise ValueError(f"size {size} exceeds {_MAX_PIXELS} pixel guard")


def _mesh_bbox(mesh: Mesh) -> tuple[np.ndarray, np.ndarray]:
    all_pos = np.concatenate([p.positions for p in mesh.primitives])
    return all_pos.min(axis=0), all_pos.max(axis=0)


def _apply_camera(ax, camera: Camera, lo: np.ndarray, hi: np.ndarray) -> None:
    """Set matplotlib 3D axes limits + view orientation from Camera."""
    ax.view_init(elev=camera.elevation_deg, azim=camera.azimuth_deg)

    # Center axes on camera.target with half-extent driven by camera.distance
    # if provided, otherwise by the bbox itself plus margin.
    cx, cy, cz = camera.target
    if camera.distance is not None:
        half = camera.distance * 0.5
    else:
        half = float((hi - lo).max()) * 0.5 * (1.0 + camera.margin)

    ax.set_xlim(cx - half, cx + half)
    # In matplotlib's mplot3d, axis "z" is the up axis. We use Y-up convention
    # in palubicki, so we swap Y and Z when feeding matplotlib.
    ax.set_ylim(cz - half, cz + half)
    ax.set_zlim(cy - half, cy + half)


def render_mesh(
    mesh: Mesh,
    *,
    size: tuple[int, int] = (800, 800),
    camera: Camera | None = None,
    bg: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
    light_dir: tuple[float, float, float] = (-0.3, -1.0, -0.5),
    drop_leaves: bool = False,  # kept for symmetry with render_glb; no-op on Mesh
) -> np.ndarray:
    """Render a Mesh to an (H, W, 4) uint8 RGBA ndarray. Matplotlib backend."""
    _validate_size(size)

    total_tris = sum(len(p.indices) // 3 for p in mesh.primitives)
    if total_tris == 0:
        raise RenderError("mesh has no triangles to render")

    # Bbox + degenerate check
    lo, hi = _mesh_bbox(mesh)
    if float((hi - lo).max()) < 1e-9:
        raise RenderError("mesh bounding box is degenerate (extent ≈ 0)")

    if camera is None:
        camera = Camera.fit(mesh)

    # Lazy matplotlib import — raises RenderDependencyError if missing.
    try:
        import matplotlib
        matplotlib.use("Agg")  # MUST be before pyplot
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    except ImportError as e:
        raise RenderDependencyError(
            "matplotlib is required for rendering; install with: "
            "pip install -e '.[render]'"
        ) from e
    from PIL import Image

    t0 = time.perf_counter()
    tri, norms, cols = _flatten(mesh)
    shaded = _shade(norms, cols, light_dir)

    # Swap Y and Z for matplotlib (mplot3d treats Z as up, palubicki is Y-up)
    tri_swap = tri[..., [0, 2, 1]]

    dpi = 100
    fig = plt.figure(figsize=(size[0] / dpi, size[1] / dpi), dpi=dpi)
    fig.patch.set_facecolor(bg[:3])
    fig.patch.set_alpha(bg[3])
    ax = fig.add_subplot(111, projection="3d", computed_zorder=False)
    ax.set_axis_off()
    ax.set_proj_type("persp")
    ax.set_box_aspect((1, 1, 1))
    # Make 3D axes fill the figure so bbox_inches='tight' produces an image
    # close to the requested size (the default axes leave large empty margins).
    ax.set_position([0, 0, 1, 1])

    coll = Poly3DCollection(tri_swap, facecolors=shaded, edgecolors="none", linewidth=0)
    ax.add_collection3d(coll)
    _apply_camera(ax, camera, lo, hi)

    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=dpi,
        bbox_inches="tight", pad_inches=0,
        facecolor=fig.get_facecolor(),
        transparent=(bg[3] < 1.0),
    )
    plt.close(fig)

    img = np.asarray(Image.open(buf).convert("RGBA"))
    _LOG.info(
        "rendered %dx%d, %d triangles, took %.0fms",
        img.shape[1], img.shape[0], total_tris,
        (time.perf_counter() - t0) * 1000,
    )
    return img


def render_glb(
    glb_path: Path,
    *,
    size: tuple[int, int] = (800, 800),
    camera: Camera | None = None,
    bg: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
    light_dir: tuple[float, float, float] = (-0.3, -1.0, -0.5),
    drop_leaves: bool = False,
) -> np.ndarray:
    """Load a .glb and render it to an (H, W, 4) uint8 ndarray."""
    from palubicki.render.io import _glb_to_mesh
    mesh = _glb_to_mesh(Path(glb_path), drop_leaves=drop_leaves)
    return render_mesh(
        mesh, size=size, camera=camera, bg=bg, light_dir=light_dir,
    )
