import io

import numpy as np
from PIL import Image

from palubicki.geom._textures import (
    blade_albedo_png,
    default_leaf_png,
    leaf_vein_mask,
)


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


def test_blade_albedo_lamina_reaches_petiole_base():
    """The outline-derived albedo paints opaque lamina right at the petiole
    attachment (tex_v=0 → top row, centre col), so the alpha-MASK can't open the
    basal gap the old centred silhouettes left."""
    size = 128
    a = np.asarray(Image.open(io.BytesIO(
        blade_albedo_png(size=size, shape="palmate", aspect=1.0))).convert("RGBA"))[:, :, 3]
    cx = size // 2
    # opaque lamina exists in the top band near the centre (the base reaches it)
    assert (a[0:6, cx - 6:cx + 7] > 127).any()
    # the opaque region starts at the very top edge — not floating mid-card
    rows = np.where(a.max(axis=1) > 127)[0]
    assert rows.min() <= 2
    # ... yet does not fill the whole square (it's a leaf silhouette)
    assert (a > 127).mean() < 0.85


def test_leaf_vein_mask_palmate_fans_from_base_to_lobes():
    """The palmate vein mask radiates from the petiole anchor (top) out to the five
    lobe tips, instead of the old centre-anchored fan with the wrong angles."""
    size = 128
    vm = leaf_vein_mask(size=size, shape="palmate", aspect=1.0)  # 1 lamina, →0 vein
    dark = vm < 0.55
    cx = size // 2
    # the petiole anchor region (top band, centre) carries vein/petiole ink
    assert dark[0:14, cx - 8:cx + 9].any()
    # the fan spreads wide across u in the lower half (the 5 diverging lobe ribs)
    lower_cols = np.where(dark[size // 2:, :].any(axis=0))[0]
    assert lower_cols.max() - lower_cols.min() > size * 0.5
    # the centre column carries the central rib all the way down toward the tip
    assert dark[int(size * 0.8):, cx - 2:cx + 3].any()
