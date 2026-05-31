from __future__ import annotations

import math
from dataclasses import dataclass

# Leaflet placement in the leaf's local (u, v) frame, in whole-leaf-size units.
#   origin_uv  : (u, v) petiole-attachment point of the leaflet
#   axis_angle : radians; leaflet v-axis = cos(a)*leaf_up + sin(a)*rot_axis_u
#   scale      : leaflet size as a multiple of the whole-leaf size
Leaflet = tuple[tuple[float, float], float, float]
# Rachis centerline segment: (start_uv, end_uv, radius) in size-units.
RachisSeg = tuple[tuple[float, float], tuple[float, float], float]

_OUTWARD = math.radians(60.0)   # pinnate leaflet splay from the rachis
_FAN = math.radians(55.0)       # palmate half-fan half-angle


@dataclass(frozen=True)
class CompoundLayout:
    leaflets: list[Leaflet]
    rachis_segments: list[RachisSeg]


def compound_layout(
    kind: str,
    *,
    leaflet_count: int,
    leaflet_pair_count: int,
    terminal_leaflet: bool,
    rachis_length: float,
    petiole_length: float,
    rachis_radius: float,
) -> CompoundLayout:
    if kind == "simple":
        return CompoundLayout(leaflets=[((0.0, 0.0), 0.0, 1.0)], rachis_segments=[])
    if kind == "pinnate":
        return _pinnate(leaflet_count, terminal_leaflet, rachis_length,
                        petiole_length, rachis_radius)
    if kind == "palmate":
        return _palmate(leaflet_count, petiole_length, rachis_radius)
    if kind == "bipinnate":
        return _bipinnate(leaflet_pair_count, leaflet_count, rachis_length,
                          petiole_length, rachis_radius)
    raise ValueError(f"unknown compound leaf kind: {kind!r}")


def _pinnate(n_lat, terminal, rachis_length, petiole_length, radius):
    leaflets: list[Leaflet] = []
    v0, v1 = petiole_length, petiole_length + rachis_length
    n_levels = max(1, math.ceil(n_lat / 2))
    spacing = (v1 - v0) / n_levels
    lscale = min(0.6, 0.9 * spacing)
    placed = 0
    for i in range(n_levels):
        v = v0 + (i + 0.5) * spacing
        # right then left
        leaflets.append(((0.0, v), _OUTWARD, lscale))
        placed += 1
        if placed < n_lat:
            leaflets.append(((0.0, v), -_OUTWARD, lscale))
            placed += 1
    if terminal:
        leaflets.append(((0.0, v1), 0.0, lscale))
    segs: list[RachisSeg] = [
        ((0.0, 0.0), (0.0, v0), radius),
        ((0.0, v0), (0.0, v1), radius),
    ]
    return CompoundLayout(leaflets=leaflets, rachis_segments=segs)


def _palmate(n, petiole_length, radius):
    leaflets: list[Leaflet] = []
    lscale = 0.8
    if n == 1:
        angles = [0.0]
    else:
        angles = [(-_FAN + 2 * _FAN * k / (n - 1)) for k in range(n)]
    for a in angles:
        leaflets.append(((0.0, petiole_length), a, lscale))
    segs: list[RachisSeg] = (
        [((0.0, 0.0), (0.0, petiole_length), radius)] if petiole_length > 0 else []
    )
    return CompoundLayout(leaflets=leaflets, rachis_segments=segs)


def _bipinnate(pair_count, leaflets_per, rachis_length, petiole_length, radius):
    leaflets: list[Leaflet] = []
    segs: list[RachisSeg] = [
        ((0.0, 0.0), (0.0, petiole_length), radius),
        ((0.0, petiole_length), (0.0, petiole_length + rachis_length), radius),
    ]
    v0, v1 = petiole_length, petiole_length + rachis_length
    n_levels = max(1, pair_count)
    spacing = (v1 - v0) / n_levels
    sec_len = 0.7 * spacing * leaflets_per  # secondary rachis length
    lscale = min(0.4, 0.9 * spacing)
    side_count = 0
    for i in range(n_levels):
        v = v0 + (i + 0.5) * spacing
        for sign in (+1.0, -1.0):
            if side_count >= pair_count:
                break
            sec_ang = sign * _OUTWARD
            # secondary direction unit vector in (u, v): (sin, cos) of sec_ang
            du, dv = math.sin(sec_ang), math.cos(sec_ang)
            base_u, base_v = 0.0, v
            end_u, end_v = base_u + du * sec_len, base_v + dv * sec_len
            segs.append(((base_u, base_v), (end_u, end_v), radius * 0.6))
            for j in range(leaflets_per):
                t = (j + 0.5) / leaflets_per
                ou, ov = base_u + du * sec_len * t, base_v + dv * sec_len * t
                # sub-leaflet angled outward from the secondary on alternating sides
                sub = sec_ang + (_OUTWARD if j % 2 == 0 else -_OUTWARD)
                leaflets.append(((ou, ov), sub, lscale))
            side_count += 1
    return CompoundLayout(leaflets=leaflets, rachis_segments=segs)


def resolve_leaflet_blade(geom) -> tuple[str, str, float]:
    """(shape, margin, aspect) for a leaflet: leaflet_* overrides, else inherit
    the simple-leaf values."""
    shape = geom.leaflet_shape if geom.leaflet_shape is not None else geom.leaf_shape
    margin = geom.leaflet_margin if geom.leaflet_margin is not None else geom.leaf_margin
    aspect = geom.leaflet_aspect if geom.leaflet_aspect is not None else geom.leaf_aspect
    return shape, margin, aspect
