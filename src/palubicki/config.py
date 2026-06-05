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
class LengthBankingConfig:
    """Age-driven lateral length + woody persistence (#94): make the emergent
    conifer crown a real cone. A lateral's per-internode length is driven by its
    own axis AGE, ramping from ~0 (just born, near the apex) to the full reference
    rate over ``release_years`` — so a young top lateral stays short even when lit
    (the lit-youth growth that inverts the crown is suppressed at the source) and
    an old low lateral reaches full length. Length comes from integration TIME
    (age ∝ depth), not the height-monotone lit vigor, so it does not re-invert.
    Established laterals persist through shade so they live long enough to age into
    length.

    Default OFF ⇒ byte-identical. ``persist_rate_fraction == 0`` collapses to the
    off path structurally (gated ``enabled and persist_rate_fraction > 0``), so
    'engaged-but-zero' is identical too.
    """
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    # An axis is ESTABLISHED once its banked_vigor reaches this — i.e. it was once
    # lit enough to grow (pair with sim.vigor_dormancy). Below it, no persistence.
    establish_threshold: float = field(
        default=0.5, metadata={"ui": {"min": 0.0, "max": 5.0, "step": 0.05}})
    # Base-width knob: the FULL reference rate (fraction of shoot_extension_max) an
    # OLD lateral emits at once its axis age reaches `release_years`. A young lateral
    # emits a small fraction of this via the age ramp, so the top stays short.
    # Height-independent (no re-inversion). 0.0 ⇒ mechanism off.
    persist_rate_fraction: float = field(
        default=0.0, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.05}})
    # Age ramp (years): a lateral's per-internode length scales from ~0 (just born,
    # near the apex) to the full reference rate over this span. Larger ⇒ a slower
    # release ⇒ a sharper spire (the top stays short longer). The taper-steepness
    # lever, paired with persist_rate_fraction (the base width).
    release_years: float = field(
        default=12.0, metadata={"ui": {"min": 1.0, "max": 40.0, "step": 1.0}})


@dataclass(frozen=True)
class SimConfig:
    r_perception: float = field(default=0.6, metadata={"ui": {"min": 0.1, "max": 3.0, "step": 0.05}})
    theta_perception_deg: float = field(default=90.0, metadata={"ui": {"min": 10.0, "max": 180.0, "step": 5.0}})
    r_kill: float = field(default=0.15, metadata={"ui": {"min": 0.01, "max": 1.0, "step": 0.01}})
    alpha_basipetal: float = field(default=2.0, metadata={"ui": {"min": 0.0, "max": 5.0, "step": 0.1}})
    lambda_apical: float = field(default=0.55, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.01}})
    shoot_extension_max: float = field(default=0.3, metadata={"ui": {"min": 0.02, "max": 1.0, "step": 0.01}})
    # Apical control (#56): acropetal suppression of LATERAL internode length by
    # depth below the tree apex, independent of light. A lateral's emitted length
    # is scaled by clip(gap_below_apex / apical_control_length, 0.1, 1.0), so
    # young laterals near the leader stay short and old laterals far below reach
    # full length — the top-down taper that light-driven vigor alone inverts
    # (light makes the lit top grow widest). 0.0 = off (byte-identical); a conifer
    # uses ~tree_height to taper the whole crown. The main axis is never suppressed.
    apical_control_length: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 15.0, "step": 0.5}})
    vigor_ref: float = field(default=1.0, metadata={"ui": {"min": 0.05, "max": 5.0, "step": 0.05}})
    vigor_dormancy: float = field(default=1.0, metadata={"ui": {"min": 0.0, "max": 5.0, "step": 0.05}})
    vigor_smoothing: float = field(default=0.5, metadata={"ui": {"min": 0.05, "max": 1.0, "step": 0.05}})
    vigor_diameter_gain: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    dt_years: float = field(default=1.0, metadata={"ui": {"min": 0.1, "max": 2.0, "step": 0.05}})
    max_simulation_years: float = field(
        default=30.0, metadata={"ui": {"min": 1.0, "max": 80.0, "step": 1.0}}
    )
    # Fraction of the year [lo, hi) during which growth (new internodes) is
    # active. Default spans the whole year => no seasonal gating. Only bites
    # when dt_years < 1.0 (sub-annual steps). Not exposed in UI (vec2).
    annual_growth_period: tuple[float, float] = (0.0, 1.0)
    # Graded phenology (#65): half-open ramp width (fraction of the year) applied
    # to BOTH ends of annual_growth_period, turning the binary gate into a
    # symmetric trapezoid (linear bud-break ramp / plateau / growth-cessation
    # ramp). 0.0 (default) => the trapezoid degenerates to today's crisp [lo, hi)
    # step => byte-identical evolution. The activity scalar scales emitted
    # internode length; growth/senescence/flowering all read it via
    # sim.clock.phenology_activity. Editor-tunable.
    growth_period_shoulder: float = field(
        default=0.0, metadata={"ui": {"min": 0.0, "max": 0.5, "step": 0.01}}
    )
    # Fix #1: if dot(v_perc, current_direction) < cos_min_perception, the bud
    # is sitting at the envelope boundary (markers only behind/below). It goes
    # DORMANT instead of folding back. -0.2 ≈ allow 100° before bending; raise
    # toward 0.0 to be strict, lower toward -1.0 to disable.
    cos_min_perception: float = field(default=-0.2, metadata={"ui": {"min": -1.0, "max": 1.0, "step": 0.05}})
    # Gaussian jitter (σ as a fraction of the computed shoot extension) applied
    # per new internode. 0.0 = exact computed length; 0.10-0.15 = realistic
    # variability. The drawn factor is clamped to [0.5, 1.5] regardless of σ.
    internode_length_jitter: float = field(
        default=0.0, metadata={"ui": {"min": 0.0, "max": 0.5, "step": 0.01}}
    )
    sympodial: SympodialConfig = field(default_factory=lambda: SympodialConfig())
    shade_mortality: ShadeMortalityConfig = field(default_factory=lambda: ShadeMortalityConfig())
    shade_avoidance: ShadeAvoidanceConfig = field(default_factory=lambda: ShadeAvoidanceConfig())
    elongation: ElongationConfig = field(default_factory=lambda: ElongationConfig())
    length_banking: LengthBankingConfig = field(default_factory=lambda: LengthBankingConfig())
    bud_break_bias: BudBreakConfig = field(default_factory=lambda: BudBreakConfig())
    leaf_phenology: LeafPhenologyConfig = field(default_factory=lambda: LeafPhenologyConfig())

    @property
    def num_iterations(self) -> int:
        """Iteration budget derived from the time budget."""
        return round(self.max_simulation_years / self.dt_years)


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
class ShadeAvoidanceConfig:
    """Shade-avoidance at bud initiation (#63).

    At emission, each lateral bud breaks ACTIVE only with probability
    ``shade_avoidance.lateral_break_probability(light_factor, strength)``; the rest
    start RESERVE (kept in ``dormant_reserve_buds``, retained and reactivatable via
    reiteration when a shaded branch is later shed). So the crown *withholds*
    lateral investment in shaded zones at initiation, instead of only culling
    laterals after the fact (``shade_mortality``) — the two are complementary
    (this withholds; that prunes).

    ``strength`` in [0, 1] is the fraction of laterals withheld at full shade
    (light_factor = 0); it ramps linearly to 0 withheld in full sun.

    Disabled (``enabled=False``, the default) — or ``strength == 0``, or a fully
    lit bud — leaves every lateral ACTIVE and draws NO RNG at emission, so the
    evolution stays byte-identical to the legacy path (presence-gated; shipped
    presets unchanged).
    """
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    strength: float = field(
        default=0.6, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.05}}
    )


@dataclass(frozen=True)
class BudBreakConfig:
    """Per-species lateral-quality bias by node position along parent axis.

    ``mode``:
      * ``uniform`` — all positions equal (default; preserves legacy behavior).
      * ``acrotonic`` — tip-end laterals favored (strong apical dominance).
      * ``basitonic`` — base-end laterals favored (shrubs, multi-stem clumps).
      * ``mesotonic`` — middle-axis laterals favored.

    ``strength`` in [0, 1]: 0 = no bias, 1 = full bias (the disfavored end
    receives 0 quality multiplier). Independent of ``lambda_apical``.
    """
    mode: Literal["uniform", "acrotonic", "basitonic", "mesotonic"] = field(
        default="uniform", metadata={"ui": {"label": "Mode"}}
    )
    strength: float = field(
        default=0.0, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.05}}
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
    # Epinasty (#34): ramp the EFFECTIVE plagiotropism weight with branch age,
    # 1 - exp(-age / epinasty_tau_years), so laterals emerge near the parent
    # axis and arch toward horizontal over years. Disabled => ramp is
    # identically 1.0 (bit-identical to the constant-weight behaviour).
    epinasty_enabled: bool = field(
        default=False, metadata={"ui": {"label": "Epinasty enabled"}}
    )
    epinasty_tau_years: float = field(
        default=8.0, metadata={"ui": {"min": 0.5, "max": 30.0, "step": 0.5}}
    )
    w_phototropism: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    w_direction_inertia: float = field(default=0.4, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    photo_direction: tuple[float, float, float] = (0.0, 1.0, 0.0)  # not exposed; vec3 stays defaulted
    axis_decay: float = field(default=1.0, metadata={"ui": {"min": 0.1, "max": 1.0, "step": 0.05}})
    # Spray-plane lateral fan (#55): reference plagiotropism AND the radial
    # insertion basis to the parent axis's plane (derived at bud-break) instead of
    # world-XY, so order-2+ laterals fan into a coherent flat frond (conifer spray)
    # rather than splaying out of plane. When on, plagiotropism is not decayed by
    # axis_decay (in-plane flattening stays full strength at every order). Off by
    # default => bit-identical legacy behaviour (arbitrary insertion frame +
    # world-XY plagiotropism with order decay).
    spray_plane_enabled: bool = field(
        default=False, metadata={"ui": {"label": "Spray-plane lateral fan"}}
    )


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
class LeafPhenologyConfig:
    """Leaf caducity: age + season drive ``LeafState`` transitions (#61).

    A per-iteration pass advances each leaf ``ACTIVE -> SENESCENT -> ABSCISSED``
    as a pure function of ``clock.t - birth_time`` (no RNG, fully deterministic).
    Disabled by default, so a config that never opts in keeps every leaf
    ``ACTIVE`` for life (legacy behavior / unchanged goldens).

    Two senescence triggers, whichever fires first:
      * **age cap** — ``age >= leaf_lifespan_years`` (evergreen needle turnover;
        also a safety cap for deciduous leaves).
      * **dormant-window entry** (deciduous only) — the leaf senesces as soon as
        ``year_fraction`` leaves ``sim.annual_growth_period``. This only bites
        when ``dt_years < 1.0`` carries the clock into the dormant window, same
        as the growth gate it complements. Since #65 (graded phenology) this
        boundary is the SHARED dormancy-entry trigger: caducity senesces when
        ``sim.clock.phenology_activity(...) == 0``, the exact same point at which
        the simulator stops emitting growth, so the two never drift. With
        ``growth_period_shoulder > 0`` new growth tapers through the falling
        shoulder while existing foliage stays active until activity hits 0
        (graded leaf senescence within the shoulder is deferred — see #65).

    A senesced leaf abscises ``senescence_duration_years`` later — a brief window
    where the leaf is off the ``ACTIVE`` roster but still on the node, the hook
    autumn-color tinting (#9 COLOR_0 path) and marcescence will read.
    """
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    # True: shed within the dormant window (broadleaves). False: evergreen —
    # leaves persist across years, shedding only past the lifespan cap.
    deciduous: bool = field(default=False, metadata={"ui": {"label": "Deciduous"}})
    leaf_lifespan_years: float = field(
        default=2.0, metadata={"ui": {"min": 0.25, "max": 12.0, "step": 0.25}}
    )
    senescence_duration_years: float = field(
        default=0.1, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.05}}
    )
    # Marcescence (oak/beech): dead leaves stay attached (rendered SENESCENT)
    # through winter instead of abscising after senescence_duration; they finally
    # drop at the next growth-window onset, pushed off by the new flush. Deciduous
    # only (an evergreen has no dormant retention to model).
    marcescent: bool = field(default=False, metadata={"ui": {"label": "Marcescent"}})


@dataclass(frozen=True)
class ElongationConfig:
    """Progressive internode elongation (S-curve).

    Each Internode records its birth_time and length_target at creation.
    Its effective ``length`` ramps from 0 toward ``length_target`` via a sigmoid
    centered at ``tau_years`` after birth (so length ≈ 0.5 * target at
    age=tau, ≈ 0.88 * target at age=2*tau).
    """
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    tau_years: float = field(
        default=3.0, metadata={"ui": {"min": 0.5, "max": 10.0, "step": 0.1}}
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
    leaf_shape: Literal["linear", "elliptic", "lanceolate", "ovate", "cordate", "palmate"] = field(
        default="ovate", metadata={"ui": {"label": "Leaf shape"}}
    )
    leaf_margin: Literal["entire", "serrate", "dentate", "lobed"] = field(
        default="entire", metadata={"ui": {"label": "Leaf margin"}}
    )
    leaf_margin_depth: float = field(
        default=0.0, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.05}}
    )
    leaf_margin_count: int = field(
        default=0, metadata={"ui": {"min": 0, "max": 30, "step": 1}}
    )
    leaf_aspect: float = field(default=1.0, metadata={"ui": {"min": 0.02, "max": 4.0, "step": 0.005}})
    leaf_splay_deg: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 90.0, "step": 1.0}})
    enable_leaves: bool = field(default=True, metadata={"ui": {"label": "Enable leaves"}})
    # Fix #4: emit leaves on internodes within ``foliage_depth`` steps of the
    # nearest terminal apex. 1 = legacy (apex only). 3–4 = realistic young
    # shoot coverage. Larger values approach evergreen full-foliage density.
    foliage_depth: int = field(default=1, metadata={"ui": {"min": 1, "max": 8, "step": 1}})
    # #36: along-shoot needle distribution. 0.0 = legacy (one cluster per
    # leaf-bearing node; broadleaves). >0 = clothe each leaf-bearing internode
    # with clusters spaced this many meters apart (conifers).
    needle_cluster_spacing: float = field(
        default=0.0, metadata={"ui": {"min": 0.0, "max": 0.5, "step": 0.01}}
    )
    # #7: conifer needle fascicles — needles bundled 2–5 (pines) and wrapped by a
    # short basal sheath. fascicle_count == 1 (default) = each needle stands alone,
    # so every existing species stays byte-identical. > 1 emits fascicle_count
    # needles from each rendered needle position, distributed 360/N apart in azimuth
    # and tilted off the shared bundle axis by fascicle_spread_deg. Needle-only
    # (leaf_shape == "linear"); ignored for broadleaves. A *third*, intra-position
    # multiplier composing with leaf_cluster_count (#14, phyllotactic seats) and
    # needle_cluster_spacing (#36, along-shoot) — a node carries
    # (cluster_count × along-shoot) bundles, each a fascicle_count-needle tuft.
    fascicle_count: int = field(default=1, metadata={"ui": {"min": 1, "max": 8, "step": 1}})
    # Basal sheath length as a fraction of needle length (leaf_size): the short
    # papery ring wrapping the bundle base. 0 = no sheath geometry emitted.
    fascicle_sheath_length_ratio: float = field(
        default=0.05, metadata={"ui": {"min": 0.0, "max": 0.5, "step": 0.01}}
    )
    # Tilt of each needle off the shared bundle axis (deg). Pines are tight bundles,
    # so small. Added on top of leaf_splay_deg for each fascicle member.
    fascicle_spread_deg: float = field(
        default=8.0, metadata={"ui": {"min": 0.0, "max": 45.0, "step": 1.0}}
    )
    # Distinct brown sheath material colour (#7 nice-to-have) so the bundle base
    # reads as a papery ring against the green needles.
    fascicle_sheath_color: tuple[float, float, float] = (0.40, 0.28, 0.18)
    leaf_sun_shade_k: float = field(
        default=0.0,
        metadata={"ui": {"min": 0.0, "max": 2.0, "step": 0.05}},
    )
    # Autumn color (#61): per-vertex COLOR_0 multiplier applied to SENESCENT
    # leaves (same tint mechanism as bark #9). None = senescing leaves keep their
    # green material until they abscise. Picked against the green leaf base/texture
    # to read as autumn foliage; only takes effect when leaf_phenology drives
    # leaves into SENESCENT.
    leaf_autumn_color: tuple[float, float, float] | None = None
    # --- Photoreal master (#73 / export pipeline P2) ---
    # Emit the PBR map set (tangent-space normal + packed ORM + cuticle specular +
    # leaf back-light) on the bark/leaf materials. Geometry-neutral (no vertex
    # change), so the canonical master is photoreal by default; target profiles
    # (P3) strip what a given engine can't read. Maps are baked from the clean
    # procedural sources in _textures.py (never a lit photo).
    enable_pbr_maps: bool = field(default=True, metadata={"ui": {"label": "PBR maps"}})
    # Bark normal-map bump depth (mirrors normalTexture.scale at runtime); only
    # emitted for proc bark, where a clean height field exists.
    bark_normal_strength: float = field(default=3.5, metadata={"ui": {"min": 0.0, "max": 5.0, "step": 0.1}})
    # Leaf vein/midrib normal-map depth.
    leaf_normal_strength: float = field(default=0.6, metadata={"ui": {"min": 0.0, "max": 5.0, "step": 0.1}})
    # Leaf back-light strength (KHR_materials_diffuse_transmission factor). 0 = no
    # transmission emitted. NOTE: this is now rendered by current engines (e.g.
    # Babylon), not the inert forward-looking metadata the original design assumed.
    # At the old 0.55 it washed the rich dark-green adaxial albedo into a pale,
    # underside-like glow under image-based lighting; 0.2 keeps a subtle back-lit
    # sheen while letting the opaque green of the top surface read.
    leaf_translucency: float = field(default=0.2, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.05}})
    # Cuticle / dielectric specular (KHR_materials_specular). 0 = omit.
    bark_specular: float = field(default=0.2, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.05}})
    leaf_specular: float = field(default=0.35, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.05}})
    # Per-species leaf base roughness (metallic-roughness roughnessFactor). Low =
    # waxy/glossy cuticle (oak); high = soft/matte (maple). SceneKit-safe: it rides
    # core PBR roughness, so the look survives even where KHR_materials_specular is
    # dropped (e.g. Apple Preview). 0.85 = the prior hard-coded leaf default.
    leaf_roughness: float = field(default=0.85, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.05}})
    # Geometric hero blade (geom/leaf_blade3d.py): midrib crease half-angle (deg)
    # + longitudinal recurve depth (fraction of blade length). 0/0 = flat alpha
    # card (legacy, byte-identical). Broadleaf-only (flat needles stay planar).
    leaf_blade_fold_deg: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 80.0, "step": 1.0}})
    leaf_blade_curl: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 2.0, "step": 0.05}})
    # Concave bowl across the blade half-width (the lamina edges curl up toward the
    # adaxial face), fraction of blade length. 0 = no cupping. Broadleaf-only; reads
    # together with leaf_blade_fold_deg/curl on the hero blade.
    leaf_blade_cup: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 0.6, "step": 0.05}})
    # Diaheliotropic re-seat: rotate the leaf frame about the petiole axis so the
    # adaxial (top) surface tilts toward the sky (+Y), as a fraction [0, 1] of full
    # alignment. 0 = orientation purely from branch geometry (legacy); 1 = top as
    # vertical as the petiole pose allows. Broadleaf-only (needles stay at 0). Pure
    # rotation, so the projected leaf area / light grid / botanical bounds are
    # untouched — render-only.
    leaf_skyface: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.05}})
    # Seasons: emit KHR_materials_variants ("summer"/"autumn") on the leaf
    # material, swapping base colour. Needs leaf_autumn_color; use *instead of*
    # the COLOR_1 phenology tint, not alongside it.
    leaf_season_variants: bool = field(default=False, metadata={"ui": {"label": "Season variants"}})
    # --- Compound leaves (#6) ---
    leaf_kind: Literal["simple", "pinnate", "palmate", "bipinnate"] = field(
        default="simple", metadata={"ui": {"label": "Leaf kind"}}
    )
    leaflet_count: int = field(default=5, metadata={"ui": {"min": 1, "max": 21, "step": 1}})
    leaflet_pair_count: int = field(default=0, metadata={"ui": {"min": 0, "max": 12, "step": 1}})
    terminal_leaflet: bool = field(default=True, metadata={"ui": {"label": "Terminal leaflet"}})
    rachis_length_ratio: float = field(
        default=1.5, metadata={"ui": {"min": 0.1, "max": 6.0, "step": 0.1}}
    )
    rachis_radius_ratio: float = field(
        default=0.03, metadata={"ui": {"min": 0.005, "max": 0.2, "step": 0.005}}
    )
    petiole_length_ratio: float = field(
        default=0.4, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.1}}
    )
    petiole_radius_ratio: float = field(
        default=0.03, metadata={"ui": {"min": 0.005, "max": 0.2, "step": 0.005}}
    )  # simple-leaf petiole base radius / leaf_size
    petiole_taper: float = field(
        default=0.6, metadata={"ui": {"min": 0.1, "max": 1.0, "step": 0.05}}
    )  # petiole tip radius / base radius
    petiole_sides: int = field(
        default=6, metadata={"ui": {"min": 3, "max": 12, "step": 1}}
    )  # petiole tube cross-section polygon sides
    petiole_droop_deg: float = field(
        default=0.0, metadata={"ui": {"min": 0.0, "max": 90.0, "step": 1.0}}
    )  # rigid downward (-Y) bend of petiole + blade
    petiole_color: tuple[float, float, float] = (0.32, 0.42, 0.18)
    leaflet_shape: Literal[
        "linear", "elliptic", "lanceolate", "ovate", "cordate", "palmate"
    ] | None = None
    leaflet_margin: Literal["entire", "serrate", "dentate", "lobed"] | None = None
    leaflet_aspect: float | None = None
    root_flare_height: float = field(
        default=0.3, metadata={"ui": {"min": 0.0, "max": 2.0, "step": 0.05}}
    )
    root_flare_factor: float = field(
        default=1.6, metadata={"ui": {"min": 1.0, "max": 3.0, "step": 0.05}}
    )
    root_flare_falloff: Literal["linear", "smoothstep"] = field(
        default="linear", metadata={"ui": {"label": "Root flare falloff"}}
    )
    root_buttress_count: int = field(
        default=0, metadata={"ui": {"min": 0, "max": 8, "step": 1}}
    )
    root_buttress_amplitude: float = field(
        default=0.15, metadata={"ui": {"min": 0.0, "max": 0.9, "step": 0.05}}
    )
    root_flare_variation: float = field(
        default=0.08, metadata={"ui": {"min": 0.0, "max": 0.9, "step": 0.01}}
    )
    # Issue #9: three-way bark tint blended by Internode.diameter.
    # Presence-gated: bark_tint_young is None => blend off, identical to today.
    bark_tint_young: tuple[float, float, float] | None = None
    bark_tint_mature: tuple[float, float, float] | None = None      # None => falls back to bark_color
    bark_tint_senescent: tuple[float, float, float] | None = None   # None => two-way (young->mature)
    # Stops calibrated to the sim's actual internode-diameter scale: 99% of
    # internodes are 1.6-8.6 cm (median ~2 cm), so the gradient spans the range
    # branches occupy rather than 2-30 cm where only the trunk lives (#9).
    bark_blend_diameter_young: float = field(
        default=0.015, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.005}}
    )
    bark_blend_diameter_mature: float = field(
        default=0.035, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.005}}
    )
    bark_blend_diameter_senescent: float = field(
        default=0.07, metadata={"ui": {"min": 0.0, "max": 2.0, "step": 0.005}}
    )


@dataclass(frozen=True)
class LightConfig:
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    grid_origin: tuple[float, float, float] | None = None
    grid_size: tuple[float, float, float] | None = None
    # Hard override; when None the resolution is derived from voxel_edge_m and the
    # grid size: clamp(ceil(size_axis / voxel_edge_m), 8, 192) per axis (#65).
    grid_resolution: tuple[int, int, int] | None = None
    # Target physical cell edge (metres) — drives scale-aware grid resolution when
    # grid_resolution is None: each axis count = clamp(ceil(size/voxel_edge_m), 8, 192).
    # CALIBRATION CONTRACT (#85): every species preset's light constants
    # (k_absorption, leaf_area_scale, needle_area_scale) are tuned for THIS value
    # (0.04 m); no preset pins voxel_edge_m, so all six inherit it. Per-leaf optical
    # depth scales ~1/voxel_edge_m**2 (LAI = area/cell_volume; tau += k*LAI*step_len
    # with step_len ~= voxel_edge_m), so changing it silently rescales ALL self-
    # shading and decalibrates the whole library. If you must change it, re-tune the
    # light constants and re-verify against the #87 guardrail — full procedure in
    # docs/botany/realism-assessment.md "Contrat de calibration".
    voxel_edge_m: float = field(default=0.04, metadata={"ui": {"min": 0.005, "max": 0.2, "step": 0.005}})
    k_absorption: float = field(default=0.5, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    # Broadleaf foliage occlusion (#62): unitless multiplier on the *real* per-leaf
    # blade area deposited into the LAI grid. 1.0 = pure rendered foliage area;
    # >1 thickens the self-shading, 0 disables leaf occlusion.
    leaf_area_scale: float = field(default=1.0, metadata={"ui": {"min": 0.0, "max": 5.0, "step": 0.1}})
    # Needle/conifer foliage occlusion (#7 — picks up the #62-deferred coupling):
    # unitless multiplier on the *real* per-needle blade area (fascicle multiplicity
    # included) deposited into the LAI grid — the same leaf_area_records area the
    # rendered .glb and total_leaf_area use, now shared by conifers too. Replaces the
    # legacy terminal-bud scalar canopy shell; conifer apical dominance is now
    # re-calibrated against this physical deposit (lambda_apical / vigor_ref /
    # k_absorption), not propped up by a uniform shell. 0 disables needle occlusion.
    needle_area_scale: float = field(default=1.0, metadata={"ui": {"min": 0.0, "max": 5.0, "step": 0.1}})
    internode_area_scale: float = field(default=1.0, metadata={"ui": {"min": 0.0, "max": 5.0, "step": 0.1}})
    # Multiplies the wood/internode LAD at deposit time; 1.0 = legacy (unchanged),
    # raise toward ~8 to model opaque branches that fully shade what's behind them.
    wood_extinction_scale: float = field(default=1.0, metadata={"ui": {"min": 0.0, "max": 20.0, "step": 0.5}})
    n_rays: int = field(default=16, metadata={"ui": {"min": 4, "max": 64, "step": 4}})
    light_direction: tuple[float, float, float] = (0.0, 1.0, 0.0)


@dataclass(frozen=True)
class ShadowConfig:
    """Shadow-propagation exposure backend (#56, Palubicki 2009).

    Active only when ``Config.exposure == "shadow_propagation"``; with the
    default ``"bhse"`` backend this whole block is inert. Each organ stamps a
    pyramid of "shadow" into the voxels below it that decays with depth as
    ``Δs = a · b**(−q)`` over ``q = 0..q_max`` layers; a bud's exposure is
    ``Q = max(0, full_light_C − s + a)`` (the ``+a`` cancels the bud's own
    ``q=0`` self-stamp, so an unshaded bud reads exactly ``full_light_C``). Q
    drives both the light-gradient growth direction and bud fate (dormancy /
    shedding), so crown form emerges from self-shadowing instead of a prescribed
    ``envelope.shape``.

    Grid extent/resolution and the perception cone are NOT duplicated here: they
    are reused from ``LightConfig`` (``voxel_edge_m`` / ``grid_*``) and
    ``SimConfig`` (``r_perception`` / ``theta_perception_deg``), so the
    ``voxel_edge_m = 0.04`` calibration contract stays single-sourced. ``Δs`` is
    voxel-edge-dependent (``q_max`` counts voxels; physical penumbra depth is
    ``q_max · voxel_edge_m``), so these constants are tuned for that same edge —
    see docs/botany/realism-assessment.md.
    """
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    # Self-contribution / apex shadow intensity: Δs at q=0 (the organ's own cell).
    a: float = field(default=1.0, metadata={"ui": {"min": 0.05, "max": 5.0, "step": 0.05}})
    # Per-layer decay base of the shadow pyramid, Δs = a·b**(−q); must be > 1.
    b: float = field(default=2.0, metadata={"ui": {"min": 1.05, "max": 5.0, "step": 0.05}})
    # Penumbra depth cap (voxel layers below an organ); physical depth = q_max·voxel_edge_m.
    q_max: int = field(default=4, metadata={"ui": {"min": 0, "max": 16, "step": 1}})
    # Open-sky exposure constant C; bud exposure Q = max(0, C − s + a).
    full_light_C: float = field(default=1.0, metadata={"ui": {"min": 0.1, "max": 10.0, "step": 0.1}})
    # Multiplier on each organ's real leaf_area_records area when it deposits Δs
    # (the #62/#7 coupling lever): 1.0 = pure rendered foliage area, 0 disables.
    area_weight: float = field(default=1.0, metadata={"ui": {"min": 0.0, "max": 10.0, "step": 0.1}})
    # Exposure below which a bud goes DORMANT (Q < q_dormancy): the clear-bole /
    # soft height governor — the lever this issue is about.
    q_dormancy: float = field(default=0.05, metadata={"ui": {"min": 0.0, "max": 5.0, "step": 0.01}})
    # Maps exposure Q (∈ [0, full_light_C]) onto the Borchert-Honda quality
    # currency. BH and its absolute thresholds (sim.vigor_dormancy,
    # sympodial.q_threshold, shedding.quality_threshold) are calibrated against
    # integer MARKER COUNTS (~1–50 under BHse), not Q (~order 1), so Q is scaled
    # into that regime here (#56 C1). Re-fit per species during calibration.
    quality_scale: float = field(default=20.0, metadata={"ui": {"min": 0.1, "max": 200.0, "step": 1.0}})
    # How a bud's exposure Q is measured:
    #   "skyview" — Q = the #37 hemisphere transmission (open-sky fraction). A
    #     lower-edge branch open to the side reads high Q, keeps vigor, and grows
    #     out → the crown widens toward the base (a real conifer cone).
    #   "pyramid" — Q from the downward shadow-propagation field (a / b / q_max
    #     below; the Palubicki proxy). Cheaper but over-suppresses lower branches
    #     (no side light) → an inverted crown. Kept for comparison.
    measure: Literal["skyview", "pyramid"] = field(
        default="skyview", metadata={"ui": {"label": "Exposure measure"}})


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
    shadow: ShadowConfig = field(default_factory=ShadowConfig)
    forest: ForestConfig = field(default_factory=ForestConfig)
    sag: SagConfig = field(default_factory=SagConfig)
    # Bud-exposure backend (#56): "bhse" = space-colonization markers in an
    # envelope (default; macro form prescribed by envelope.shape).
    # "shadow_propagation" = emergent form from a self-shadowing light grid
    # (see ShadowConfig). Nothing reads this until the shadow backend lands;
    # BHse stays byte-identical.
    exposure: Literal["bhse", "shadow_propagation"] = field(
        default="bhse", metadata={"ui": {"label": "Exposure backend"}}
    )
    seed: int = field(default=0, metadata={"ui": {"min": 0, "max": 2**31 - 1, "step": 1}})
    output: Path = field(default_factory=lambda: Path("tree.glb"))
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if self.exposure not in ("bhse", "shadow_propagation"):
            raise ConfigError(
                f"exposure must be 'bhse' or 'shadow_propagation', got {self.exposure!r}"
            )

        env = self.envelope
        # rx/ry/rz are the bounds AABB under BOTH backends, so always validate.
        if env.rx <= 0 or env.ry <= 0 or env.rz <= 0:
            raise ConfigError(f"envelope rx/ry/rz must be > 0, got {(env.rx, env.ry, env.rz)}")
        # marker_count is BHse-only — shadow propagation seeds no markers and
        # treats the envelope as an advisory bounds volume, so it is gated here.
        if self.exposure == "bhse" and env.marker_count <= 0:
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
        if s.shoot_extension_max <= 0:
            raise ConfigError(f"sim.shoot_extension_max must be > 0, got {s.shoot_extension_max}")
        if s.apical_control_length < 0:
            raise ConfigError(f"sim.apical_control_length must be >= 0, got {s.apical_control_length}")
        lb = s.length_banking
        if not (0.0 <= lb.persist_rate_fraction <= 1.0):
            raise ConfigError(
                f"sim.length_banking.persist_rate_fraction must be in [0, 1], got {lb.persist_rate_fraction}")
        if lb.establish_threshold < 0:
            raise ConfigError(
                f"sim.length_banking.establish_threshold must be >= 0, got {lb.establish_threshold}")
        if lb.release_years <= 0:
            raise ConfigError(
                f"sim.length_banking.release_years must be > 0, got {lb.release_years}")
        if s.vigor_ref <= 0:
            raise ConfigError(f"sim.vigor_ref must be > 0, got {s.vigor_ref}")
        if s.vigor_dormancy < 0:
            raise ConfigError(f"sim.vigor_dormancy must be >= 0, got {s.vigor_dormancy}")
        if not (0.0 < s.vigor_smoothing <= 1.0):
            raise ConfigError(f"sim.vigor_smoothing must be in (0, 1], got {s.vigor_smoothing}")
        if s.vigor_diameter_gain < 0:
            raise ConfigError(f"sim.vigor_diameter_gain must be >= 0, got {s.vigor_diameter_gain}")
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
        sa = s.shade_avoidance
        if not (0.0 <= sa.strength <= 1.0):
            raise ConfigError(
                f"sim.shade_avoidance.strength must be in [0, 1], got {sa.strength}"
            )
        if sa.enabled and not self.light.enabled:
            raise ConfigError(
                "sim.shade_avoidance.enabled=True requires light.enabled=True"
            )
        e = self.sim.elongation
        if e.tau_years <= 0:
            raise ConfigError(f"sim.elongation.tau_years must be > 0, got {e.tau_years}")
        lp = self.sim.leaf_phenology
        if lp.leaf_lifespan_years <= 0:
            raise ConfigError(
                f"sim.leaf_phenology.leaf_lifespan_years must be > 0, got {lp.leaf_lifespan_years}"
            )
        if lp.senescence_duration_years < 0:
            raise ConfigError(
                "sim.leaf_phenology.senescence_duration_years must be >= 0, "
                f"got {lp.senescence_duration_years}"
            )
        bb = s.bud_break_bias
        if bb.mode not in ("uniform", "acrotonic", "basitonic", "mesotonic"):
            raise ConfigError(
                f"sim.bud_break_bias.mode must be one of "
                f"'uniform'|'acrotonic'|'basitonic'|'mesotonic', got {bb.mode!r}"
            )
        if not (0.0 <= bb.strength <= 1.0):
            raise ConfigError(
                f"sim.bud_break_bias.strength must be in [0, 1], got {bb.strength}"
            )
        if s.dt_years <= 0:
            raise ConfigError(f"sim.dt_years must be > 0, got {s.dt_years}")
        if s.max_simulation_years < 0:
            raise ConfigError(
                f"sim.max_simulation_years must be >= 0, got {s.max_simulation_years}"
            )
        lo, hi = s.annual_growth_period
        if not (0.0 <= lo < hi <= 1.0):
            raise ConfigError(
                f"sim.annual_growth_period must satisfy 0.0 <= lo < hi <= 1.0, "
                f"got {s.annual_growth_period}"
            )
        sh = s.growth_period_shoulder
        if sh < 0.0:
            raise ConfigError(
                f"sim.growth_period_shoulder must be >= 0.0, got {sh}"
            )
        # Two shoulders must fit inside the window or they would erase the
        # plateau (and overlap into a non-monotone ramp). lo < hi is guaranteed
        # above, so hi - lo > 0.
        if 2.0 * sh > (hi - lo):
            raise ConfigError(
                f"sim.growth_period_shoulder * 2 ({2.0 * sh}) must be <= the "
                f"annual_growth_period width ({hi - lo}); shoulders would erase "
                f"the plateau"
            )

        t = self.tropism
        for fname in (
            "w_orthotropy_main", "w_orthotropy_lateral",
            "w_gravitropism_main", "w_gravitropism_lateral",
            "w_plagiotropism_main", "w_plagiotropism_lateral",
        ):
            v = getattr(t, fname)
            if v < 0:
                raise ConfigError(f"tropism.{fname} must be >= 0, got {v}")
        if t.epinasty_enabled and t.epinasty_tau_years <= 0:
            raise ConfigError(
                f"tropism.epinasty_tau_years must be > 0 when epinasty_enabled, "
                f"got {t.epinasty_tau_years}"
            )

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
        if g.needle_cluster_spacing < 0.0:
            raise ConfigError(
                f"geom.needle_cluster_spacing must be >= 0, got {g.needle_cluster_spacing}"
            )
        if g.fascicle_count < 1:
            raise ConfigError(f"geom.fascicle_count must be >= 1, got {g.fascicle_count}")
        if g.fascicle_count > 1 and not (g.leaf_kind == "simple" and g.leaf_shape == "linear"):
            # Fascicles are a conifer needle feature. Restricting >1 to simple linear
            # leaves keeps the geometry (build_leaves_primitive, gated on leaf_shape)
            # and the occluding area (leaf_area_records) from ever disagreeing on the
            # needle count for a compound leaf whose leaflet_shape differs in linearity.
            raise ConfigError(
                "geom.fascicle_count > 1 requires leaf_kind='simple' and "
                "leaf_shape='linear' (fascicles are a conifer needle feature); got "
                f"fascicle_count={g.fascicle_count}, leaf_kind={g.leaf_kind!r}, "
                f"leaf_shape={g.leaf_shape!r}"
            )
        if g.fascicle_sheath_length_ratio < 0.0:
            raise ConfigError(
                "geom.fascicle_sheath_length_ratio must be >= 0, "
                f"got {g.fascicle_sheath_length_ratio}"
            )
        if not (0.0 <= g.fascicle_spread_deg <= 90.0):
            raise ConfigError(
                f"geom.fascicle_spread_deg must be in [0, 90], got {g.fascicle_spread_deg}"
            )
        if len(g.fascicle_sheath_color) != 3 or not all(
            0.0 <= c <= 1.0 for c in g.fascicle_sheath_color
        ):
            raise ConfigError(
                "geom.fascicle_sheath_color must be 3 floats in [0, 1], "
                f"got {g.fascicle_sheath_color}"
            )
        if not (0.0 <= g.leaf_sun_shade_k <= 2.0):
            raise ConfigError(
                f"geom.leaf_sun_shade_k must be in [0, 2], got {g.leaf_sun_shade_k}"
            )
        if g.leaf_autumn_color is not None and (
            len(g.leaf_autumn_color) != 3
            or not all(0.0 <= c <= 1.0 for c in g.leaf_autumn_color)
        ):
            raise ConfigError(
                "geom.leaf_autumn_color must be 3 floats in [0, 1], "
                f"got {g.leaf_autumn_color}"
            )
        for fname in ("bark_normal_strength", "leaf_normal_strength",
                      "bark_specular", "leaf_specular", "leaf_blade_curl"):
            v = getattr(g, fname)
            if v < 0:
                raise ConfigError(f"geom.{fname} must be >= 0, got {v}")
        if not (0.0 <= g.leaf_translucency <= 1.0):
            raise ConfigError(f"geom.leaf_translucency must be in [0, 1], got {g.leaf_translucency}")
        if not (0.0 <= g.leaf_roughness <= 1.0):
            raise ConfigError(f"geom.leaf_roughness must be in [0, 1], got {g.leaf_roughness}")
        if not (0.0 <= g.leaf_blade_fold_deg <= 80.0):
            raise ConfigError(
                f"geom.leaf_blade_fold_deg must be in [0, 80], got {g.leaf_blade_fold_deg}"
            )
        if not (0.0 <= g.leaf_blade_cup <= 0.6):
            raise ConfigError(
                f"geom.leaf_blade_cup must be in [0, 0.6], got {g.leaf_blade_cup}"
            )
        if not (0.0 <= g.leaf_skyface <= 1.0):
            raise ConfigError(
                f"geom.leaf_skyface must be in [0, 1], got {g.leaf_skyface}"
            )
        if g.leaf_season_variants and g.leaf_autumn_color is None:
            raise ConfigError(
                "geom.leaf_season_variants=True requires geom.leaf_autumn_color to be set"
            )
        if g.leaf_shape not in ("linear", "elliptic", "lanceolate", "ovate", "cordate", "palmate"):
            raise ConfigError(
                f"geom.leaf_shape must be one of "
                f"'linear'|'elliptic'|'lanceolate'|'ovate'|'cordate'|'palmate', "
                f"got {g.leaf_shape!r}"
            )
        if g.leaf_margin not in ("entire", "serrate", "dentate", "lobed"):
            raise ConfigError(
                f"geom.leaf_margin must be one of "
                f"'entire'|'serrate'|'dentate'|'lobed', got {g.leaf_margin!r}"
            )
        if not (0.0 <= g.leaf_margin_depth <= 1.0):
            raise ConfigError(
                f"geom.leaf_margin_depth must be in [0, 1], got {g.leaf_margin_depth}"
            )
        if g.leaf_margin_count < 0:
            raise ConfigError(
                f"geom.leaf_margin_count must be >= 0, got {g.leaf_margin_count}"
            )
        if g.leaf_kind not in ("simple", "pinnate", "palmate", "bipinnate"):
            raise ConfigError(
                f"geom.leaf_kind must be one of "
                f"'simple'|'pinnate'|'palmate'|'bipinnate', got {g.leaf_kind!r}"
            )
        if g.leaflet_count < 1:
            raise ConfigError(f"geom.leaflet_count must be >= 1, got {g.leaflet_count}")
        if g.leaflet_pair_count < 0:
            raise ConfigError(
                f"geom.leaflet_pair_count must be >= 0, got {g.leaflet_pair_count}"
            )
        if g.leaf_kind == "bipinnate" and g.leaflet_pair_count < 1:
            raise ConfigError(
                "geom.leaflet_pair_count must be >= 1 when leaf_kind is 'bipinnate'"
            )
        if g.rachis_length_ratio <= 0:
            raise ConfigError(
                f"geom.rachis_length_ratio must be > 0, got {g.rachis_length_ratio}"
            )
        if g.rachis_radius_ratio <= 0:
            raise ConfigError(
                f"geom.rachis_radius_ratio must be > 0, got {g.rachis_radius_ratio}"
            )
        if g.petiole_length_ratio < 0:
            raise ConfigError(
                f"geom.petiole_length_ratio must be >= 0, got {g.petiole_length_ratio}"
            )
        if g.leaflet_shape is not None and g.leaflet_shape not in (
            "linear", "elliptic", "lanceolate", "ovate", "cordate", "palmate"
        ):
            raise ConfigError(f"geom.leaflet_shape invalid, got {g.leaflet_shape!r}")
        if g.leaflet_margin is not None and g.leaflet_margin not in (
            "entire", "serrate", "dentate", "lobed"
        ):
            raise ConfigError(f"geom.leaflet_margin invalid, got {g.leaflet_margin!r}")
        if g.leaflet_aspect is not None and not (0.0 < g.leaflet_aspect <= 4.0):
            raise ConfigError(
                f"geom.leaflet_aspect must be in (0, 4], got {g.leaflet_aspect}"
            )
        if g.root_flare_factor < 1.0:
            raise ConfigError(
                f"geom.root_flare_factor must be >= 1.0, got {g.root_flare_factor}"
            )
        if g.root_flare_height < 0.0:
            raise ConfigError(
                f"geom.root_flare_height must be >= 0.0, got {g.root_flare_height}"
            )
        if g.root_flare_falloff not in ("linear", "smoothstep"):
            raise ConfigError(
                f"geom.root_flare_falloff must be 'linear'|'smoothstep', "
                f"got {g.root_flare_falloff!r}"
            )
        if g.root_buttress_count < 0:
            raise ConfigError(
                f"geom.root_buttress_count must be >= 0, got {g.root_buttress_count}"
            )
        if not (0.0 <= g.root_buttress_amplitude < 1.0):
            raise ConfigError(
                f"geom.root_buttress_amplitude must be in [0, 1), "
                f"got {g.root_buttress_amplitude}"
            )
        if not (0.0 <= g.root_flare_variation < 1.0):
            raise ConfigError(
                f"geom.root_flare_variation must be in [0, 1), "
                f"got {g.root_flare_variation}"
            )

        light = self.light
        if light.n_rays <= 0:
            raise ConfigError(f"light.n_rays must be > 0, got {light.n_rays}")
        if light.k_absorption < 0:
            raise ConfigError(f"light.k_absorption must be >= 0, got {light.k_absorption}")
        if light.leaf_area_scale < 0:
            raise ConfigError(f"light.leaf_area_scale must be >= 0, got {light.leaf_area_scale}")
        if light.needle_area_scale < 0:
            raise ConfigError(f"light.needle_area_scale must be >= 0, got {light.needle_area_scale}")
        if light.internode_area_scale < 0:
            raise ConfigError(f"light.internode_area_scale must be >= 0, got {light.internode_area_scale}")
        if light.grid_resolution is not None and any(r <= 0 for r in light.grid_resolution):
            raise ConfigError(f"light.grid_resolution must be all > 0, got {light.grid_resolution}")
        if light.voxel_edge_m <= 0:
            raise ConfigError(f"light.voxel_edge_m must be > 0, got {light.voxel_edge_m}")
        if light.wood_extinction_scale < 0:
            raise ConfigError(f"light.wood_extinction_scale must be >= 0, got {light.wood_extinction_scale}")
        if sum(c * c for c in light.light_direction) <= 0:
            raise ConfigError(f"light.light_direction must be non-zero, got {light.light_direction}")

        shadow = self.shadow
        if shadow.a <= 0:
            raise ConfigError(f"shadow.a must be > 0, got {shadow.a}")
        if shadow.b <= 1:
            raise ConfigError(f"shadow.b must be > 1, got {shadow.b}")
        if shadow.q_max < 0:
            raise ConfigError(f"shadow.q_max must be >= 0, got {shadow.q_max}")
        if shadow.full_light_C <= 0:
            raise ConfigError(f"shadow.full_light_C must be > 0, got {shadow.full_light_C}")
        if shadow.area_weight < 0:
            raise ConfigError(f"shadow.area_weight must be >= 0, got {shadow.area_weight}")
        if shadow.q_dormancy < 0:
            raise ConfigError(f"shadow.q_dormancy must be >= 0, got {shadow.q_dormancy}")
        if shadow.quality_scale <= 0:
            raise ConfigError(f"shadow.quality_scale must be > 0, got {shadow.quality_scale}")

        if not self.output.parent.exists():
            raise ConfigError(f"output parent directory does not exist: {self.output.parent}")


# --- YAML loading ---

import types  # noqa: E402
import typing  # noqa: E402
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
    "shadow": ShadowConfig,
    "sag": SagConfig,
}


def _tuple_element_caster(args: tuple):
    """Pick the scalar caster for a ``tuple[...]`` annotation's element type.

    ``tuple[float, ...]`` / ``tuple[float, float, float]`` -> float;
    ``tuple[int, int, int]`` -> int; anything mixed/bare/unknown -> identity.
    """
    scalars = [a for a in args if a is not Ellipsis]
    if scalars and all(a is int for a in scalars):
        return int
    if scalars and all(a is float for a in scalars):
        return float
    return lambda x: x


def _coerce_value(annotation, value, *, path: str):
    """Coerce one field ``value`` to its ``annotation``: descend into nested
    dataclasses, normalize sequences to (typed) tuples. Anything else passes
    through. Values that are already the target type (e.g. a built dataclass
    instance, or a tuple) are left untouched."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    # Optional[...] / `X | None`: keep None, otherwise coerce against the
    # single non-None member.
    if origin in (typing.Union, types.UnionType):
        if value is None:
            return None
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _coerce_value(non_none[0], value, path=path)
        return value

    if is_dataclass(annotation) and isinstance(value, dict):
        return _coerce(annotation, value, path=path)

    if origin is tuple and isinstance(value, (list, tuple)):
        cast = _tuple_element_caster(args)
        return tuple(cast(x) for x in value)

    return value


def _coerce(dc_type, data: dict, *, path: str):
    """Recursively build a (frozen) dataclass from a nested dict.

    Descends into fields whose annotation is itself a dataclass; normalizes
    sequence fields to tuples; rejects unknown keys (with the dotted ``path``).
    One definition shared by ``load_config`` and ``forest.per_tree_config`` so
    nested coercion can never silently diverge between single-tree and forest
    entry points.
    """
    if not isinstance(data, dict):
        raise ConfigError(f"section {path!r} must be a mapping, got {type(data).__name__}")
    allowed = {f.name for f in fields(dc_type)}
    unknown = set(data) - allowed
    if unknown:
        raise ConfigError(f"unknown keys in section {path!r}: {sorted(unknown)}")
    hints = typing.get_type_hints(dc_type)
    kwargs = {
        key: _coerce_value(hints.get(key), value, path=f"{path}.{key}")
        for key, value in data.items()
    }
    return dc_type(**kwargs)


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
        sections[name] = _coerce(type_, sec_data, path=name)

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


def _load_forest_seed(d: dict) -> ForestSeed:
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


def _load_forest_config(d: dict) -> ForestConfig:
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
