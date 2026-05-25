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

    # marker_idx -> (best_bud_idx, best_distance)
    claims: dict[int, tuple[int, float]] = {}
    candidate_lists: list[np.ndarray] = []

    for bi, bud in enumerate(buds):
        result.quality[bud] = 0
        result.direction[bud] = np.zeros(3, dtype=np.float64)
        idx = markers.query_radius(bud.position, r_perception)
        if len(idx) == 0:
            candidate_lists.append(idx)
            continue
        positions = markers.positions_for(idx)
        delta = positions - bud.position
        dist = np.linalg.norm(delta, axis=1)
        safe = dist > 1e-12
        dir_norm = np.zeros_like(delta)
        dir_norm[safe] = delta[safe] / dist[safe, None]
        cos_angle = dir_norm @ bud.direction
        in_cone = cos_angle >= cos_theta
        kept_idx = idx[in_cone & safe]
        kept_dist = dist[in_cone & safe]
        candidate_lists.append(kept_idx)
        for marker_id, d in zip(kept_idx.tolist(), kept_dist.tolist()):
            prev = claims.get(marker_id)
            if prev is None or d < prev[1]:
                claims[marker_id] = (bi, d)

    bud_to_markers: dict[int, list[int]] = {bi: [] for bi in range(len(buds))}
    for marker_id, (bi, _d) in claims.items():
        bud_to_markers[bi].append(marker_id)

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
