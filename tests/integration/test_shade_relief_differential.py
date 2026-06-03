"""Acceptance for issue #86, criterion 3 — the shade-relief differential.

#86 enables shade-avoidance per species so crown density has TWO independently-set
levers: withhold-at-initiation (this) vs. cull-after-the-fact (``shade_mortality``).
This test pins the property that makes the initiation lever distinct from the
culler: **it responds to the light FIELD**, not just to a binary on/off.

#63 already proved two things at the unit/integration level, which this test does
NOT duplicate:
  * laterals are WITHHELD in shade with the feature ON vs OFF
    (``test_shade_avoidance_initiation.py::test_avoidance_withholds_laterals_at_emission``), and
  * a withheld RESERVE lateral IS reactivatable through the existing reiteration
    path (``...::test_suppressed_laterals_are_reserve_and_reactivatable``) — the
    "recovery when a shaded sibling is shed" mechanism.

What #86 adds, and this test asserts, is the *graded* response: at a FIXED strength
and with the culler OFF, a more heavily self-shaded crown withholds MORE laterals
(``lateral_reserve_fraction`` rises with shade). Because ``shade_mortality`` is off,
that gradient is purely the initiation lever reading the light field — culling can
never MINT a RESERVE bud, so a reserve fraction that tracks the light regime cannot
be a "fewer survivors" artifact.

We deliberately do NOT assert spontaneous in-sim *reactivation* counts here. Probing
shows shade-avoidance reserves rarely wake via the current shed path (the shaded,
growth-stalled nodes that withhold reserves seldom have a vigorous child subtree
that later sheds), which is consistent with the roadmap: a real light->reactivation
loop is deferred to #61 (foliar re-flush on old wood). The reactivation *mechanism*
is covered by the #63 unit test above; forcing a count here would be contrived.

Isolation follows the #63 recipe: ``shade_mortality`` OFF (no culling confound) and
``dormant_reserve_count = 0`` (the ONLY RESERVE source is shade-avoidance, so
``lateral_reserve_fraction`` is a pure readback of withheld laterals). The same
oak/8000-marker self-shading scenario as the #63 test drives the crown interior into
real shade across seeds {0,1,2}. ``strength`` is pinned to a fixed test value,
decoupled from the calibrated oak preset (0.40), so re-tuning the preset cannot break
this test.
"""
import pytest

from palubicki.config import load_config
from palubicki.sim.diagnostics import compute_metrics
from palubicki.sim.simulator import simulate

pytestmark = pytest.mark.slow

# Same self-shading recipe as tests/integration/test_shade_avoidance_initiation.py
# (#63), which robustly drives the oak crown interior into shade across seeds.
_MARKERS = 8000
_YEARS = 18
_STRENGTH = 0.9   # fixed test value (decoupled from the oak preset's 0.40).
_K_LOW = 0.2      # little extinction -> little self-shading -> little withholding
_K_HIGH = 2.0     # heavy extinction -> deep interior shade -> robust withholding


def _cfg(tmp_path, *, k_absorption, seed):
    return load_config(
        yaml_path=None,
        cli_overrides={
            "seed": seed,
            "envelope.marker_count": _MARKERS,
            "sim.max_simulation_years": _YEARS,
            "light.k_absorption": k_absorption,
            "sim.shade_mortality.enabled": False,        # isolate from culling
            "phyllotaxy.dormant_reserve_count": 0,       # only SA mints RESERVE
            "sim.shade_avoidance.enabled": True,
            "sim.shade_avoidance.strength": _STRENGTH,
        },
        output=tmp_path / "oak.glb",
        species="oak",
    )


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_initiation_responds_to_light_field(tmp_path, seed):
    """At a FIXED strength, heavier self-shading withholds MORE laterals: the
    initiation lever reads the light field. Mortality is OFF, so this is the
    shade-relief differential and not a 'fewer survivors' culling artifact — a
    purely binary or static lever would not vary with the light regime."""
    low = compute_metrics(simulate(_cfg(tmp_path, k_absorption=_K_LOW, seed=seed)))
    high = compute_metrics(simulate(_cfg(tmp_path, k_absorption=_K_HIGH, seed=seed)))

    assert high["lateral_reserve_fraction"] > low["lateral_reserve_fraction"], (
        seed, low["lateral_reserve_fraction"], high["lateral_reserve_fraction"]
    )
    # Heavy shade withholds a material share (not a noise-level trickle).
    assert high["lateral_reserve_fraction"] > 0.10, high["lateral_reserve_fraction"]
