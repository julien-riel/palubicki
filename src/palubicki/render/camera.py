# src/palubicki/render/camera.py
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import numpy as np

from palubicki.render.errors import RenderError

if TYPE_CHECKING:
    from palubicki.geom.mesh import Mesh


_DEFAULT_MARGIN = 0.08


@dataclass(frozen=True)
class Camera:
    """Y-up perspective camera. Defaults give a 3/4 view of a standing tree.

    elevation_deg: 0 = horizon, 90 = top-down
    azimuth_deg:   rotation around vertical (Y) axis
    target:        point the camera looks at (typically bbox center)
    distance:      camera-to-target distance; None = auto-fit from bbox
    margin:        padding around bbox in fit mode (8% default)
    """
    elevation_deg: float = 20.0
    azimuth_deg: float = 35.0
    target: tuple[float, float, float] = (0.0, 0.0, 0.0)
    distance: float | None = None
    margin: float = _DEFAULT_MARGIN

    @staticmethod
    def fit(mesh: "Mesh", **overrides) -> "Camera":
        """Auto-fit camera to mesh bbox. Concatenates all primitives' positions
        to compute the bbox, then sets target = bbox center and distance from
        the bbox extent (with `margin` padding)."""
        if not mesh.primitives:
            raise RenderError("cannot fit camera to empty mesh (no primitives)")

        all_positions = np.concatenate([p.positions for p in mesh.primitives])
        lo = all_positions.min(axis=0)
        hi = all_positions.max(axis=0)
        extent = (hi - lo).max()

        if extent < 1e-9:
            raise RenderError("mesh bounding box is degenerate (extent ≈ 0)")

        center = (lo + hi) * 0.5
        # Distance heuristic: extent / (2 tan(fov/2)) with fov=45° → ~1.21*extent.
        # Add margin and a small safety factor so the bbox sits inside the frame.
        margin = overrides.pop("margin", _DEFAULT_MARGIN)
        distance = extent * (1.0 + margin) * 1.5

        cam = Camera(
            target=tuple(float(c) for c in center),
            distance=float(distance),
            margin=margin,
        )
        return replace(cam, **overrides)
