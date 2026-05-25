import io

from PIL import Image

from palubicki.geom._leaf_texture import default_leaf_png


def test_returns_png_bytes():
    data = default_leaf_png()
    assert isinstance(data, bytes)
    img = Image.open(io.BytesIO(data))
    assert img.format == "PNG"
    assert img.mode in ("RGBA", "LA")


def test_has_alpha_variation():
    data = default_leaf_png()
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    alphas = img.split()[3]
    bbox = alphas.getbbox()
    # Some opaque area smaller than the canvas (leaf doesn't fill the whole quad)
    assert bbox is not None
    w, h = img.size
    assert (bbox[2] - bbox[0]) < w
    assert (bbox[3] - bbox[1]) < h
