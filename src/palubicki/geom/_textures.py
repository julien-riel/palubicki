from __future__ import annotations

import hashlib
import io
import math
import random
from collections.abc import Callable

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage


def default_leaf_png(size: int = 128) -> bytes:
    """Return PNG bytes of a simple oval green leaf with alpha mask."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = size // 8
    # Pointed oval
    draw.ellipse(
        (margin, margin // 2, size - margin, size - margin // 2),
        fill=(85, 138, 60, 255),
    )
    # Subtle vein
    draw.line((size // 2, margin // 2, size // 2, size - margin // 2),
              fill=(50, 90, 35, 200), width=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _seeded_rng(label: str) -> random.Random:
    """Deterministic Random keyed by texture label — guarantees reproducibility
    across processes (Python's built-in hash() is randomized via PYTHONHASHSEED)."""
    digest = hashlib.md5(label.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big")
    return random.Random(seed)


# ---------- BARK ----------

def oak_bark_png(size: int = 256) -> bytes:
    """Gris-brun fissuré vertical, sillons larges. Tileable horizontalement."""
    img = Image.new("RGB", (size, size), (95, 70, 50))
    draw = ImageDraw.Draw(img)
    rng = _seeded_rng("oak_bark")
    for _ in range(120):
        x = rng.randint(0, size)
        y = rng.randint(0, size)
        r = rng.randint(8, 28)
        shade = rng.randint(60, 110)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(shade, int(shade * 0.75), int(shade * 0.5)))
    for _ in range(14):
        x0 = rng.randint(0, size)
        amp = rng.uniform(2.0, 6.0)
        phase = rng.uniform(0, math.tau)
        width = rng.randint(2, 4)
        for tile_dx in (0, size):
            pts = []
            for y in range(0, size + 1, 4):
                x = x0 + tile_dx + amp * math.sin(phase + y * 0.05)
                pts.append((x, y))
            draw.line(pts, fill=(35, 25, 18), width=width)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def pine_bark_png(size: int = 256) -> bytes:
    """Plaques ocre/rouge irrégulières. Tileable."""
    img = Image.new("RGB", (size, size), (120, 70, 45))
    draw = ImageDraw.Draw(img)
    rng = _seeded_rng("pine_bark")
    for _ in range(40):
        cx = rng.randint(0, size)
        cy = rng.randint(0, size)
        n_verts = rng.randint(5, 8)
        radius = rng.randint(15, 35)
        pts = []
        for i in range(n_verts):
            angle = 2 * math.pi * i / n_verts + rng.uniform(-0.3, 0.3)
            r = radius * rng.uniform(0.7, 1.2)
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        shade_r = rng.randint(80, 170)
        shade_g = rng.randint(40, 80)
        shade_b = rng.randint(25, 55)
        draw.polygon(pts, fill=(shade_r, shade_g, shade_b), outline=(40, 20, 12))
        if cx < radius:
            pts2 = [(p[0] + size, p[1]) for p in pts]
            draw.polygon(pts2, fill=(shade_r, shade_g, shade_b), outline=(40, 20, 12))
        elif cx > size - radius:
            pts2 = [(p[0] - size, p[1]) for p in pts]
            draw.polygon(pts2, fill=(shade_r, shade_g, shade_b), outline=(40, 20, 12))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def birch_bark_png(size: int = 256) -> bytes:
    """Blanc cassé + stries horizontales noires + 'yeux' ovales. Tileable."""
    img = Image.new("RGB", (size, size), (235, 230, 220))
    draw = ImageDraw.Draw(img)
    rng = _seeded_rng("birch_bark")
    for _ in range(8):
        y = rng.randint(0, size - 1)
        h = rng.randint(2, 8)
        shade = rng.randint(20, 60)
        draw.rectangle((0, y, size, y + h), fill=(shade, shade, shade))
    for _ in range(12):
        cx = rng.randint(0, size)
        cy = rng.randint(0, size)
        w = rng.randint(6, 18)
        h = rng.randint(2, 6)
        draw.ellipse((cx - w, cy - h, cx + w, cy + h), fill=(20, 18, 15))
        if cx - w < 0:
            draw.ellipse((cx - w + size, cy - h, cx + w + size, cy + h), fill=(20, 18, 15))
        elif cx + w > size:
            draw.ellipse((cx - w - size, cy - h, cx + w - size, cy + h), fill=(20, 18, 15))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------- LEAVES ----------

def oak_leaf_png(size: int = 128) -> bytes:
    """Lobed silhouette (8 lobes), vert moyen, RGBA mask."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size / 2, size / 2
    n_lobes = 8
    pts = []
    for i in range(64):
        t = i / 64
        angle = 2 * math.pi * t - math.pi / 2
        lobe = 0.78 + 0.22 * math.cos(n_lobes * angle)
        r_x = (size * 0.42) * lobe
        r_y = (size * 0.48) * lobe
        pts.append((cx + r_x * math.cos(angle), cy + r_y * math.sin(angle)))
    draw.polygon(pts, fill=(75, 130, 55, 255))
    draw.line((cx, int(size * 0.05), cx, int(size * 0.95)), fill=(45, 85, 35, 220), width=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def pine_needle_png(size: int = 128) -> bytes:
    """Aiguille fine verticale, vert foncé, RGBA. Width ~12% of size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = size // 2
    w = max(2, size // 18)
    top = int(size * 0.05)
    bot = int(size * 0.95)
    draw.rectangle((cx - w, top, cx + w, bot), fill=(40, 80, 35, 255))
    draw.ellipse((cx - w, top - w, cx + w, top + w), fill=(40, 80, 35, 255))
    draw.polygon([(cx - w, bot), (cx + w, bot), (cx, min(bot + w * 2, size - 1))], fill=(40, 80, 35, 255))
    draw.line((cx, top, cx, bot), fill=(70, 110, 55, 200), width=1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def birch_leaf_png(size: int = 128) -> bytes:
    """Triangle pointu dentelé, vert clair, RGBA."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = size / 2
    top_y = size * 0.05
    bot_y = size * 0.95
    half_w = size * 0.32
    pts = [(cx, top_y)]
    n_teeth = 10
    for i in range(1, n_teeth + 1):
        t = i / n_teeth
        y = top_y + (bot_y - top_y) * t
        x_outer = cx + half_w * t
        x_inner = cx + half_w * t * 0.85
        pts.append((x_outer, y - (bot_y - top_y) / (n_teeth * 2)))
        pts.append((x_inner, y))
    pts.append((cx, bot_y))
    for i in range(n_teeth, 0, -1):
        t = i / n_teeth
        y = top_y + (bot_y - top_y) * t
        x_outer = cx - half_w * t
        x_inner = cx - half_w * t * 0.85
        pts.append((x_inner, y))
        pts.append((x_outer, y - (bot_y - top_y) / (n_teeth * 2)))
    draw.polygon(pts, fill=(120, 175, 80, 255))
    draw.line((cx, int(top_y), cx, int(bot_y)), fill=(70, 110, 50, 220), width=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------- HEIGHT FIELDS (P2 normal/ORM source) ----------
#
# Clean grayscale relief fields (NOT lit albedo) per species, the source
# geom/maps.py bakes into tangent-space normal + cavity-AO maps. Ridges high
# (→1), furrows low (→0). Seeded with a "_height" label so they draw
# independently of the albedo generators (no shared RNG stream → adding these
# never perturbs the existing base-colour textures). Each is Gaussian-blurred so
# the Sobel pass yields smooth normals instead of stair-stepped line edges.


def _l_to_field(img: Image.Image, sigma: float) -> np.ndarray:
    """8-bit 'L' image → blurred float32 height field in [0, 1]."""
    a = np.asarray(img, dtype=np.float32) / 255.0
    if sigma > 0:
        # wrap horizontally (bark tiles in u) for a seamless furrow normal.
        a = ndimage.gaussian_filter(a, sigma=sigma, mode=("nearest", "wrap"))
    lo, hi = float(a.min()), float(a.max())
    if hi - lo > 1e-6:
        a = (a - lo) / (hi - lo)
    return a


def oak_bark_height(size: int = 256) -> np.ndarray:
    """Deep vertical fissures over rounded ridges (mirrors oak_bark_png's relief)."""
    img = Image.new("L", (size, size), 150)
    draw = ImageDraw.Draw(img)
    rng = _seeded_rng("oak_bark_height")
    for _ in range(110):  # rounded ridge bumps (raised)
        x, y = rng.randint(0, size), rng.randint(0, size)
        r = rng.randint(10, 30)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=rng.randint(170, 215))
    for _ in range(14):  # sinuous vertical furrows (recessed grooves)
        x0 = rng.randint(0, size)
        amp = rng.uniform(2.0, 6.0)
        phase = rng.uniform(0, math.tau)
        width = rng.randint(3, 6)
        for tile_dx in (0, size):
            pts = [(x0 + tile_dx + amp * math.sin(phase + y * 0.05), y)
                   for y in range(0, size + 1, 4)]
            draw.line(pts, fill=20, width=width)
    return _l_to_field(img, sigma=2.5)


def pine_bark_height(size: int = 256) -> np.ndarray:
    """Raised irregular plates separated by recessed boundary grooves."""
    img = Image.new("L", (size, size), 70)  # boundary / groove level
    draw = ImageDraw.Draw(img)
    rng = _seeded_rng("pine_bark_height")
    for _ in range(40):
        cx, cy = rng.randint(0, size), rng.randint(0, size)
        n_verts = rng.randint(5, 8)
        radius = rng.randint(15, 35)
        pts = []
        for i in range(n_verts):
            angle = 2 * math.pi * i / n_verts + rng.uniform(-0.3, 0.3)
            r = radius * rng.uniform(0.7, 1.2)
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        shade = rng.randint(180, 235)  # plate top (raised)
        draw.polygon(pts, fill=shade, outline=40)
        if cx < radius:
            draw.polygon([(p[0] + size, p[1]) for p in pts], fill=shade, outline=40)
        elif cx > size - radius:
            draw.polygon([(p[0] - size, p[1]) for p in pts], fill=shade, outline=40)
    return _l_to_field(img, sigma=2.0)


def birch_bark_height(size: int = 256) -> np.ndarray:
    """Mostly smooth (birch bark is flat) with shallow horizontal lenticel grooves."""
    img = Image.new("L", (size, size), 200)
    draw = ImageDraw.Draw(img)
    rng = _seeded_rng("birch_bark_height")
    for _ in range(8):  # lenticel stripes (slightly recessed)
        y = rng.randint(0, size - 1)
        h = rng.randint(2, 7)
        draw.rectangle((0, y, size, y + h), fill=rng.randint(70, 120))
    for _ in range(12):  # "eyes" (recessed)
        cx, cy = rng.randint(0, size), rng.randint(0, size)
        w, h = rng.randint(6, 18), rng.randint(2, 6)
        draw.ellipse((cx - w, cy - h, cx + w, cy + h), fill=60)
    return _l_to_field(img, sigma=1.5)


_BARK_HEIGHT_FNS: dict[str, Callable[..., np.ndarray]] = {
    "oak_bark": oak_bark_height,
    "pine_bark": pine_bark_height,
    "birch_bark": birch_bark_height,
}


def bark_height_for(texture_name: str | None, size: int = 256) -> np.ndarray | None:
    """Height field matching a ``proc:<name>`` bark texture, else None.

    Returns ``None`` for authored/file bark (no clean height to synthesise) so the
    caller can fall back to a flat normal — never baking relief from a lit photo
    (design §6.3)."""
    if not texture_name:
        return None
    name = texture_name[5:] if texture_name.startswith("proc:") else texture_name
    fn = _BARK_HEIGHT_FNS.get(name)
    return fn(size) if fn is not None else None


# ---------- LEAF VEIN / MIDRIB SOURCE (P2 translucency + leaf normal) ----------


def leaf_vein_mask(
    size: int = 128,
    *,
    shape: str = "ovate",
    vein_pairs: int = 6,
) -> np.ndarray:
    """Lamina/vein source field in [0, 1]: 1 over thin lamina, →0 on the opaque
    midrib / secondary veins / petiole base.

    UV-aligned with :func:`palubicki.geom.leaf_blade.build_blade` (``tex_u`` runs
    across the blade with the midrib at ``u=0`` → column ``0.5``; ``tex_v`` runs
    base→tip). geom/maps.py turns this into the back-light alpha mask AND (via
    ``1 - mask``) a subtle vein normal map. ``palmate`` radiates veins from the
    base; every other shape uses a pinnate herringbone off the midrib.
    """
    img = Image.new("L", (size, size), 255)  # white lamina
    draw = ImageDraw.Draw(img)
    cx = size * 0.5
    midrib = max(2, int(size * 0.035))

    if shape == "palmate":
        base = (cx, size * 0.5)
        for k in range(5):
            ang = math.radians(-90 + (k - 2) * 32.0)  # fan upward from centre
            tip = (base[0] + size * 0.55 * math.sin(ang),
                   base[1] - size * 0.55 * math.cos(ang))
            draw.line([base, tip], fill=45, width=max(2, midrib - 1))
    else:
        # Midrib: tapered wedge, thick at the base (tex_v≈0, top row) → thin at tip.
        top, bot = int(size * 0.04), int(size * 0.96)
        draw.polygon(
            [(cx - midrib, top), (cx + midrib, top),
             (cx + max(1, midrib // 3), bot), (cx - max(1, midrib // 3), bot)],
            fill=45,
        )
        # Secondary veins: herringbone, alternating up the midrib toward the margin.
        for i in range(1, vein_pairs + 1):
            t = i / (vein_pairs + 1)
            y = top + (bot - top) * t
            reach = size * 0.42 * (1.0 - 0.5 * t)
            rise = size * 0.10
            draw.line([(cx, y), (cx + reach, y - rise)], fill=80, width=2)
            draw.line([(cx, y), (cx - reach, y - rise)], fill=80, width=2)

    # Petiole base: opaque wedge at the attachment end (tex_v≈0 → top).
    draw.polygon([(cx - midrib * 1.6, 0), (cx + midrib * 1.6, 0),
                  (cx, int(size * 0.10))], fill=30)

    a = np.asarray(img, dtype=np.float32) / 255.0
    a = ndimage.gaussian_filter(a, sigma=1.0, mode="nearest")
    return a


# ---------- REGISTRY ----------

_PROC_TEXTURES: dict[str, Callable[..., bytes]] = {
    "oak_bark": oak_bark_png,
    "pine_bark": pine_bark_png,
    "birch_bark": birch_bark_png,
    "oak_leaf": oak_leaf_png,
    "pine_needle": pine_needle_png,
    "birch_leaf": birch_leaf_png,
}
