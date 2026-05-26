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

    # Pass 1: per-bud candidate scan (still requires KDTree per bud).
    per_bud_kept_idx: list[np.ndarray] = []
    per_bud_kept_dist: list[np.ndarray] = []
    for bud in buds:
        result.quality[bud] = 0
        result.direction[bud] = np.zeros(3, dtype=np.float64)
        idx = markers.query_radius(bud.position, r_perception)
        if len(idx) == 0:
            per_bud_kept_idx.append(np.empty(0, dtype=np.intp))
            per_bud_kept_dist.append(np.empty(0, dtype=np.float64))
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
        all_bi = np.repeat(np.arange(len(buds), dtype=np.intp), lengths)
        # Stable lexsort: primary key = marker_id, secondary = distance. First occurrence per
        # marker_id wins (ties broken by smallest bud_index, matching the original strict ``<``).
        order = np.lexsort((all_dist, all_mid))
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
        for bi_val, mid_val in zip(ordered_winning_bi.tolist(), ordered_winning_mid.tolist()):
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
