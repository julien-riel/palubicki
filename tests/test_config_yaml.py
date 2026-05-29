# tests/test_config_yaml.py

import pytest

from palubicki.config import ConfigError, load_config


def test_load_full_yaml(tmp_path):
    yaml_text = """
envelope:
  shape: cone
  rx: 2.0
  ry: 8.0
  rz: 2.0
  marker_count: 5000
sim:
  max_simulation_years: 15
  lambda_apical: 0.7
seed: 99
"""
    p = tmp_path / "c.yaml"
    p.write_text(yaml_text)
    cfg = load_config(yaml_path=p, cli_overrides={}, output=tmp_path / "out.glb")
    assert cfg.envelope.shape == "cone"
    assert cfg.envelope.ry == 8.0
    assert cfg.sim.max_simulation_years == 15.0
    assert cfg.sim.lambda_apical == 0.7
    assert cfg.seed == 99


def test_cli_overrides_yaml(tmp_path):
    yaml_text = "seed: 5\nsim:\n  max_simulation_years: 20\n"
    p = tmp_path / "c.yaml"
    p.write_text(yaml_text)
    cfg = load_config(
        yaml_path=p,
        cli_overrides={"seed": 123, "sim.max_simulation_years": 7},
        output=tmp_path / "out.glb",
    )
    assert cfg.seed == 123
    assert cfg.sim.max_simulation_years == 7.0


def test_no_yaml_uses_defaults(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={}, output=tmp_path / "out.glb")
    assert cfg.sim.max_simulation_years == 30.0


def test_unknown_yaml_key_rejected(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("sim:\n  not_a_real_key: 1\n")
    with pytest.raises(ConfigError, match="not_a_real_key"):
        load_config(yaml_path=p, cli_overrides={}, output=tmp_path / "out.glb")


def test_load_config_with_obstacles(tmp_path):
    from palubicki.config import ObstacleAABB, ObstacleSphere, load_config
    yaml_path = tmp_path / "scene.yaml"
    yaml_path.write_text("""
forest:
  obstacles:
    - kind: aabb
      min: [0.0, 0.0, 0.0]
      max: [2.0, 1.0, 2.0]
    - kind: sphere
      center: [5.0, 0.0, 5.0]
      radius: 1.5
""")
    cfg = load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")
    assert len(cfg.forest.obstacles) == 2
    assert isinstance(cfg.forest.obstacles[0], ObstacleAABB)
    assert cfg.forest.obstacles[0].min == (0.0, 0.0, 0.0)
    assert cfg.forest.obstacles[0].max == (2.0, 1.0, 2.0)
    assert isinstance(cfg.forest.obstacles[1], ObstacleSphere)
    assert cfg.forest.obstacles[1].radius == 1.5


def test_load_config_with_forest_seeds(tmp_path):
    from palubicki.config import load_config
    yaml_path = tmp_path / "scene.yaml"
    yaml_path.write_text("""
forest:
  seeds:
    - position: [0.0, 0.0, 0.0]
    - position: [5.0, 0.0, 0.0]
      seed: 42
      overrides:
        envelope.shape: cone
        tropism.w_orthotropy_main: 0.5
""")
    cfg = load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")
    assert len(cfg.forest.seeds) == 2
    assert cfg.forest.seeds[0].position == (0.0, 0.0, 0.0)
    assert cfg.forest.seeds[0].seed is None
    assert cfg.forest.seeds[1].position == (5.0, 0.0, 0.0)
    assert cfg.forest.seeds[1].seed == 42
    assert cfg.forest.seeds[1].overrides == {"envelope.shape": "cone", "tropism.w_orthotropy_main": 0.5}


def test_load_config_unknown_obstacle_kind_raises(tmp_path):
    import pytest

    from palubicki.config import ConfigError, load_config
    yaml_path = tmp_path / "scene.yaml"
    yaml_path.write_text("""
forest:
  obstacles:
    - kind: tetrahedron
      min: [0, 0, 0]
""")
    with pytest.raises(ConfigError, match="unknown obstacle kind"):
        load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")
