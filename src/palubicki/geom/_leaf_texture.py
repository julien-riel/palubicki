from __future__ import annotations

import io

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
