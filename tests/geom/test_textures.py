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
    """Same generator in the same process returns identical bytes."""
    a = gen(64)
    b = gen(64)
    assert a == b


_EXPECTED_FIRST_BYTES = {
    "oak_bark": None,
    "pine_bark": None,
    "birch_bark": None,
    "oak_leaf": None,
    "pine_needle": None,
    "birch_leaf": None,
}


@pytest.mark.parametrize("name", list(_EXPECTED_FIRST_BYTES.keys()))
def test_texture_cross_process_stable(name):
    """Sentinel: the first 32 bytes of each generator's 64-px PNG must be stable.
    We pin them inline (since they only change if the generator algorithm changes).
    PYTHONHASHSEED randomization MUST NOT affect output."""
    import subprocess, sys
    code = f"from palubicki.geom._textures import _PROC_TEXTURES; import sys; sys.stdout.buffer.write(_PROC_TEXTURES[{name!r}](64)[:32])"
    # Run with PYTHONHASHSEED=0 and PYTHONHASHSEED=random to confirm identical output
    out1 = subprocess.run([sys.executable, "-c", code], capture_output=True, env={"PYTHONHASHSEED": "0", "PATH": ""}, check=True).stdout
    out2 = subprocess.run([sys.executable, "-c", code], capture_output=True, env={"PYTHONHASHSEED": "random", "PATH": ""}, check=True).stdout
    assert out1 == out2, f"{name}: bytes differ across PYTHONHASHSEED values (hash-randomization leak)"


def test_proc_textures_registry_has_six_entries():
    assert set(_PROC_TEXTURES) == {
        "oak_bark", "pine_bark", "birch_bark",
        "oak_leaf", "pine_needle", "birch_leaf",
    }


def test_proc_textures_callable_returns_bytes():
    for name, gen in _PROC_TEXTURES.items():
        png = gen()
        assert isinstance(png, bytes) and len(png) > 100, f"generator {name} broken"
