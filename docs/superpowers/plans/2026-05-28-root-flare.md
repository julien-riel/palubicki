# Root Flare at Trunk Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a render-time flare at the trunk base (axisymmetric radial widening + optional azimuthal buttress ridges + per-tree variation), leaving the simulation layer untouched.

**Architecture:** A `_FlareSpec` descriptor is built in `build_bark_primitive` for the trunk chain (chain index 0) only and passed into `_emit_chain_tube`, which turns its single-axis radius array `(N,)` into a per-vertex radius field `(N, columns)`: `r_eff = radii * radial_flare(y) * buttress(y, θ)`. All other chains keep the unchanged `(N,)` fast path. `_emit_root_cap` is untouched (it reuses the already-inflated ring-0 positions). No `sim/` changes.

**Tech Stack:** Python, NumPy, pytest, frozen dataclass config, pygltflib goldens.

---

### Task 1: Add `GeomConfig` fields + validation

**Files:**
- Modify: `src/palubicki/config.py` (GeomConfig at `:214`, geom validation block in `Config.__post_init__`, ending `:448`)
- Test: `tests/test_config.py` (existing — append to it)

> Validation runs in `Config.__post_init__` (`config.py:322`), so an invalid value raises `ConfigError` at **construction time** — there is no separate `.validate()` call.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py` (it already imports the config dataclasses — reuse them; add any missing names to its existing import):

```python
def _geom_cfg(**geom_kwargs):
    from palubicki.config import (
        Config, EnvelopeConfig, GeomConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    return Config(
        envelope=EnvelopeConfig(), sim=SimConfig(), tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(), shedding=SheddingConfig(),
        geom=GeomConfig(**geom_kwargs),
    )


def test_flare_defaults_present():
    from palubicki.config import GeomConfig
    g = GeomConfig()
    assert g.root_flare_height == 0.3
    assert g.root_flare_factor == 1.6
    assert g.root_flare_falloff == "linear"
    assert g.root_buttress_count == 0
    assert g.root_buttress_amplitude == 0.15
    assert g.root_flare_variation == 0.08


def test_flare_factor_below_one_rejected():
    import pytest
    from palubicki.config import ConfigError
    with pytest.raises(ConfigError, match="root_flare_factor"):
        _geom_cfg(root_flare_factor=0.9)  # raises in __post_init__


def test_buttress_amplitude_out_of_range_rejected():
    import pytest
    from palubicki.config import ConfigError
    with pytest.raises(ConfigError, match="root_buttress_amplitude"):
        _geom_cfg(root_buttress_amplitude=1.0)


def test_flare_variation_out_of_range_rejected():
    import pytest
    from palubicki.config import ConfigError
    with pytest.raises(ConfigError, match="root_flare_variation"):
        _geom_cfg(root_flare_variation=1.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -k "flare or buttress" -v`
Expected: FAIL — `AttributeError: ... 'GeomConfig' object has no attribute 'root_flare_height'`

- [ ] **Step 3: Add the fields to `GeomConfig`**

In `src/palubicki/config.py`, after `leaf_sun_shade_k` (`:243-246`) inside `class GeomConfig`:

```python
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
```

- [ ] **Step 4: Add validation**

In `config.py`, append to the geom validation block inside `Config.__post_init__` (after the `leaf_margin` check ends, before the next config section's checks — around `:460`):

```python
        if g.root_flare_factor < 1.0:
            raise ConfigError(
                f"geom.root_flare_factor must be >= 1.0, got {g.root_flare_factor}"
            )
        if g.root_flare_height < 0.0:
            raise ConfigError(
                f"geom.root_flare_height must be >= 0, got {g.root_flare_height}"
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
```

> `Literal` is already imported in `config.py` (used by `leaf_shape`). Verify with `grep -n "from typing import" src/palubicki/config.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -k "flare or buttress" -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "geom(config): add root flare + buttress + variation fields (#8)"
```

---

### Task 2: `_falloff` helper

**Files:**
- Modify: `src/palubicki/geom/tubes.py`
- Test: `tests/geom/test_tubes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/geom/test_tubes.py`:

```python
def test_falloff_linear_identity():
    from palubicki.geom.tubes import _falloff
    t = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    np.testing.assert_allclose(_falloff(t, "linear"), t)


def test_falloff_smoothstep_known_values():
    from palubicki.geom.tubes import _falloff
    t = np.array([0.0, 0.25, 0.5, 1.0])
    # 3t^2 - 2t^3
    expected = np.array([0.0, 0.15625, 0.5, 1.0])
    np.testing.assert_allclose(_falloff(t, "smoothstep"), expected)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/geom/test_tubes.py -k falloff -v`
Expected: FAIL — `ImportError: cannot import name '_falloff'`

- [ ] **Step 3: Add the helper**

In `src/palubicki/geom/tubes.py`, after the imports / before `build_bark_primitive` (around `:17`):

```python
def _falloff(t: np.ndarray, mode: str) -> np.ndarray:
    """Flare blend weight on ``t`` in [0, 1] (1 at base, 0 at top of flare zone).

    ``linear`` is identity; ``smoothstep`` is the classic ``3t^2 - 2t^3``.
    """
    if mode == "smoothstep":
        return t * t * (3.0 - 2.0 * t)
    return t
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/geom/test_tubes.py -k falloff -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/geom/tubes.py tests/geom/test_tubes.py
git commit -m "geom(tubes): add _falloff blend helper (#8)"
```

---

### Task 3: Radial flare in `_emit_chain_tube` + `build_bark_primitive` flare params

**Files:**
- Modify: `src/palubicki/geom/tubes.py` (`_ChainBuild` area `:13`, `build_bark_primitive` `:19-56`, `_emit_chain_tube` `:114-198`)
- Test: `tests/geom/test_tubes.py`

This task adds the `_FlareSpec` descriptor and the per-column radius field, but only the **radial (axisymmetric)** component. Buttress comes in Task 4.

- [ ] **Step 1: Write the failing tests**

Append to `tests/geom/test_tubes.py`:

```python
def _radial_dist(prim, ring_sides):
    # radial distance from the +Y axis for each vertex (vertical chain through origin)
    return np.sqrt(prim.positions[:, 0] ** 2 + prim.positions[:, 2] ** 2)


def test_flare_factor_one_is_identity():
    tree_a = _vertical_chain(n=4, length=0.2, r=0.05)
    tree_b = _vertical_chain(n=4, length=0.2, r=0.05)
    base = build_bark_primitive(tree_a, ring_sides=8, material=_mat())
    flared = build_bark_primitive(
        tree_b, ring_sides=8, material=_mat(),
        flare_height=0.5, flare_factor=1.0, flare_falloff="linear",
    )
    np.testing.assert_array_equal(base.positions, flared.positions)


def test_flare_widens_base_ring_only():
    # chain nodes at y = 0, 0.2, 0.4, 0.6, 0.8 ; flare_height 0.5 ⇒ y>=0.5 untouched
    tree = _vertical_chain(n=4, length=0.2, r=0.05)
    prim = build_bark_primitive(
        tree, ring_sides=8, material=_mat(),
        flare_height=0.5, flare_factor=2.0, flare_falloff="linear",
        flare_variation=0.0,
    )
    columns = 8 + 1
    rad = _radial_dist(prim, 8)
    base_ring = rad[0:columns]            # y = 0  ⇒ t = 1 ⇒ scale 2.0
    top_ring = rad[4 * columns:5 * columns]  # y = 0.8 ⇒ t = 0 ⇒ scale 1.0
    np.testing.assert_allclose(base_ring, 0.10, atol=1e-6)   # 0.05 * 2
    np.testing.assert_allclose(top_ring, 0.05, atol=1e-6)


def test_flare_only_applies_to_trunk_chain():
    # A lateral branch (chain index > 0) must NOT be flared even if its nodes are low.
    # Build a tree whose lateral starts near the base and verify lateral radii unchanged.
    # (Uses the trunk-only guard: flare passed to chains[0] only.)
    tree = _vertical_chain(n=3, length=0.2, r=0.05)
    flared = build_bark_primitive(
        tree, ring_sides=8, material=_mat(),
        flare_height=0.5, flare_factor=2.0,
    )
    # vertical-only tree has a single chain, so this is a smoke test that flare still builds.
    assert np.isfinite(flared.positions).all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/geom/test_tubes.py -k flare -v`
Expected: FAIL — `build_bark_primitive() got an unexpected keyword argument 'flare_height'`

- [ ] **Step 3: Add the `_FlareSpec` dataclass**

In `src/palubicki/geom/tubes.py`, after the existing `_ChainBuild` dataclass (`:13-16`):

```python
@dataclass
class _FlareSpec:
    """Render-time flare descriptor for the trunk chain. Ground reference is the
    chain's own first-node Y (computed inside ``_emit_chain_tube``)."""
    height: float
    factor: float            # already jittered + clamped to >= 1.0 by build_bark_primitive
    falloff: str             # "linear" | "smoothstep"
    buttress_count: int
    buttress_amplitude: float
    buttress_phase: float
```

- [ ] **Step 4: Extend `build_bark_primitive` signature and build the spec**

Replace the signature and chain loop in `build_bark_primitive` (`:19-45`). New signature:

```python
def build_bark_primitive(
    tree: Tree,
    *,
    ring_sides: int,
    material: Material,
    flare_height: float = 0.0,
    flare_factor: float = 1.0,
    flare_falloff: str = "linear",
    buttress_count: int = 0,
    buttress_amplitude: float = 0.0,
    flare_variation: float = 0.0,
    seed: int = 0,
) -> Primitive:
    chains = _collect_chains(tree)

    # Per-tree variation: phase rotates buttress ridges, jitter perturbs the factor.
    # Two draws in fixed order keep seed -> output deterministic.
    rng = np.random.default_rng(seed)
    buttress_phase = float(rng.uniform(0.0, 2.0 * np.pi))
    jitter = float(rng.uniform(-1.0, 1.0)) * flare_variation
    eff_factor = max(1.0, flare_factor * (1.0 + jitter))

    flare = _FlareSpec(
        height=flare_height,
        factor=eff_factor,
        falloff=flare_falloff,
        buttress_count=buttress_count,
        buttress_amplitude=buttress_amplitude,
        buttress_phase=buttress_phase,
    )

    pos_parts: list[np.ndarray] = []
    nor_parts: list[np.ndarray] = []
    uv_parts: list[np.ndarray] = []
    idx_parts: list[np.ndarray] = []
    vertex_offset = 0

    for i, chain in enumerate(chains):
        chain_flare = flare if i == 0 else None  # trunk chain only
        p, n, u, idx = _emit_chain_tube(chain, ring_sides, vertex_offset, chain_flare)
        if p.shape[0]:
            pos_parts.append(p)
            nor_parts.append(n)
            uv_parts.append(u)
            idx_parts.append(idx)
            vertex_offset += p.shape[0]
```

> Leave the rest of `build_bark_primitive` (the root-cap block `:37-45` and the concatenation `:47-56`) unchanged. The root-cap call already uses `chains[0]` and the now-inflated ring-0 positions.

- [ ] **Step 5: Add the per-column radius field to `_emit_chain_tube`**

Change the signature (`:114-118`):

```python
def _emit_chain_tube(
    chain: _ChainBuild,
    ring_sides: int,
    vertex_offset: int,
    flare: "_FlareSpec | None" = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
```

Then, after `angles`, `cos_a`, `sin_a` and `radials` are computed (immediately after the `radials = ...` line at `:172`), replace the position line. Find:

```python
    radials = cos_a[None, :, None] * rights[:, None, :] + sin_a[None, :, None] * ups[:, None, :]
    positions = node_positions[:, None, :] + radii_arr[:, None, None] * radials
```

Replace the `positions = ...` line with:

```python
    r_eff = _flare_radius_field(node_positions, radii_arr, angles, flare)
    positions = node_positions[:, None, :] + r_eff[:, :, None] * radials
```

- [ ] **Step 6: Add the `_flare_radius_field` helper**

In `tubes.py`, add directly above `_emit_chain_tube` (`:113`):

```python
def _flare_radius_field(
    node_positions: np.ndarray,   # (N, 3) bent positions
    radii_arr: np.ndarray,        # (N,)
    angles: np.ndarray,           # (columns,)
    flare: "_FlareSpec | None",
) -> np.ndarray:
    """Effective per-vertex radius. ``(N, 1)`` (broadcasts over columns) when no
    flare, ``(N, columns)`` when the trunk chain carries a ``_FlareSpec``.

    Radial (axisymmetric) component only is added here; buttress is layered on in
    a later step. Ground reference is the chain's own first node ``node_positions[0, 1]``.
    """
    if flare is None or flare.height <= 0.0:
        return radii_arr[:, None]

    base_y = node_positions[0, 1]
    y = node_positions[:, 1] - base_y                       # (N,)
    t = np.clip((flare.height - y) / flare.height, 0.0, 1.0)  # 1 at base, 0 at top
    f = _falloff(t, flare.falloff)                          # (N,)
    radial = 1.0 + (flare.factor - 1.0) * f                 # (N,)
    return (radii_arr * radial)[:, None]                    # (N, 1)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/geom/test_tubes.py -k flare -v`
Expected: PASS (3 flare tests)

- [ ] **Step 8: Run the full tubes suite to confirm no regression**

Run: `.venv/bin/pytest tests/geom/test_tubes.py -v`
Expected: PASS (existing + new). The existing tests call `build_bark_primitive` without flare args (defaults `factor=1.0`, `height=0.0`), so positions are byte-identical.

- [ ] **Step 9: Commit**

```bash
git add src/palubicki/geom/tubes.py tests/geom/test_tubes.py
git commit -m "geom(tubes): axisymmetric root flare via per-vertex radius field (#8)"
```

---

### Task 4: Azimuthal buttress modulation

**Files:**
- Modify: `src/palubicki/geom/tubes.py` (`_flare_radius_field`)
- Test: `tests/geom/test_tubes.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/geom/test_tubes.py`:

```python
def test_buttress_modulates_base_ring():
    tree = _vertical_chain(n=4, length=0.2, r=0.05)
    prim = build_bark_primitive(
        tree, ring_sides=8, material=_mat(),
        flare_height=0.5, flare_factor=1.5, flare_falloff="linear",
        buttress_count=4, buttress_amplitude=0.3, flare_variation=0.0, seed=0,
    )
    columns = 8 + 1
    rad = _radial_dist(prim, 8)
    base_ring = rad[0:columns]
    # ridges ⇒ base ring radii are NOT all equal
    assert base_ring.std() > 1e-3


def test_buttress_seam_welded():
    tree = _vertical_chain(n=4, length=0.2, r=0.05)
    prim = build_bark_primitive(
        tree, ring_sides=8, material=_mat(),
        flare_height=0.5, flare_factor=1.5,
        buttress_count=5, buttress_amplitude=0.3, flare_variation=0.0, seed=0,
    )
    columns = 8 + 1
    # column 0 and the duplicated seam column (index ring_sides) must coincide in 3D
    np.testing.assert_allclose(prim.positions[0], prim.positions[8], atol=1e-12)


def test_buttress_count_zero_is_axisymmetric():
    tree = _vertical_chain(n=4, length=0.2, r=0.05)
    prim = build_bark_primitive(
        tree, ring_sides=8, material=_mat(),
        flare_height=0.5, flare_factor=1.5,
        buttress_count=0, buttress_amplitude=0.3, flare_variation=0.0,
    )
    columns = 8 + 1
    rad = _radial_dist(prim, 8)
    base_ring = rad[0:columns]
    np.testing.assert_allclose(base_ring, base_ring[0], atol=1e-9)  # all equal
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/geom/test_tubes.py -k buttress -v`
Expected: FAIL — `test_buttress_modulates_base_ring` fails (`std` ~0, radius still axisymmetric).

- [ ] **Step 3: Add buttress to `_flare_radius_field`**

Replace the body of `_flare_radius_field` after `radial = ...` (the final `return` line):

```python
    radial = 1.0 + (flare.factor - 1.0) * f                 # (N,)

    if flare.buttress_count <= 0 or flare.buttress_amplitude <= 0.0:
        return (radii_arr * radial)[:, None]                # (N, 1)

    # Azimuthal ridges, fading with the same falloff so they live only in the collar.
    # ``angles`` already uses ``k % ring_sides`` so angles[ring_sides] == angles[0];
    # the seam vertex therefore stays welded.
    butt = 1.0 + flare.buttress_amplitude * f[:, None] * np.cos(
        flare.buttress_count * angles[None, :] + flare.buttress_phase
    )                                                       # (N, columns)
    return radii_arr[:, None] * radial[:, None] * butt      # (N, columns)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/geom/test_tubes.py -k buttress -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full tubes suite**

Run: `.venv/bin/pytest tests/geom/test_tubes.py -v`
Expected: PASS (all). `buttress_count=0` default keeps non-buttressed builds axisymmetric and identity-preserving.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/geom/tubes.py tests/geom/test_tubes.py
git commit -m "geom(tubes): azimuthal buttress ridges with welded seam (#8)"
```

---

### Task 5: Per-tree variation test (RNG already wired in Task 3)

**Files:**
- Test: `tests/geom/test_tubes.py`

The RNG draws (`buttress_phase`, `jitter`) were added in Task 3 Step 4. This task only locks the behavior with tests.

- [ ] **Step 1: Write the failing/locking tests**

Append to `tests/geom/test_tubes.py`:

```python
def test_variation_differs_by_seed():
    rad0 = _seeded_base_radius(seed=0)
    rad1 = _seeded_base_radius(seed=1)
    assert not np.allclose(rad0, rad1)


def test_variation_same_seed_is_deterministic():
    assert np.allclose(_seeded_base_radius(seed=3), _seeded_base_radius(seed=3))


def test_variation_zero_means_identical_flares():
    rad0 = _seeded_base_radius(seed=0, variation=0.0)
    rad1 = _seeded_base_radius(seed=99, variation=0.0)
    # no buttress, no jitter ⇒ base radius identical regardless of seed
    np.testing.assert_allclose(rad0, rad1, atol=1e-12)


def _seeded_base_radius(seed: int, variation: float = 0.1):
    tree = _vertical_chain(n=4, length=0.2, r=0.05)
    prim = build_bark_primitive(
        tree, ring_sides=8, material=_mat(),
        flare_height=0.5, flare_factor=1.6, flare_falloff="linear",
        buttress_count=0, buttress_amplitude=0.0,
        flare_variation=variation, seed=seed,
    )
    columns = 8 + 1
    return _radial_dist(prim, 8)[0:columns]
```

- [ ] **Step 2: Run tests to verify they pass (RNG wired in Task 3)**

Run: `.venv/bin/pytest tests/geom/test_tubes.py -k variation -v`
Expected: PASS (3 tests). If `test_variation_differs_by_seed` fails, the `eff_factor`/jitter draw in `build_bark_primitive` is missing — re-check Task 3 Step 4.

- [ ] **Step 3: Commit**

```bash
git add tests/geom/test_tubes.py
git commit -m "geom(tubes): lock per-tree flare variation behavior (#8)"
```

---

### Task 6: Wire flare config through `build_mesh`

**Files:**
- Modify: `src/palubicki/geom/builder.py:25`
- Test: `tests/geom/test_builder.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/geom/test_builder.py` (mirror its existing imports — it already builds a `Config` + `tree`; reuse whatever tree/config helper it defines. If it has a `_simple_tree()`/`_cfg()` helper, use those names; otherwise build a minimal `Config` like the golden tests do):

```python
def test_build_mesh_applies_flare_from_config():
    import numpy as np
    from palubicki.config import (
        Config, EnvelopeConfig, GeomConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.geom.builder import build_mesh
    from palubicki.sim.simulator import simulate

    def cfg(factor):
        return Config(
            envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=400),
            sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_iterations=8),
            tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(enabled=False),
            geom=GeomConfig(root_flare_factor=factor, root_flare_height=0.5, root_flare_variation=0.0),
            seed=7,
        )

    tree = simulate(cfg(1.0))
    flat = build_mesh(tree, cfg(1.0)).primitives[0].positions
    flared = build_mesh(tree, cfg(2.0)).primitives[0].positions
    # flaring the base must move at least some bark vertices outward
    assert not np.array_equal(flat, flared)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/geom/test_builder.py -k flare -v`
Expected: FAIL — `flat` and `flared` are equal (builder ignores the flare config).

- [ ] **Step 3: Pass the flare config into `build_bark_primitive`**

In `src/palubicki/geom/builder.py`, replace the call at `:25`:

```python
    bark_prim = build_bark_primitive(
        tree,
        ring_sides=cfg.geom.ring_sides,
        material=bark_mat,
        flare_height=cfg.geom.root_flare_height,
        flare_factor=cfg.geom.root_flare_factor,
        flare_falloff=cfg.geom.root_flare_falloff,
        buttress_count=cfg.geom.root_buttress_count,
        buttress_amplitude=cfg.geom.root_buttress_amplitude,
        flare_variation=cfg.geom.root_flare_variation,
        seed=cfg.seed,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/geom/test_builder.py -k flare -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/geom/builder.py tests/geom/test_builder.py
git commit -m "geom(builder): wire root flare config into bark primitive (#8)"
```

---

### Task 7: Per-species YAML defaults

**Files:**
- Modify: `src/palubicki/configs/species/oak.yaml`, `maple.yaml`, `pine.yaml`, `fir.yaml`, `birch.yaml`

- [ ] **Step 1: Add a `geom:` flare block to each species**

Append these keys under the existing `geom:` block in each file (do NOT create a second `geom:` mapping — add to the one already present).

`oak.yaml`:
```yaml
  root_flare_height: 0.4
  root_flare_factor: 1.8
  root_flare_falloff: smoothstep
  root_buttress_count: 5
  root_buttress_amplitude: 0.15
```

`maple.yaml`:
```yaml
  root_flare_height: 0.3
  root_flare_factor: 1.6
  root_flare_falloff: linear
  root_buttress_count: 3
  root_buttress_amplitude: 0.10
```

`pine.yaml` and `fir.yaml` (identical):
```yaml
  root_flare_height: 0.2
  root_flare_factor: 1.3
  root_flare_falloff: linear
  root_buttress_count: 0
```

`birch.yaml`:
```yaml
  root_flare_height: 0.15
  root_flare_factor: 1.15
  root_flare_falloff: linear
  root_buttress_count: 0
```

- [ ] **Step 2: Verify each species config loads and validates**

Run: `.venv/bin/python -c "from palubicki.cli import main; import sys; sys.exit(any(main(['dump-defaults','--species',s]) for s in ['oak','maple','pine','fir','birch']))"`
Expected: exit 0, YAML for each species printed to stdout with the new `root_flare_*` keys present.

- [ ] **Step 3: Commit**

```bash
git add src/palubicki/configs/species/oak.yaml src/palubicki/configs/species/maple.yaml \
        src/palubicki/configs/species/pine.yaml src/palubicki/configs/species/fir.yaml \
        src/palubicki/configs/species/birch.yaml
git commit -m "geom(species): per-species root flare defaults (#8)"
```

---

### Task 8: Regenerate goldens + acceptance check

**Files:**
- Modify (regenerate): `tests/golden/data/*.sha256`

The default `GeomConfig` now flares (factor 1.6), so the ellipsoid goldens in `test_goldens.py` change too — not just species goldens. This is expected per the acceptance criteria.

- [ ] **Step 1: Confirm the goldens fail BEFORE regenerating**

Run: `.venv/bin/pytest tests/golden/ -v -m slow`
Expected: FAIL — `golden mismatch` for species and ellipsoid hashes (flare changed the buffers).

- [ ] **Step 2: Visually verify the oak flare (acceptance criterion 1)**

Run:
```bash
.venv/bin/palubicki generate --species oak --seed 0 -o /tmp/oak_flare.glb
.venv/bin/palubicki preview /tmp/oak_flare.glb --no-leaves -o /tmp/oak_flare.png
```
Open `/tmp/oak_flare.png` (or load the `.glb`) and confirm a visibly widened, ridged trunk base. If `preview` reports the render extra is missing, run `.venv/bin/pip install -e '.[render]'` first.

- [ ] **Step 3: Confirm `factor=1.0` reproduces the old shape (acceptance criterion 2)**

`generate` has no generic key=value override flag, so dump the oak preset to a YAML, set the factor to 1.0, and generate via `--config`:

```bash
.venv/bin/palubicki dump-defaults --species oak > /tmp/oak_noflare.yaml
# edit /tmp/oak_noflare.yaml: under geom:, set  root_flare_factor: 1.0
.venv/bin/palubicki generate --config /tmp/oak_noflare.yaml --seed 0 -o /tmp/oak_noflare.glb
```
The base should look like the pre-flare cylinder-on-fan. (The YAML edit can be done with any editor; the key already exists in the dumped file after Task 7.)

- [ ] **Step 4: Confirm the sim layer is untouched (acceptance criterion 3)**

Run: `.venv/bin/pytest tests/sim/ -v`
Expected: PASS with no changes. Also confirm no `sim/` file is in the branch diff:
Run: `git diff main --name-only -- src/palubicki/sim/`
Expected: empty output.

- [ ] **Step 5: Regenerate goldens**

Run: `.venv/bin/pytest tests/golden/ -m slow --update-goldens`
Expected: tests SKIP with "golden written" messages.

- [ ] **Step 6: Verify regenerated goldens pass**

Run: `.venv/bin/pytest tests/golden/ -v -m slow`
Expected: PASS (all species + ellipsoid).

- [ ] **Step 7: Run the full suite + lint**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`
Expected: PASS, no lint errors.

- [ ] **Step 8: Commit**

```bash
git add tests/golden/data
git commit -m "test(golden): regenerate trunk goldens for root flare (#8)"
```

---

## Self-Review notes

- **Spec coverage:** config fields + validation (T1), `_falloff` (T2), axisymmetric flare + trunk-only guard + factor=1.0 identity (T3), buttress + seam weld (T4), per-tree variation knob (T5), builder wiring (T6), species defaults (T7), goldens + all four acceptance criteria (T8). All spec sections covered.
- **Type consistency:** `_FlareSpec` fields (`height`, `factor`, `falloff`, `buttress_count`, `buttress_amplitude`, `buttress_phase`) are defined in T3 and consumed identically in T3/T4's `_flare_radius_field`. `build_bark_primitive` kwargs match between T3 (definition), T5, and T6 (builder call). `_falloff(t, mode)` signature consistent T2→T3→T4.
- **Ground reference:** computed inside `_emit_chain_tube` as `node_positions[0, 1]` (trunk chain's first node) — no `base_y` threaded through the spec, matching the refinement noted at plan start.
