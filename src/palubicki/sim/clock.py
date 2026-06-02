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

    def activity(self, lo: float, hi: float, shoulder: float) -> float:
        """Graded seasonal activity in [0, 1] at the current time (#65).

        Thin delegate over :func:`phenology_activity` mirroring :meth:`in_window`;
        ``activity(...) > 0`` recovers ``in_window(...)`` exactly when
        ``shoulder == 0``.
        """
        return phenology_activity(self.year_fraction(), lo, hi, shoulder)


def phenology_activity(year_fraction: float, lo: float, hi: float, shoulder: float) -> float:
    """Seasonal growth-rate multiplier in [0, 1] (#65).

    A symmetric trapezoid over the growth window ``[lo, hi)``: a ``shoulder``-wide
    linear ramp rising at ``lo``, a plateau of 1.0 through the middle, and a
    ``shoulder``-wide ramp falling to 0 at ``hi``. ``shoulder <= 0`` degenerates
    to the legacy crisp step (1.0 inside ``[lo, hi)``, 0.0 outside) — byte-identical
    to the binary ``annual_growth_period`` gate it replaces.

    Pure and RNG-free: a deterministic function of ``year_fraction`` alone, so a
    fixed seed reproduces the exact same evolution. This is the SOLE definition of
    the season shape — growth (``simulator``), senescence (``caducity``) and any
    future flowering (#11) all read it. Assumes ``lo < hi`` (no wrap-around; the
    config validator enforces it).
    """
    f = year_fraction
    if shoulder <= 0.0:
        # Branch-exact legacy step: matches ``lo <= f < hi`` bit-for-bit and keeps
        # any division off the path that the default presets exercise.
        return 1.0 if (lo <= f < hi) else 0.0
    if f < lo or f >= hi:
        return 0.0
    if f < lo + shoulder:
        return (f - lo) / shoulder          # rising shoulder (bud break)
    if f >= hi - shoulder:
        return (hi - f) / shoulder          # falling shoulder (growth cessation)
    return 1.0                              # plateau (full vegetative growth)


def phenology_phase(year_fraction: float, lo: float, hi: float, shoulder: float) -> str:
    """Named phenophase derived purely from :func:`phenology_activity` (#65).

    One fixed vocabulary, shared by diagnostics and (future) #11 flowering:

    * ``"dormant"``    — activity == 0 (outside the window)
    * ``"bud_break"``  — rising shoulder (0 < activity < 1, below the plateau)
    * ``"vegetative"`` — plateau (activity == 1)
    * ``"cessation"``  — falling shoulder (0 < activity < 1, above the plateau)

    At ``dt_years == 1.0`` (``year_fraction == 0.0``) with the default full-year
    window this is ``"vegetative"``.
    """
    a = phenology_activity(year_fraction, lo, hi, shoulder)
    if a <= 0.0:
        return "dormant"
    if a >= 1.0:
        return "vegetative"
    # Strictly between 0 and 1 => in exactly one shoulder (the validator keeps the
    # shoulders disjoint), so the rising/falling split is unambiguous.
    return "bud_break" if year_fraction < lo + shoulder else "cessation"
