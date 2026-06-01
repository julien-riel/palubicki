from __future__ import annotations

import dataclasses
from pathlib import Path

from palubicki.config import Config, ConfigError, GeomConfig
from palubicki.geom import maps
from palubicki.geom._textures import (
    _PROC_TEXTURES,
    bark_height_for,
    default_leaf_png,
    leaf_vein_mask,
)
from palubicki.geom.bark_blend import BarkBlendStops
from palubicki.geom.compound_leaf import build_rachis_primitive, resolve_leaflet_blade
from palubicki.geom.leaves import build_leaves_primitive
from palubicki.geom.mesh import Material, Mesh
from palubicki.geom.tubes import build_bark_primitive
from palubicki.sim.tree import Tree

# Leaf back-light tint (KHR_materials_diffuse_transmission colour): warm
# transmitted green so a leaf lit from behind glows instead of going black.
_LEAF_TRANSMISSION_COLOR = (0.50, 0.65, 0.25)


def build_mesh(tree: Tree, cfg: Config) -> Mesh:
    g = cfg.geom
    bark_png = _resolve_texture(g.bark_texture)
    bark_normal_png, bark_orm_png = _bark_maps(g)
    bark_mat = Material(
        name="bark",
        base_color=(*g.bark_color, 1.0),
        metallic=0.0,
        roughness=0.9,
        base_color_texture_png=bark_png,
        alpha_mode="OPAQUE",
        alpha_cutoff=0.5,
        double_sided=False,
        normal_texture_png=bark_normal_png,
        normal_scale=1.0,
        orm_texture_png=bark_orm_png,
        specular_factor=(g.bark_specular if (g.enable_pbr_maps and g.bark_specular > 0) else None),
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

    if g.enable_leaves:
        leaf_png = _resolve_texture(g.leaf_texture)
        if leaf_png is None:
            leaf_png = default_leaf_png()
        leaf_maps = _leaf_maps(g)
        leaf_mat = Material(
            name="leaf",
            base_color=(0.4, 0.6, 0.2, 1.0),
            metallic=0.0,
            roughness=0.85,
            base_color_texture_png=leaf_png,
            alpha_mode="MASK",
            alpha_cutoff=0.5,
            double_sided=True,
            **leaf_maps,
        )
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
            blade_fold_deg=g.leaf_blade_fold_deg,
            blade_curl=g.leaf_blade_curl,
        )
        if g.leaf_season_variants and g.leaf_autumn_color is not None:
            # KHR_materials_variants: discrete season swap (summer = the green
            # base material, autumn = same maps with an autumn base colour). The
            # primitive's default material stays summer for variant-unaware viewers.
            autumn_mat = dataclasses.replace(
                leaf_mat, name="leaf_autumn", base_color=(*g.leaf_autumn_color, 1.0)
            )
            leaf_prim.material_variants = [("summer", leaf_mat), ("autumn", autumn_mat)]
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


def _bark_maps(g: GeomConfig) -> tuple[bytes | None, bytes | None]:
    """(normal_png, ORM_png) for the bark material, or (None, None).

    Only proc bark has a clean height field to bake from (design §6.3 — never a
    lit photo); file/None bark stays flat-normal. ORM = cavity-AO (R) + a matte
    roughness (G) + zero metal (B)."""
    if not g.enable_pbr_maps:
        return None, None
    name = str(g.bark_texture) if g.bark_texture is not None else None
    height = bark_height_for(name)
    if height is None:
        return None, None
    normal_png = maps.height_to_normal_png(height, strength=g.bark_normal_strength)
    occ = maps.occlusion_from_height(height, strength=0.7)
    orm_png = maps.pack_orm_png(occ, 0.9, 0.0)
    return normal_png, orm_png


def _leaf_maps(g: GeomConfig) -> dict:
    """Material kwargs for the leaf PBR maps (vein normal, ORM, back-light mask).

    Baked from a UV-aligned vein/midrib source: the lamina is the waxy, slightly
    occluded, translucent body; the veins/midrib are matte, raised in relief, and
    opaque to back-light. Empty when ``enable_pbr_maps`` is off."""
    if not g.enable_pbr_maps:
        return {}
    vein = leaf_vein_mask(shape=g.leaf_shape)  # 1 = lamina, →0 over veins/midrib/base
    rough = 0.55 + 0.35 * (1.0 - vein)         # veins rougher than the waxy lamina
    occ = 0.70 + 0.30 * vein                   # veins faintly self-occlude
    out: dict = {
        "normal_texture_png": maps.height_to_normal_png(
            vein, strength=g.leaf_normal_strength, wrap_x=False, wrap_y=False),
        "normal_scale": 1.0,
        "orm_texture_png": maps.pack_orm_png(occ, rough, 0.0),
    }
    if g.leaf_specular > 0:
        out["specular_factor"] = g.leaf_specular
    if g.leaf_translucency > 0:
        out["transmission_texture_png"] = maps.translucency_png(
            vein, color=_LEAF_TRANSMISSION_COLOR)
        out["diffuse_transmission_factor"] = g.leaf_translucency
        out["diffuse_transmission_color"] = _LEAF_TRANSMISSION_COLOR
    return out


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
