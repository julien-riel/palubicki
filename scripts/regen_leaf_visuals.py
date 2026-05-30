"""Regenerate matplotlib PNG references for each (shape, margin) combo.

These are human-review artifacts, not automated tests. They live in
tests/geom/visual/ and should be regenerated whenever leaf_blade.py changes
visually. Commit the new PNGs alongside the code change.

Usage:
    .venv/bin/python scripts/regen_leaf_visuals.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from palubicki.geom.leaf_blade import _OUTLINE_FNS, _apply_margin

OUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "geom" / "visual"

# Subset focused on what species presets actually use, plus pure-shape refs.
COMBOS = [
    ("linear", "entire", 0.0, 0),
    ("elliptic", "entire", 0.0, 0),
    ("lanceolate", "entire", 0.0, 0),
    ("ovate", "entire", 0.0, 0),
    ("ovate", "serrate", 0.08, 12),
    ("ovate", "dentate", 0.10, 10),
    ("ovate", "lobed", 0.35, 7),
    ("cordate", "entire", 0.0, 0),
    ("palmate", "entire", 0.0, 0),
    # cordate+toothed not committed: _eligible_arc_range needs a cordate-
    # specific carve-out for the basal notch (out of scope here; default
    # 2% skip places teeth in the notch and looks wrong).
]

L, W = 1.0, 0.7


def render(shape: str, margin: str, depth: float, count: int) -> None:
    boundary, anchor = _OUTLINE_FNS[shape](L, W) if shape != "palmate" \
        else _OUTLINE_FNS[shape](L, W)
    boundary = _apply_margin(boundary, margin, depth, count, shape, L, W)
    # Close the polygon for plotting.
    closed = np.vstack([boundary, boundary[:1]])
    fig, ax = plt.subplots(figsize=(3, 4))
    ax.fill(closed[:, 0], closed[:, 1], color="#4d7a2e", alpha=0.85)
    ax.plot(closed[:, 0], closed[:, 1], color="#2a4317", linewidth=1)
    ax.plot(anchor[0], anchor[1], "o", color="red", markersize=3)
    ax.set_aspect("equal")
    ax.set_title(f"{shape} / {margin}")
    ax.set_xlim(-0.5, 0.5)
    ax.set_ylim(-0.2, 1.1)
    ax.grid(True, alpha=0.3)
    out = OUT_DIR / f"{shape}_{margin}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=80, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    for combo in COMBOS:
        render(*combo)
