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


def test_cli_forest_subcommand_generates_glb(tmp_path):
    from palubicki.cli import main
    output = tmp_path / "scene.glb"
    code = main([
        "forest",
        "-o", str(output),
        "--config", "tests/fixtures/forest_minimal.yaml",
    ])
    assert code == 0
    assert output.exists()
    assert output.stat().st_size > 0


def test_cli_forest_help_returns_zero():
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "palubicki", "forest", "--help"],
        capture_output=True,
    )
    assert result.returncode == 0


def test_cli_forest_missing_mesh_returns_clean_error(tmp_path, capsys):
    """A scene YAML pointing to a missing mesh file → clean error, no traceback."""
    from palubicki.cli import main
    yaml_path = tmp_path / "scene.yaml"
    yaml_path.write_text("""
envelope:
  marker_count: 500
sim:
  max_iterations: 2
forest:
  obstacles:
    - kind: mesh
      path: /nonexistent/path/missing.obj
""")
    code = main([
        "forest",
        "-o", str(tmp_path / "out.glb"),
        "--config", str(yaml_path),
    ])
    assert code == 1
    captured = capsys.readouterr()
    assert "forest error" in captured.err


@pytest.mark.slow
@pytest.mark.parametrize("species", ["oak", "pine", "birch"])
def test_generate_species_creates_valid_glb(tmp_path, species):
    out = tmp_path / f"{species}.glb"
    res = _run("generate", "--species", species, "--seed", "42",
               "--marker-count", "500",
               "--iterations", "8",
               "-o", str(out))
    assert res.returncode == 0, res.stderr
    assert out.exists()
    loaded = pygltflib.GLTF2().load(str(out))
    assert len(loaded.meshes) == 1
    assert len(loaded.meshes[0].primitives) >= 2  # bark + leaves
    assert len(loaded.textures) >= 1


def test_species_unknown_exits_nonzero(tmp_path):
    res = _run("generate", "--species", "redwood", "-o", str(tmp_path / "x.glb"))
    assert res.returncode != 0


def test_dump_defaults_species_oak_prints_preset_yaml():
    res = _run("dump-defaults", "--species", "oak")
    assert res.returncode == 0
    data = yaml.safe_load(res.stdout)
    assert data["envelope"]["shape"] == "half_ellipsoid"
    assert data["geom"]["bark_texture"] == "proc:oak_bark"
