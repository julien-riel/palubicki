# src/palubicki/sim/debug_capture.py
"""Observational debug capture for the editor's sim-internals visualizer (#29).

The collector only READS forest state and diffs it between frames — it never
mutates the sim, so threading it through ``simulate_forest`` cannot perturb the
deterministic evolution (the bit-exact backward-compat contract holds)."""
from __future__ import annotations

import numpy as np

_NDIGITS = 4


def _round_vec(v) -> list[float]:
    """Round a 3-vector to plain rounded floats for a lean JSON payload."""
    return [round(float(x), _NDIGITS) for x in v]


class DebugCollector:
    def __init__(self) -> None:
        self._envelope: dict | None = None
        self._marker_positions: np.ndarray | None = None
        self._prev_alive: np.ndarray | None = None
        self._prev_iods: dict[int, tuple[list, list]] | None = None
        self._frames: list[dict] = []

    def capture_static(self, forest, cfg) -> None:
        env = forest.per_tree_cfgs[0].envelope
        self._envelope = {
            "shape": env.shape,
            "center": [float(x) for x in env.center],
            "radii": [float(env.rx), float(env.ry), float(env.rz)],
        }
        self._marker_positions = np.asarray(forest.markers.positions, dtype=float)
        self._prev_alive = forest.markers.alive_mask()
        self._prev_iods = self._current_iods(forest)

    @staticmethod
    def _current_iods(forest) -> dict[int, tuple[list, list]]:
        """Map id(internode) -> (rounded parent endpoint, rounded child endpoint)
        across all trees. Endpoints are rounded copies, so later in-place position
        edits (sag/elongation) cannot corrupt a remembered shed segment."""
        out: dict[int, tuple[list, list]] = {}
        for tree in forest.trees:
            for iod in tree.all_internodes:
                out[id(iod)] = (
                    _round_vec(iod.parent_node.position),
                    _round_vec(iod.child_node.position),
                )
        return out

    def timeline(self) -> dict:
        positions = (
            [_round_vec(p) for p in self._marker_positions]
            if self._marker_positions is not None else []
        )
        return {
            "envelope": self._envelope,
            "markers": {"positions": positions},
            "frames": self._frames,
        }
