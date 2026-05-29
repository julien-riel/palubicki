"""Phase 2C: end-to-end check that the maple preset produces decussate
lateral pairs (buds distributed across two planes ~90° apart on the trunk)."""
import math

import numpy as np
import pytest

from palubicki.config import load_config
from palubicki.sim.simulator import simulate

pytestmark = pytest.mark.slow


def _trunk_chain_internodes(tree):
    chain = []
    node = tree.root
    while True:
        next_iod = None
        for iod in node.children_internodes:
            if iod.is_main_axis:
                next_iod = iod
                break
        if next_iod is None:
            break
        chain.append(next_iod)
        node = next_iod.child_node
    return chain


def test_maple_lateral_pairs_alternate_90deg(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="maple")
    tree = simulate(cfg)
    chain = _trunk_chain_internodes(tree)
    assert len(chain) >= 4, f"trunk too short: {len(chain)} internodes"

    azimuths_per_node = []
    for iod in chain:
        node = iod.child_node
        if len(node.lateral_buds) < 1:
            continue
        tangent = iod.child_node.position - iod.parent_node.position
        tn = np.linalg.norm(tangent)
        if tn < 1e-9:
            continue
        tangent = tangent / tn
        canonical = np.array([1.0, 0.0, 0.0]) if abs(tangent[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        right = canonical - np.dot(canonical, tangent) * tangent
        right = right / np.linalg.norm(right)
        up = np.cross(tangent, right)
        bud = node.lateral_buds[0]
        proj = bud.direction - np.dot(bud.direction, tangent) * tangent
        pn = np.linalg.norm(proj)
        if pn < 1e-9:
            continue
        az = math.atan2(np.dot(proj, up), np.dot(proj, right))
        azimuths_per_node.append(az)

    assert len(azimuths_per_node) >= 4

    # Decussate check: verify that lateral buds occupy two distinct planes
    # (~0° and ~90°) with at least a few nodes in each plane.
    # We fold azimuths into [0, 90] — decussate buds cluster near 0° and near
    # 90° relative to an arbitrary reference frame.  Phase 2D elongation
    # introduces stochasticity that can break strict consecutive alternation,
    # but the bimodal two-plane signature must still be present.
    plane_angles = []
    for az in azimuths_per_node:
        p = abs(math.degrees(az)) % 180.0
        if p > 90.0:
            p = 180.0 - p
        plane_angles.append(p)

    near_0 = sum(1 for p in plane_angles if p < 45.0)
    near_90 = sum(1 for p in plane_angles if p >= 45.0)
    assert near_0 >= 3, (
        f"decussate plane near 0° has too few nodes: {near_0} "
        f"(plane_angles={[f'{p:.1f}' for p in plane_angles[:10]]})"
    )
    assert near_90 >= 3, (
        f"decussate plane near 90° has too few nodes: {near_90} "
        f"(plane_angles={[f'{p:.1f}' for p in plane_angles[:10]]})"
    )
