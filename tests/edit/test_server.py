from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from palubicki.config import load_config
from palubicki.edit.server import create_app


@pytest.fixture
def default_cfg(tmp_path):
    return load_config(yaml_path=None, cli_overrides={}, output=tmp_path / "tree.glb")


@pytest.fixture
def client(default_cfg):
    app = create_app(default_cfg)
    return TestClient(app)


def test_get_schema_returns_sections_and_species(client):
    r = client.get("/api/schema")
    assert r.status_code == 200
    body = r.json()
    assert "sections" in body
    assert "species" in body
    assert any(sec["name"] == "envelope" for sec in body["sections"])


def test_get_initial_returns_valid_config(client, tmp_path):
    r = client.get("/api/initial")
    assert r.status_code == 200
    body = r.json()
    # Round-trip: must produce a valid Config via load_config
    from palubicki.edit.config_io import config_dict_to_overrides
    cfg = load_config(
        yaml_path=None,
        cli_overrides=config_dict_to_overrides(body),
        output=tmp_path / "tree.glb",
    )
    assert cfg.envelope.shape in ("sphere", "ellipsoid", "cone", "half_ellipsoid")


def test_post_species_oak_returns_preset_dict(client):
    r = client.post("/api/species/oak")
    assert r.status_code == 200
    body = r.json()
    # Preset YAML for oak contains an "envelope" section
    assert "envelope" in body or "sim" in body or "geom" in body


def test_post_species_unknown_returns_400(client):
    r = client.post("/api/species/notarealspecies")
    assert r.status_code == 400
    assert "error" in r.json()
