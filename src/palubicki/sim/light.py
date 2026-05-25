# src/palubicki/sim/light.py
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from palubicki.config import EnvelopeConfig, LightConfig
from palubicki.sim.tree import BudState, Tree


def _envelope_aabb(env: EnvelopeConfig) -> tuple[np.ndarray, np.ndarray]:
    """Returns (aabb_min, aabb_max) for the envelope."""
    c = np.asarray(env.center, dtype=np.float64)
    if env.shape == "sphere":
        r = env.rx
        return c - r, c + r
    if env.shape == "ellipsoid":
        r = np.array([env.rx, env.ry, env.rz])
        return c - r, c + r
    if env.shape == "half_ellipsoid":
        r = np.array([env.rx, env.ry, env.rz])
        amin = c - np.array([env.rx, 0.0, env.rz])
        amax = c + r
        return amin, amax
    if env.shape == "cone":
        amin = c - np.array([env.rx, 0.0, env.rz])
        amax = c + np.array([env.rx, env.ry, env.rz])
        return amin, amax
    raise ValueError(f"unknown envelope shape: {env.shape}")


def _autofit_bounds(env: EnvelopeConfig) -> tuple[np.ndarray, np.ndarray]:
    """Return (origin, size) auto-fit to envelope AABB with sky margin.

    The grid is padded by 10% of extent on each side in x and z, and 10%
    below + 30% above in y (sky clearance), giving total size factors of
    1.2× in x/z and 1.4× in y.
    """
    aabb_min, aabb_max = _envelope_aabb(env)
    extent = aabb_max - aabb_min
    origin = aabb_min - 0.1 * extent
    # margin_top: extra space above aabb_max
    # x/z: 0.1*extent so that total = 0.1 below + 0.1 above = 1.2× extent
    # y:   0.3*extent so that total = 0.1 below + 0.3 above = 1.4× extent
    margin_top = np.array([0.1 * extent[0], 0.3 * extent[1], 0.1 * extent[2]])
    size = (aabb_max + margin_top) - origin
    return origin, size


@dataclass
class LightGrid:
    origin: np.ndarray            # (3,) float64
    cell_size: np.ndarray         # (3,) float64
    resolution: tuple[int, int, int]
    lai: np.ndarray               # (nx, ny, nz) float32

    @classmethod
    def from_config(cls, light_cfg: LightConfig, env_cfg: EnvelopeConfig) -> "LightGrid":
        if light_cfg.grid_origin is None or light_cfg.grid_size is None:
            origin, size = _autofit_bounds(env_cfg)
        else:
            origin = np.asarray(light_cfg.grid_origin, dtype=np.float64)
            size = np.asarray(light_cfg.grid_size, dtype=np.float64)
        nx, ny, nz = light_cfg.grid_resolution
        cell_size = size / np.array([nx, ny, nz], dtype=np.float64)
        lai = np.zeros((nx, ny, nz), dtype=np.float32)
        return cls(origin=origin, cell_size=cell_size, resolution=(nx, ny, nz), lai=lai)

    def world_to_cell(self, p: np.ndarray) -> tuple[int, int, int] | None:
        local = p - self.origin
        idx = np.floor(local / self.cell_size).astype(int)
        nx, ny, nz = self.resolution
        if (idx[0] < 0 or idx[0] >= nx or idx[1] < 0 or idx[1] >= ny or idx[2] < 0 or idx[2] >= nz):
            return None
        return int(idx[0]), int(idx[1]), int(idx[2])

    def cell_to_world_center(self, i: int, j: int, k: int) -> np.ndarray:
        return self.origin + (np.array([i, j, k], dtype=np.float64) + 0.5) * self.cell_size

    def rebuild_from_tree(self, tree: Tree, cfg: LightConfig) -> None:
        """Full rebuild. Zero LAI, then inject leaves (terminal buds on tip nodes)."""
        self.lai.fill(0.0)
        cell_volume = float(np.prod(self.cell_size))
        if cell_volume <= 0:
            return
        leaf_lai = cfg.leaf_area / cell_volume

        stack = [tree.root]
        while stack:
            node = stack.pop()
            for child_iod in node.children_internodes:
                stack.append(child_iod.child_node)
            bud = node.terminal_bud
            if bud is None or bud.state == BudState.DEAD:
                continue
            if node.children_internodes:
                continue  # not a tip — skip (no leaf at an interior node)
            cell = self.world_to_cell(bud.position)
            if cell is None:
                continue
            self.lai[cell] += leaf_lai
