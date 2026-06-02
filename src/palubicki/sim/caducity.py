"""Leaf caducity: age + season drive ``LeafState`` transitions (#61).

A single per-iteration pass (``advance_leaf_states``) walks every leaf and
advances it ``ACTIVE -> SENESCENT -> ABSCISSED`` as a *pure function* of the
clock and the leaf's ``birth_time`` — no RNG, so a fixed seed reproduces the
exact same shed schedule. Abscised leaves leave the ``ACTIVE`` roster and so
vanish from the rendered mesh for free (``geom.leaves.selected_leaves`` already
filters on ``LeafState.ACTIVE``).

Wired into ``simulator._apply_temporal_dynamics`` so it runs on both growth and
dormant-season iterations. Leaves emitted *this* iteration have age 0 and never
senesce on their birth step.
"""
from __future__ import annotations

import math

from palubicki.sim.clock import phenology_activity
from palubicki.sim.tree import LeafState


def advance_leaf_states(forest, cfg, t: float) -> None:
    """Advance every leaf's ``LeafState`` for the iteration at time ``t`` (years).

    No-op unless ``cfg.sim.leaf_phenology.enabled``. Two senescence triggers fire
    independently (whichever first): the lifespan age cap, and — for deciduous
    presets — leaving the seasonal growth window. A senesced leaf abscises once
    it has been ``SENESCENT`` for ``senescence_duration_years``.
    """
    ph = cfg.sim.leaf_phenology
    if not ph.enabled:
        return

    # Shared dormancy-entry trigger (#65): senescence keys off the SAME graded
    # phenology boundary the simulator uses to gate growth, so the growth-stop
    # and leaf-shed boundaries can never drift. activity > 0 <=> in the (possibly
    # shouldered) growth window; with growth_period_shoulder == 0 this is exactly
    # the legacy ``lo <= year_fraction < hi`` step.
    lo, hi = cfg.sim.annual_growth_period
    year_fraction = t - math.floor(t)
    activity = phenology_activity(year_fraction, lo, hi, cfg.sim.growth_period_shoulder)
    in_growth_window = activity > 0.0
    seasonal_shed = ph.deciduous and not in_growth_window
    marcescent = ph.deciduous and ph.marcescent

    for tree in forest.trees:
        for leaf in tree.all_leaves():
            if leaf.state is LeafState.ACTIVE:
                aged_out = (t - leaf.birth_time) >= ph.leaf_lifespan_years
                if aged_out or seasonal_shed:
                    leaf.state = LeafState.SENESCENT
                    leaf.senescence_time = t
            elif leaf.state is LeafState.SENESCENT:
                if marcescent:
                    # Dead but retained: drop only once the next growth window
                    # opens (the new flush pushes the old leaf off). Guard against
                    # abscising in the same season it senesced.
                    senesced = leaf.senescence_time if leaf.senescence_time is not None else t
                    if in_growth_window and (t - senesced) > 0.0:
                        leaf.state = LeafState.ABSCISSED
                # senescence_time is always set on the ACTIVE->SENESCENT edge;
                # the ``or`` is a defensive guard for hand-constructed leaves.
                elif (
                    leaf.senescence_time is None
                    or (t - leaf.senescence_time) >= ph.senescence_duration_years
                ):
                    leaf.state = LeafState.ABSCISSED
