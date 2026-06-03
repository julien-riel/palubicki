import numpy as np

from palubicki.config import ShadeMortalityConfig
from palubicki.sim.shade_mortality import kill_shaded_buds
from palubicki.sim.tree import Bud, BudState, Node


def _make_bud(state=BudState.ACTIVE):
    node = Node(position=np.zeros(3))
    return Bud(
        position=np.zeros(3),
        direction=np.array([0.0, 1.0, 0.0]),
        axis_order=0,
        parent_node=node,
        state=state,
    )


def test_kill_skipped_when_disabled():
    bud = _make_bud()
    cfg = ShadeMortalityConfig(enabled=False, light_threshold=0.5, n_consecutive_steps=1)
    n = kill_shaded_buds([bud], {bud: 0.0}, cfg)
    assert n == 0
    assert bud.state is BudState.ACTIVE
    assert bud.low_light_steps == 0


def test_counter_increments_under_threshold():
    bud = _make_bud()
    cfg = ShadeMortalityConfig(enabled=True, light_threshold=0.5, n_consecutive_steps=10)
    kill_shaded_buds([bud], {bud: 0.1}, cfg)
    assert bud.low_light_steps == 1
    assert bud.state is BudState.ACTIVE


def test_counter_resets_above_threshold():
    bud = _make_bud()
    bud.low_light_steps = 4
    cfg = ShadeMortalityConfig(enabled=True, light_threshold=0.5, n_consecutive_steps=10)
    kill_shaded_buds([bud], {bud: 0.9}, cfg)
    assert bud.low_light_steps == 0
    assert bud.state is BudState.ACTIVE


def test_dies_after_n_consecutive_steps():
    bud = _make_bud()
    cfg = ShadeMortalityConfig(enabled=True, light_threshold=0.5, n_consecutive_steps=3)
    for _ in range(2):
        kill_shaded_buds([bud], {bud: 0.0}, cfg)
        assert bud.state is BudState.ACTIVE
    killed = kill_shaded_buds([bud], {bud: 0.0}, cfg)
    assert killed == 1
    assert bud.state is BudState.DEAD


def test_skips_reserves_and_dead_but_kills_dormants():
    # RESERVE and DEAD are never touched; DORMANT is living tissue and dies of
    # sustained shade exactly like ACTIVE (it stays in active_buds and is
    # re-evaluated every iteration, so it must not be immortal-in-shade).
    reserve = _make_bud(state=BudState.RESERVE)
    dormant = _make_bud(state=BudState.DORMANT)
    dead = _make_bud(state=BudState.DEAD)
    cfg = ShadeMortalityConfig(enabled=True, light_threshold=0.5, n_consecutive_steps=1)
    light = {reserve: 0.0, dormant: 0.0, dead: 0.0}
    n = kill_shaded_buds([reserve, dormant, dead], light, cfg)
    assert n == 1
    assert reserve.state is BudState.RESERVE
    assert reserve.low_light_steps == 0
    assert dormant.state is BudState.DEAD
    assert dead.state is BudState.DEAD


def test_dormant_recovers_shade_counter_when_lit():
    # A dormant bud that regains light resets its shade counter — its second
    # chance is preserved, only sustained-shade dormants die.
    dormant = _make_bud(state=BudState.DORMANT)
    dormant.low_light_steps = 2
    cfg = ShadeMortalityConfig(enabled=True, light_threshold=0.5, n_consecutive_steps=3)
    kill_shaded_buds([dormant], {dormant: 0.9}, cfg)
    assert dormant.low_light_steps == 0
    assert dormant.state is BudState.DORMANT


def test_missing_light_factor_defaults_to_full_sun():
    bud = _make_bud()
    cfg = ShadeMortalityConfig(enabled=True, light_threshold=0.5, n_consecutive_steps=1)
    kill_shaded_buds([bud], {}, cfg)
    assert bud.state is BudState.ACTIVE
    assert bud.low_light_steps == 0
