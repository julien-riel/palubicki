from __future__ import annotations

from pathlib import Path

from palubicki.config import Config, ConfigError, GeomConfig
from palubicki.geom._textures import _PROC_TEXTURES, default_leaf_png
from palubicki.geom.bark_blend import BarkBlendStops
from palubicki.geom.compound_leaf import build_rachis_primitive, resolve_leaflet_blade
from palubicki.geom.leaves import build_leaves_primitive
from palubicki.geom.mesh import Material, Mesh
from palubicki.geom.tubes import build_bark_primitive
from palubicki.sim.tree import Tree


def build_mesh(tree: Tree, cfg: Config) -> Mesh:
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
    stops = _bark_blend_stops(cfg.geom)
    bark_prim = build_bark_primitive(
        tree,
        ring_sides=cfg.geom.ring_sides,
        material=bark_mat,
        flare_height=cfg.geom.root_flare_height,
        flare_factor=cfg.geom.root_flare_factor,
        flare_falloff=cfg.geom.root_flare_falloff,
        buttress_count=cfg.geom.root_buttress_count,
        buttress_amplitude=cfg.geom.root_buttress_amplitude,
        flare_variation=cfg.geom.root_flare_variation,
        seed=cfg.seed,
        stops=stops,
    )
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
        g = cfg.geom
        is_compound = g.leaf_kind != "simple"
        if is_compound:
            lshape, lmargin, laspect = resolve_leaflet_blade(g)
            leaflet_specs = {
                "leaflet_count": g.leaflet_count,
                "leaflet_pair_count": g.leaflet_pair_count,
                "terminal_leaflet": g.terminal_leaflet,
                "rachis_length": g.rachis_length_ratio,
                "petiole_length": g.petiole_length_ratio,
                "rachis_radius": g.rachis_radius_ratio,
                "petiole_taper": 1.0,
                "leaflet_shape": lshape,
                "leaflet_margin": lmargin,
                "leaflet_aspect": laspect,
            }
        else:
            leaflet_specs = {
                "leaflet_count": 1,
                "leaflet_pair_count": 0,
                "terminal_leaflet": False,
                "rachis_length": 0.0,
                "petiole_length": g.petiole_length_ratio,
                "rachis_radius": g.petiole_radius_ratio,
                "petiole_taper": g.petiole_taper,
            }
        leaf_prim = build_leaves_primitive(
            tree,
            leaf_size=g.leaf_size,
            material=leaf_mat,
            aspect=g.leaf_aspect,
            splay_deg=g.leaf_splay_deg,
            droop_deg=g.petiole_droop_deg,
            foliage_depth=g.foliage_depth,
            needle_cluster_spacing=g.needle_cluster_spacing,
            sun_shade_k=g.leaf_sun_shade_k,
            leaf_shape=g.leaf_shape,
            leaf_margin=g.leaf_margin,
            leaf_margin_depth=g.leaf_margin_depth,
            leaf_margin_count=g.leaf_margin_count,
            leaf_kind=g.leaf_kind,
            leaflet_specs=leaflet_specs,
            autumn_color=g.leaf_autumn_color,
        )
        primitives.append(leaf_prim)

        stem_mat = Material(
            name=("rachis" if is_compound else "petiole"),
            base_color=((*g.bark_color, 1.0) if is_compound else (*g.petiole_color, 1.0)),
            metallic=0.0,
            roughness=0.9,
            base_color_texture_png=None,
            alpha_mode="OPAQUE",
            alpha_cutoff=0.5,
            double_sided=False,
        )
        stem_prim = build_rachis_primitive(
            tree,
            material=stem_mat,
            leaf_size=g.leaf_size,
            foliage_depth=g.foliage_depth,
            leaf_kind=g.leaf_kind,
            leaflet_specs=leaflet_specs,
            ring_sides=(max(3, g.ring_sides // 2) if is_compound else max(3, g.petiole_sides)),
            needle_cluster_spacing=g.needle_cluster_spacing,
            sun_shade_k=g.leaf_sun_shade_k,
            splay_deg=g.leaf_splay_deg,
            droop_deg=g.petiole_droop_deg,
        )
        if stem_prim.positions.shape[0] > 0:
            primitives.append(stem_prim)

    return Mesh(primitives=primitives)


def _bark_blend_stops(geom: GeomConfig) -> BarkBlendStops | None:
    """Assemble blend stops from GeomConfig; None when blend is disabled.

    Gated on bark_tint_young. Mature falls back to bark_color; senescent falls
    back to mature (two-way blend)."""
    if geom.bark_tint_young is None:
        return None
    mature = geom.bark_tint_mature if geom.bark_tint_mature is not None else geom.bark_color
    senescent = geom.bark_tint_senescent if geom.bark_tint_senescent is not None else mature
    return BarkBlendStops(
        d_young=geom.bark_blend_diameter_young,
        d_mature=geom.bark_blend_diameter_mature,
        d_senescent=geom.bark_blend_diameter_senescent,
        c_young=tuple(geom.bark_tint_young),
        c_mature=tuple(mature),
        c_senescent=tuple(senescent),
    )


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
