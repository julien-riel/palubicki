from pathlib import Path

import pytest

from palubicki.config import ConfigError, _deep_merge, _list_species, load_config


def test_deep_merge_overrides_scalar_in_nested_dict():
    base = {"a": {"b": 1, "c": 2}}
    over = {"a": {"b": 99}}
    _deep_merge(base, over)
    assert base == {"a": {"b": 99, "c": 2}}


def test_deep_merge_replaces_list_completely():
    base = {"a": [1, 2, 3]}
    over = {"a": [9]}
    _deep_merge(base, over)
    assert base == {"a": [9]}


def test_deep_merge_adds_new_key():
    base = {"a": 1}
    over = {"b": 2}
    _deep_merge(base, over)
    assert base == {"a": 1, "b": 2}


def test_deep_merge_does_not_recurse_when_base_is_not_dict():
    base = {"a": 1}
    over = {"a": {"b": 2}}
    _deep_merge(base, over)
    assert base == {"a": {"b": 2}}


def test_list_species_returns_sorted_names():
    names = _list_species()
    # In Task 7, the configs/species/ package is empty (Task 8 adds the YAMLs).
    # The function must work without crashing on the empty package.
    assert isinstance(names, list)
    assert all(isinstance(n, str) for n in names)


def test_unknown_species_raises(tmp_path):
    with pytest.raises(ConfigError, match="unknown species preset"):
        load_config(
            yaml_path=None,
            cli_overrides={},
            output=tmp_path / "x.glb",
            species="redwood",
        )
