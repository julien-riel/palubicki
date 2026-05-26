from __future__ import annotations

import hashlib
import io
import math
import random
from collections.abc import Callable

from PIL import Image, ImageDraw


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


# ---------- REGISTRY ----------

_PROC_TEXTURES: dict[str, Callable[..., bytes]] = {
    "oak_bark": oak_bark_png,
    "pine_bark": pine_bark_png,
    "birch_bark": birch_bark_png,
    "oak_leaf": oak_leaf_png,
    "pine_needle": pine_needle_png,
    "birch_leaf": birch_leaf_png,
}
