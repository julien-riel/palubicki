import pytest

from palubicki.config import load_config
from palubicki.sim.simulator import simulate_forest

pytestmark = pytest.mark.slow


def _count_promotions(tree) -> int:
    """Count sympodial fork events recorded on nodes during simulation."""
    return sum(
        1
        for internode in tree.all_internodes
        if internode.parent_node.sympodial_fork
        and internode.parent_node.children_internodes[0] is internode
    )


def test_oak_produces_forks(tmp_path):
    cfg = load_config(
        yaml_path=None,
        cli_overrides={"sim.max_simulation_years": 30, "envelope.marker_count": 8000},
        output=tmp_path / "oak.glb",
        species="oak",
    )
    forest = simulate_forest(cfg)
    tree = forest.trees[0]
    forks = _count_promotions(tree)
    assert forks >= 4, f"expected >=4 sympodial forks, got {forks}"


def test_pine_produces_no_forks(tmp_path):
    cfg = load_config(
        yaml_path=None,
        cli_overrides={"sim.max_simulation_years": 30, "envelope.marker_count": 8000},
        output=tmp_path / "pine.glb",
        species="pine",
    )
    forest = simulate_forest(cfg)
    tree = forest.trees[0]
    forks = _count_promotions(tree)
    assert forks == 0, f"pine is monopodial; expected 0 forks, got {forks}"
