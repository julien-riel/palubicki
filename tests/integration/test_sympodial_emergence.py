import pytest

from palubicki.config import load_config
from palubicki.sim.simulator import simulate_forest
from palubicki.sim.tree import BudState


pytestmark = pytest.mark.slow


def _count_promotions(tree) -> int:
    """Count nodes with multiple main-axis child internodes (post-promotion fork)."""
    forks = 0
    for internode in tree.all_internodes:
        parent = internode.parent_node
        main_children = [c for c in parent.children_internodes if c.is_main_axis]
        if len(main_children) > 1 and main_children[0] is internode:
            forks += 1
    return forks


def test_oak_produces_forks(tmp_path):
    cfg = load_config(
        yaml_path=None,
        cli_overrides={"sim.max_iterations": 30, "envelope.marker_count": 8000},
        output=tmp_path / "oak.glb",
        species="oak",
    )
    forest = simulate_forest(cfg)
    tree = forest.trees[0]
    forks = _count_promotions(tree)
    assert forks >= 5, f"expected >=5 sympodial forks, got {forks}"


def test_pine_produces_no_forks(tmp_path):
    cfg = load_config(
        yaml_path=None,
        cli_overrides={"sim.max_iterations": 30, "envelope.marker_count": 8000},
        output=tmp_path / "pine.glb",
        species="pine",
    )
    forest = simulate_forest(cfg)
    tree = forest.trees[0]
    forks = _count_promotions(tree)
    assert forks == 0, f"pine is monopodial; expected 0 forks, got {forks}"
