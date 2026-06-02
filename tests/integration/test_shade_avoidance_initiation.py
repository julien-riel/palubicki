"""Acceptance for issue #63 (shade-avoidance at bud initiation).

Dense shade should make a crown *withhold* lateral investment at emission —
laterals start RESERVE instead of ACTIVE — not merely cull laterals after the
fact (that is ``shade_mortality``, kept and complementary). The proof is a seeded
oak that self-shades its interior, compared with avoidance ON vs OFF.

To isolate the *initiation* lever from confounders the scenario:
  * disables ``shade_mortality`` — so the OFF baseline loses NO structure to light
    at all; any withholding in the ON run is therefore initiation-side, not
    "fewer survivors";
  * sets ``phyllotaxy.dormant_reserve_count = 0`` — so the ONLY source of RESERVE
    buds is shade-avoidance, making ``lateral_reserve_fraction`` a pure readback
    of withheld laterals (exactly 0.0 when the feature is off).
"""
import pytest

from palubicki.config import load_config
from palubicki.sim.diagnostics import compute_metrics
from palubicki.sim.simulator import simulate

pytestmark = pytest.mark.slow

# k_absorption=2.0 (vs the oak preset's 0.55) + 8k markers over 18 years drives
# the interior light_factor well down, so emitting buds in the crown interior
# break their laterals in real shade.
_MARKERS = 8000
_YEARS = 18
_K = 2.0
_STRENGTH = 0.9


def _run(tmp_path, *, enabled, strength=_STRENGTH, seed=0, dormant_reserve_count=0,
         shade_mortality=False):
    cfg = load_config(
        yaml_path=None,
        cli_overrides={
            "seed": seed,
            "envelope.marker_count": _MARKERS,
            "sim.max_simulation_years": _YEARS,
            "light.k_absorption": _K,
            "sim.shade_mortality.enabled": shade_mortality,
            "phyllotaxy.dormant_reserve_count": dormant_reserve_count,
            "sim.shade_avoidance.enabled": enabled,
            "sim.shade_avoidance.strength": strength,
        },
        output=tmp_path / "oak.glb",
        species="oak",
    )
    return simulate(cfg)


def _reserve_count(metrics) -> int:
    return int(metrics["bud_state_histogram"].get("RESERVE", 0))


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_avoidance_withholds_laterals_at_emission_per_seed(tmp_path, seed):
    """#63 headline criterion, per seed (banded-metric convention): with
    avoidance ON the shaded crown holds a measurable share of laterals in RESERVE
    at emission; with it OFF (and shade_mortality OFF) nothing is withheld and no
    RESERVE bud exists — so the difference is initiation-side, not 'fewer
    survivors'."""
    tree_off = _run(tmp_path, enabled=False, seed=seed)
    tree_on = _run(tmp_path, enabled=True, seed=seed)
    m_off = compute_metrics(tree_off)
    m_on = compute_metrics(tree_on)

    # OFF: no reserves at all (dormant_reserve_count=0, avoidance off) → a clean
    # zero floor. shade_mortality is off too, so NO bud is killed by light; the
    # DEAD buds in the histogram are spent emitters (every bud that emits a node is
    # marked DEAD), a light-independent structural fact shared by both runs. The
    # RESERVE differential below is therefore purely the initiation lever, not
    # "fewer survivors" (a quality/mortality lever would shift ACTIVE/DEAD, never
    # mint RESERVE buds).
    assert _reserve_count(m_off) == 0
    assert m_off["lateral_reserve_fraction"] == 0.0

    # ON: a substantial share of laterals are withheld as RESERVE in shade.
    # Observed ~0.40 / ~180-220 reserves across these seeds; assert with margin.
    assert _reserve_count(m_on) >= 20, m_on["bud_state_histogram"]
    assert m_on["lateral_reserve_fraction"] > 0.15, m_on["lateral_reserve_fraction"]
    assert m_on["lateral_reserve_fraction"] > m_off["lateral_reserve_fraction"]


def test_withholding_scales_with_strength(tmp_path):
    """Monotonic dose-response: a stronger knob withholds more laterals (the
    fraction is the design lever, not a side effect)."""
    weak = compute_metrics(_run(tmp_path, enabled=True, strength=0.3, seed=0))
    strong = compute_metrics(_run(tmp_path, enabled=True, strength=1.0, seed=0))
    assert (
        0.0 < weak["lateral_reserve_fraction"] < strong["lateral_reserve_fraction"]
    ), (weak["lateral_reserve_fraction"], strong["lateral_reserve_fraction"])


def test_suppressed_laterals_are_reserve_and_reactivatable(tmp_path):
    """Criterion 2: a withheld lateral is held as RESERVE in dormant_reserve_buds
    and can be woken through the EXISTING reiteration path (no bespoke wake-up):
    activate_reserves_on_shed flips it RESERVE → ACTIVE and moves it onto the
    lateral track."""
    from palubicki.sim.reiteration import activate_reserves_on_shed
    from palubicki.sim.tree import BudState

    tree = _run(tmp_path, enabled=True, seed=0)

    # Every reserve bud in this scenario was withheld by shade-avoidance
    # (dormant_reserve_count=0), and all are RESERVE-state.
    node = next(
        (
            n
            for n in _walk(tree.root)
            if n.dormant_reserve_buds
        ),
        None,
    )
    assert node is not None, "expected at least one node with a withheld reserve"
    assert all(b.state is BudState.RESERVE for b in node.dormant_reserve_buds)

    before_reserve = len(node.dormant_reserve_buds)
    before_lateral = len(node.lateral_buds)
    woken = activate_reserves_on_shed(node, n_to_activate=1)

    assert len(woken) == 1
    assert woken[0].state is BudState.ACTIVE
    assert len(node.dormant_reserve_buds) == before_reserve - 1
    assert len(node.lateral_buds) == before_lateral + 1
    assert woken[0] in node.lateral_buds


def test_disabled_and_zero_strength_are_byte_identical(tmp_path):
    """Criterion 3 (determinism): the OFF gate draws no RNG, so enabled=False and
    enabled=True+strength=0 produce the IDENTICAL tree — same topology and the
    same jittered internode lengths (oak has internode_length_jitter=0.12, so a
    perturbed RNG stream would shift every length). dormant_reserve_count is left
    at the oak default here to exercise the real shipped path."""
    a = _run(tmp_path, enabled=False, dormant_reserve_count=2, seed=0)
    b = _run(tmp_path, enabled=True, strength=0.0, dormant_reserve_count=2, seed=0)

    assert len(a.all_internodes) == len(b.all_internodes)
    fa = [(i.birth_time, i.length_target, i.vigor) for i in a.all_internodes]
    fb = [(i.birth_time, i.length_target, i.vigor) for i in b.all_internodes]
    assert fa == fb
    assert compute_metrics(a)["bud_state_histogram"] == compute_metrics(b)["bud_state_histogram"]


def _walk(root):
    stack = [root]
    while stack:
        n = stack.pop()
        yield n
        for iod in n.children_internodes:
            stack.append(iod.child_node)
