# src/palubicki/sim/light.py
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from palubicki.config import EnvelopeConfig, LightConfig
from palubicki.sim.radii import compute_radii
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

    def rebuild_from_tree(
        self, tree: Tree, cfg: LightConfig, *, r_tip: float | None = None, exponent: float | None = None,
    ) -> None:
        """Full rebuild. Zero LAI, optionally recompute radii, then inject leaves + internodes."""
        self.lai.fill(0.0)
        cell_volume = float(np.prod(self.cell_size))
        if cell_volume <= 0:
            return

        if r_tip is not None and exponent is not None:
            compute_radii(tree, r_tip=r_tip, exponent=exponent)

        leaf_lai = cfg.leaf_area / cell_volume
        sub_step = float(np.min(self.cell_size))

        stack = [tree.root]
        while stack:
            node = stack.pop()
            for child_iod in node.children_internodes:
                stack.append(child_iod.child_node)
                self._inject_internode(child_iod, sub_step, cfg.internode_area_scale, cell_volume)
            bud = node.terminal_bud
            if bud is None or bud.state == BudState.DEAD:
                continue
            if node.children_internodes:
                continue
            cell = self.world_to_cell(bud.position)
            if cell is None:
                continue
            self.lai[cell] += leaf_lai

    def sample_transmission(self, p: np.ndarray, direction: np.ndarray, *, k: float) -> float:
        """Ray-march Beer-Lambert from p along direction. Returns T = exp(-Σ k·LAI·step)."""
        d_norm = float(np.linalg.norm(direction))
        if d_norm < 1e-12:
            return 1.0
        d = direction / d_norm

        step_len = float(np.min(self.cell_size))
        # Max number of steps to traverse the grid diagonally.
        grid_diag = float(np.linalg.norm(self.cell_size * np.array(self.resolution)))
        max_steps = int(np.ceil(grid_diag / step_len)) + 2

        optical_depth = 0.0
        pos = p.astype(np.float64).copy()
        for _ in range(max_steps):
            cell = self.world_to_cell(pos)
            if cell is None:
                pos = pos + d * step_len
                continue  # outside the grid: don't accumulate, but keep marching
            optical_depth += k * float(self.lai[cell]) * step_len
            pos = pos + d * step_len
        return float(np.exp(-optical_depth))

    def sample_hemisphere(
        self,
        p: np.ndarray,
        *,
        n_rays: int,
        light_direction: np.ndarray,
        k: float,
        seed: int,
    ) -> tuple[float, np.ndarray]:
        """Sample K cosine-weighted directions around light_direction.

        Returns (light_factor, gradient):
          light_factor = mean(T_k) ∈ [0, 1]
          gradient = normalize(Σ T_k · d_k), or zero vector if Σ ≈ 0
        """
        rng = np.random.default_rng(seed)
        # Build orthonormal basis (u, v, w) with w = light_direction (normalized).
        w = np.asarray(light_direction, dtype=np.float64)
        w_norm = float(np.linalg.norm(w))
        if w_norm < 1e-12:
            return 1.0, np.zeros(3)
        w = w / w_norm
        # Pick a canonical axis not parallel to w.
        canonical = np.array([1.0, 0.0, 0.0]) if abs(w[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u = canonical - np.dot(canonical, w) * w
        u = u / np.linalg.norm(u)
        v = np.cross(w, u)

        # Cosine-weighted hemisphere sampling: concentric disk + projection.
        u1 = rng.random(n_rays)
        u2 = rng.random(n_rays)
        r = np.sqrt(u1)
        phi = 2 * np.pi * u2
        x_d = r * np.cos(phi)
        y_d = r * np.sin(phi)
        z_d = np.sqrt(np.maximum(0.0, 1.0 - u1))
        # Directions in world frame
        dirs = x_d[:, None] * u + y_d[:, None] * v + z_d[:, None] * w   # (n_rays, 3)

        transmissions = np.empty(n_rays)
        for i in range(n_rays):
            transmissions[i] = self.sample_transmission(p, dirs[i], k=k)

        light_factor = float(np.mean(transmissions))
        weighted = (transmissions[:, None] * dirs).sum(axis=0)
        grad_norm = float(np.linalg.norm(weighted))
        gradient = weighted / grad_norm if grad_norm > 1e-12 else np.zeros(3)
        return light_factor, gradient

    def _inject_internode(self, iod, sub_step: float, scale: float, cell_volume: float) -> None:
        """Inject lateral surface LAI along the internode in sub-segments of length sub_step."""
        if iod.diameter <= 0 or scale <= 0 or iod.length <= 0:
            return
        p0 = iod.parent_node.position
        p1 = iod.child_node.position
        seg = p1 - p0
        seg_len = float(np.linalg.norm(seg))
        if seg_len < 1e-12:
            return
        direction = seg / seg_len
        radius = 0.5 * iod.diameter
        n_steps = max(1, int(np.ceil(seg_len / sub_step)))
        actual_step = seg_len / n_steps
        sub_surface = 2.0 * np.pi * radius * actual_step * scale
        sub_lai = sub_surface / cell_volume
        for k in range(n_steps):
            p = p0 + (k + 0.5) * actual_step * direction
            cell = self.world_to_cell(p)
            if cell is not None:
                self.lai[cell] += sub_lai
