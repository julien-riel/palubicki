# src/palubicki/config.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


class ConfigError(ValueError):
    """Raised when configuration validation fails."""


@dataclass(frozen=True)
class EnvelopeConfig:
    shape: Literal["sphere", "ellipsoid", "cone", "half_ellipsoid"] = field(
        default="ellipsoid",
        metadata={"ui": {"label": "Shape"}},
    )
    rx: float = field(default=1.0, metadata={"ui": {"min": 0.5, "max": 20.0, "step": 0.1}})
    ry: float = field(default=1.0, metadata={"ui": {"min": 0.5, "max": 20.0, "step": 0.1}})
    rz: float = field(default=1.0, metadata={"ui": {"min": 0.5, "max": 20.0, "step": 0.1}})
    center: tuple[float, float, float] = (0.0, 0.0, 0.0)  # not exposed in UI
    marker_count: int = field(default=20_000, metadata={"ui": {"min": 500, "max": 100_000, "step": 500}})


@dataclass(frozen=True)
class SympodialConfig:
    """When the terminal_bud fails (Q < threshold) for N consecutive steps,
    the lateral on the same node with the highest quality takes its place.
    The old terminal dies. The new leader orients itself naturally via the
    (stronger) main-axis tropism weights.
    """
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    q_threshold: float = field(default=1.0, metadata={"ui": {"min": 0.0, "max": 20.0, "step": 0.5}})
    n_consecutive_steps: int = field(default=3, metadata={"ui": {"min": 1, "max": 10, "step": 1}})


@dataclass(frozen=True)
class SimConfig:
    r_perception: float = field(default=0.6, metadata={"ui": {"min": 0.1, "max": 3.0, "step": 0.05}})
    theta_perception_deg: float = field(default=90.0, metadata={"ui": {"min": 10.0, "max": 180.0, "step": 5.0}})
    r_kill: float = field(default=0.15, metadata={"ui": {"min": 0.01, "max": 1.0, "step": 0.01}})
    internode_length: float = field(default=0.1, metadata={"ui": {"min": 0.02, "max": 0.5, "step": 0.01}})
    alpha_basipetal: float = field(default=2.0, metadata={"ui": {"min": 0.0, "max": 5.0, "step": 0.1}})
    lambda_apical: float = field(default=0.55, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.01}})
    max_iterations: int = field(default=30, metadata={"ui": {"min": 1, "max": 80, "step": 1}})
    re_perceive_per_substep: bool = field(default=True, metadata={"ui": {"label": "Re-perceive per substep"}})
    # Fix #1: if dot(v_perc, current_direction) < cos_min_perception, the bud
    # is sitting at the envelope boundary (markers only behind/below). It goes
    # DORMANT instead of folding back. -0.2 ≈ allow 100° before bending; raise
    # toward 0.0 to be strict, lower toward -1.0 to disable.
    cos_min_perception: float = field(default=-0.2, metadata={"ui": {"min": -1.0, "max": 1.0, "step": 0.05}})
    # Hard cap on internodes a single bud can extend in one iteration.
    # Default 1 matches the original Palubicki BHse: each iteration re-evaluates
    # perception, light, and competition; each apical bud either extends by one
    # internode or stays dormant. Higher values let vigorous buds outpace others
    # but also exhaust nearby markers faster (n internodes worth of growth +
    # r_kill in a single year), and re-introduce the "wineglass" fold-back when
    # the trunk shoots through the envelope in one iteration.
    n_substeps_max: int = field(default=1, metadata={"ui": {"min": 1, "max": 8, "step": 1}})
    # Gaussian jitter (σ as a fraction of internode_length) applied per new
    # internode. 0.0 = exact constant length; 0.10-0.15 = realistic variability.
    # The drawn factor is clamped to [0.5, 1.5] regardless of σ.
    internode_length_jitter: float = field(
        default=0.0, metadata={"ui": {"min": 0.0, "max": 0.5, "step": 0.01}}
    )
    sympodial: SympodialConfig = field(default_factory=lambda: SympodialConfig())
    shade_mortality: "ShadeMortalityConfig" = field(default_factory=lambda: ShadeMortalityConfig())
    elongation: "ElongationConfig" = field(default_factory=lambda: ElongationConfig())


@dataclass(frozen=True)
class ShadeMortalityConfig:
    """Kills buds whose light_factor stays below threshold for N consecutive steps."""
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    light_threshold: float = field(
        default=0.15, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.01}}
    )
    n_consecutive_steps: int = field(
        default=3, metadata={"ui": {"min": 1, "max": 10, "step": 1}}
    )


@dataclass(frozen=True)
class TropismConfig:
    w_perception: float = field(default=1.0, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    # Orthotropy = pull toward +Y. Distinct main-vs-lateral weights so axe principal
    # can stay vertical while latéraux open horizontally (oak/birch) or stay
    # near-horizontal (pine whorls).
    w_orthotropy_main: float = field(default=0.3, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    w_orthotropy_lateral: float = field(default=0.1, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    # Gravitropism = pull toward -Y. Distinct main vs lateral so e.g. birch
    # pendula can droop its laterals while the trunk stays vertical.
    w_gravitropism_main: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    w_gravitropism_lateral: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    # Plagiotropism = push toward the horizontal plane. v_plagio is the
    # projection of current_direction onto XY, renormalized. Main typically
    # stays 0 (trunk vertical); lateral > 0 forces branches to splay
    # horizontally. Independent of gravity (no pendula side effect).
    w_plagiotropism_main: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    w_plagiotropism_lateral: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    w_phototropism: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    w_direction_inertia: float = field(default=0.4, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    photo_direction: tuple[float, float, float] = (0.0, 1.0, 0.0)  # not exposed; vec3 stays defaulted
    axis_decay: float = field(default=1.0, metadata={"ui": {"min": 0.1, "max": 1.0, "step": 0.05}})


@dataclass(frozen=True)
class PhyllotaxyConfig:
    mode: Literal["alternate", "opposite", "whorled", "decussate", "distichous"] = field(
        default="alternate", metadata={"ui": {"label": "Mode"}}
    )
    whorl_count: int = field(default=3, metadata={"ui": {"min": 2, "max": 8, "step": 1}})
    divergence_angle_deg: float = field(default=137.5, metadata={"ui": {"min": 0.0, "max": 360.0, "step": 0.5}})
    # Insertion angle (deg) by axis_order. branch_angle_by_order[k] is the
    # angle of laterals emitted by a bud whose axis_order is k. If k exceeds
    # len(list)-1, the value is clamped to the last entry. Must have at least
    # one element. Example oak: (60.0, 40.0, 30.0, 25.0).
    branch_angle_by_order: tuple[float, ...] = field(
        default=(45.0,),
        metadata={"ui": {"label": "Branch angles by order"}},
    )
    # Gaussian jitter (σ in degrees) on the azimuthal divergence between
    # successive lateral buds. 4-6deg matches realistic biological variability.
    divergence_jitter_deg: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 30.0, "step": 0.5}})
    # Gaussian jitter on the branch insertion angle. Clamped to [0deg, 90deg].
    branch_angle_jitter_deg: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 20.0, "step": 0.5}})
    dormant_reserve_count: int = field(
        default=0, metadata={"ui": {"min": 0, "max": 5, "step": 1}}
    )
    distichous_on_plagiotropic: bool = field(
        default=False,
        metadata={"ui": {"label": "Distichous on lateral axes"}},
    )


@dataclass(frozen=True)
class SheddingConfig:
    quality_threshold: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 5.0, "step": 0.05}})
    window: int = field(default=5, metadata={"ui": {"min": 1, "max": 20, "step": 1}})
    enabled: bool = field(default=True, metadata={"ui": {"label": "Enabled"}})
    reactivation_count: int = field(
        default=1, metadata={"ui": {"min": 0, "max": 5, "step": 1}}
    )


@dataclass(frozen=True)
class SagConfig:
    """Post-sim mechanical sag (cantilever beam approximation).

    For each internode, computes a bending angle ``bend = k * load / stiffness``
    where ``load`` is the subtree's wood volume and ``stiffness`` is ``diameter²``
    (proxy for the section's bending moment of inertia). The rotation is applied
    at the internode's proximal joint; all descendants follow rigidly. Resulting
    shape: tips droop more than mid-branches, the trunk barely moves.
    """
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    # Global gain on the per-internode bend angle (rad). 0.01 produces visible
    # but moderate droop on default oak; 0.05 yields pronounced weep on birch.
    k: float = field(default=0.01, metadata={"ui": {"min": 0.0, "max": 0.2, "step": 0.005}})
    # Hard cap (deg) per single internode to avoid pathological hairpins near tips
    # where diameter² → 0.
    max_bend_deg: float = field(default=8.0, metadata={"ui": {"min": 0.0, "max": 45.0, "step": 0.5}})
    # Sag direction (typically straight down).
    direction: tuple[float, float, float] = (0.0, -1.0, 0.0)
    # Internodes whose ``axis_order`` is less than this stay rigid. 1 = trunk
    # doesn't sag (typical); 0 = even trunk can sag (extreme weep).
    rigid_axis_order: int = field(default=1, metadata={"ui": {"min": 0, "max": 4, "step": 1}})


@dataclass(frozen=True)
class ElongationConfig:
    """Progressive internode elongation (S-curve) + age_factor on target length.

    Each Internode records its birth_iteration and length_target at creation.
    Its effective ``length`` ramps from 0 toward ``length_target`` via a sigmoid
    centered at ``tau_iterations`` after birth (so length ≈ 0.5 * target at
    age=tau, ≈ 0.88 * target at age=2*tau).
    """
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    tau_iterations: float = field(
        default=3.0, metadata={"ui": {"min": 0.5, "max": 10.0, "step": 0.1}}
    )
    age_factor_min: float = field(
        default=0.5, metadata={"ui": {"min": 0.1, "max": 1.0, "step": 0.05}}
    )
    age_factor_decay: float = field(
        default=0.5, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.1}}
    )


@dataclass(frozen=True)
class GeomConfig:
    ring_sides: int = field(default=8, metadata={"ui": {"min": 3, "max": 32, "step": 1}})
    r_tip: float = field(default=0.005, metadata={"ui": {"min": 0.001, "max": 0.05, "step": 0.001}})
    pipe_exponent: float = field(default=2.49, metadata={"ui": {"min": 1.0, "max": 4.0, "step": 0.01}})
    leaf_size: float = field(default=0.06, metadata={"ui": {"min": 0.01, "max": 0.5, "step": 0.01}})
    leaf_texture: Path | None = None
    bark_color: tuple[float, float, float] = (0.35, 0.22, 0.12)
    bark_texture: Path | None = None
    leaf_cluster_count: int = field(default=1, metadata={"ui": {"min": 1, "max": 8, "step": 1}})
    leaf_aspect: float = field(default=1.0, metadata={"ui": {"min": 0.02, "max": 4.0, "step": 0.005}})
    leaf_splay_deg: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 90.0, "step": 1.0}})
    enable_leaves: bool = field(default=True, metadata={"ui": {"label": "Enable leaves"}})
    # Fix #4: emit leaves on internodes within ``foliage_depth`` steps of the
    # nearest terminal apex. 1 = legacy (apex only). 3–4 = realistic young
    # shoot coverage. Larger values approach evergreen full-foliage density.
    foliage_depth: int = field(default=1, metadata={"ui": {"min": 1, "max": 8, "step": 1}})
    leaf_sun_shade_k: float = field(
        default=0.0,
        metadata={"ui": {"min": 0.0, "max": 2.0, "step": 0.05}},
    )


@dataclass(frozen=True)
class LightConfig:
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    grid_origin: tuple[float, float, float] | None = None
    grid_size: tuple[float, float, float] | None = None
    grid_resolution: tuple[int, int, int] = (64, 64, 64)
    k_absorption: float = field(default=0.5, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    leaf_area: float = field(default=0.04, metadata={"ui": {"min": 0.0, "max": 0.5, "step": 0.01}})
    internode_area_scale: float = field(default=1.0, metadata={"ui": {"min": 0.0, "max": 5.0, "step": 0.1}})
    n_rays: int = field(default=16, metadata={"ui": {"min": 4, "max": 64, "step": 4}})
    light_direction: tuple[float, float, float] = (0.0, 1.0, 0.0)


@dataclass(frozen=True)
class ObstacleAABB:
    kind: Literal["aabb"] = "aabb"
    min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    max: tuple[float, float, float] = (1.0, 1.0, 1.0)


@dataclass(frozen=True)
class ObstacleSphere:
    kind: Literal["sphere"] = "sphere"
    center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius: float = 1.0


@dataclass(frozen=True)
class ObstacleOBB:
    kind: Literal["obb"] = "obb"
    center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    half_extents: tuple[float, float, float] = (1.0, 1.0, 1.0)
    axes: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


@dataclass(frozen=True)
class ObstacleMesh:
    kind: Literal["mesh"] = "mesh"
    path: Path = field(default_factory=lambda: Path("obstacle.obj"))
    translate: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: float = 1.0


@dataclass(frozen=True)
class ForestSeed:
    position: tuple[float, float, float]
    seed: int | None = None
    species: str | None = None
    overrides: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ForestConfig:
    seeds: tuple = ()
    obstacles: tuple = ()
    export_obstacles_geometry: bool = True


@dataclass(frozen=True)
class Config:
    envelope: EnvelopeConfig
    sim: SimConfig
    tropism: TropismConfig
    phyllotaxy: PhyllotaxyConfig
    shedding: SheddingConfig
    geom: GeomConfig
    light: LightConfig = field(default_factory=LightConfig)
    forest: ForestConfig = field(default_factory=ForestConfig)
    sag: SagConfig = field(default_factory=SagConfig)
    seed: int = field(default=0, metadata={"ui": {"min": 0, "max": 2**31 - 1, "step": 1}})
    output: Path = field(default_factory=lambda: Path("tree.glb"))
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        env = self.envelope
        if env.rx <= 0 or env.ry <= 0 or env.rz <= 0:
            raise ConfigError(f"envelope rx/ry/rz must be > 0, got {(env.rx, env.ry, env.rz)}")
        if env.marker_count <= 0:
            raise ConfigError(f"envelope.marker_count must be > 0, got {env.marker_count}")

        s = self.sim
        if not (0 < s.theta_perception_deg <= 180):
            raise ConfigError(f"sim.theta_perception_deg must be in (0, 180], got {s.theta_perception_deg}")
        if not (0.0 <= s.lambda_apical <= 1.0):
            raise ConfigError(f"sim.lambda_apical must be in [0, 1], got {s.lambda_apical}")
        if s.r_perception <= 0:
            raise ConfigError(f"sim.r_perception must be > 0, got {s.r_perception}")
        if s.r_kill <= 0:
            raise ConfigError(f"sim.r_kill must be > 0, got {s.r_kill}")
        if s.internode_length <= 0:
            raise ConfigError(f"sim.internode_length must be > 0, got {s.internode_length}")
        if not (0.0 <= s.internode_length_jitter <= 0.5):
            raise ConfigError(
                f"sim.internode_length_jitter must be in [0, 0.5], got {s.internode_length_jitter}"
            )
        sym = s.sympodial
        if sym.q_threshold < 0:
            raise ConfigError(
                f"sim.sympodial.q_threshold must be >= 0, got {sym.q_threshold}"
            )
        if sym.n_consecutive_steps < 1:
            raise ConfigError(
                f"sim.sympodial.n_consecutive_steps must be >= 1, "
                f"got {sym.n_consecutive_steps}"
            )
        sm = s.shade_mortality
        if not (0.0 <= sm.light_threshold <= 1.0):
            raise ConfigError(
                f"sim.shade_mortality.light_threshold must be in [0, 1], got {sm.light_threshold}"
            )
        if sm.n_consecutive_steps < 1:
            raise ConfigError(
                f"sim.shade_mortality.n_consecutive_steps must be >= 1, got {sm.n_consecutive_steps}"
            )
        if sm.enabled and not self.light.enabled:
            raise ConfigError(
                "sim.shade_mortality.enabled=True requires light.enabled=True"
            )
        e = self.sim.elongation
        if e.tau_iterations <= 0:
            raise ConfigError(f"sim.elongation.tau_iterations must be > 0, got {e.tau_iterations}")
        if not (0.1 <= e.age_factor_min <= 1.0):
            raise ConfigError(
                f"sim.elongation.age_factor_min must be in [0.1, 1.0], got {e.age_factor_min}"
            )
        if e.age_factor_decay < 0:
            raise ConfigError(
                f"sim.elongation.age_factor_decay must be >= 0, got {e.age_factor_decay}"
            )
        if s.max_iterations < 0:
            raise ConfigError(f"sim.max_iterations must be >= 0, got {s.max_iterations}")

        t = self.tropism
        for fname in (
            "w_orthotropy_main", "w_orthotropy_lateral",
            "w_gravitropism_main", "w_gravitropism_lateral",
            "w_plagiotropism_main", "w_plagiotropism_lateral",
        ):
            v = getattr(t, fname)
            if v < 0:
                raise ConfigError(f"tropism.{fname} must be >= 0, got {v}")

        p = self.phyllotaxy
        if p.divergence_jitter_deg < 0:
            raise ConfigError(
                f"phyllotaxy.divergence_jitter_deg must be >= 0, got {p.divergence_jitter_deg}"
            )
        if p.branch_angle_jitter_deg < 0:
            raise ConfigError(
                f"phyllotaxy.branch_angle_jitter_deg must be >= 0, got {p.branch_angle_jitter_deg}"
            )
        if not p.branch_angle_by_order:
            raise ConfigError(
                "phyllotaxy.branch_angle_by_order must have at least one element"
            )
        for i, a in enumerate(p.branch_angle_by_order):
            if not (0.0 <= a <= 90.0):
                raise ConfigError(
                    f"phyllotaxy.branch_angle_by_order[{i}] must be in [0, 90], got {a}"
                )
        if p.dormant_reserve_count < 0:
            raise ConfigError(
                f"phyllotaxy.dormant_reserve_count must be >= 0, got {p.dormant_reserve_count}"
            )

        sh = self.shedding
        if sh.reactivation_count < 0:
            raise ConfigError(
                f"shedding.reactivation_count must be >= 0, got {sh.reactivation_count}"
            )

        g = self.geom
        if not (1.0 <= g.pipe_exponent <= 4.0):
            raise ConfigError(f"geom.pipe_exponent must be in [1, 4], got {g.pipe_exponent}")
        if g.ring_sides < 3:
            raise ConfigError(f"geom.ring_sides must be >= 3, got {g.ring_sides}")
        if g.r_tip <= 0:
            raise ConfigError(f"geom.r_tip must be > 0, got {g.r_tip}")
        if g.leaf_size <= 0:
            raise ConfigError(f"geom.leaf_size must be > 0, got {g.leaf_size}")
        if g.leaf_cluster_count < 1:
            raise ConfigError(f"geom.leaf_cluster_count must be >= 1, got {g.leaf_cluster_count}")
        if not (0.0 < g.leaf_aspect <= 4.0):
            raise ConfigError(f"geom.leaf_aspect must be in (0, 4], got {g.leaf_aspect}")
        if not (0.0 <= g.leaf_splay_deg <= 90.0):
            raise ConfigError(f"geom.leaf_splay_deg must be in [0, 90], got {g.leaf_splay_deg}")
        if not (0.0 <= g.leaf_sun_shade_k <= 2.0):
            raise ConfigError(
                f"geom.leaf_sun_shade_k must be in [0, 2], got {g.leaf_sun_shade_k}"
            )

        light = self.light
        if light.n_rays <= 0:
            raise ConfigError(f"light.n_rays must be > 0, got {light.n_rays}")
        if light.k_absorption < 0:
            raise ConfigError(f"light.k_absorption must be >= 0, got {light.k_absorption}")
        if light.leaf_area < 0:
            raise ConfigError(f"light.leaf_area must be >= 0, got {light.leaf_area}")
        if light.internode_area_scale < 0:
            raise ConfigError(f"light.internode_area_scale must be >= 0, got {light.internode_area_scale}")
        if any(r <= 0 for r in light.grid_resolution):
            raise ConfigError(f"light.grid_resolution must be all > 0, got {light.grid_resolution}")
        if sum(c * c for c in light.light_direction) <= 0:
            raise ConfigError(f"light.light_direction must be non-zero, got {light.light_direction}")

        if not self.output.parent.exists():
            raise ConfigError(f"output parent directory does not exist: {self.output.parent}")


# --- YAML loading ---

from dataclasses import fields, is_dataclass  # noqa: E402

import yaml  # noqa: E402


_SECTION_TYPES = {
    "envelope": EnvelopeConfig,
    "sim": SimConfig,
    "tropism": TropismConfig,
    "phyllotaxy": PhyllotaxyConfig,
    "shedding": SheddingConfig,
    "geom": GeomConfig,
    "light": LightConfig,
    "sag": SagConfig,
}


def load_config(
    *,
    yaml_path: Path | None,
    cli_overrides: dict,
    output: Path,
    species: str | None = None,
) -> Config:
    data: dict = {}
    if species is not None:
        data = _load_packaged_species(species)

    if yaml_path is not None:
        with open(yaml_path) as f:
            user = yaml.safe_load(f) or {}
        _deep_merge(data, user)

    for dotted, value in cli_overrides.items():
        _set_dotted(data, dotted, value)

    sections = {}
    section_field_names = set(_SECTION_TYPES.keys()) | {"forest"}
    top_field_names = {f.name for f in fields(Config)}

    for name, type_ in _SECTION_TYPES.items():
        sec_data = data.get(name, {}) or {}
        allowed = {f.name for f in fields(type_)}
        unknown = set(sec_data) - allowed
        if unknown:
            raise ConfigError(f"unknown keys in section '{name}': {sorted(unknown)}")
        if name == "phyllotaxy" and "branch_angle_by_order" in sec_data:
            v = sec_data["branch_angle_by_order"]
            if not isinstance(v, (list, tuple)):
                raise ConfigError(
                    f"phyllotaxy.branch_angle_by_order must be a list, got {type(v).__name__}"
                )
            sec_data = {**sec_data, "branch_angle_by_order": tuple(float(x) for x in v)}
        if name == "sim" and "sympodial" in sec_data and isinstance(sec_data["sympodial"], dict):
            sec_data = {**sec_data, "sympodial": SympodialConfig(**sec_data["sympodial"])}
        if name == "sim" and "shade_mortality" in sec_data and isinstance(sec_data["shade_mortality"], dict):
            sec_data = {**sec_data, "shade_mortality": ShadeMortalityConfig(**sec_data["shade_mortality"])}
        if name == "sim" and isinstance(sec_data.get("elongation"), dict):
            elong_data = sec_data["elongation"]
            elong_allowed = {f.name for f in fields(ElongationConfig)}
            elong_unknown = set(elong_data) - elong_allowed
            if elong_unknown:
                raise ConfigError(
                    f"unknown keys in section 'sim.elongation': {sorted(elong_unknown)}"
                )
            sec_data = {**sec_data, "elongation": ElongationConfig(**elong_data)}
        sections[name] = type_(**sec_data)

    if "forest" in data:
        sections["forest"] = _load_forest_config(data["forest"])

    top_kwargs = {k: v for k, v in data.items() if k not in section_field_names and k in top_field_names}
    unknown_top = set(data) - section_field_names - top_field_names
    if unknown_top:
        raise ConfigError(f"unknown top-level keys: {sorted(unknown_top)}")

    if "output" in cli_overrides:
        top_kwargs["output"] = Path(cli_overrides["output"])
    else:
        top_kwargs.setdefault("output", output)

    return Config(**sections, **top_kwargs)


def _deep_merge(base: dict, override: dict) -> None:
    """Merge `override` into `base` in-place. Recursive on dict-vs-dict; otherwise replace."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _load_packaged_species(name: str) -> dict:
    from importlib import resources
    try:
        text = (
            resources.files("palubicki.configs.species")
            .joinpath(f"{name}.yaml")
            .read_text()
        )
    except (FileNotFoundError, ModuleNotFoundError, AttributeError) as e:
        raise ConfigError(f"unknown species preset: {name!r}") from e
    return yaml.safe_load(text) or {}


def _list_species() -> list[str]:
    from importlib import resources
    try:
        files = resources.files("palubicki.configs.species").iterdir()
    except (FileNotFoundError, ModuleNotFoundError):
        return []
    return sorted(f.stem for f in files if f.name.endswith(".yaml"))


def _set_dotted(data: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    cur = data
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


_OBSTACLE_TYPES = {
    "aabb": ObstacleAABB,
    "sphere": ObstacleSphere,
    "obb": ObstacleOBB,
    "mesh": ObstacleMesh,
}


def _load_obstacle(d: dict):
    if not isinstance(d, dict):
        raise ConfigError(f"obstacle must be a dict, got {type(d).__name__}")
    kind = d.get("kind")
    if kind is None:
        raise ConfigError(f"obstacle missing 'kind' field: {d}")
    type_ = _OBSTACLE_TYPES.get(kind)
    if type_ is None:
        raise ConfigError(f"unknown obstacle kind: {kind!r} (expected one of {sorted(_OBSTACLE_TYPES)})")
    fields_allowed = {f.name for f in fields(type_)}
    payload = {k: v for k, v in d.items() if k != "kind"}
    unknown = set(payload) - fields_allowed
    if unknown:
        raise ConfigError(f"unknown keys in obstacle {kind!r}: {sorted(unknown)}")
    if "path" in payload:
        payload["path"] = Path(payload["path"])
    for tuple_field in ("min", "max", "center", "half_extents", "translate", "axes"):
        if tuple_field in payload:
            payload[tuple_field] = tuple(payload[tuple_field])
    return type_(**payload)


def _load_forest_seed(d: dict) -> "ForestSeed":
    if not isinstance(d, dict):
        raise ConfigError(f"forest seed must be a dict, got {type(d).__name__}")
    allowed = {"position", "seed", "species", "overrides"}
    unknown = set(d) - allowed
    if unknown:
        raise ConfigError(f"unknown keys in forest seed: {sorted(unknown)}")
    if "position" not in d:
        raise ConfigError("forest seed missing 'position'")
    return ForestSeed(
        position=tuple(d["position"]),
        seed=d.get("seed"),
        species=d.get("species"),
        overrides=dict(d.get("overrides") or {}),
    )


def _load_forest_config(d: dict) -> "ForestConfig":
    if not isinstance(d, dict):
        raise ConfigError(f"forest section must be a dict, got {type(d).__name__}")
    allowed = {"seeds", "obstacles", "export_obstacles_geometry"}
    unknown = set(d) - allowed
    if unknown:
        raise ConfigError(f"unknown keys in forest section: {sorted(unknown)}")
    seeds = tuple(_load_forest_seed(s) for s in (d.get("seeds") or ()))
    obstacles = tuple(_load_obstacle(o) for o in (d.get("obstacles") or ()))
    export = bool(d.get("export_obstacles_geometry", True))
    return ForestConfig(seeds=seeds, obstacles=obstacles, export_obstacles_geometry=export)
