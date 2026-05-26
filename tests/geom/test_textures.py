import io

import pytest
from PIL import Image

from palubicki.geom._textures import (
    _PROC_TEXTURES,
    birch_bark_png, birch_leaf_png,
    default_leaf_png,
    oak_bark_png, oak_leaf_png,
    pine_bark_png, pine_needle_png,
)


BARK_GENS = [oak_bark_png, pine_bark_png, birch_bark_png]
LEAF_GENS = [oak_leaf_png, pine_needle_png, birch_leaf_png]


@pytest.mark.parametrize("gen", BARK_GENS)
def test_bark_png_produces_valid_image(gen):
    png = gen(256)
    assert len(png) > 100
    img = Image.open(io.BytesIO(png))
    assert img.size == (256, 256)
    assert img.mode in {"RGB", "RGBA"}


@pytest.mark.parametrize("gen", LEAF_GENS)
def test_leaf_png_is_rgba_with_alpha(gen):
    png = gen(128)
    img = Image.open(io.BytesIO(png))
    assert img.size == (128, 128)
    assert img.mode == "RGBA"
    alpha = img.split()[-1]
    extrema = alpha.getextrema()
    assert extrema[0] == 0, "leaf should have transparent regions outside the silhouette"
    assert extrema[1] == 255, "leaf should have fully opaque pixels inside the silhouette"


@pytest.mark.parametrize("gen", BARK_GENS + LEAF_GENS + [default_leaf_png])
def test_texture_is_deterministic(gen):
    a = gen(64)
    b = gen(64)
    assert a == b


def test_proc_textures_registry_has_six_entries():
    assert set(_PROC_TEXTURES) == {
        "oak_bark", "pine_bark", "birch_bark",
        "oak_leaf", "pine_needle", "birch_leaf",
    }


def test_proc_textures_callable_returns_bytes():
    for name, gen in _PROC_TEXTURES.items():
        png = gen()
        assert isinstance(png, bytes) and len(png) > 100, f"generator {name} broken"
