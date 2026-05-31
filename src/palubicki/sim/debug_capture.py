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
    """Per-run, read-only collector for the sim-internals debug overlay (#29).

    Lifecycle: call ``capture_static`` once after ``build_forest``, then
    ``capture_frame`` once per simulation step (added in a later task), then read
    the assembled payload via ``timeline``. It only reads forest state, so wiring
    it into ``simulate_forest`` cannot perturb the deterministic evolution.
    """

    def __init__(self) -> None:
        self._envelope: dict | None = None
        self._marker_positions: np.ndarray | None = None
        self._prev_alive: np.ndarray | None = None
        self._prev_iods: dict[int, tuple[list, list]] | None = None
        self._frames: list[dict] = []

    def capture_static(self, forest, cfg) -> None:
        """Record the static (sent-once) data: the displayed tree's envelope and
        the full marker cloud, plus baseline snapshots for later per-frame diffs.

        ``cfg`` is accepted for a stable capture API and future static sim-param
        extraction; only ``forest`` is read today. The envelope is taken from
        ``per_tree_cfgs[0]`` — the visualizer currently assumes a single displayed
        tree (forest mode shows all trees' buds over one envelope; see #29 spec).
        """
        env = forest.per_tree_cfgs[0].envelope
        self._envelope = {
            "shape": env.shape,
            "center": [float(x) for x in env.center],
            "radii": [float(env.rx), float(env.ry), float(env.rz)],
        }
        self._marker_positions = np.asarray(forest.markers.positions, dtype=float)
        self._prev_alive = forest.markers.alive_mask()  # baseline for per-frame killed-marker diffs (later task)
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

    def capture_frame(self, forest, t: float) -> None:
        # Markers: report only those that flipped alive->dead since the last frame.
        alive = forest.markers.alive_mask()
        newly_killed = np.flatnonzero(self._prev_alive & ~alive)
        self._prev_alive = alive

        # Shed: internodes present last frame but gone now (shed_low_quality
        # removes them from tree.all_internodes). Use the previously remembered
        # rounded endpoints so the segment is the branch as it was when culled.
        cur_iods = self._current_iods(forest)
        shed = [
            [p0, p1]
            for iid, (p0, p1) in self._prev_iods.items()
            if iid not in cur_iods
        ]
        self._prev_iods = cur_iods

        # Buds: the live set (ACTIVE / DORMANT), flattened across trees.
        buds = [
            {
                "p": _round_vec(b.position),
                "dir": _round_vec(b.direction),
                "state": b.state.name,
            }
            for tree in forest.trees
            for b in tree.active_buds
        ]

        self._frames.append({
            "t": round(float(t), _NDIGITS),
            "markers_killed": [int(i) for i in newly_killed],
            "buds": buds,
            "shed": shed,
        })

    def timeline(self) -> dict:
        """Return the JSON-ready debug payload (envelope, static markers, frames)."""
        positions = (
            [_round_vec(p) for p in self._marker_positions]
            if self._marker_positions is not None else []
        )
        return {
            "envelope": self._envelope,
            "markers": {"positions": positions},
            "frames": self._frames,
        }
