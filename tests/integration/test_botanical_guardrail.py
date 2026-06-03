"""#87 — botanical guardrail (the multi-seed bounds invariant).

Every calibrated species must keep its architectural + phyllotaxis metrics within
the *cited* ``configs/literature.yaml`` bounds, across multiple seeds. This turns
the manual ``palubicki diagnose`` ritual into an automated test: the determinism
goldens (``tests/golden``) pin that the sim is REPRODUCIBLE; this pins that it
sits within its cited bounds — a preset can hash-match a golden (or be freshly
tuned) and still drift outside those bounds, and nothing else would fail.

WHERE IT RUNS — this is ``@pytest.mark.slow``, so it runs in the **full local
suite**, NOT the GitHub Actions matrix (the sole CI job runs ``-m 'not slow and
not pinned'`` and deselects it). It is an enforced invariant of the full suite /
pre-merge run, not a per-push GitHub gate — a deliberate scope choice (#87)
because the sweep is minutes-long (pine, below). To gate it on GitHub too, add a
dedicated job (single pinned interpreter) running ``-m slow``, ideally scheduled
rather than per-push given the runtime.

GATED (hard-asserted) — every metric that carries a literature bound, resolved
from the manifest by :func:`sim.diagnostics.gated_fields`, so adding a bound to
``literature.yaml`` automatically extends the guard:

    tree_height, trunk_base_diameter, crown_radius,
    main_axis_continuation_rate, leader_deviation_deg,
    horton_bifurcation_ratio_mean,
    divergence_angle_deg__order1_mean,
    insertion_angle_deg_vs_parent__order1_mean

ADVISORY (measured by ``diagnose`` but NOT gated — no cited bound, so no ✓/✗):
total_leaf_area, foliage_area_density, out_of_plane_deviation_deg,
internode_length_*, strahler_order_max, sympodial_fork_count,
lateral_reserve_fraction, the phenology metrics, and angle orders > 1. The
explicit gated set is pinned (fast, no sim) in
``tests/sim/test_metric_ranges.py`` (``gated_fields`` tests), so a bound added or
removed is a conscious change rather than a silent widening of the guard.

ash is gated only on the three bounds it carries (its decussate divergence
override + the inherited global insertion/horton bands). It has no Fraxinus
*architectural* numbers in the manifest, so height/crown/trunk/leader/continuation
are not gated for it — a documented deferral, not an accident (``gated_fields``
skips None bounds). Adding Fraxinus architectural bounds later would gate them
automatically.

Multi-seed — each species is simulated at ``SEEDS`` (>1; the bands were derived
against this 3-seed set in #83) and aggregated by ``compute_metrics([trees])``,
then ``check_bounds`` compares the aggregated MEAN against each band — exactly
what ``diagnose --seed 0,1,2`` reports. At each species' default
``max_simulation_years`` (~30, the reference age the bounds are cited at — do NOT
shorten it, or the size bands no longer apply). Only the multi-seed MEAN is gated,
not per-seed values: a consistent drift moves the mean out of band (caught), but a
pathological bimodal spread that straddles the band averages back in and passes —
an accepted limitation, since per-seed hard-gating would false-alarm on chaotic
metrics (``crown_radius`` is a single-furthest-branch max-extent measure) and noisy
ones (Horton). Supersedes the per-metric, single-seed #83/#48/#7 guards that used
to live in ``tests/sim/test_diagnostics.py`` (each re-simulated seed 0 once per
metric) with one sweep per species: fewer simulations, full-metric coverage.

Runtime — measured, clean, single core, at each species' default ~30yr: per seed
birch ~11s, fir ~19s, ash/maple ~25s, oak ~29s, pine ~210–820s (stochastic:
whorled k=5 churns many competing buds against the marker cloud). pine dominates
and is highly seed-dependent, so the 3-seed pine sweep alone is roughly 10–40 min;
the five cheap species are ~5–6 min together. Whole sweep ≈ 15–45 min — the heavy
invariant of the full slow suite. Deselect with ``-m 'not slow'``; the quick
per-species spot check is ``palubicki diagnose --species <name> --seed 0,1,2``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from palubicki.config import load_config
from palubicki.sim.diagnostics import MetricRanges, check_bounds, compute_metrics
from palubicki.sim.simulator import simulate

pytestmark = pytest.mark.slow

# Seeds the multi-seed mean is taken over. {0,1,2} is the set the order-1 angle
# bands were derived against in #83; the architectural bands are seed-independent
# field dimensions, so the mean over these three is a fair, low-variance estimate.
# Keep len > 1: _aggregate_over_seeds always takes compute_metrics' list/aggregate
# path (mean leaves), which only matches `diagnose` for a multi-seed invocation.
SEEDS = (0, 1, 2)

# Every species carrying literature bounds. ash included: it is gated on the
# phyllotaxis/topology subset it has (see module docstring).
SPECIES = ("oak", "birch", "maple", "fir", "pine", "ash")


def _aggregate_over_seeds(species: str) -> dict:
    """Simulate ``species`` once per seed at its calibrated config and return the
    multi-seed aggregated metrics — the same path ``diagnose --seed 0,1,2`` takes.
    ``cfg`` is threaded into ``compute_metrics`` so divergence is measured in the
    species' phyllotaxis mode (spiral / decussate / whorled)."""
    cfg = None
    trees = []
    for seed in SEEDS:
        cfg = load_config(
            yaml_path=None,
            cli_overrides={"seed": seed},
            output=Path("tree.glb"),
            species=species,
        )
        trees.append(simulate(cfg))
    return compute_metrics(trees, cfg=cfg)


@pytest.mark.parametrize("species", SPECIES)
def test_species_within_literature_bounds(species):
    """Hard gate: every bounded metric's multi-seed mean sits inside its cited
    ``literature.yaml`` band. A drift fails loudly, naming the offending metric,
    its value, the band, and how to reproduce — never an xfail, so a regression
    is impossible to miss."""
    metrics = _aggregate_over_seeds(species)
    ranges = MetricRanges.from_species(species)

    # check_bounds resolves and compares EVERY field that carries a bound for this
    # species (gated_fields). A missing/NaN metric is itself a violation.
    violations = check_bounds(metrics, ranges)

    assert not violations, (
        f"{species} drifted outside literature.yaml bounds "
        f"(multi-seed mean over seeds {list(SEEDS)}):\n  "
        + "\n  ".join(str(v) for v in violations)
        + f"\nreproduce: palubicki diagnose --species {species} "
        f"--seed {','.join(map(str, SEEDS))}"
    )
