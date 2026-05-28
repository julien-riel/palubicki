"""Position-based lateral-bud-break bias along an axis (acro/basi/mesotonic)."""
from __future__ import annotations

from typing import Literal


def position_weight(
    node_index: int,
    axis_length: int,
    mode: Literal["uniform", "acrotonic", "basitonic", "mesotonic"],
    strength: float,
) -> float:
    """Position-based multiplier in [0, 1] for lateral-bud quality.

    ``node_index`` is 0 at the axis base, ``axis_length - 1`` at the tip.
    ``strength`` in [0, 1]: 0 = no bias (returns 1.0 in any mode),
    1 = full bias (disfavored end returns 0.0).
    """
    if mode == "uniform" or strength == 0.0 or axis_length <= 1:
        return 1.0

    t = node_index / (axis_length - 1)  # 0 at base, 1 at tip

    if mode == "acrotonic":
        shape = t
    elif mode == "basitonic":
        shape = 1.0 - t
    elif mode == "mesotonic":
        shape = 1.0 - 2.0 * abs(t - 0.5)  # tent function peaking at t=0.5
    else:
        raise ValueError(
            f"unknown bud_break_bias mode: {mode!r} "
            f"(expected 'uniform'|'acrotonic'|'basitonic'|'mesotonic')"
        )

    return (1.0 - strength) + strength * shape
