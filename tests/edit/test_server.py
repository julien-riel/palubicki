
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


def test_post_species_oak_returns_full_merged_config(client):
    r = client.post("/api/species/oak")
    assert r.status_code == 200
    body = r.json()
    # Response is defaults + preset merged: all sections must be present
    # so the frontend can replace state.values wholesale.
    for section in ("envelope", "sim", "tropism", "phyllotaxy", "shedding",
                    "geom", "light", "sag"):
        assert section in body, f"missing section: {section}"


def test_post_species_switch_does_not_carry_over_previous_species(client):
    # Pine has no sag override, so requesting pine after oak must NOT return
    # oak's sag settings — it should be pristine defaults + pine's overrides.
    oak = client.post("/api/species/oak").json()
    pine = client.post("/api/species/pine").json()
    # Defaults for sag are enabled=False, k=0.01 (per config.SagConfig).
    assert pine["sag"]["enabled"] is False
    # And oak's leaf settings must not leak into pine.
    assert pine["geom"]["leaf_aspect"] != oak["geom"]["leaf_aspect"]


def test_post_species_unknown_returns_400(client):
    r = client.post("/api/species/notarealspecies")
    assert r.status_code == 400
    assert "error" in r.json()


def _tiny_config_dict():
    return {
        "envelope": {"shape": "ellipsoid", "rx": 1.0, "ry": 2.0, "rz": 1.0, "marker_count": 200},
        "sim": {"max_simulation_years": 3},
        "seed": 1,
    }


def test_post_generate_returns_glb(client):
    r = client.post("/api/generate", json=_tiny_config_dict())
    assert r.status_code == 200
    assert r.headers["content-type"] == "model/gltf-binary"
    body = r.content
    assert body[:4] == b"glTF"


def test_post_generate_invalid_config_returns_400(client):
    bad = _tiny_config_dict()
    bad["envelope"]["rx"] = -1.0
    r = client.post("/api/generate", json=bad)
    assert r.status_code == 400
    assert "error" in r.json()


def test_post_save_yaml_returns_loadable_yaml(client, tmp_path):
    import yaml as _yaml
    r = client.post("/api/save-yaml", json=_tiny_config_dict())
    assert r.status_code == 200
    body = r.text
    parsed = _yaml.safe_load(body)
    assert parsed["envelope"]["marker_count"] == 200

    # Should round-trip through load_config
    from palubicki.edit.config_io import config_dict_to_overrides
    cfg = load_config(
        yaml_path=None,
        cli_overrides=config_dict_to_overrides(parsed),
        output=tmp_path / "tree.glb",
    )
    assert cfg.envelope.marker_count == 200


def test_get_root_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<html" in r.text.lower()


def test_get_static_path_404_for_missing(client):
    r = client.get("/static/nonexistent.js")
    assert r.status_code == 404


def test_index_html_links_static_assets(client):
    r = client.get("/")
    assert r.status_code == 200
    text = r.text
    # Verify the vendored scripts and app entry are referenced
    assert "/static/style.css" in text
    assert "/static/vendor/three.min.js" in text
    assert "/static/vendor/GLTFLoader.js" in text
    assert "/static/vendor/OrbitControls.js" in text
    assert "/static/app.js" in text
    # Key DOM ids the JS will hook into
    for el_id in ("sections-root", "regenerate-btn", "viewer-canvas",
                  "species-select", "spinner", "toast-container"):
        assert f'id="{el_id}"' in text


def test_static_style_css_served(client):
    r = client.get("/static/style.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")


def test_app_js_served(client):
    r = client.get("/static/app.js")
    assert r.status_code == 200
    body = r.text
    # Sanity: core functions must be present
    assert "function init" in body or "async function init" in body
    assert "renderSidebar" in body
    assert "renderField" in body
    assert "regenerate" in body


def test_app_js_has_viewer_logic(client):
    r = client.get("/static/app.js")
    body = r.text
    # Symbols introduced in Task 16:
    assert "THREE.WebGLRenderer" in body
    assert "THREE.OrbitControls" in body
    assert "THREE.GLTFLoader" in body
    assert "disposeChildren" in body
    assert "fitCameraToObject" in body
    assert "replaceTree" in body


def test_app_js_has_export_and_toggle_handlers(client):
    r = client.get("/static/app.js")
    body = r.text
    for sym in ("exportGlb", "exportYaml", "toggleLeaves", "toggleWireframe"):
        assert sym in body
    # Action handlers must be wired to the DOM ids:
    for el_id in ("export-glb-btn", "export-yaml-btn", "toggle-leaves-btn", "toggle-wireframe-btn"):
        assert el_id in body


def test_debug_endpoint_404_before_any_capture(client):
    r = client.get("/api/debug")
    assert r.status_code == 404
    assert "error" in r.json()


def test_generate_without_debug_flag_leaves_no_capture(client):
    r = client.post("/api/generate", json=_tiny_config_dict())
    assert r.status_code == 200
    # No debug flag -> cost-free path, nothing cached.
    r2 = client.get("/api/debug")
    assert r2.status_code == 404


def test_generate_with_debug_flag_populates_timeline(client):
    payload = _tiny_config_dict()
    payload["debug"] = True
    r = client.post("/api/generate", json=payload)
    assert r.status_code == 200
    assert r.headers["content-type"] == "model/gltf-binary"
    assert r.content[:4] == b"glTF"
    # The debug flag must NOT leak into config parsing (still a valid GLB above).
    r2 = client.get("/api/debug")
    assert r2.status_code == 200
    tl = r2.json()
    assert set(tl.keys()) == {"envelope", "markers", "frames"}
    assert "positions" in tl["markers"]
    assert isinstance(tl["frames"], list) and len(tl["frames"]) >= 1
    frame = tl["frames"][0]
    assert set(frame.keys()) == {"t", "markers_killed", "buds", "shed"}


def test_index_html_has_debug_controls(client):
    text = client.get("/").text
    for el_id in (
        "debug-capture-toggle", "debug-panel", "timeline-slider",
        "timeline-play-btn", "timeline-readout",
        "layer-markers-toggle", "layer-envelope-toggle",
        "layer-buds-toggle", "layer-shed-toggle",
    ):
        assert f'id="{el_id}"' in text, f"missing debug control id: {el_id}"


def test_app_js_has_debug_overlay_logic(client):
    body = client.get("/static/app.js").text
    for sym in (
        "fetchDebugTimeline", "buildDebugLayers", "setFrame",
        "togglePlay", "debug-capture-toggle", "timeline-slider",
        "THREE.Points", "BufferGeometry",
    ):
        assert sym in body, f"missing app.js debug symbol: {sym}"


def test_app_js_regenerate_sends_debug_flag(client):
    body = client.get("/static/app.js").text
    # regenerate() must transmit the capture flag, else the server never captures.
    assert "debug: state.debug.enabled" in body
