# tests/test_config_yaml.py
from pathlib import Path

import pytest

from palubicki.config import Config, ConfigError, load_config


def test_load_full_yaml(tmp_path):
    yaml_text = """
envelope:
  shape: cone
  rx: 2.0
  ry: 8.0
  rz: 2.0
  marker_count: 5000
sim:
  max_iterations: 15
  lambda_apical: 0.7
seed: 99
"""
    p = tmp_path / "c.yaml"
    p.write_text(yaml_text)
    cfg = load_config(yaml_path=p, cli_overrides={}, output=tmp_path / "out.glb")
    assert cfg.envelope.shape == "cone"
    assert cfg.envelope.ry == 8.0
    assert cfg.sim.max_iterations == 15
    assert cfg.sim.lambda_apical == 0.7
    assert cfg.seed == 99


def test_cli_overrides_yaml(tmp_path):
    yaml_text = "seed: 5\nsim:\n  max_iterations: 20\n"
    p = tmp_path / "c.yaml"
    p.write_text(yaml_text)
    cfg = load_config(
        yaml_path=p,
        cli_overrides={"seed": 123, "sim.max_iterations": 7},
        output=tmp_path / "out.glb",
    )
    assert cfg.seed == 123
    assert cfg.sim.max_iterations == 7


def test_no_yaml_uses_defaults(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={}, output=tmp_path / "out.glb")
    assert cfg.sim.max_iterations == 30


def test_unknown_yaml_key_rejected(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("sim:\n  not_a_real_key: 1\n")
    with pytest.raises(ConfigError, match="not_a_real_key"):
        load_config(yaml_path=p, cli_overrides={}, output=tmp_path / "out.glb")
