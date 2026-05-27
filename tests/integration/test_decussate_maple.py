"""Phase 2C: end-to-end check that the maple preset produces decussate
lateral pairs (each consecutive pair rotated ~90° around the parent's axis)."""
import math

import numpy as np
import pytest

from palubicki.config import load_config
from palubicki.sim.simulator import simulate
from palubicki.sim.tree import BudState


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

    diffs = []
    for a, b in zip(azimuths_per_node, azimuths_per_node[1:]):
        delta = math.degrees(abs(((b - a + math.pi) % (2 * math.pi)) - math.pi))
        diffs.append(delta)
    median = float(np.median(diffs))
    assert 65.0 <= median <= 115.0, (
        f"expected median pair-to-pair azimuth diff ≈ 90°, got {median:.1f}°"
    )
