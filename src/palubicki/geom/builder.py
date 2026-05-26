from __future__ import annotations

from pathlib import Path

from palubicki.config import Config, ConfigError
from palubicki.geom._textures import _PROC_TEXTURES, default_leaf_png
from palubicki.geom.leaves import build_leaves_primitive
from palubicki.geom.mesh import Material, Mesh
from palubicki.geom.radii import compute_radii
from palubicki.geom.tubes import build_bark_primitive
from palubicki.sim.tree import Tree


def build_mesh(tree: Tree, cfg: Config) -> Mesh:
    compute_radii(tree, r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent)

    bark_png = _resolve_texture(cfg.geom.bark_texture)
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
        leaf_png = _resolve_texture(cfg.geom.leaf_texture)
        if leaf_png is None:
            leaf_png = default_leaf_png()
        leaf_mat = Material(
            name="leaf",
            base_color=(0.4, 0.6, 0.2, 1.0),
            metallic=0.0,
            roughness=0.85,
            base_color_texture_png=leaf_png,
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


def _resolve_texture(value: Path | str | None) -> bytes | None:
    if value is None:
        return None
    s = str(value)
    if s.startswith("proc:"):
        name = s[5:]
        if name not in _PROC_TEXTURES:
            raise ConfigError(
                f"unknown proc texture: {name!r} (expected one of {sorted(_PROC_TEXTURES)})"
            )
        return _PROC_TEXTURES[name]()
    return Path(s).read_bytes()
