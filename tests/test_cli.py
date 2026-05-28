import subprocess
import sys
from pathlib import Path

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


def test_preview_smoke(tmp_path):
    """End-to-end: generate a .glb, then preview it to a PNG."""
    from palubicki.cli import main
    glb = tmp_path / "tree.glb"
    rc = main([
        "generate", "-o", str(glb),
        "--seed", "7",
        "--envelope", "ellipsoid",
        "--envelope-radii", "0.5", "1.0", "0.5",
        "--marker-count", "200",
        "--iterations", "4",
    ])
    assert rc == 0
    assert glb.exists()

    png = tmp_path / "tree.png"
    rc = main(["preview", str(glb), "-o", str(png), "--size", "200x200"])
    assert rc == 0
    assert png.exists()
    assert png.stat().st_size > 1_000


def test_preview_invalid_glb(tmp_path, capsys):
    from palubicki.cli import main
    rc = main(["preview", str(tmp_path / "missing.glb"),
               "-o", str(tmp_path / "x.png")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "preview error" in err and "could not load" in err


def test_preview_parses_size_flag(tmp_path):
    from palubicki.cli import _parse_size
    assert _parse_size("1200x900") == (1200, 900)
    assert _parse_size("800x800") == (800, 800)


def test_preview_size_flag_rejects_garbage():
    from palubicki.cli import _parse_size
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_size("not-a-size")
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_size("800x")


def test_preview_parses_bg_flag():
    from palubicki.cli import _parse_bg
    assert _parse_bg("white") == (1.0, 1.0, 1.0, 1.0)
    assert _parse_bg("black") == (0.0, 0.0, 0.0, 1.0)
    assert _parse_bg("transparent") == (1.0, 1.0, 1.0, 0.0)


def test_preview_renderer_dep_missing_exits_2(tmp_path, capsys, monkeypatch):
    """If matplotlib is missing at runtime, preview returns exit 2 (setup error),
    not exit 1 (data error)."""
    from palubicki.cli import main
    # Generate a valid .glb first
    glb = tmp_path / "tree.glb"
    rc = main([
        "generate", "-o", str(glb),
        "--seed", "7",
        "--envelope", "ellipsoid",
        "--envelope-radii", "0.5", "1.0", "0.5",
        "--marker-count", "200",
        "--iterations", "4",
    ])
    assert rc == 0

    # Force the matplotlib import inside render_mesh to fail
    import sys as _sys
    monkeypatch.setitem(_sys.modules, "matplotlib", None)

    rc = main(["preview", str(glb), "-o", str(tmp_path / "out.png"),
               "--size", "100x100"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "preview error" in err
    assert "matplotlib" in err


def test_edit_help_lists_flags(capsys):
    from palubicki.cli import main
    with pytest.raises(SystemExit) as exc:
        main(["edit", "--help"])
    out = capsys.readouterr().out
    assert exc.value.code == 0
    for flag in ("--config", "--species", "--seed", "--port", "--no-browser"):
        assert flag in out


@pytest.mark.slow
def test_cli_diagnose_single_seed_runs():
    res = _run("diagnose", "--species", "oak", "--seed", "0")
    assert res.returncode == 0, res.stderr
    assert "tree_height" in res.stdout
    assert ("bif_ratio" in res.stdout) or ("bifurcation_ratio" in res.stdout)


@pytest.mark.slow
def test_cli_diagnose_json():
    import json as _json
    res = _run("diagnose", "--species", "oak", "--seed", "0", "--json")
    assert res.returncode == 0, res.stderr
    data = _json.loads(res.stdout)
    assert "tree_height" in data
    assert "strahler_order_max" in data
    assert "horton_bifurcation_ratio_mean" in data


@pytest.mark.slow
def test_cli_diagnose_multi_seed():
    res = _run("diagnose", "--species", "oak", "--seed", "0,1,2")
    assert res.returncode == 0, res.stderr
    assert "mean" in res.stdout
    assert "stddev" in res.stdout


def test_cli_diagnose_bad_seed_list():
    res = _run("diagnose", "--species", "oak", "--seed", "0,foo")
    assert res.returncode == 2


@pytest.mark.slow
def test_edit_server_boots_and_serves_schema():
    import socket
    import threading
    import time
    import urllib.request
    import urllib.error

    from palubicki.cli import _find_free_port
    from palubicki.edit.server import create_app
    from palubicki.config import load_config

    port = _find_free_port(9000)
    assert port is not None

    cfg = load_config(yaml_path=None, cli_overrides={}, output=Path("tree.glb"))
    app = create_app(cfg)

    import uvicorn
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    # Poll up to 3s for readiness
    deadline = time.time() + 3.0
    body = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/schema", timeout=0.5) as resp:
                body = resp.read()
                break
        except (urllib.error.URLError, ConnectionRefusedError):
            time.sleep(0.05)
    server.should_exit = True
    t.join(timeout=2.0)

    assert body is not None, "server never answered /api/schema"
    import json
    parsed = json.loads(body)
    assert "sections" in parsed
