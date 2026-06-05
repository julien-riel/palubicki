# src/palubicki/sim/light.py
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from palubicki.config import EnvelopeConfig, GeomConfig, LightConfig, ShadowConfig
from palubicki.sim.radii import compute_radii
from palubicki.sim.tree import Tree


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
    below + 50% above in y (sky clearance), giving total size factors of
    1.2× in x/z and 1.6× in y. The top margin is generous so vigorous leaders
    that overshoot the envelope still fall inside the grid AABB (#FIX G);
    overshoot past even this is surfaced by a one-time warning in perception.
    """
    aabb_min, aabb_max = _envelope_aabb(env)
    extent = aabb_max - aabb_min
    origin = aabb_min - 0.1 * extent
    # margin_top: extra space above aabb_max
    # x/z: 0.1*extent so that total = 0.1 below + 0.1 above = 1.2× extent
    # y:   0.5*extent so that total = 0.1 below + 0.5 above = 1.6× extent
    margin_top = np.array([0.1 * extent[0], 0.5 * extent[1], 0.1 * extent[2]])
    size = (aabb_max + margin_top) - origin
    return origin, size


def _resolution_for(light_cfg: LightConfig, size: np.ndarray) -> tuple[int, int, int]:
    """Per-axis grid resolution. ``light.grid_resolution`` is a HARD override; when
    None it is DERIVED scale-aware from the post-autofit ``size`` and the target
    physical cell edge: clamp(ceil(size_axis / voxel_edge_m), 8, 192) per axis (#65)."""
    if light_cfg.grid_resolution is not None:
        return tuple(light_cfg.grid_resolution)
    size = np.asarray(size, dtype=np.float64)
    return tuple(
        int(np.clip(np.ceil(size[axis] / light_cfg.voxel_edge_m), 8, 192)) for axis in range(3)
    )


def _fib_hemisphere(n: int) -> np.ndarray:
    """``n`` roughly-even unit directions in the +Z hemisphere (Fibonacci
    spiral). Deterministic — no per-bud RNG — so the shadow-propagation gradient
    sampling (#56) is reproducible across runs. ``z ∈ (0, 1)`` keeps every
    direction forward (ahead of the bud's heading once rotated into its frame)."""
    n = max(1, int(n))
    i = np.arange(n, dtype=np.float64) + 0.5
    z = i / n                                       # (0, 1): forward hemisphere
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    phi = np.pi * (1.0 + 5.0 ** 0.5) * i            # golden-angle azimuth
    return np.stack([r * np.cos(phi), r * np.sin(phi), z], axis=1)


@dataclass
class LightGrid:
    origin: np.ndarray            # (3,) float64
    cell_size: np.ndarray         # (3,) float64
    resolution: tuple[int, int, int]
    lai: np.ndarray               # (nx, ny, nz) float32
    shadow: np.ndarray            # (nx, ny, nz) float32 — shadow-propagation field (#56)

    @classmethod
    def from_config(cls, light_cfg: LightConfig, env_cfg: EnvelopeConfig) -> LightGrid:
        if light_cfg.grid_origin is None or light_cfg.grid_size is None:
            origin, size = _autofit_bounds(env_cfg)
        else:
            origin = np.asarray(light_cfg.grid_origin, dtype=np.float64)
            size = np.asarray(light_cfg.grid_size, dtype=np.float64)
        nx, ny, nz = _resolution_for(light_cfg, size)
        cell_size = size / np.array([nx, ny, nz], dtype=np.float64)
        lai = np.zeros((nx, ny, nz), dtype=np.float32)
        shadow = np.zeros((nx, ny, nz), dtype=np.float32)
        return cls(origin=origin, cell_size=cell_size, resolution=(nx, ny, nz),
                   lai=lai, shadow=shadow)

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
        self, tree: Tree, cfg: LightConfig, *, geom: GeomConfig,
        r_tip: float | None = None, exponent: float | None = None,
        vigor_ref: float = 1.0, vigor_diameter_gain: float = 0.0,
    ) -> None:
        """Full rebuild. Zero LAI, optionally recompute radii, then inject leaves + internodes.

        Foliage occlusion is the real per-leaf/needle blade area from ``geom``
        (broadleaves via ``light.leaf_area_scale`` #62, conifers via
        ``light.needle_area_scale`` #7); see :meth:`_inject_tree`.
        ``vigor_ref``/``vigor_diameter_gain`` are forwarded to ``compute_radii`` so the
        light grid's occlusion diameters match the vigor-seeded rendered geometry (#37).
        """
        self.lai.fill(0.0)
        cell_volume = float(np.prod(self.cell_size))
        if cell_volume <= 0:
            return

        if r_tip is not None and exponent is not None:
            compute_radii(
                tree, r_tip=r_tip, exponent=exponent,
                vigor_ref=vigor_ref, vigor_diameter_gain=vigor_diameter_gain,
            )

        sub_step = float(np.min(self.cell_size))
        self._inject_tree(tree, geom, cfg, sub_step, cell_volume)

    def rebuild_from_forest(
        self,
        forest,
        cfg: LightConfig,
        *,
        geom: GeomConfig,
        r_tip: float | None = None,
        exponent: float | None = None,
        vigor_ref: float = 1.0,
        vigor_diameter_gain: float = 0.0,
    ) -> None:
        """Full rebuild for a forest. Zero LAI → inject leaves+internodes per tree →
        apply obstacle mask (lai[mask] = LAI_OPAQUE).

        Foliage occlusion is the real per-leaf/needle blade area from ``geom``
        (broadleaves via ``light.leaf_area_scale`` #62, conifers via
        ``light.needle_area_scale`` #7); see :meth:`_inject_tree`.
        ``vigor_ref``/``vigor_diameter_gain`` are forwarded to ``compute_radii`` so the
        light grid's occlusion diameters match the vigor-seeded rendered geometry (#37)."""
        from palubicki.sim.obstacles import LAI_OPAQUE

        self.lai.fill(0.0)
        cell_volume = float(np.prod(self.cell_size))
        if cell_volume <= 0:
            if forest.obstacle_voxel_mask is not None:
                self.lai[forest.obstacle_voxel_mask] = np.float32(LAI_OPAQUE)
            return

        sub_step = float(np.min(self.cell_size))

        for tree in forest.trees:
            if r_tip is not None and exponent is not None:
                compute_radii(
                    tree, r_tip=r_tip, exponent=exponent,
                    vigor_ref=vigor_ref, vigor_diameter_gain=vigor_diameter_gain,
                )
            self._inject_tree(tree, geom, cfg, sub_step, cell_volume)

        if forest.obstacle_voxel_mask is not None:
            self.lai[forest.obstacle_voxel_mask] = np.float32(LAI_OPAQUE)

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
        # Apex self-shading fix: record the ray's ORIGIN cell once and skip
        # optical-depth accumulation whenever the marched cell is that same cell.
        # The half-step start offset fails to leave the origin voxel ~43% of the
        # time, so a bud would otherwise be shaded by the foliage deposited at its
        # own node's cell (also handles any later re-entry of the self-voxel).
        origin_cell = tuple(
            np.floor((p.astype(np.float64) - self.origin) / self.cell_size).astype(int)
        )
        pos = p.astype(np.float64).copy() + 0.5 * step_len * d
        for _ in range(max_steps):
            cell = self.world_to_cell(pos)
            if cell is None:
                pos = pos + d * step_len
                continue  # outside the grid: don't accumulate, but keep marching
            if cell != origin_cell:
                optical_depth += k * float(self.lai[cell]) * step_len
            pos = pos + d * step_len
        return float(np.exp(-optical_depth))

    def sample_hemisphere_batch(
        self,
        positions: np.ndarray,
        *,
        n_rays: int,
        light_direction: np.ndarray,
        k: float,
        seeds: list[int],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Batched cosine-weighted hemisphere sampling for B query positions.

        Returns:
          light_factors: (B,) float64, mean transmission per bud.
          gradients:     (B, 3) float64, normalised *centered* brightness-weighted
            direction Σ (T_k - mean(T_k))·d_k / ‖·‖. Subtracting the per-bud mean
            transmission makes the gradient ZERO under uniform illumination (no
            spurious pull toward light_direction) and point toward the brighter side
            otherwise. Zero-norm => zero vector.

        Bit-exact with sequential ``sample_hemisphere`` calls: each (bud, ray) pair
        accumulates its optical depth step-by-step independently; we only batch the
        per-step LAI lookup across rays.
        """
        positions = np.asarray(positions, dtype=np.float64)
        B = positions.shape[0]
        if B == 0:
            return np.zeros(0, dtype=np.float64), np.zeros((0, 3), dtype=np.float64)

        # Per-bud frame and direction sampling — done independently per bud to
        # preserve the canonical-axis choice and the rng-stream-per-bud invariants.
        w = np.asarray(light_direction, dtype=np.float64)
        w_norm = float(np.linalg.norm(w))
        if w_norm < 1e-12:
            return np.ones(B, dtype=np.float64), np.zeros((B, 3), dtype=np.float64)
        w = w / w_norm
        canonical = np.array([1.0, 0.0, 0.0]) if abs(w[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u = canonical - np.dot(canonical, w) * w
        u = u / np.linalg.norm(u)
        v = np.cross(w, u)

        all_dirs = np.empty((B, n_rays, 3), dtype=np.float64)
        for bi, s in enumerate(seeds):
            rng = np.random.default_rng(s)
            u1 = rng.random(n_rays)
            u2 = rng.random(n_rays)
            r = np.sqrt(u1)
            phi = 2 * np.pi * u2
            x_d = r * np.cos(phi)
            y_d = r * np.sin(phi)
            z_d = np.sqrt(np.maximum(0.0, 1.0 - u1))
            all_dirs[bi] = x_d[:, None] * u + y_d[:, None] * v + z_d[:, None] * w

        flat_dirs = all_dirs.reshape(B * n_rays, 3)
        flat_origins = np.repeat(positions, n_rays, axis=0)  # (B*n_rays, 3)
        transmissions = self._sample_transmission_batch_origins(flat_origins, flat_dirs, k=k)
        T = transmissions.reshape(B, n_rays)

        light_factors = T.mean(axis=1)
        # Centered gradient: subtract the per-bud mean transmission before weighting,
        # so uniform illumination yields a zero gradient (no spurious light_direction
        # pull) while a brighter side still produces a net direction toward it.
        T_centered = T - light_factors[:, None]
        weighted = (T_centered[:, :, None] * all_dirs).sum(axis=1)  # (B, 3)
        grad_norms = np.linalg.norm(weighted, axis=1)
        gradients = np.zeros((B, 3), dtype=np.float64)
        nz = grad_norms > 1e-12
        gradients[nz] = weighted[nz] / grad_norms[nz, None]
        return light_factors, gradients

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
          gradient = normalize(Σ (T_k - mean(T_k)) · d_k), or zero vector if Σ ≈ 0.
            The *centered* weighting subtracts the bud's mean transmission so the
            gradient is ZERO under uniform illumination (no spurious pull toward
            light_direction) and points toward the brighter side otherwise.
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

        transmissions = self._sample_transmission_batch(p, dirs, k=k)

        light_factor = float(np.mean(transmissions))
        # Centered gradient: subtract the bud's mean transmission before weighting,
        # so uniform illumination yields a zero gradient (no spurious light_direction
        # pull) while a brighter side still produces a net direction toward it.
        weighted = ((transmissions - light_factor)[:, None] * dirs).sum(axis=0)
        grad_norm = float(np.linalg.norm(weighted))
        gradient = weighted / grad_norm if grad_norm > 1e-12 else np.zeros(3)
        return light_factor, gradient

    def _sample_transmission_batch_origins(
        self, origins: np.ndarray, dirs: np.ndarray, *, k: float,
    ) -> np.ndarray:
        """Same as _sample_transmission_batch but each ray has its own origin.

        Used by sample_hemisphere_batch for cross-bud batching.
        """
        n_rays = dirs.shape[0]
        d_norms = np.linalg.norm(dirs, axis=1)
        out = np.ones(n_rays, dtype=np.float64)
        active = d_norms >= 1e-12
        if not active.any():
            return out
        dirs_n = np.zeros_like(dirs)
        dirs_n[active] = dirs[active] / d_norms[active, None]

        step_len = float(np.min(self.cell_size))
        grid_diag = float(np.linalg.norm(self.cell_size * np.array(self.resolution)))
        max_steps = int(np.ceil(grid_diag / step_len)) + 2

        nx, ny, nz = self.resolution
        n_active = int(active.sum())
        positions = (origins[active] + 0.5 * step_len * dirs_n[active]).copy()
        step_vec = dirs_n[active] * step_len
        optical_depth = np.zeros(n_active, dtype=np.float64)

        cell_size = self.cell_size
        origin = self.origin
        lai = self.lai
        # Apex self-shading fix: record each ray's ORIGIN cell index once and skip
        # accumulation whenever the marched cell equals it (the half-step offset
        # fails to leave the origin voxel ~43% of the time). Per-ray here since each
        # ray has its own origin. Bit-consistent with the other two march paths.
        origin_cells = np.floor((origins[active] - origin) / cell_size).astype(np.intp)
        for _ in range(max_steps):
            local = positions - origin
            cells = np.floor(local / cell_size).astype(np.intp)
            in_grid = (
                (cells[:, 0] >= 0) & (cells[:, 0] < nx) &
                (cells[:, 1] >= 0) & (cells[:, 1] < ny) &
                (cells[:, 2] >= 0) & (cells[:, 2] < nz)
            )
            not_self = np.any(cells != origin_cells, axis=1)
            accumulate = in_grid & not_self
            if accumulate.any():
                vc = cells[accumulate]
                lai_vals = lai[vc[:, 0], vc[:, 1], vc[:, 2]].astype(np.float64)
                optical_depth[accumulate] += (k * lai_vals) * step_len
            positions += step_vec

        out[active] = np.exp(-optical_depth)
        return out

    def _sample_transmission_batch(
        self, p: np.ndarray, dirs: np.ndarray, *, k: float,
    ) -> np.ndarray:
        """Vectorised Beer-Lambert across rays. Bit-exact with sample_transmission per ray:
        same float32→float64 cast on LAI, same per-ray accumulation order (step 0, 1, ...),
        same ``(k * lai) * step_len`` multiplication order."""
        n_rays = dirs.shape[0]
        # Filter out zero-length directions (matches sample_transmission's 1.0 return).
        d_norms = np.linalg.norm(dirs, axis=1)
        out = np.ones(n_rays, dtype=np.float64)
        active = d_norms >= 1e-12
        if not active.any():
            return out
        dirs_n = np.zeros_like(dirs)
        dirs_n[active] = dirs[active] / d_norms[active, None]

        step_len = float(np.min(self.cell_size))
        grid_diag = float(np.linalg.norm(self.cell_size * np.array(self.resolution)))
        max_steps = int(np.ceil(grid_diag / step_len)) + 2

        nx, ny, nz = self.resolution
        n_active = int(active.sum())
        positions = (p.astype(np.float64) + 0.5 * step_len * dirs_n[active]).copy()  # (n_active, 3)
        step_vec = dirs_n[active] * step_len
        optical_depth = np.zeros(n_active, dtype=np.float64)

        cell_size = self.cell_size
        origin = self.origin
        lai = self.lai
        # Apex self-shading fix: record the shared ORIGIN cell index once and skip
        # accumulation whenever the marched cell equals it (the half-step offset
        # fails to leave the origin voxel ~43% of the time). All rays share origin p
        # here. Bit-consistent with the other two march paths.
        origin_cell = np.floor((p.astype(np.float64) - origin) / cell_size).astype(np.intp)
        for _ in range(max_steps):
            local = positions - origin
            cells = np.floor(local / cell_size).astype(np.intp)
            in_grid = (
                (cells[:, 0] >= 0) & (cells[:, 0] < nx) &
                (cells[:, 1] >= 0) & (cells[:, 1] < ny) &
                (cells[:, 2] >= 0) & (cells[:, 2] < nz)
            )
            not_self = np.any(cells != origin_cell, axis=1)
            accumulate = in_grid & not_self
            if accumulate.any():
                vc = cells[accumulate]
                lai_vals = lai[vc[:, 0], vc[:, 1], vc[:, 2]].astype(np.float64)
                optical_depth[accumulate] += (k * lai_vals) * step_len
            positions += step_vec

        out[active] = np.exp(-optical_depth)
        return out

    def _inject_tree(
        self, tree: Tree, geom: GeomConfig, cfg: LightConfig,
        sub_step: float, cell_volume: float,
    ) -> None:
        """Deposit one tree's internode + foliage occlusion into the LAI grid.

        Foliage uses the *real* per-leaf blade area from
        :func:`palubicki.geom.leaves.leaf_area_records` — the same per-Leaf area the
        ``total_leaf_area`` diagnostic and the rendered ``.glb`` use — deposited at
        each rendered leaf's cell, so self-shading reflects the actual foliage
        morphology (blade shape/size, compound layout, fascicle multiplicity,
        sun/shade). The scale is unitless and ``<= 0`` opts the foliage out:

        * **Broadleaves** (``leaf_shape != "linear"``): ``light.leaf_area_scale``.
        * **Conifers** (``leaf_shape == "linear"``): ``light.needle_area_scale``
          (#7). This replaces the pre-#7 terminal-bud scalar "canopy shell": conifer
          self-shading is now physical (a 5-needle pine fascicle deposits 5× the
          needle area into its cell), and conifer apical dominance is re-calibrated
          against this deposit (``sim.lambda_apical`` / ``sim.vigor_ref`` /
          ``light.k_absorption``) rather than propped up by a uniform shell — the
          #62-deferred coupling, landed together with the #7 fascicle geometry.
        """
        is_needle = geom.leaf_shape == "linear"
        foliage_scale = cfg.needle_area_scale if is_needle else cfg.leaf_area_scale
        if foliage_scale > 0.0:
            from palubicki.geom.leaves import leaf_area_records

            for pos, area in leaf_area_records(tree, geom):
                cell = self.world_to_cell(pos)
                if cell is not None:
                    self.lai[cell] += area * foliage_scale / cell_volume

        stack = [tree.root]
        while stack:
            node = stack.pop()
            for child_iod in node.children_internodes:
                stack.append(child_iod.child_node)
                self._inject_internode(
                    child_iod, sub_step, cfg.internode_area_scale, cell_volume,
                    wood_extinction_scale=cfg.wood_extinction_scale,
                )

    def _inject_internode(
        self, iod, sub_step: float, scale: float, cell_volume: float,
        *, wood_extinction_scale: float = 1.0,
    ) -> None:
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
        # Wood opacity knob (#65): scale the deposited wood LAD; 1.0 (default) =>
        # byte-identical, raise to model opaque branches that fully shade behind them.
        sub_lai = sub_surface * wood_extinction_scale / cell_volume
        for k in range(n_steps):
            p = p0 + (k + 0.5) * actual_step * direction
            cell = self.world_to_cell(p)
            if cell is not None:
                self.lai[cell] += sub_lai

    # ── Shadow-propagation exposure backend (#56) ─────────────────────────

    def propagate_shadow(self, forest, cfg: ShadowConfig, *, geom: GeomConfig) -> None:
        """Rebuild the shadow-propagation field from the current foliage (#56).

        Each leaf/needle stamps a downward pyramid of "shadow" into the voxels
        below it, decaying with depth as ``Δs = (area·area_weight)·a·b**(−q)``
        over ``q = 0..q_max`` layers, with a ``(2q+1)²`` footprint at layer q —
        the Palubicki 2009 index set ``(I±p, J−q, K±p)``, ``p = 0..q``. Occluders
        are the SAME real per-blade-area organs the LAI deposit uses
        (:func:`leaf_area_records`), so the canopy's shadow matches its rendered
        foliage (fascicle multiplicity, blade shape, sun/shade — all inherited).
        Wood is foliage-only for the first cut (#56 watch-item: a bole reading
        full light could sprout along its length).
        """
        self.shadow.fill(0.0)
        if int(cfg.q_max) < 0 or cfg.a <= 0 or cfg.area_weight <= 0:
            return
        from palubicki.geom.leaves import leaf_area_records

        positions: list = []
        areas: list = []
        for tree in forest.trees:
            for pos, area in leaf_area_records(tree, geom):
                positions.append(pos)
                areas.append(area)
        if positions:
            self._deposit_shadow(
                np.asarray(positions, dtype=np.float64),
                np.asarray(areas, dtype=np.float64),
                cfg,
            )

    def _deposit_shadow(
        self, positions: np.ndarray, areas: np.ndarray, cfg: ShadowConfig,
    ) -> None:
        """Stamp each organ's decaying downward pyramid into ``self.shadow``.

        ``positions`` (M,3) world; ``areas`` (M,). Readable per-organ loop with a
        per-layer slab add (the ``(2q+1)²`` footprint as a clamped array slice);
        vectorize across organs only if profiling the sim demands it (#56 R8)."""
        nx, ny, nz = self.resolution
        a, b, q_max, aw = float(cfg.a), float(cfg.b), int(cfg.q_max), float(cfg.area_weight)
        layer_factor = [a * (b ** (-q)) for q in range(q_max + 1)]
        weights = np.asarray(areas, dtype=np.float64) * aw
        for p, w in zip(positions, weights, strict=True):
            if w <= 0.0:
                continue
            home = self.world_to_cell(p)
            if home is None:
                continue
            cI, cJ, cK = home
            for q in range(q_max + 1):
                j = cJ - q
                if j < 0:
                    break
                ds = np.float32(w * layer_factor[q])
                i0, i1 = max(cI - q, 0), min(cI + q + 1, nx)
                k0, k1 = max(cK - q, 0), min(cK + q + 1, nz)
                if i0 < i1 and k0 < k1:
                    self.shadow[i0:i1, j, k0:k1] += ds

    def _shadow_at(self, pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Vectorised shadow lookup at world points ``pts`` (N,3). Returns
        ``(s, in_grid)``: ``s[i]`` is the shadow in the cell containing ``pts[i]``
        (0.0 where off-grid), ``in_grid[i]`` whether it fell inside the grid."""
        local = (np.asarray(pts, dtype=np.float64) - self.origin) / self.cell_size
        cells = np.floor(local).astype(np.intp)
        nx, ny, nz = self.resolution
        in_grid = (
            (cells[:, 0] >= 0) & (cells[:, 0] < nx) &
            (cells[:, 1] >= 0) & (cells[:, 1] < ny) &
            (cells[:, 2] >= 0) & (cells[:, 2] < nz)
        )
        s = np.zeros(cells.shape[0], dtype=np.float64)
        vc = cells[in_grid]
        if vc.size:
            s[in_grid] = self.shadow[vc[:, 0], vc[:, 1], vc[:, 2]].astype(np.float64)
        return s, in_grid

    def sample_exposure_batch(
        self,
        positions: np.ndarray,
        directions: np.ndarray,
        *,
        cfg: ShadowConfig,
        r_perception: float,
        n_dirs: int = 16,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Per-bud exposure ``Q`` and the light-gradient growth direction (#56).

        Returns:
          Q:        (B,) float64 exposure ``min(C, max(0, C − s_home + a))``. The
            ``+a`` cancels a bud's own ``q=0`` self-stamp so an unshaded bud reads
            exactly ``full_light_C`` (the upper clamp keeps Q ≤ C even when an
            organ's area-weighted self-stamp is below ``a``). Off-grid buds read
            full light. Q drives bud fate (dormancy / shedding).
          gradients: (B,3) float64 unit direction toward the most-exposed part of
            the perception cone, built like ``sample_hemisphere_batch`` (frame with
            w = bud heading; centered brightness weighting over forward
            directions), but reading the exposure field ``C − s`` at distance
            ``r_perception`` — NOT the ``+a`` self-corrected Q, since ``+a`` is a
            home-cell-only correction that must not bias neighbour samples (#56 C4).
            Zero under uniform exposure, so the tropism blend's inertia / orthotropy
            decide direction there (the #56 R1 fate/direction decoupling). A
            zero-length heading yields a zero gradient.
        """
        positions = np.asarray(positions, dtype=np.float64)
        directions = np.asarray(directions, dtype=np.float64)
        B = positions.shape[0]
        if B == 0:
            return np.zeros(0, dtype=np.float64), np.zeros((0, 3), dtype=np.float64)

        C = float(cfg.full_light_C)
        a = float(cfg.a)

        # Q (fate): home-cell shadow with flat +a self-cancel, clamped to C.
        s_home, home_in = self._shadow_at(positions)
        Q = np.where(home_in, np.minimum(C, np.maximum(0.0, C - s_home + a)), C)

        # Gradient (direction): toward the brightest perception-cone sample.
        canon = _fib_hemisphere(n_dirs)                 # (M,3) forward (+Z) hemisphere
        gradients = np.zeros((B, 3), dtype=np.float64)
        for i in range(B):
            w = directions[i]
            wn = float(np.linalg.norm(w))
            if wn < 1e-12:
                continue
            w = w / wn
            ref = np.array([1.0, 0.0, 0.0]) if abs(w[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
            u = ref - np.dot(ref, w) * w
            u = u / np.linalg.norm(u)
            v = np.cross(w, u)
            world_dirs = canon[:, 0:1] * u + canon[:, 1:2] * v + canon[:, 2:3] * w  # (M,3)
            pts = positions[i] + r_perception * world_dirs
            s_m, in_m = self._shadow_at(pts)
            E = np.where(in_m, np.maximum(0.0, C - s_m), C)   # off-grid = open sky
            weighted = ((E - E.mean())[:, None] * world_dirs).sum(axis=0)
            gn = float(np.linalg.norm(weighted))
            if gn > 1e-12:
                gradients[i] = weighted / gn
        return Q, gradients
