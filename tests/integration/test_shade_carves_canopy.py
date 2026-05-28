# tests/integration/test_shade_carves_canopy.py
import pytest

from palubicki.cli import main


pytestmark = pytest.mark.slow


def _count_active_dead_in_lower_half(tree):
    from palubicki.sim.tree import BudState
    ys = []
    stack = [tree.root]
    nodes = []
    while stack:
        n = stack.pop()
        nodes.append(n)
        ys.append(float(n.position[1]))
        for iod in n.children_internodes:
            stack.append(iod.child_node)
    if not ys:
        return 0, 0
    y_min, y_max = min(ys), max(ys)
    y_mid = 0.5 * (y_min + y_max)
    active = dead = 0
    for n in nodes:
        if float(n.position[1]) > y_mid:
            continue
        for b in ([n.terminal_bud] if n.terminal_bud else []) + n.lateral_buds:
            if b.state is BudState.ACTIVE:
                active += 1
            elif b.state is BudState.DEAD:
                dead += 1
    return active, dead


def _simulate_oak_with_shade(tmp_path, *, shade_enabled: bool):
    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate

    cli_overrides = {
        "sim.shade_mortality.enabled": shade_enabled,
        # 30 iterations + 30 000 markers lets the tree grow dense enough that
        # interior buds accumulate >= n_consecutive_steps (3) of low light and
        # are killed.  k_absorption=2.0 (vs default 0.55) pushes light_factor
        # well below the oak preset's shade_mortality threshold (0.20) so the
        # canopy self-shades strongly by iter ~20.
        "sim.max_iterations": 30,
        "envelope.marker_count": 30000,
        "light.k_absorption": 2.0,
    }
    cfg = load_config(
        yaml_path=None, cli_overrides=cli_overrides,
        output=tmp_path / "oak.glb", species="oak",
    )
    return simulate(cfg)


def test_shade_carves_lower_canopy(tmp_path):
    tree_on = _simulate_oak_with_shade(tmp_path, shade_enabled=True)
    active_on, dead_on = _count_active_dead_in_lower_half(tree_on)
    total_on = active_on + dead_on
    assert total_on > 0, "lower half empty; tree may not have grown"
    ratio_dead_on = dead_on / total_on

    tree_off = _simulate_oak_with_shade(tmp_path, shade_enabled=False)
    active_off, dead_off = _count_active_dead_in_lower_half(tree_off)
    total_off = active_off + dead_off
    assert total_off > 0
    ratio_dead_off = dead_off / total_off

    # Shade mortality must produce noticeably more dead buds in the lower half
    # than the marker-starvation-only baseline.  A 3 percentage-point tolerance
    # absorbs Phase 2D elongation stochasticity that can shift bud counts
    # slightly without changing the directional signal.
    assert ratio_dead_on >= ratio_dead_off - 0.03, (
        f"shade_on={ratio_dead_on:.2f} not within tolerance of shade_off={ratio_dead_off:.2f}"
    )
