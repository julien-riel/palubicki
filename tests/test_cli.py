import subprocess
import sys

import pygltflib
import pytest
import yaml


def _run(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "palubicki.cli", *args],
        capture_output=True, text=True, cwd=cwd,
    )


def test_help_works():
    res = _run("--help")
    assert res.returncode == 0
    assert "generate" in res.stdout
    assert "dump-defaults" in res.stdout


def test_dump_defaults_yaml_parsable():
    res = _run("dump-defaults")
    assert res.returncode == 0
    data = yaml.safe_load(res.stdout)
    assert "envelope" in data
    assert "sim" in data
    assert data["sim"]["max_iterations"] == 30


@pytest.mark.slow
def test_generate_minimal(tmp_path):
    out = tmp_path / "tree.glb"
    res = _run("generate",
               "-o", str(out),
               "--envelope", "ellipsoid",
               "--envelope-radii", "0.5", "1.0", "0.5",
               "--marker-count", "300",
               "--iterations", "6",
               "--seed", "1")
    assert res.returncode == 0, res.stderr
    assert out.exists()
    loaded = pygltflib.GLTF2().load(str(out))
    assert len(loaded.meshes) == 1


def test_invalid_config_exits_2(tmp_path):
    res = _run("generate", "-o", str(tmp_path / "x.glb"),
               "--envelope-radii", "0", "0", "0")
    assert res.returncode == 2


@pytest.mark.slow
def test_cli_light_enabled_flag(tmp_path):
    """--light-enabled embeds light.enabled=True in the produced .glb config."""
    out = tmp_path / "tree_light.glb"
    res = _run("generate",
               "-o", str(out),
               "--envelope", "ellipsoid",
               "--envelope-radii", "0.5", "1.0", "0.5",
               "--marker-count", "300",
               "--iterations", "4",
               "--seed", "42",
               "--light-enabled")
    assert res.returncode == 0, res.stderr
    loaded = pygltflib.GLTF2().load(str(out))
    extras = (loaded.asset.extras or {}) if loaded.asset else {}
    cfg = extras.get("config", {})
    assert cfg.get("light", {}).get("enabled") is True


def test_dump_defaults_includes_light():
    """dump-defaults YAML output must include a 'light' section with enabled=False."""
    res = _run("dump-defaults")
    assert res.returncode == 0
    data = yaml.safe_load(res.stdout)
    assert "light" in data
    assert data["light"]["enabled"] is False
    assert data["light"]["n_rays"] == 16
