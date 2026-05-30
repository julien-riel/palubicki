# tests/sim/test_phyllotaxy_per_axis.py
"""Issue #24: phyllotaxy azimuth must be driven by a per-axis ordinal, not the
global node_index.

test_phyllotaxy.py already covers lateral_bud_directions in isolation for
explicit node_index. These tests grow a real tree and assert the divergence
*delivered along each anatomical axis* matches the mode.

With the global-node_index bug the step-major substep loop interleaves the global
counter across all bud chains, so along a single axis consecutive nodes advance
the counter by a variable gap instead of +1 — scrambling spiral divergence and
collapsing decussate/distichous parity. A correct per-axis ordinal advances by
exactly +1 on every axis.

Oracle: we recover the ``base_azimuth`` the simulator fed each node by projecting
that node's first lateral-bud direction into the SAME in-plane frame
``lateral_bud_directions`` builds (perpendicular to the node's terminal-bud
direction ``d``). Measuring the bud directions rather than the grown internodes,
in the emission frame rather than the bent chain-tangent frame, makes the test
gauge-exact: the divergence step is ``mode_value`` to within float error on every
axis when the fix is in place (verified: max deviation 0.00° fixed vs up to 180°
on the buggy code), so a tight tolerance both proves the fix and guards the bug.
"""
import math
from pathlib import Path

import numpy as np

from palubicki.config import (
    Config,
    EnvelopeConfig,
    GeomConfig,
    LightConfig,
    PhyllotaxyConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
)
from palubicki.sim.phyllotaxy import _frame_perpendicular_to
from palubicki.sim.simulator import simulate

SEEDS = (0, 1, 2)
TOL_DEG = 0.5


def _make_cfg(mode, extra, seed):
    return Config(
        envelope=EnvelopeConfig(
            shape="ellipsoid", rx=2.0, ry=3.0, rz=2.0, marker_count=3000
        ),
        sim=SimConfig(max_simulation_years=12.0),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(
            mode=mode,
            divergence_jitter_deg=0.0,
            branch_angle_jitter_deg=0.0,
            **extra,
        ),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        light=LightConfig(enabled=False),
        seed=seed,
        output=Path("/tmp/_per_axis.glb"),
    )


def _base_azimuth_deg(lateral_dir, growth_dir):
    """Recover base_azimuth (deg) in the frame lateral_bud_directions used: the
    in-plane basis perpendicular to the node's terminal growth direction."""
    g = growth_dir / np.linalg.norm(growth_dir)
    right, up = _frame_perpendicular_to(g)
    perp = lateral_dir - np.dot(lateral_dir, g) * g
    return math.degrees(math.atan2(float(np.dot(perp, up)), float(np.dot(perp, right))))


def _axis_chains(root):
    """Lists of nodes, each following is_main_axis=True continuation. A lateral
    starts a fresh chain (its own anatomical axis)."""
    chains = []
    stack = [root]
    while stack:
        start = stack.pop()
        chain = [start]
        cur = start
        while True:
            nxt = None
            for iod in cur.children_internodes:
                if iod.is_main_axis:
                    nxt = iod.child_node
                else:
                    stack.append(iod.child_node)
            if nxt is None:
                break
            chain.append(nxt)
            cur = nxt
        chains.append(chain)
    return chains


def _whorl_member_azimuths(tree):
    """All lateral-bud azimuths (deg, in the emission frame) across every node on
    every anatomical axis. For whorled mode each node contributes whorl_count
    members; binning these across successive whorls reveals whether the whorls
    interleave or collapse onto a single set of ranks."""
    azs = []
    for chain in _axis_chains(tree.root):
        for node in chain:
            if node.terminal_bud is None or not node.lateral_buds:
                continue
            g = node.terminal_bud.direction
            for bud in node.lateral_buds:
                azs.append(_base_azimuth_deg(bud.direction, g) % 360.0)
    return azs


def _divergence_steps(tree):
    """Wrapped azimuth steps (deg) between successive nodes' first laterals along
    every anatomical axis."""
    steps = []
    for chain in _axis_chains(tree.root):
        azs = []
        for node in chain:
            if node.terminal_bud is None or not node.lateral_buds:
                azs.append(None)
                continue
            azs.append(
                _base_azimuth_deg(node.lateral_buds[0].direction, node.terminal_bud.direction)
            )
        for a, b in zip(azs, azs[1:], strict=False):
            if a is not None and b is not None:
                steps.append((b - a) % 360.0)
    return steps


def _circular_dist(a, b):
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _assert_mode(mode, extra, expected_deg, symmetric_180=False):
    """Assert every measured divergence step is within TOL of expected_deg.

    ``symmetric_180``: for decussate, each node carries a 180°-opposite pair, so
    measuring ``lateral_buds[0]`` reads the alternation as +expected on even→odd
    nodes and (expected+180) on odd→even nodes (e.g. 90° then 270°). Both encode
    the same physical 90° pair-rotation, so accept either. (origin/main's axes
    were too short to ever measure the back-step; the vigor model #20 grows axes
    long enough to expose it — a measurement artifact, not a chirality defect.)
    """
    checked = 0
    offenders = []
    for seed in SEEDS:
        steps = _divergence_steps(simulate(_make_cfg(mode, extra, seed)))
        for s in steps:
            checked += 1
            dist = _circular_dist(s, expected_deg)
            if symmetric_180:
                dist = min(dist, _circular_dist(s, expected_deg + 180.0))
            if dist > TOL_DEG:
                offenders.append(f"seed={seed} step={s:.2f}° (expected {expected_deg}°)")
    assert checked > 5, f"{mode}: too few measurable steps ({checked})"
    assert not offenders, (
        f"{mode} divergence off by > {TOL_DEG}° on {len(offenders)}/{checked} steps; "
        f"first few:\n  " + "\n  ".join(offenders[:8])
    )


def test_spiral_divergence_137_on_every_axis():
    """Spiral: every axis (trunk AND lateral branches) advances ~137.5°/node."""
    _assert_mode("alternate", {"divergence_angle_deg": 137.5}, 137.5)


def test_decussate_alternates_90_on_every_axis():
    """Decussate (maple): successive same-axis nodes rotate the pair ~90°."""
    _assert_mode("decussate", {"divergence_angle_deg": 0.0}, 90.0, symmetric_180=True)


def test_distichous_flips_180_on_every_axis():
    """Distichous: successive same-axis nodes flip ~180° (2-ranked)."""
    _assert_mode("distichous", {}, 180.0)


def test_whorled_interleaves_across_successive_whorls():
    """Issue #35: successive whorls must be rotationally offset so members
    interleave radially instead of stacking into whorl_count vertical ranks.

    Pine (whorl_count=5, divergence=72°=360/5) is the degenerate case the bug
    exposed: with no inter-whorl offset every whorl lands on the same 5 azimuths,
    so all measured member azimuths collapse to exactly whorl_count distinct
    directions. The half-spacing alternation offsets odd whorls by 36°, so the
    union across successive whorls occupies 2·whorl_count directions.

    Jitter is 0 in _make_cfg, so emission-frame azimuths are exact and bin to
    nearest degree cleanly (the per-axis oracle is gauge-exact to <0.01°)."""
    whorl_count = 5
    extra = {"whorl_count": whorl_count, "divergence_angle_deg": 72.0}
    distinct_by_seed = []
    for seed in SEEDS:
        tree = simulate(_make_cfg("whorled", extra, seed))
        binned = {round(a) % 360 for a in _whorl_member_azimuths(tree)}
        distinct_by_seed.append(len(binned))
    assert all(n > whorl_count for n in distinct_by_seed), (
        f"whorled azimuths stack into <= whorl_count ranks: distinct directions "
        f"per seed = {distinct_by_seed} (expected > {whorl_count})"
    )
