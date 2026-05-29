from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Clock:
    """Fractional-year simulation clock.

    ``t`` is the current simulation time in years; ``dt`` is the time advance
    per simulation iteration. ``year_fraction`` in [0, 1) is the phenology
    coordinate used to gate seasonal growth.
    """
    dt: float
    t: float = 0.0

    def tick(self) -> None:
        self.t += self.dt

    def year(self) -> int:
        return math.floor(self.t)

    def year_fraction(self) -> float:
        return self.t - math.floor(self.t)

    def in_window(self, lo: float, hi: float) -> bool:
        f = self.year_fraction()
        return lo <= f < hi
