# src/palubicki/geom/wind.py
"""Wind authoring (export pipeline L1, design doc §6.1 + milestone P1).

A *read-only* derivation of the portable per-vertex wind contract from the frozen
FSPM graph. ``sim/`` is never mutated: this module only reads diameters, topology
and (bent) node positions, and returns scalars the geometry builders stamp onto
vertices.

The hierarchical (Crysis / GPU-Gems / SpeedTree-style) model has three tiers,
authored *once* here and consumed by per-engine shaders (the reference is
``edit/static/wind.js``):

- **Tier 0 GLOBAL** (trunk) — low-frequency sway of the whole tree, pivot at the
  collar.
- **Tier 1 BRANCH** (primaries) — each branch oscillates about its own base
  pivot, amplitude growing with flexibility ``1 - stiffness`` (thick = barely
  moves, thin = whips), phase desynchronised per branch.
- **Tier 2 DETAIL** (deeper axes + leaves) — per-leaf flutter along the normal.

Portable encoding (the hard constraint, design correction #3 — three.js / Unity
silently drop ``_underscore`` attributes, and glTF restricts ``TEXCOORD_n`` to
VEC2 so the design's "TEXCOORD_1 = pivot (VEC3)" is split across two channels):

    COLOR_0   VEC3  (phase, stiffness, leafMask)   ← this module's output
    COLOR_1   VEC3  tint (autumn / bark age)
    TEXCOORD_1 VEC2 (pivot.x, pivot.y)
    TEXCOORD_2 VEC2 (pivot.z, wind_tier)
    TANGENT   VEC4  (xyz, MikkTSpace handedness)   ← unblocks normal maps (P2)

``phase`` is hashed from a *stable* identity — the axis base's structural
position plus the node's ordinal along its axis — never the global ``node_index``
(which the step-major substep loop interleaves across chains, so it is unstable;
design §6.1). ``stiffness`` is calibrated to THIS tree's real diameter range
(read at bake time, ~1.5-8.6 cm per the pipe model), so the motion hierarchy
survives pipe-model unit/exponent drift instead of pinning to a hardcoded span.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from palubicki.sim.tree import Node, Tree

# Tier ceiling: trunk = 0, primary branches = 1, everything deeper + leaves = 2
# (design §6.1: wind_tier = min(2, axis_order)).
WIND_TIER_MAX = 2

# Along-axis phase advance per node, in turns (the phase wheel is [0, 1)). Small,
# so bending reads as a slow travelling wave from each branch's base to its tip
# rather than the whole branch snapping in unison.
_PHASE_PER_NODE = 0.11

# Leaves are treated as near-maximally flexible regardless of the wood that bears
# them, so canopy detail always shimmers (stiffness near 0 -> flexibility near 1).
LEAF_STIFFNESS = 0.05


@dataclass(frozen=True)
class WindCalibration:
    """Per-tree stiffness calibration over THIS tree's real diameter range.

    ``stiffness`` maps the thinnest wood to 0 (fully flexible) and the thickest to
    1 (rigid), matching the design's ``clamp((diameter - d_min)/(d_max - d_min))``.
    Reading the span per-tree (not a constant) keeps the trunk-rigid / twig-whippy
    hierarchy intact even if the pipe model's units or exponent drift.
    """

    d_min: float
    d_max: float

    def stiffness(self, diameter: float) -> float:
        span = self.d_max - self.d_min
        if span <= 1e-9:
            # Degenerate (single diameter / no wood): treat everything as rigid so
            # a flat tree never develops spurious motion.
            return 1.0
        return float(min(1.0, max(0.0, (float(diameter) - self.d_min) / span)))


def calibrate(tree: Tree) -> WindCalibration:
    """Diameter range of every internode in ``tree`` (positive diameters only)."""
    d_min = math.inf
    d_max = -math.inf
    q: deque[Node] = deque([tree.root])
    while q:
        node = q.popleft()
        for iod in node.children_internodes:
            d = float(iod.diameter)
            if d > 0.0:
                d_min = min(d_min, d)
                d_max = max(d_max, d)
            q.append(iod.child_node)
    if d_min is math.inf or d_max is -math.inf:
        return WindCalibration(0.0, 1.0)
    return WindCalibration(d_min, d_max)


def tier(axis_order: int) -> int:
    """Clamp an axis order to a wind tier in {0, 1, 2}."""
    return min(WIND_TIER_MAX, max(0, int(axis_order)))


def _hash01(x: float, y: float, z: float) -> float:
    """Deterministic, position-stable scalar hash in [0, 1).

    The classic ``frac(sin(dot)·k)`` GLSL hash. Used to decorrelate neighbouring
    branch / leaf phases so the canopy never sways in lockstep. Branch phases
    (:func:`branch_phase` / :func:`branch_phase_series`) feed it the *structural*
    (pre-sag) axis-base position, so toggling sag never reshuffles the skeleton's
    phases; leaf phases (:func:`leaf_phase`) feed the bent leaf position, where
    per-cluster (needle) desync matters more than sag-toggle stability.
    """
    s = math.sin(x * 12.9898 + y * 78.233 + z * 37.719) * 43758.5453
    return s - math.floor(s)


_ZERO = np.zeros(3, dtype=np.float64)


def branch_phase(axis_base_pos: np.ndarray, ordinal: int, origin: np.ndarray = _ZERO) -> float:
    """Wind phase (turns, in [0, 1)) for a node ``ordinal`` steps along its axis.

    The base term is a spatial hash of the axis's attachment point, so sibling
    branches desynchronise; the ordinal term advances the phase along the axis,
    so a single branch bends as a travelling wave. The hash is taken on the
    position *relative to ``origin``* (the tree's collar) so two geometrically
    identical trees placed at different forest positions get the *same* wind and
    can share one instanced mesh; any inter-tree desync is left to the consuming
    engine's shader (derived per-instance from the instance transform / id), never
    baked into the shared phase. Inputs are stable (structural position + per-axis
    ordinal), never the global node index.
    """
    return float(branch_phase_series(axis_base_pos, int(ordinal) + 1, origin)[int(ordinal)])


def branch_phase_series(axis_base_pos: np.ndarray, count: int, origin: np.ndarray = _ZERO) -> np.ndarray:
    """Vectorised :func:`branch_phase` for ordinals ``0 .. count-1`` along one axis.

    The single source of the branch-phase formula — the geometry builders call this
    instead of re-deriving the hash inline, so the authored and tested formula
    cannot drift. ``axis_base_pos`` should be the *structural* (pre-sag) axis base.
    """
    p = np.asarray(axis_base_pos, dtype=np.float64) - origin
    base = _hash01(float(p[0]), float(p[1]), float(p[2]))
    return (base + _PHASE_PER_NODE * np.arange(max(0, int(count)), dtype=np.float64)) % 1.0


def axis_frames(tree: Tree) -> dict[int, tuple[np.ndarray, int]]:
    """Map ``id(node) -> (bent axis-base position, axis_order)`` for every node.

    The base is the branch pivot every vertex on that axis swings about: trunk
    nodes map to the collar; a lateral axis's nodes map to the attachment node
    where the lateral sprang. The order is the axis nesting depth (trunk 0, each
    lateral +1). Mirrors ``tubes._collect_chains`` so a leaf and the bark of the
    twig it hangs on share the *same* pivot AND the *same* tier — giving foliage a
    real tier-1 moment arm, while leaves on the (order-0) trunk stay tier 0 and so
    only get global sway, never a spurious whole-trunk swing about the collar.
    """
    out: dict[int, tuple[np.ndarray, int]] = {}
    root = tree.root
    root_base = np.asarray(root.position + root.sag_offset, dtype=np.float64)
    out[id(root)] = (root_base, 0)
    stack: list[tuple[Node, np.ndarray, int]] = [(root, root_base, 0)]
    while stack:
        node, axis_base, order = stack.pop()
        for iod in node.children_internodes:
            child = iod.child_node
            if iod.is_main_axis:
                out[id(child)] = (axis_base, order)             # same axis
                stack.append((child, axis_base, order))
            else:
                new_base = np.asarray(node.position + node.sag_offset, dtype=np.float64)
                out[id(child)] = (new_base, order + 1)          # lateral attaches here
                stack.append((child, new_base, order + 1))
    return out


def leaf_phase(position: np.ndarray, azimuth: float, origin: np.ndarray = _ZERO) -> float:
    """Wind phase (turns) for one leaf, desynchronised from its node siblings.

    Hashes the leaf's (bent) position *relative to ``origin``* (so identical trees
    stay instance-shareable, as in :func:`branch_phase`) and folds in the
    phyllotactic azimuth (as a fraction of a turn) so leaves seated at the same
    node still flutter out of step, giving per-leaf canopy shimmer.
    """
    p = np.asarray(position, dtype=np.float64) - origin
    ph = _hash01(float(p[0]), float(p[1]), float(p[2])) + float(azimuth) / (2.0 * math.pi)
    return float(ph - math.floor(ph))
