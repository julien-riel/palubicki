from pathlib import Path

import pytest

from palubicki.config import (
    Config,
    ConfigError,
    EnvelopeConfig,
    GeomConfig,
    PhyllotaxyConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
)
from palubicki.geom.builder import _resolve_texture, build_mesh
from palubicki.sim.simulator import simulate


def _make_cfg(out, **geom_overrides):
    return Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.5, ry=1.0, rz=0.5, marker_count=200),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_iterations=4),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(**geom_overrides),
        seed=1, output=out,
    )


def test_resolve_none_returns_none():
    assert _resolve_texture(None) is None


def test_resolve_proc_scheme_returns_bytes():
    png = _resolve_texture("proc:oak_bark")
    assert isinstance(png, bytes) and len(png) > 100


def test_resolve_proc_unknown_raises_configerror():
    with pytest.raises(ConfigError, match="unknown proc texture"):
        _resolve_texture("proc:not_a_real_texture")


def test_resolve_path_reads_file(tmp_path):
    from PIL import Image
    p = tmp_path / "x.png"
    Image.new("RGB", (4, 4), (1, 2, 3)).save(p)
    assert _resolve_texture(p) == p.read_bytes()
    assert _resolve_texture(str(p)) == p.read_bytes()


def test_build_mesh_with_proc_bark_attaches_texture(tmp_path):
    cfg = _make_cfg(tmp_path / "x.glb", bark_texture=Path("proc:oak_bark"))
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    assert mesh.primitives[0].material.base_color_texture_png is not None
