from pathlib import Path

from palubicki.config import (
    Config,
    EnvelopeConfig,
    GeomConfig,
    PhyllotaxyConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
)
from palubicki.geom.builder import build_mesh
from palubicki.sim.simulator import simulate


def _cfg(out: Path, bark_texture: Path | None) -> Config:
    return Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.5, ry=1.0, rz=0.5, marker_count=200),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, shoot_extension_max=0.1, vigor_dormancy=0.5, max_simulation_years=4.0),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(bark_texture=bark_texture),
        seed=1,
        output=out,
    )


def test_bark_material_has_no_texture_by_default(tmp_path):
    cfg = _cfg(tmp_path / "x.glb", bark_texture=None)
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    bark = mesh.primitives[0].material
    assert bark.base_color_texture_png is None


def test_bark_material_loads_supplied_png(tmp_path):
    from PIL import Image
    png_path = tmp_path / "bark.png"
    Image.new("RGB", (8, 8), (200, 150, 100)).save(png_path)

    cfg = _cfg(tmp_path / "x.glb", bark_texture=png_path)
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    bark = mesh.primitives[0].material
    assert bark.base_color_texture_png is not None
    assert bark.base_color_texture_png == png_path.read_bytes()
