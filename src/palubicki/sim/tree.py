from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto

import numpy as np


class BudState(Enum):
    ACTIVE = auto()
    DORMANT = auto()
    DEAD = auto()
    RESERVE = auto()


@dataclass(eq=False)
class Bud:
    position: np.ndarray
    direction: np.ndarray
    axis_order: int
    parent_node: Node
    state: BudState = BudState.ACTIVE
    low_quality_steps: int = 0
    low_light_steps: int = 0
    # Phyllotactic ordinal along THIS bud's own anatomical axis: 0 for a bud that
    # starts an axis (the root, or a lateral beginning a new branch axis),
    # incrementing by 1 for each node the axis adds. Drives the divergence azimuth
    # in phyllotaxy.lateral_bud_directions. Unlike the global _SimState.node_index
    # — which the step-major substep loop interleaves across chains, so it does NOT
    # advance by a constant step along any single axis — this counter is per-axis,
    # giving correct spiral/decussate/distichous divergence on the real tree (#24).
    axis_node_ordinal: int = 0
    # EMA of this bud's per-iteration BH flux v_b. Governs the hysteresis
    # dormancy decision (recent_vigor < vigor_dormancy -> DORMANT) so a single
    # starved/lucky iteration cannot flip the bud's state. Updated each iteration.
    recent_vigor: float = 0.0


@dataclass(eq=False)
class Node:
    position: np.ndarray
    parent_internode: Internode | None = None
    children_internodes: list[Internode] = field(default_factory=list)
    terminal_bud: Bud | None = None
    lateral_buds: list[Bud] = field(default_factory=list)
    dormant_reserve_buds: list[Bud] = field(default_factory=list)
    # Set to True by sym.promote_lateral_if_failing when a lateral bud is
    # promoted to terminal at this node. Lets diagnostics count promotion
    # events without traversing structural geometry.
    sympodial_fork: bool = False
    sag_offset: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))


@dataclass(eq=False)
class Internode:
    parent_node: Node
    child_node: Node
    length: float
    is_main_axis: bool
    diameter: float = 0.0
    window: int = 5
    light_factor: float = 1.0
    birth_time: float = 0.0
    length_target: float = 0.0
    # The continuous BH flux v_b that produced this internode. Drives the
    # vigor-seeded tip radius in radii.py and the internode-length diagnostics.
    vigor: float = 0.0
    quality_history: deque[float] = field(init=False)

    def __post_init__(self) -> None:
        self.quality_history = deque(maxlen=self.window)

    def push_quality(self, q: float) -> None:
        self.quality_history.append(q)

    def average_quality(self) -> float:
        if not self.quality_history:
            return 0.0
        return sum(self.quality_history) / len(self.quality_history)


@dataclass
class Tree:
    root: Node
    active_buds: list[Bud] = field(default_factory=list)
    all_internodes: list[Internode] = field(default_factory=list)
