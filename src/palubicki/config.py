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
    enable_leaves: bool = True


@dataclass(frozen=True)
class Config:
    envelope: EnvelopeConfig
    sim: SimConfig
    tropism: TropismConfig
    phyllotaxy: PhyllotaxyConfig
    shedding: SheddingConfig
    geom: GeomConfig
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
        if s.max_iterations <= 0:
            raise ConfigError(f"sim.max_iterations must be > 0, got {s.max_iterations}")

        g = self.geom
        if not (1.0 <= g.pipe_exponent <= 4.0):
            raise ConfigError(f"geom.pipe_exponent must be in [1, 4], got {g.pipe_exponent}")
        if g.ring_sides < 3:
            raise ConfigError(f"geom.ring_sides must be >= 3, got {g.ring_sides}")
        if g.r_tip <= 0:
            raise ConfigError(f"geom.r_tip must be > 0, got {g.r_tip}")
        if g.leaf_size <= 0:
            raise ConfigError(f"geom.leaf_size must be > 0, got {g.leaf_size}")

        if not self.output.parent.exists():
            raise ConfigError(f"output parent directory does not exist: {self.output.parent}")
