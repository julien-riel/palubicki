from palubicki.config import Config
from palubicki.edit.config_io import config_dict_to_overrides, config_to_dict_for_ui


def test_flatten_nested_dict():
    nested = {
        "envelope": {"shape": "cone", "rx": 2.0},
        "sim": {"max_iterations": 5},
        "seed": 7,
    }
    flat = config_dict_to_overrides(nested)
    assert flat == {
        "envelope.shape": "cone",
        "envelope.rx": 2.0,
        "sim.max_iterations": 5,
        "seed": 7,
    }


def test_flatten_empty_returns_empty():
    assert config_dict_to_overrides({}) == {}


def test_flatten_skips_none_values():
    flat = config_dict_to_overrides({"envelope": {"rx": None}})
    assert flat == {}


def test_config_to_dict_for_ui_is_loadable_back():
    from palubicki.config import load_config
    from pathlib import Path

    cfg = load_config(yaml_path=None, cli_overrides={}, output=Path("tree.glb"))
    d = config_to_dict_for_ui(cfg)
    overrides = config_dict_to_overrides(d)
    cfg2 = load_config(yaml_path=None, cli_overrides=overrides, output=Path("tree.glb"))
    assert cfg2.envelope.shape == cfg.envelope.shape
    assert cfg2.sim.max_iterations == cfg.sim.max_iterations
    assert cfg2.seed == cfg.seed
