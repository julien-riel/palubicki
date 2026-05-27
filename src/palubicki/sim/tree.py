from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

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
    parent_node: "Node"
    age: int = 0
    state: BudState = BudState.ACTIVE
    low_quality_steps: int = 0
    low_light_steps: int = 0


@dataclass(eq=False)
class Node:
    position: np.ndarray
    parent_internode: Optional["Internode"] = None
    children_internodes: list["Internode"] = field(default_factory=list)
    terminal_bud: Optional[Bud] = None
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
