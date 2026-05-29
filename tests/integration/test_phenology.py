# tests/integration/test_phenology.py
"""Acceptance for issue #10: annual_growth_period gates growth to a window."""
import math

import pytest

from palubicki.config import load_config
from palubicki.sim.simulator import simulate

pytestmark = pytest.mark.slow


def _run(tmp_path, *, dt_years, window, years=4.0):
    cfg = load_config(
        yaml_path=None,
        cli_overrides={
            "sim.dt_years": dt_years,
            "sim.max_simulation_years": years,
            "sim.annual_growth_period": list(window),
            "envelope.marker_count": 1500,
            "seed": 0,
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
    assert all(0.0 <= f < 0.5 for f in fractions), sorted(set(round(f, 3) for f in fractions))


def test_no_internodes_born_in_dormant_half(tmp_path):
    tree = _run(tmp_path, dt_years=0.25, window=(0.0, 0.5))
    dormant = [iod for iod in tree.all_internodes if _year_fraction(iod.birth_time) >= 0.5]
    assert dormant == []


def test_full_year_window_grows_every_step(tmp_path):
    # dt_years=1.0 + full window: growth occurs (the gate must not suppress the
    # default case).
    tree = _run(tmp_path, dt_years=1.0, window=(0.0, 1.0))
    assert len(tree.all_internodes) > 0
