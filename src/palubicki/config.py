# src/palubicki/config.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


class ConfigError(ValueError):
    """Raised when configuration validation fails."""


@dataclass(frozen=True)
class EnvelopeConfig:
    shape: Literal["sphere", "ellipsoid", "cone", "half_ellipsoid"] = "ellipsoid"
    rx: float = 1.0
    ry: float = 1.0
    rz: float = 1.0
    center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    marker_count: int = 20_000


@dataclass(frozen=True)
class SimConfig:
    r_perception: float = 0.6
    theta_perception_deg: float = 90.0
    r_kill: float = 0.15
    internode_length: float = 0.1
    alpha_basipetal: float = 2.0
    lambda_apical: float = 0.55
    max_iterations: int = 30
    re_perceive_per_substep: bool = True


@dataclass(frozen=True)
class TropismConfig:
    w_perception: float = 1.0
    w_gravity: float = 0.3
    w_phototropism: float = 0.0
    w_direction_inertia: float = 0.4
    photo_direction: tuple[float, float, float] = (0.0, 1.0, 0.0)


@dataclass(frozen=True)
class PhyllotaxyConfig:
    mode: Literal["alternate", "opposite", "whorled"] = "alternate"
    whorl_count: int = 3
    divergence_angle_deg: float = 137.5
    branch_angle_deg: float = 45.0


@dataclass(frozen=True)
class SheddingConfig:
    quality_threshold: float = 0.0
    window: int = 5
    enabled: bool = True


@dataclass(frozen=True)
class GeomConfig:
    ring_sides: int = 8
    r_tip: float = 0.005
    pipe_exponent: float = 2.49
    leaf_size: float = 0.06
    leaf_texture: Path | None = None
    bark_color: tuple[float, float, float] = (0.35, 0.22, 0.12)
    bark_texture: Path | None = None
    leaf_cluster_count: int = 1
    leaf_aspect: float = 1.0
    leaf_splay_deg: float = 0.0
    enable_leaves: bool = True


@dataclass(frozen=True)
class LightConfig:
    enabled: bool = False
    grid_origin: tuple[float, float, float] | None = None
    grid_size: tuple[float, float, float] | None = None
    grid_resolution: tuple[int, int, int] = (64, 64, 64)
    k_absorption: float = 0.5
    leaf_area: float = 0.04
    internode_area_scale: float = 1.0
    n_rays: int = 16
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
    seed: int = 0
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
        if s.max_iterations < 0:
            raise ConfigError(f"sim.max_iterations must be >= 0, got {s.max_iterations}")

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
}


def load_config(*, yaml_path: Path | None, cli_overrides: dict, output: Path) -> Config:
    data: dict = {}
    if yaml_path is not None:
        with open(yaml_path) as f:
            data = yaml.safe_load(f) or {}

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
    allowed = {"position", "seed", "overrides"}
    unknown = set(d) - allowed
    if unknown:
        raise ConfigError(f"unknown keys in forest seed: {sorted(unknown)}")
    if "position" not in d:
        raise ConfigError("forest seed missing 'position'")
    return ForestSeed(
        position=tuple(d["position"]),
        seed=d.get("seed"),
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
