# tests/integration/test_light_behavior.py
"""V2 behavioral tests: verify that light shadowing has measurable biological effects.

These tests compare trees grown with and without light enabled, asserting that
activating V2 (BHls) light model produces expected biological outcomes:
  1. Light-driven shedding reduces total internode count.
  2. Light concentration biases biomass higher (positive-y centroid shift).

Parameters are tuned for reliable signal: large envelope (rx=2, ry=3, rz=2),
high marker count (3000), strong absorption (k_absorption=1.0), large leaf-area
scale (leaf_area_scale=92, thickening the real per-leaf blade occlusion), and
enough years (max_simulation_years=12) to accumulate effect.

The light grid now deposits each leaf's real blade area (#62) times
``leaf_area_scale``; the scales here (37, 92) reproduce the magnitude of the old
scalar-per-terminal deposits (0.08, 0.2) given the default ovate blade.
"""
from pathlib import Path

import numpy as np
import pytest

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
from palubicki.sim.simulator import simulate

pytestmark = pytest.mark.slow


def _base_cfg(**overrides) -> Config:
    base = {
        "envelope": EnvelopeConfig(shape="ellipsoid", rx=2.0, ry=3.0, rz=2.0, marker_count=3000),
        "sim": SimConfig(max_simulation_years=12.0),
        "tropism": TropismConfig(w_phototropism=0.3),
        "phyllotaxy": PhyllotaxyConfig(),
        "shedding": SheddingConfig(),
        "geom": GeomConfig(),
        "seed": 42,
        "output": Path("/tmp/x.glb"),
    }
    base.update(overrides)
    return Config(**base)


def test_light_enabled_reduces_internode_count():
    """Light absorption (k=0.3, leaf_area_scale=37) sheds shaded branches, producing fewer
    internodes than a tree grown without light shadowing.

    Phototropism is disabled here (w_phototropism=0) to isolate the shade-SUPPRESSION
    channel. With the corrected centered light gradient (#FIX D), phototropism under
    real light fills lateral gaps better than the no-light +Y fallback, which can RAISE
    internode count — so net density is not a clean suppression signal when photo is on.
    The directional light effects (centroid raise, canopy carving) are covered separately."""
    no_photo = TropismConfig(w_phototropism=0.0)
    tree_off = simulate(_base_cfg(tropism=no_photo, light=LightConfig(enabled=False)))
    tree_on = simulate(_base_cfg(
        tropism=no_photo, light=LightConfig(enabled=True, k_absorption=0.3, leaf_area_scale=37.0)
    ))
    assert len(tree_on.all_internodes) < len(tree_off.all_internodes)


def test_light_enabled_raises_centroid():
    """Light-driven shedding + phototropism should concentrate biomass higher (positive y).

    With light coming from above (default direction (0,1,0)), lower branches are
    shaded by the canopy and shed, while upper growth is favoured. The mean y
    position of internode endpoints should be higher with light enabled.

    Each bud now extends a single internode per iteration unconditionally, so light_factor
    no longer scales internode count per iteration, only the dormancy gate (Q*light <1).
    Stronger absorption (k=2.5) is needed so shaded buds reliably cross below the cap,
    and more iterations (30) let the upward bias accumulate. Phototropism weight stays
    moderate (0.3) — very strong photo (>0.5) lets shaded laterals chase lateral
    light gaps and lowers the centroid instead of raising it.
    Observed shift: 0.40 → 0.67 (delta ~+0.27).
    """
    tree_off = simulate(_base_cfg(sim=SimConfig(max_simulation_years=30.0), light=LightConfig(enabled=False)))
    tree_on = simulate(_base_cfg(
        sim=SimConfig(max_simulation_years=30.0),
        light=LightConfig(enabled=True, k_absorption=2.5, leaf_area_scale=92.0),
    ))
    centroid_y_off = np.mean([iod.child_node.position[1] for iod in tree_off.all_internodes])
    centroid_y_on = np.mean([iod.child_node.position[1] for iod in tree_on.all_internodes])
    assert centroid_y_on > centroid_y_off
