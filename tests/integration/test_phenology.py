# tests/integration/test_phenology.py
"""Acceptance for issue #10 (annual_growth_period gates growth to a window) and
issue #65 (graded phenology: growth_period_shoulder tapers internodes at the
window edges)."""
import math

import pytest

from palubicki.config import load_config
from palubicki.sim.simulator import simulate

pytestmark = pytest.mark.slow


def _run(tmp_path, *, dt_years, window, years=4.0, shoulder=0.0, seed=0,
         marker_count=1500):
    cfg = load_config(
        yaml_path=None,
        cli_overrides={
            "sim.dt_years": dt_years,
            "sim.max_simulation_years": years,
            "sim.annual_growth_period": list(window),
            "sim.growth_period_shoulder": shoulder,
            "envelope.marker_count": marker_count,
            "seed": seed,
        },
        output=tmp_path / "o.glb",
    )
    return simulate(cfg)


def _year_fraction(t: float) -> float:
    return t - math.floor(t)


def test_growth_confined_to_first_half_year(tmp_path):
    tree = _run(tmp_path, dt_years=0.25, window=(0.0, 0.5))
    fractions = [_year_fraction(iod.birth_time) for iod in tree.all_internodes]
    assert fractions, "expected some internodes"
    # Every internode is born in the growth window [0.0, 0.5).
    assert all(0.0 <= f < 0.5 for f in fractions), sorted({round(f, 3) for f in fractions})


def test_no_internodes_born_in_dormant_half(tmp_path):
    tree = _run(tmp_path, dt_years=0.25, window=(0.0, 0.5))
    dormant = [iod for iod in tree.all_internodes if _year_fraction(iod.birth_time) >= 0.5]
    assert dormant == []


def test_full_year_window_grows_every_step(tmp_path):
    # dt_years=1.0 + full window: growth occurs (the gate must not suppress the
    # default case).
    tree = _run(tmp_path, dt_years=1.0, window=(0.0, 1.0))
    assert len(tree.all_internodes) > 0


# --- issue #65: graded phenology tapers internodes at the window edges --------
#
# Window (0.2, 0.8) with shoulder 0.2 and dt=0.25 samples exactly three growth
# fractions per year: f=0.25 and f=0.75 sit a quarter of the way into the rising
# / falling shoulders (activity = 0.25 -> "edge"), while f=0.5 is on the plateau
# (activity = 1.0). f=0.0 is dormant. All three fractions are exact in binary
# (multiples of 0.25), so the buckets are unambiguous.
_PHENO_WINDOW = (0.2, 0.8)
_PHENO_SHOULDER = 0.2


def _length_targets_by_bucket(tree):
    """Split emitted internodes into shoulder-edge vs plateau by birth fraction."""
    edge, plateau = [], []
    for iod in tree.all_internodes:
        f = _year_fraction(iod.birth_time)
        if abs(f - 0.5) < 1e-9:
            plateau.append(iod.length_target)
        elif abs(f - 0.25) < 1e-9 or abs(f - 0.75) < 1e-9:
            edge.append(iod.length_target)
    return edge, plateau


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_shoulder_tapers_edge_internodes_per_seed(tmp_path, seed):
    """#65 headline criterion, verified independently per seed (banded-metric
    convention): internodes born in the rising/falling shoulders are scaled
    shorter than plateau internodes, and the seasonal taper reduces overall
    emitted length vs the crisp-gate baseline (shoulder=0, same seed/window).

    Edge activity here is 0.25 — a 4x multiplier that dominates any vigor
    difference between early/mid/late-season buds, so the comparison is not a
    coincidence of the RNG draw."""
    shouldered = _run(tmp_path, dt_years=0.25, window=_PHENO_WINDOW, years=8.0,
                      shoulder=_PHENO_SHOULDER, seed=seed, marker_count=4000)
    baseline = _run(tmp_path, dt_years=0.25, window=_PHENO_WINDOW, years=8.0,
                    shoulder=0.0, seed=seed, marker_count=4000)

    # No internode is ever born in the dormant part of the year.
    assert all(
        _PHENO_WINDOW[0] <= _year_fraction(iod.birth_time) < _PHENO_WINDOW[1]
        for iod in shouldered.all_internodes
    )

    edge, plateau = _length_targets_by_bucket(shouldered)
    assert edge, f"seed {seed}: expected shoulder-edge internodes"
    assert plateau, f"seed {seed}: expected plateau internodes"

    edge_mean = sum(edge) / len(edge)
    plateau_mean = sum(plateau) / len(plateau)

    # (1) The taper exists: shoulder internodes are strictly shorter than plateau.
    assert 0.0 < edge_mean < plateau_mean, (
        f"seed {seed}: edge_mean={edge_mean:.4f} plateau_mean={plateau_mean:.4f}"
    )
    # (2) Clearly tapered (edge activity 0.25): ratio well below 1, every seed.
    ratio = edge_mean / plateau_mean
    assert 0.0 < ratio < 0.9, f"seed {seed}: edge/plateau ratio {ratio:.3f}"

    # (3) Cross-check vs the crisp-gate baseline: tapering edge steps lowers the
    # mean emitted internode length (same seed + window, shoulder the only change).
    mean_shoulder = sum(i.length_target for i in shouldered.all_internodes) / len(
        shouldered.all_internodes
    )
    mean_base = sum(i.length_target for i in baseline.all_internodes) / len(
        baseline.all_internodes
    )
    assert mean_shoulder < mean_base, (
        f"seed {seed}: mean length_target {mean_shoulder:.4f} not < "
        f"baseline {mean_base:.4f}"
    )


def test_shoulder_zero_default_grows_full_window(tmp_path):
    """Regression guard: shoulder=0 (the shipped default) reproduces the crisp
    gate — growth occurs across the whole window and nothing is tapered to zero."""
    tree = _run(tmp_path, dt_years=0.25, window=(0.2, 0.8), shoulder=0.0)
    fracs = {round(_year_fraction(i.birth_time), 2) for i in tree.all_internodes}
    assert fracs, "expected internodes"
    assert fracs <= {0.25, 0.5, 0.75}
    assert all(i.length_target > 0.0 for i in tree.all_internodes)
