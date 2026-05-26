from __future__ import annotations

from pathlib import Path

from palubicki.config import Config
from palubicki.geom._textures import default_leaf_png
from palubicki.geom.leaves import build_leaves_primitive
from palubicki.geom.mesh import Material, Mesh
from palubicki.geom.radii import compute_radii
from palubicki.geom.tubes import build_bark_primitive
from palubicki.sim.tree import Tree


def build_mesh(tree: Tree, cfg: Config) -> Mesh:
    compute_radii(tree, r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent)

    bark_png = _load_bark_texture(cfg.geom.bark_texture)
    bark_mat = Material(
        name="bark",
        base_color=(*cfg.geom.bark_color, 1.0),
        metallic=0.0,
        roughness=0.9,
        base_color_texture_png=bark_png,
        alpha_mode="OPAQUE",
        alpha_cutoff=0.5,
        double_sided=False,
    )
    bark_prim = build_bark_primitive(tree, ring_sides=cfg.geom.ring_sides, material=bark_mat)
    primitives = [bark_prim]

    if cfg.geom.enable_leaves:
        png = _load_leaf_texture(cfg.geom.leaf_texture)
        leaf_mat = Material(
            name="leaf",
            base_color=(0.4, 0.6, 0.2, 1.0),
            metallic=0.0,
            roughness=0.85,
            base_color_texture_png=png,
            alpha_mode="MASK",
            alpha_cutoff=0.5,
            double_sided=True,
        )
        leaf_prim = build_leaves_primitive(
            tree,
            leaf_size=cfg.geom.leaf_size,
            material=leaf_mat,
            cluster_count=cfg.geom.leaf_cluster_count,
            aspect=cfg.geom.leaf_aspect,
            splay_deg=cfg.geom.leaf_splay_deg,
        )
        primitives.append(leaf_prim)

    return Mesh(primitives=primitives)


def _load_bark_texture(path: Path | None) -> bytes | None:
    if path is None:
        return None
    return path.read_bytes()


def _load_leaf_texture(path: Path | None) -> bytes:
    if path is None:
        return default_leaf_png()
    return path.read_bytes()
