# src/palubicki/sim/space_competition.py
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from palubicki.sim.markers import MarkerCloud
from palubicki.sim.tree import Bud


@dataclass
class PerceptionResult:
    quality: dict[Bud, int] = field(default_factory=dict)
    direction: dict[Bud, np.ndarray] = field(default_factory=dict)


def perceive(
    buds: list[Bud],
    markers: MarkerCloud,
    *,
    r_perception: float,
    theta_perception_deg: float,
) -> PerceptionResult:
    """Compute Q(b) and v_perc(b) for each bud, with closest-bud competition."""
    result = PerceptionResult()
    if not buds:
        return result

    cos_theta = math.cos(math.radians(theta_perception_deg))

    # Pass 1 (Fix #6): batched KDTree radius query, then per-bud vector filtering.
    # We still allocate per-bud kept arrays because the cone test depends on the bud's
    # own direction; only the KDTree scan is hoisted out of the Python loop.
    for bud in buds:
        result.quality[bud] = 0
        result.direction[bud] = np.zeros(3, dtype=np.float64)
    bud_positions = np.asarray([bud.position for bud in buds], dtype=np.float64)
    idx_lists = markers.query_radius_batch(bud_positions, r_perception)
    per_bud_kept_idx: list[np.ndarray] = []
    per_bud_kept_dist: list[np.ndarray] = []
    per_bud_kept_cos: list[np.ndarray] = []
    for bud, idx in zip(buds, idx_lists, strict=True):
        if len(idx) == 0:
            per_bud_kept_idx.append(np.empty(0, dtype=np.intp))
            per_bud_kept_dist.append(np.empty(0, dtype=np.float64))
            per_bud_kept_cos.append(np.empty(0, dtype=np.float64))
            continue
        positions = markers.positions_for(idx)
        delta = positions - bud.position
        dist = np.linalg.norm(delta, axis=1)
        safe = dist > 1e-12
        dir_norm = np.zeros_like(delta)
        dir_norm[safe] = delta[safe] / dist[safe, None]
        cos_angle = dir_norm @ bud.direction
        in_cone = cos_angle >= cos_theta
        mask = in_cone & safe
        per_bud_kept_idx.append(idx[mask])
        per_bud_kept_dist.append(dist[mask])
        per_bud_kept_cos.append(cos_angle[mask])

    # Pass 2: vectorised closest-bud competition.
    # The original code inserted markers into a dict during the bud loop and later iterated
    # ``claims.items()`` in insertion order — meaning each bud's attributed markers ended up
    # in the order they were FIRST SEEN across all buds (i.e. concatenation order in bud_index
    # then marker order within bud). That ordering cascades into ``dir_norm.sum(axis=0)`` below,
    # so we must reproduce it bit-exactly to keep mesh goldens stable.
    lengths = np.fromiter((len(x) for x in per_bud_kept_idx), dtype=np.intp, count=len(buds))
    total = int(lengths.sum())
    if total > 0:
        all_mid = np.concatenate(per_bud_kept_idx)
        all_dist = np.concatenate(per_bud_kept_dist)
        all_cos = np.concatenate(per_bud_kept_cos)
        all_bi = np.repeat(np.arange(len(buds), dtype=np.intp), lengths)
        # Stable lexsort, keys listed least- to most-significant (last = primary):
        #   primary   = marker_id   (group the claims for each marker)
        #   secondary = distance    (nearest bud wins)
        #   tertiary  = -cos_angle  (on a distance tie, the bud whose cone the marker
        #               best aligns with wins — see below)
        #   quaternary= bud_index   (final deterministic tiebreak, was the original key)
        # The tertiary key resolves CO-LOCATED buds (a terminal and its laterals share
        # the emission point, so distance is identical for every marker). Without it the
        # tie fell through to bud_index, and since laterals are listed before the terminal
        # they captured every contested marker — starving the leader (no conifer spire).
        # By cone alignment instead, a vertical marker goes to the terminal and a side
        # marker to the lateral pointing at it. First occurrence per marker_id wins.
        order = np.lexsort((all_bi, -all_cos, all_dist, all_mid))
        sorted_mid = all_mid[order]
        sorted_bi = all_bi[order]
        keep = np.empty(len(sorted_mid), dtype=bool)
        keep[0] = True
        keep[1:] = sorted_mid[1:] != sorted_mid[:-1]
        winning_bi_by_mid = sorted_bi[keep]  # parallel to unique mids sorted asc
        # Restore original insertion order: sort winners by FIRST appearance in all_mid.
        # np.unique returns unique values sorted asc and the first index of each in all_mid,
        # which matches winning_bi_by_mid's order (both sorted by mid asc).
        _unique_mids, first_idx = np.unique(all_mid, return_index=True)
        order_by_insertion = np.argsort(first_idx)
        ordered_winning_mid = _unique_mids[order_by_insertion]
        ordered_winning_bi = winning_bi_by_mid[order_by_insertion]
        bud_to_markers: list[list[int]] = [[] for _ in range(len(buds))]
        for bi_val, mid_val in zip(
            ordered_winning_bi.tolist(), ordered_winning_mid.tolist(), strict=True
        ):
            bud_to_markers[bi_val].append(mid_val)
    else:
        bud_to_markers = [[] for _ in range(len(buds))]

    # Pass 3: compute Q and v_perc per bud from attributed markers.
    for bi, bud in enumerate(buds):
        attributed = bud_to_markers[bi]
        if not attributed:
            continue
        positions = markers.positions_for(attributed)
        delta = positions - bud.position
        dist = np.linalg.norm(delta, axis=1)
        safe = dist > 1e-12
        dir_norm = delta[safe] / dist[safe, None]
        result.quality[bud] = int(safe.sum())
        if result.quality[bud] > 0:
            v = dir_norm.sum(axis=0)
            n = np.linalg.norm(v)
            if n > 1e-12:
                result.direction[bud] = v / n
    return result
