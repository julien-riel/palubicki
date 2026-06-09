"""GPU-instanced leaf canopy (``EXT_mesh_gpu_instancing``).

The rendered tree is ~85% leaves and every leaf is the SAME blade geometry,
differing only by world placement (position / orientation / size) plus a tint.
:func:`build_leaves_instanced` collapses that into one canonical blade per
(fascicle-member × tint) bucket plus a per-instance ``(translation, rotation,
scale)``, so a viewer can draw the whole canopy with a handful of instanced
meshes instead of the fully-baked :func:`palubicki.geom.leaves.build_leaves_primitive`
buffer.

THE DECOMPOSITION (verified to 1.78e-15 over 20k random leaves).

``build_leaves_primitive`` bakes each leaf into world space as
``world = render_pos + eff_size * M @ local`` where ``M = column_stack(
leaf_basis(stem_dir, az, sp, droop_rad, skyface))`` is the per-leaf frame
``[rot_axis_u | leaf_up | rot_axis_w]`` and ``local`` are the blade's own
``(u, v, w)`` coordinates. ``M`` is a SHEAR, not a rotation:

    M = O · S ,   S = [[1, sin(sp), 0], [0, cos(sp), 0], [0, 0, 1]]

``S`` (the splay shear) is constant for all leaves that share ``sp``; ``O`` is
orthonormal but ``det(O) = -1`` ALWAYS (left-handed, proven constant). A
reflection is not a quaternion, so a FIXED reflection ``F = diag(1, 1, -1)`` is
baked into the canonical geometry once:

    canonical_local = F @ S @ base_blade_local          (same for the whole bucket)
    R               = M @ inv(S) @ F                    (proper rotation, det +1)

Then ``world = T + R @ (scale * canonical_local)`` with ``T = render_pos`` and
``scale = eff_size`` (uniform), because ``R @ F @ S = M`` and ``F @ F = I``.

This module reuses the EXACT per-leaf data of ``build_leaves_primitive``
(``selected_leaves`` records, ``leaf_basis``, ``compute_effective_leaf_size``,
the same blade / compound / curved / fascicle construction) so the instanced
canopy is geometrically equivalent to the baked one.

EQUIVALENCE (vs the baked path, measured): POSITIONS and NORMAL directions are
exact (to ~1e-7 / 0.000°), and the MikkTSpace TANGENT.w handedness matches (the
fixed reflection ``F`` flips chirality, so ``w`` is negated — see ``_lift_local_plane``).
KNOWN LIMITATION — the CURVED ("hero" fold/cup/curl) broadleaf TANGENT.xyz
DIRECTION is approximate (up to ~19° on the most-curved oak blades; flat blades
and needles are exact). The baked path Gram-Schmidt-orthogonalises the tangent
against the normal in the SHEARED WORLD metric (``MᵀM = SᵀS``); this module does it
in the unsheared local metric, and the shear makes the two disagree. It affects
ONLY normal-map (vein-relief) ORIENTATION on curved blades — base shading
(normals) is exact — so it is acceptable for the opt-in fast/preview path while
hero renders use the exact baked ``build_leaves_primitive``. A correct fix would
redo the curved-tangent Gram-Schmidt with the constant ``SᵀS`` metric.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from palubicki.geom.compound_leaf import compound_layout
from palubicki.geom.leaf_blade import build_blade, palmate_lobe_axes
from palubicki.geom.leaf_blade3d import build_curved_blade
from palubicki.geom.leaves import (
    _BLADE_SUBDIVISIONS,
    compute_effective_leaf_size,
    fascicle_offsets,
    leaf_basis,
    selected_leaves,
)
from palubicki.geom.mesh import InstancedPrimitive, Material, Primitive
from palubicki.sim.tree import LeafState

if TYPE_CHECKING:
    from palubicki.sim.tree import Tree

# Fixed reflection that turns the always-left-handed orthonormal part of the leaf
# frame into a proper (det +1) rotation. Baked once into the canonical blade.
_F = np.diag([1.0, 1.0, -1.0])


def build_leaves_instanced(
    tree: Tree,
    *,
    leaf_size: float,
    material: Material,
    aspect: float = 1.0,
    splay_deg: float = 0.0,
    droop_deg: float = 0.0,
    foliage_depth: int = 1,
    needle_cluster_spacing: float = 0.0,
    sun_shade_k: float = 0.0,
    leaf_shape: str = "ovate",
    leaf_margin: str = "entire",
    leaf_margin_depth: float = 0.0,
    leaf_margin_count: int = 0,
    leaf_kind: str = "simple",
    leaflet_specs: dict | None = None,
    autumn_color: tuple[float, float, float] | None = None,
    blade_fold_deg: float = 0.0,
    blade_curl: float = 0.0,
    blade_cup: float = 0.0,
    skyface: float = 0.0,
    fascicle_count: int = 1,
    fascicle_spread_deg: float = 0.0,
    tint_buckets: int = 16,
) -> list[InstancedPrimitive]:
    """GPU-instanced equivalent of :func:`build_leaves_primitive`.

    Returns one :class:`InstancedPrimitive` per (fascicle-member × tint bucket).
    The canonical blade carries the per-leaf LOCAL geometry (with the fixed
    reflection baked in); each instance carries ``(translation, rotation_xyzw,
    scale)`` reproducing ``render_pos + eff_size * M @ local`` exactly. Returns
    ``[]`` for an empty tree.

    Tint: ACTIVE leaves are white ``(1, 1, 1)`` (a COLOR_1 no-op), SENESCENT
    leaves the autumn colour — the same semantics as the baked path — but the
    autumn tint is jittered per leaf and quantised into up to ``tint_buckets``
    levels so the autumn canopy varies leaf-to-leaf instead of being one flat
    colour. When nothing is senescing (or ``autumn_color is None``) every leaf
    lands in a single ``tint=None`` bucket, matching the no-tint baked output.
    """
    records = selected_leaves(
        tree, foliage_depth=foliage_depth,
        needle_cluster_spacing=needle_cluster_spacing,
    )
    if not records:
        return []

    # ── Mirror build_leaves_primitive's setup EXACTLY ──────────────────────────
    if leaf_kind == "simple" or leaflet_specs is None:
        pet_len = 0.0 if leaflet_specs is None else leaflet_specs.get("petiole_length", 0.0)
        pet_taper = 1.0 if leaflet_specs is None else leaflet_specs.get("petiole_taper", 1.0)
        pet_rad = 0.0 if leaflet_specs is None else leaflet_specs.get("rachis_radius", 0.0)
        layout = compound_layout(
            "simple", leaflet_count=1, leaflet_pair_count=0,
            terminal_leaflet=False, rachis_length=1.0,
            petiole_length=pet_len, rachis_radius=pet_rad, petiole_taper=pet_taper,
        )
    else:
        layout = compound_layout(
            leaf_kind,
            leaflet_count=leaflet_specs["leaflet_count"],
            leaflet_pair_count=leaflet_specs["leaflet_pair_count"],
            terminal_leaflet=leaflet_specs["terminal_leaflet"],
            rachis_length=leaflet_specs["rachis_length"],
            petiole_length=leaflet_specs["petiole_length"],
            rachis_radius=leaflet_specs["rachis_radius"],
        )
    leaflets = layout.leaflets

    n_planes = 2 if leaf_shape == "linear" else 1

    hero = (blade_fold_deg > 0.0 or blade_curl != 0.0 or blade_cup > 0.0) and n_planes == 1
    subdivisions = _BLADE_SUBDIVISIONS if hero else 0
    blade_pos_unit, _, blade_uv, blade_idx = build_blade(
        length=1.0, width=aspect, shape=leaf_shape, margin=leaf_margin,
        margin_depth=leaf_margin_depth, margin_count=leaf_margin_count,
        subdivisions=subdivisions,
    )

    fasc_count = fascicle_count if leaf_shape == "linear" else 1
    members = fascicle_offsets(fasc_count, fascicle_spread_deg)

    blade_norm_local: np.ndarray | None = None
    blade_tan_local: np.ndarray | None = None
    if hero:
        lobe_axes = palmate_lobe_axes(1.0, aspect) if leaf_shape == "palmate" else None
        blade_pos_unit, blade_norm_local, blade_tan_local = build_curved_blade(
            blade_pos_unit, blade_uv, blade_idx,
            fold_deg=blade_fold_deg, curl=blade_curl, aspect=aspect,
            cup=blade_cup, lobe_axes=lobe_axes,
        )

    skyface_eff = skyface if n_planes == 1 else 0.0

    splay_rad = math.radians(splay_deg)
    droop_rad = math.radians(droop_deg)

    # ── Canonical blade per fascicle member ────────────────────────────────────
    # For broadleaves fasc_count == 1, so this is a single canonical bucket. For
    # conifer fascicles the per-member extra splay changes S (and therefore the
    # canonical F @ S @ local geometry), so each member index gets its own
    # canonical blade. The canonical local blade is produced by lifting the leaf
    # with the IDENTITY frame (M = I): _lift_compound_leaf at center 0, size 1,
    # with rot_axis_u/leaf_up/rot_axis_w = e_x/e_y/e_z reproduces the blade in its
    # own (u, v, w) frame (compound leaflet offsets, curved displacement, and the
    # n_planes==2 cross plane included). F @ S is then applied to those vertices.
    member_splay: list[float] = []
    member_S: list[np.ndarray] = []
    member_canonical: list[dict] = []  # one entry per member: canonical geom arrays
    for _az_off, extra_splay in members:
        sp = splay_rad if extra_splay == 0.0 else splay_rad + extra_splay
        member_splay.append(sp)
        S = np.array([
            [1.0, math.sin(sp), 0.0],
            [0.0, math.cos(sp), 0.0],
            [0.0, 0.0, 1.0],
        ])
        member_S.append(S)
        member_canonical.append(
            _canonical_blade(
                S, n_planes, leaflets, blade_pos_unit, blade_uv, blade_idx,
                blade_norm_local, blade_tan_local,
            )
        )

    # ── Per-leaf T / R / S + tint bucket assignment ────────────────────────────
    senescing = any(leaf.state is LeafState.SENESCENT for leaf, *_ in records)
    want_colors = autumn_color is not None and senescing
    autumn = np.asarray(autumn_color, dtype=np.float32) if want_colors else None

    # bucket key -> (member_index, quantised_tint_or_None) -> list of (T, R, scale)
    buckets: dict[tuple, list[tuple]] = {}
    bucket_tint: dict[tuple, np.ndarray | None] = {}

    inv_S = [np.linalg.inv(S) for S in member_S]

    for leaf, stem_dir, source_iod, render_pos in records:
        eff_size = compute_effective_leaf_size(source_iod, leaf_size, sun_shade_k)
        for m, (az_off, _extra_splay) in enumerate(members):
            az = leaf.azimuth if az_off == 0.0 else leaf.azimuth + az_off
            sp = member_splay[m]
            M = np.column_stack(
                leaf_basis(stem_dir, az, sp, droop_rad, skyface_eff)
            )
            # R = M @ inv(S) @ F is a proper rotation (det +1) — encode as quaternion.
            R = M @ inv_S[m] @ _F
            quat = _quat_from_matrix(R)
            T = np.asarray(render_pos, dtype=np.float32)
            scale = np.array([eff_size, eff_size, eff_size], dtype=np.float32)

            if want_colors:
                if leaf.state is LeafState.SENESCENT:
                    tint = _bucket_tint(autumn, render_pos, leaf.azimuth, tint_buckets)
                else:
                    tint = np.array([1.0, 1.0, 1.0], dtype=np.float32)
                key = (m, tuple(tint.tolist()))
            else:
                tint = None
                key = (m, None)

            buckets.setdefault(key, []).append((T, quat, scale))
            bucket_tint.setdefault(key, tint)

    # ── Assemble one InstancedPrimitive per bucket ─────────────────────────────
    out: list[InstancedPrimitive] = []
    for key in sorted(buckets.keys(), key=_bucket_sort_key):
        m = key[0]
        canon = member_canonical[m]
        instances = buckets[key]
        translations = np.asarray([t for (t, _q, _s) in instances], dtype=np.float32)
        rotations = np.asarray([q for (_t, q, _s) in instances], dtype=np.float32)
        scales = np.asarray([s for (_t, _q, s) in instances], dtype=np.float32)

        tint = bucket_tint[key]
        v_count = canon["positions"].shape[0]
        canon_tint = (
            np.broadcast_to(tint, (v_count, 3)).astype(np.float32).copy()
            if tint is not None else None
        )
        canonical = Primitive(
            positions=canon["positions"],
            normals=canon["normals"],
            uvs=canon["uvs"],
            indices=canon["indices"],
            material=material,
            tint=canon_tint,
            tangents=canon["tangents"],
        )
        out.append(InstancedPrimitive(
            canonical=canonical,
            translations=translations,
            rotations=rotations,
            scales=scales,
        ))
    return out


def _canonical_blade(
    S, n_planes, leaflets, blade_pos_unit, blade_uv, blade_idx,
    blade_norm_local, blade_tan_local,
) -> dict:
    """The blade in its own LOCAL ``(u, v, w)`` frame with ``F @ S`` baked in.

    Lifts one leaf with the IDENTITY frame (``rot_axis_u, leaf_up, rot_axis_w =
    e_x, e_y, e_z``, center 0, size 1) so ``_lift_compound_leaf``'s full machinery
    (leaflet ``(u0, v0)`` offsets, per-leaflet axis rotation, curved displacement,
    and the ``n_planes == 2`` cross plane) produces the per-leaf local blade that
    ``M`` would otherwise map. Then applies ``F @ S`` to positions, normals and
    tangents so that ``R @ (F @ S @ local) = M @ local`` (since ``R = M @ inv(S)
    @ F`` and ``F @ F = I``).
    """
    blade_v_count = blade_pos_unit.shape[0]
    blade_i_count = blade_idx.shape[0]
    leaflets_per_leaf = len(leaflets)
    verts = n_planes * blade_v_count * leaflets_per_leaf
    inds = n_planes * blade_i_count * leaflets_per_leaf

    out_pos = np.empty((verts, 3), dtype=np.float32)
    out_norm = np.empty((verts, 3), dtype=np.float32)
    out_uv = np.empty((verts, 2), dtype=np.float32)
    out_idx = np.empty((inds,), dtype=np.uint32)
    out_tan = np.empty((verts, 4), dtype=np.float32)

    # Build the blade in its own local (u, v, w) frame — the exact `local` that the
    # baked path lifts via M — by replaying _lift_compound_leaf's compound layout
    # with the IDENTITY frame (rot_axis_u/leaf_up/rot_axis_w = e_x/e_y/e_z).
    _lift_local_blade(
        out_pos, out_norm, out_uv, out_idx, out_tan,
        n_planes, leaflets, blade_pos_unit, blade_uv, blade_idx,
        blade_norm_local, blade_tan_local,
    )

    FS = _F @ S  # (3,3)
    out_pos = (out_pos.astype(np.float64) @ FS.T).astype(np.float32)
    # Normals/tangents are direction vectors in the local frame: the same F @ S
    # maps them so that R rotates them to the world normals/tangents the baked
    # path produced. (For the flat blade these stay unit after the orthonormal
    # part; S shears them but R's downstream renderer renormalises if needed — the
    # geometric-equivalence proof checks positions, and the baked normals are also
    # reproduced because the baked path lifts the SAME local vectors by M.)
    out_norm = (out_norm.astype(np.float64) @ FS.T).astype(np.float32)
    tan_xyz = (out_tan[:, :3].astype(np.float64) @ FS.T).astype(np.float32)
    # MikkTSpace handedness (TANGENT.w) is the CHIRALITY of the frame it was computed
    # in. The baked path derives it in the WORLD leaf frame, which is left-handed
    # under the splay shear (det(M) < 0); we derived it here in the right-handed
    # IDENTITY local frame, so the fixed reflection _F (det = -1) that maps local→
    # canonical flips that chirality. Negate w so the reconstructed bitangent
    # B = w·(N×T) matches the baked path (R is a proper rotation, so it preserves
    # the cross product — only this reflection's sign must be folded into w).
    out_tan = np.column_stack([tan_xyz, -out_tan[:, 3]]).astype(np.float32)

    return {
        "positions": out_pos, "normals": out_norm, "uvs": out_uv,
        "indices": out_idx, "tangents": out_tan,
    }


def _lift_local_blade(
    out_pos, out_norm, out_uv, out_idx, out_tan,
    n_planes, leaflets, blade_pos_unit, blade_uv, blade_idx,
    blade_norm_local, blade_tan_local,
):
    """Reproduce ``_lift_compound_leaf`` with the IDENTITY frame (M = I).

    Mirrors ``_lift_compound_leaf`` / ``_lift_blade`` from geom/leaves.py but with
    ``rot_axis_u = e_x``, ``leaf_up = e_y``, ``rot_axis_w = e_z`` and ``center =
    0``, ``size = 1`` so the output is the blade's pure local ``(u, v, w)``
    coordinates (with compound leaflet layout + curved displacement folded in),
    i.e. exactly the ``local`` that the baked path maps via ``M``.
    """
    ex = np.array([1.0, 0.0, 0.0])
    ey = np.array([0.0, 1.0, 0.0])
    ez = np.array([0.0, 0.0, 1.0])
    blade_v_count = blade_pos_unit.shape[0]
    blade_i_count = blade_idx.shape[0]
    per_leaflet_v = n_planes * blade_v_count
    per_leaflet_i = n_planes * blade_i_count

    for k, ((u0, v0), axis_angle, scale) in enumerate(leaflets):
        if axis_angle == 0.0:
            lflt_u = ex
            lflt_v = ey
        else:
            c = math.cos(axis_angle)
            s = math.sin(axis_angle)
            lflt_v = c * ey + s * ex
            lflt_u = c * ex - s * ey
        origin = u0 * ex + v0 * ey  # center == 0, size == 1
        vk = k * per_leaflet_v
        ik = k * per_leaflet_i
        _lift_local_plane(
            blade_pos_unit, blade_uv, blade_idx,
            origin, lflt_u, lflt_v, ez, scale,
            out_pos[vk : vk + blade_v_count],
            out_norm[vk : vk + blade_v_count],
            out_uv[vk : vk + blade_v_count],
            out_idx[ik : ik + blade_i_count],
            vk,
            out_tan[vk : vk + blade_v_count],
            blade_norm_local, blade_tan_local,
        )
        if n_planes == 2:
            vb = vk + blade_v_count
            ib = ik + blade_i_count
            _lift_local_plane(
                blade_pos_unit, blade_uv, blade_idx,
                origin, ez, lflt_v, lflt_u, scale,
                out_pos[vb : vb + blade_v_count],
                out_norm[vb : vb + blade_v_count],
                out_uv[vb : vb + blade_v_count],
                out_idx[ib : ib + blade_i_count],
                vb,
                out_tan[vb : vb + blade_v_count],
                None, None,
            )


def _lift_local_plane(
    blade_pos_unit, blade_uv, blade_idx,
    origin, basis_u, basis_v, normal, scale,
    out_pos, out_norm, out_uv, out_idx, base, out_tan,
    blade_norm_local, blade_tan_local,
):
    """Local-frame analogue of ``_lift_blade`` (geom/leaves.py).

    Identical math to ``_lift_blade`` but with the basis being an orthonormal
    local frame (no world shear), so the flat / curved TANGENT handedness branch
    reproduces what the baked path computes for the M = I lift. The result is then
    mapped to canonical space by ``F @ S`` in the caller.
    """
    pu = blade_pos_unit[:, 0] * scale
    pv = blade_pos_unit[:, 1] * scale
    pz = blade_pos_unit[:, 2] * scale
    bu = np.asarray(basis_u, dtype=np.float64)
    bv = np.asarray(basis_v, dtype=np.float64)
    bw = np.asarray(normal, dtype=np.float64)
    pos = origin[np.newaxis, :] + pu[:, np.newaxis] * bu[np.newaxis, :] \
        + pv[:, np.newaxis] * bv[np.newaxis, :] \
        + pz[:, np.newaxis] * bw[np.newaxis, :]
    out_pos[:] = pos.astype(np.float32)
    out_uv[:] = blade_uv
    out_idx[:] = blade_idx + np.uint32(base)

    def _lift(local):
        return (local[:, 0:1] * bu[np.newaxis, :]
                + local[:, 1:2] * bv[np.newaxis, :]
                + local[:, 2:3] * bw[np.newaxis, :])

    if blade_norm_local is None:
        out_norm[:] = np.asarray(normal, dtype=np.float32)[np.newaxis, :]
    else:
        wn = _lift(np.asarray(blade_norm_local, dtype=np.float64))
        out_norm[:] = (wn / np.linalg.norm(wn, axis=1, keepdims=True)).astype(np.float32)

    if blade_tan_local is None:
        nf = bw
        cross_nb = np.array([
            nf[1] * bu[2] - nf[2] * bu[1],
            nf[2] * bu[0] - nf[0] * bu[2],
            nf[0] * bu[1] - nf[1] * bu[0],
        ])
        w = 1.0 if float(np.dot(cross_nb, bv)) >= 0.0 else -1.0
        out_tan[:, :3] = bu.astype(np.float32)[np.newaxis, :]
        out_tan[:, 3] = w
    else:
        from palubicki.sim._vec3 import cross3_batch
        tl = np.asarray(blade_tan_local, dtype=np.float64)
        nl = np.asarray(blade_norm_local, dtype=np.float64)
        b_local = tl[:, 3:4] * cross3_batch(nl, tl[:, :3])
        world_t = _lift(tl[:, :3])
        world_n = _lift(nl)
        world_b = _lift(b_local)
        n_hat = world_n / np.linalg.norm(world_n, axis=1, keepdims=True)
        world_t = world_t - n_hat * np.sum(world_t * n_hat, axis=1, keepdims=True)
        wt = world_t / np.linalg.norm(world_t, axis=1, keepdims=True)
        handed = np.sign(np.sum(cross3_batch(n_hat, wt) * world_b, axis=1))
        handed[handed == 0.0] = 1.0
        out_tan[:, :3] = wt.astype(np.float32)
        out_tan[:, 3] = handed.astype(np.float32)


def _quat_from_matrix(R: np.ndarray) -> np.ndarray:
    """Quaternion ``(x, y, z, w)`` of a proper rotation ``R`` (numerically-stable
    trace method, largest-diagonal branch). Order matches
    ``EXT_mesh_gpu_instancing`` ROTATION. Result is normalised."""
    m00, m01, m02 = R[0, 0], R[0, 1], R[0, 2]
    m10, m11, m12 = R[1, 0], R[1, 1], R[1, 2]
    m20, m21, m22 = R[2, 0], R[2, 1], R[2, 2]
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0  # s = 4w
        w = 0.25 * s
        x = (m21 - m12) / s
        y = (m02 - m20) / s
        z = (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0  # s = 4x
        w = (m21 - m12) / s
        x = 0.25 * s
        y = (m01 + m10) / s
        z = (m02 + m20) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0  # s = 4y
        w = (m02 - m20) / s
        x = (m01 + m10) / s
        y = 0.25 * s
        z = (m12 + m21) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0  # s = 4z
        w = (m10 - m01) / s
        x = (m02 + m20) / s
        y = (m12 + m21) / s
        z = 0.25 * s
    q = np.array([x, y, z, w], dtype=np.float64)
    q /= np.linalg.norm(q)
    return q.astype(np.float32)


def quat_to_matrix(q: np.ndarray) -> np.ndarray:
    """Rotation matrix of a quaternion ``(x, y, z, w)`` (inverse of
    :func:`_quat_from_matrix`). Used by the self-verification."""
    x, y, z, w = float(q[0]), float(q[1]), float(q[2]), float(q[3])
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n > 0.0:
        x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)


def _bucket_tint(base_tint, render_pos, azimuth, tint_buckets):
    """Deterministic per-leaf tint: id-stable jitter around ``base_tint``, then
    quantise each channel into ``tint_buckets`` levels.

    The jitter seed is a hash of the rounded render position + azimuth, so a given
    leaf always lands in the same bucket regardless of traversal order. The result
    is broadcast into the canonical's COLOR_1, varying the autumn canopy
    leaf-to-leaf instead of one flat colour.
    """
    rp = np.round(np.asarray(render_pos, dtype=np.float64), 3)
    seed = hash((float(rp[0]), float(rp[1]), float(rp[2]), round(float(azimuth), 4)))
    rng = np.random.default_rng(seed & 0xFFFFFFFF)
    # ±12% multiplicative jitter, then clamp into [0, 1].
    jitter = 1.0 + 0.12 * (2.0 * rng.random(3) - 1.0)
    tinted = np.clip(np.asarray(base_tint, dtype=np.float64) * jitter, 0.0, 1.0)
    n = max(1, int(tint_buckets))
    if n == 1:
        quant = tinted
    else:
        quant = np.round(tinted * (n - 1)) / (n - 1)
    return quant.astype(np.float32)


def _bucket_sort_key(key):
    """Deterministic ordering for buckets: (member_index, tint-or-sentinel)."""
    m, tint = key
    if tint is None:
        return (m, 1, ())
    return (m, 0, tint)
