# Bark diameter blend (three-way tint) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vary bark color along the trunk by `Internode.diameter` — pale young bark on thin twigs, mature mid-trunk, dark senescent bark at the thick base — visible in both palubicki's internal renderer and exported GLB.

**Architecture:** A pure `bark_tint` helper maps per-vertex diameter through a three-stop piecewise-linear color gradient. `build_bark_primitive` bakes the result into a new `Primitive.colors` array. The internal renderer uses these as per-face colors; glTF emits them as `COLOR_0` with `baseColorFactor=white` so the tint carries the albedo. Blend is presence-gated on `bark_tint_young`; when off, every output path is byte-for-byte unchanged.

**Tech Stack:** Python 3, numpy, pygltflib, trimesh, PIL, pytest. Spec: `docs/superpowers/specs/2026-05-29-bark-diameter-blend-design.md`.

**Conventions:**
- The venv does not persist across shell calls — **prefix every command with `.venv/bin/`** (e.g. `.venv/bin/pytest`).
- This is a PoC: breaking YAML/goldens is fine; no backward-compat shims.
- Slow tests are marked `@pytest.mark.slow`; run them with `-m slow` or by path.

---

### Task 1: `bark_tint` helper + `BarkBlendStops`

A pure, vectorized function mapping diameters to RGB tints across three stops. New module so geometry and config can both import it without cycles.

**Files:**
- Create: `src/palubicki/geom/bark_blend.py`
- Test: `tests/geom/test_bark_blend.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/geom/test_bark_blend.py
import numpy as np

from palubicki.geom.bark_blend import BarkBlendStops, bark_tint


def _stops():
    return BarkBlendStops(
        d_young=0.02, d_mature=0.10, d_senescent=0.30,
        c_young=(0.45, 0.38, 0.30),
        c_mature=(0.35, 0.22, 0.12),
        c_senescent=(0.22, 0.20, 0.16),
    )


def test_below_young_clamps_to_young():
    out = bark_tint(np.array([0.0, 0.01, 0.02]), _stops())
    assert out.shape == (3, 3)
    assert out.dtype == np.float32
    np.testing.assert_allclose(out, np.tile([0.45, 0.38, 0.30], (3, 1)), atol=1e-6)


def test_above_senescent_clamps_to_senescent():
    out = bark_tint(np.array([0.30, 0.5, 10.0]), _stops())
    np.testing.assert_allclose(out, np.tile([0.22, 0.20, 0.16], (3, 1)), atol=1e-6)


def test_mature_stop_is_exact():
    out = bark_tint(np.array([0.10]), _stops())
    np.testing.assert_allclose(out[0], [0.35, 0.22, 0.12], atol=1e-6)


def test_midpoint_young_to_mature_is_halfway():
    # diameter halfway between d_young (0.02) and d_mature (0.10) = 0.06
    out = bark_tint(np.array([0.06]), _stops())
    expected = 0.5 * np.array([0.45, 0.38, 0.30]) + 0.5 * np.array([0.35, 0.22, 0.12])
    np.testing.assert_allclose(out[0], expected, atol=1e-6)


def test_midpoint_mature_to_senescent_is_halfway():
    # diameter halfway between d_mature (0.10) and d_senescent (0.30) = 0.20
    out = bark_tint(np.array([0.20]), _stops())
    expected = 0.5 * np.array([0.35, 0.22, 0.12]) + 0.5 * np.array([0.22, 0.20, 0.16])
    np.testing.assert_allclose(out[0], expected, atol=1e-6)


def test_degenerate_equal_stops_no_nan():
    stops = BarkBlendStops(
        d_young=0.10, d_mature=0.10, d_senescent=0.10,
        c_young=(0.4, 0.4, 0.4), c_mature=(0.3, 0.3, 0.3), c_senescent=(0.2, 0.2, 0.2),
    )
    out = bark_tint(np.array([0.05, 0.10, 0.20]), stops)
    assert np.isfinite(out).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/geom/test_bark_blend.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'palubicki.geom.bark_blend'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/palubicki/geom/bark_blend.py
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

RGB = tuple[float, float, float]


@dataclass(frozen=True)
class BarkBlendStops:
    """Three-stop diameter→color gradient for bark tinting.

    Requires d_young <= d_mature <= d_senescent. Equal adjacent stops collapse
    that segment without dividing by zero (the lower color wins at the boundary).
    """
    d_young: float
    d_mature: float
    d_senescent: float
    c_young: RGB
    c_mature: RGB
    c_senescent: RGB


def _lerp_segment(
    d: np.ndarray, lo: float, hi: float, c_lo: np.ndarray, c_hi: np.ndarray
) -> np.ndarray:
    """Per-element lerp of c_lo->c_hi by (d-lo)/(hi-lo), clamped to [0,1].
    Degenerate lo==hi yields t=0 (c_lo)."""
    span = hi - lo
    if span <= 0.0:
        t = np.zeros_like(d)
    else:
        t = np.clip((d - lo) / span, 0.0, 1.0)
    return c_lo[None, :] + t[:, None] * (c_hi - c_lo)[None, :]


def bark_tint(diameter: np.ndarray, stops: BarkBlendStops) -> np.ndarray:
    """Map per-vertex diameter to (N, 3) float32 RGB via a 3-stop gradient.

    d <= d_young            -> c_young
    d_young..d_mature       -> lerp c_young -> c_mature
    d_mature..d_senescent   -> lerp c_mature -> c_senescent
    d >= d_senescent        -> c_senescent
    """
    d = np.asarray(diameter, dtype=np.float64).reshape(-1)
    c_young = np.asarray(stops.c_young, dtype=np.float64)
    c_mature = np.asarray(stops.c_mature, dtype=np.float64)
    c_senescent = np.asarray(stops.c_senescent, dtype=np.float64)

    lower = _lerp_segment(d, stops.d_young, stops.d_mature, c_young, c_mature)
    upper = _lerp_segment(d, stops.d_mature, stops.d_senescent, c_mature, c_senescent)

    use_upper = (d >= stops.d_mature)[:, None]
    out = np.where(use_upper, upper, lower)
    return out.astype(np.float32)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/geom/test_bark_blend.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/geom/bark_blend.py tests/geom/test_bark_blend.py
git commit -m "geom(bark): three-stop diameter->tint helper (#9)"
```

---

### Task 2: Add `colors` field to `Primitive`

Per-vertex color attribute, defaulting to `None` so every existing `Primitive(...)` call is unaffected.

**Files:**
- Modify: `src/palubicki/geom/mesh.py:22-28`
- Test: `tests/geom/test_mesh.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/geom/test_mesh.py
import numpy as np

from palubicki.geom.mesh import Material, Primitive


def _bare_mat():
    return Material(name="bark", base_color=(1, 1, 1, 1), metallic=0.0, roughness=1.0,
                    base_color_texture_png=None, alpha_mode="OPAQUE",
                    alpha_cutoff=0.5, double_sided=False)


def test_primitive_colors_defaults_none():
    p = Primitive(
        positions=np.zeros((3, 3), np.float32),
        normals=np.zeros((3, 3), np.float32),
        uvs=np.zeros((3, 2), np.float32),
        indices=np.array([0, 1, 2], np.uint32),
        material=_bare_mat(),
    )
    assert p.colors is None


def test_primitive_accepts_colors():
    cols = np.ones((3, 3), np.float32)
    p = Primitive(
        positions=np.zeros((3, 3), np.float32),
        normals=np.zeros((3, 3), np.float32),
        uvs=np.zeros((3, 2), np.float32),
        indices=np.array([0, 1, 2], np.uint32),
        material=_bare_mat(),
        colors=cols,
    )
    assert p.colors is cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/geom/test_mesh.py -k colors -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'colors'`

- [ ] **Step 3: Write minimal implementation**

Edit `src/palubicki/geom/mesh.py`, in the `Primitive` dataclass add the field after `material`:

```python
@dataclass
class Primitive:
    positions: np.ndarray  # (V, 3) float32
    normals: np.ndarray    # (V, 3) float32
    uvs: np.ndarray        # (V, 2) float32
    indices: np.ndarray    # (M,)   uint32
    material: Material
    colors: np.ndarray | None = None  # (V, 3) float32 per-vertex RGB; None = no vertex color
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/geom/test_mesh.py -k colors -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/geom/mesh.py tests/geom/test_mesh.py
git commit -m "geom(mesh): optional per-vertex colors on Primitive (#9)"
```

---

### Task 3: Emit per-vertex colors from `build_bark_primitive`

Thread `stops` through the bark tube builder; each ring's diameter (`2 × radius`) drives `bark_tint`, broadcast across the ring's columns. Root cap uses the base node's diameter.

**Files:**
- Modify: `src/palubicki/geom/tubes.py` (`build_bark_primitive`, `_emit_chain_tube`, `_emit_root_cap`)
- Test: `tests/geom/test_tubes.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/geom/test_tubes.py
from palubicki.geom.bark_blend import BarkBlendStops


def _stops():
    return BarkBlendStops(
        d_young=0.02, d_mature=0.10, d_senescent=0.30,
        c_young=(0.9, 0.9, 0.9),       # near-white young
        c_mature=(0.5, 0.4, 0.3),
        c_senescent=(0.1, 0.1, 0.1),   # near-black senescent
    )


def test_no_colors_without_stops():
    tree = _vertical_chain(n=4)
    prim = build_bark_primitive(tree, ring_sides=8, material=_mat())
    assert prim.colors is None


def test_colors_present_with_stops():
    tree = _vertical_chain(n=4, r=0.05)  # diameter 0.10 == d_mature
    prim = build_bark_primitive(tree, ring_sides=8, material=_mat(), stops=_stops())
    assert prim.colors is not None
    assert prim.colors.shape == (prim.positions.shape[0], 3)
    assert prim.colors.dtype == np.float32
    assert np.isfinite(prim.colors).all()


def test_thin_ring_is_young_thick_ring_is_senescent():
    # Two separate trees: thin (twig) vs thick (trunk base).
    thin = _vertical_chain(n=3, r=0.005)   # diameter 0.01 < d_young -> young
    thick = _vertical_chain(n=3, r=0.20)   # diameter 0.40 > d_senescent -> senescent
    c_thin = build_bark_primitive(thin, ring_sides=8, material=_mat(), stops=_stops()).colors
    c_thick = build_bark_primitive(thick, ring_sides=8, material=_mat(), stops=_stops()).colors
    # young is brighter than senescent on every channel
    assert c_thin.mean() > 0.8
    assert c_thick.mean() < 0.2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/geom/test_tubes.py -k "colors or young" -v`
Expected: FAIL — `build_bark_primitive() got an unexpected keyword argument 'stops'`

- [ ] **Step 3: Write minimal implementation**

In `src/palubicki/geom/tubes.py`:

(a) Add the import near the top (after the existing `from palubicki.geom.mesh import ...`):

```python
from palubicki.geom.bark_blend import BarkBlendStops, bark_tint
```

(b) Add `stops` to `build_bark_primitive`'s signature (after `seed`):

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
    stops: BarkBlendStops | None = None,
) -> Primitive:
```

(c) Collect a `col_parts` list alongside the existing parts, and pass `stops` into the emitters. Replace the body from `pos_parts: list...` through the `return Primitive(...)` with:

```python
    pos_parts: list[np.ndarray] = []
    nor_parts: list[np.ndarray] = []
    uv_parts: list[np.ndarray] = []
    col_parts: list[np.ndarray] = []
    idx_parts: list[np.ndarray] = []
    vertex_offset = 0

    for i, chain in enumerate(chains):
        chain_flare = flare if i == 0 else None  # trunk chain only
        p, n, u, c, idx = _emit_chain_tube(chain, ring_sides, vertex_offset, chain_flare, stops)
        if p.shape[0]:
            pos_parts.append(p)
            nor_parts.append(n)
            uv_parts.append(u)
            idx_parts.append(idx)
            if c is not None:
                col_parts.append(c)
            vertex_offset += p.shape[0]

    # Cap root: only the main trunk's first ring
    if chains:
        p, n, u, c, idx = _emit_root_cap(chains[0], ring_sides, vertex_offset, stops)
        if p.shape[0]:
            pos_parts.append(p)
            nor_parts.append(n)
            uv_parts.append(u)
            idx_parts.append(idx)
            if c is not None:
                col_parts.append(c)
            vertex_offset += p.shape[0]

    pos_arr = (np.concatenate(pos_parts, axis=0).astype(np.float32, copy=False)
               if pos_parts else np.zeros((0, 3), dtype=np.float32))
    nor_arr = (np.concatenate(nor_parts, axis=0).astype(np.float32, copy=False)
               if nor_parts else np.zeros((0, 3), dtype=np.float32))
    uv_arr = (np.concatenate(uv_parts, axis=0)
              if uv_parts else np.zeros((0, 2), dtype=np.float32))
    idx_arr = (np.concatenate(idx_parts, axis=0).astype(np.uint32, copy=False)
               if idx_parts else np.zeros((0,), dtype=np.uint32))
    col_arr = (np.concatenate(col_parts, axis=0).astype(np.float32, copy=False)
               if (stops is not None and col_parts) else None)

    return Primitive(positions=pos_arr, normals=nor_arr, uvs=uv_arr, indices=idx_arr,
                     material=material, colors=col_arr)
```

(d) Update `_emit_chain_tube`'s signature and return. Change the signature to:

```python
def _emit_chain_tube(
    chain: _ChainBuild,
    ring_sides: int,
    vertex_offset: int,
    flare: _FlareSpec | None = None,
    stops: BarkBlendStops | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray | None, np.ndarray]:
```

In its early-return (when `n_nodes < 2`), return five values:

```python
    if n_nodes < 2:
        return (
            np.zeros((0, 3), dtype=np.float64),
            np.zeros((0, 3), dtype=np.float64),
            np.zeros((0, 2), dtype=np.float32),
            None,
            np.zeros((0,), dtype=np.int64),
        )
```

Just before the final `return positions_flat, normals_flat, uvs_flat, indices`, build colors and update the return:

```python
    colors_flat = None
    if stops is not None:
        # Per-node diameter = 2 * radius; broadcast each node's tint across the ring.
        diameters = 2.0 * radii_arr                                  # (N,)
        node_rgb = bark_tint(diameters, stops)                       # (N, 3) float32
        colors = np.broadcast_to(node_rgb[:, None, :], (n_nodes, columns, 3))
        colors_flat = colors.reshape(n_nodes * columns, 3).astype(np.float32, copy=True)

    return positions_flat, normals_flat, uvs_flat, colors_flat, indices
```

(e) Update `_emit_root_cap`'s signature and return. Change signature to:

```python
def _emit_root_cap(
    chain: _ChainBuild,
    ring_sides: int,
    vertex_offset: int,
    stops: BarkBlendStops | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray | None, np.ndarray]:
```

After `uvs = np.array(...)` and before the `if len(chain.nodes) < 2:` block, compute the cap color:

```python
    cap_color = None
    if stops is not None:
        base_diameter = 2.0 * chain.radii[0]
        cap_color = bark_tint(np.array([base_diameter]), stops).astype(np.float32)  # (1, 3)
```

Update both return statements in `_emit_root_cap` to include `cap_color` as the 4th element:

```python
    if len(chain.nodes) < 2:
        return positions, normals, uvs, cap_color, np.zeros((0,), dtype=np.int64)
```

and at the end:

```python
    return positions, normals, uvs, cap_color, indices
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/geom/test_tubes.py -v`
Expected: PASS (all existing tube tests + the 3 new ones). The existing tests call `build_bark_primitive` without `stops`, so they still pass.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/geom/tubes.py tests/geom/test_tubes.py
git commit -m "geom(tubes): bake per-vertex bark tint from diameter (#9)"
```

---

### Task 4: Add bark-blend fields to `GeomConfig`

Presence-gated config: `bark_tint_young is None` ⇒ blend off (default).

**Files:**
- Modify: `src/palubicki/config.py:215-264` (`GeomConfig`)
- Test: `tests/test_config.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_config.py
from palubicki.config import GeomConfig


def test_geomconfig_blend_off_by_default():
    g = GeomConfig()
    assert g.bark_tint_young is None
    assert g.bark_tint_mature is None
    assert g.bark_tint_senescent is None
    # default stops present and ordered
    assert g.bark_blend_diameter_young <= g.bark_blend_diameter_mature <= g.bark_blend_diameter_senescent


def test_geomconfig_accepts_tints():
    g = GeomConfig(
        bark_tint_young=(0.45, 0.38, 0.30),
        bark_tint_mature=(0.35, 0.22, 0.12),
        bark_tint_senescent=(0.22, 0.20, 0.16),
    )
    assert g.bark_tint_young == (0.45, 0.38, 0.30)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -k blend -v`
Expected: FAIL — `AttributeError: 'GeomConfig' object has no attribute 'bark_tint_young'`

- [ ] **Step 3: Write minimal implementation**

In `src/palubicki/config.py`, inside the `GeomConfig` dataclass, add after `bark_texture: Path | None = None` (line 222):

```python
    # Issue #9: three-way bark tint blended by Internode.diameter.
    # Presence-gated: bark_tint_young is None => blend off, identical to today.
    bark_tint_young: tuple[float, float, float] | None = None
    bark_tint_mature: tuple[float, float, float] | None = None      # None => falls back to bark_color
    bark_tint_senescent: tuple[float, float, float] | None = None   # None => two-way (young->mature)
    bark_blend_diameter_young: float = field(
        default=0.02, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.005}}
    )
    bark_blend_diameter_mature: float = field(
        default=0.10, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.005}}
    )
    bark_blend_diameter_senescent: float = field(
        default=0.30, metadata={"ui": {"min": 0.0, "max": 2.0, "step": 0.005}}
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -k blend -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "config(geom): bark tint + blend-diameter fields (#9)"
```

---

### Task 5: Assemble stops in `builder.py` and pass to bark primitive

Build a `BarkBlendStops | None` from config (gated on `bark_tint_young`), with `bark_tint_mature` falling back to `bark_color` and `bark_tint_senescent` falling back to `bark_tint_mature` (two-way).

**Files:**
- Modify: `src/palubicki/geom/builder.py:13-36`
- Test: `tests/geom/test_builder.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/geom/test_builder.py — mirror the helper style already in this file.
# This test builds a minimal Config with blend on and asserts colors are produced.
import numpy as np

from palubicki.config import (
    Config, EnvelopeConfig, GeomConfig, PhyllotaxyConfig,
    SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.geom.builder import build_mesh
from palubicki.sim.simulator import simulate


def _cfg_blend(tmp_path, *, young):
    return Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.5, ry=1.0, rz=0.5, marker_count=200),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_iterations=4),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(
            bark_tint_young=young,
            bark_tint_mature=(0.35, 0.22, 0.12),
            bark_tint_senescent=(0.22, 0.20, 0.16),
        ),
        seed=1,
        output=tmp_path / "x.glb",
    )


def test_blend_off_no_colors(tmp_path):
    cfg = _cfg_blend(tmp_path, young=None)
    mesh = build_mesh(simulate(cfg), cfg)
    assert mesh.primitives[0].colors is None


def test_blend_on_emits_colors(tmp_path):
    cfg = _cfg_blend(tmp_path, young=(0.45, 0.38, 0.30))
    mesh = build_mesh(simulate(cfg), cfg)
    bark = mesh.primitives[0]
    assert bark.colors is not None
    assert bark.colors.shape == (bark.positions.shape[0], 3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/geom/test_builder.py -k blend -v`
Expected: FAIL — `assert mesh.primitives[0].colors is not None` (build_mesh doesn't pass stops yet, so colors is None).

- [ ] **Step 3: Write minimal implementation**

In `src/palubicki/geom/builder.py`:

(a) Add imports at top:

```python
from palubicki.geom.bark_blend import BarkBlendStops
```

(b) Add a helper near `_resolve_texture`:

```python
def _bark_blend_stops(geom) -> BarkBlendStops | None:
    """Assemble blend stops from GeomConfig; None when blend is disabled.

    Gated on bark_tint_young. Mature falls back to bark_color; senescent falls
    back to mature (two-way blend)."""
    if geom.bark_tint_young is None:
        return None
    mature = geom.bark_tint_mature if geom.bark_tint_mature is not None else geom.bark_color
    senescent = geom.bark_tint_senescent if geom.bark_tint_senescent is not None else mature
    return BarkBlendStops(
        d_young=geom.bark_blend_diameter_young,
        d_mature=geom.bark_blend_diameter_mature,
        d_senescent=geom.bark_blend_diameter_senescent,
        c_young=tuple(geom.bark_tint_young),
        c_mature=tuple(mature),
        c_senescent=tuple(senescent),
    )
```

(c) In `build_mesh`, compute stops and pass to `build_bark_primitive`:

```python
    stops = _bark_blend_stops(cfg.geom)
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
        stops=stops,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/geom/test_builder.py -k blend -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/geom/builder.py tests/geom/test_builder.py
git commit -m "geom(builder): wire bark blend stops into primitive (#9)"
```

---

### Task 6: Emit `COLOR_0` in glTF and set `baseColorFactor=white` when tinted

When a primitive carries `colors`, emit a `COLOR_0` accessor and neutralize the material's `baseColorFactor` so `COLOR_0 × texture` is the final albedo. When absent, output is unchanged.

**Files:**
- Modify: `src/palubicki/export/gltf.py` (`write_glb_to_bytes`, `write_glb_forest._emit_mesh`, `_add_material`)
- Test: `tests/export/test_gltf.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/export/test_gltf.py
def _tinted_cube():
    prim = _cube_primitive()
    prim.colors = np.tile(np.array([0.2, 0.3, 0.4], dtype=np.float32), (8, 1))
    return prim


def test_color0_emitted_and_basecolor_neutralized(tmp_path):
    mesh = Mesh(primitives=[_tinted_cube()])
    out = tmp_path / "tinted.glb"
    write_glb(mesh, out, asset_meta={"seed": 1})
    loaded = pygltflib.GLTF2().load(str(out))
    prim = loaded.meshes[0].primitives[0]
    assert prim.attributes.COLOR_0 is not None
    mat = loaded.materials[prim.material]
    assert list(mat.pbrMetallicRoughness.baseColorFactor) == [1.0, 1.0, 1.0, 1.0]


def test_no_color0_when_untinted(tmp_path):
    mesh = Mesh(primitives=[_cube_primitive()])
    out = tmp_path / "plain.glb"
    write_glb(mesh, out, asset_meta={"seed": 1})
    loaded = pygltflib.GLTF2().load(str(out))
    prim = loaded.meshes[0].primitives[0]
    assert prim.attributes.COLOR_0 is None
    mat = loaded.materials[prim.material]
    # base_color preserved (0.5, 0.3, 0.1, 1.0) from _cube_primitive's material
    np.testing.assert_allclose(mat.pbrMetallicRoughness.baseColorFactor, [0.5, 0.3, 0.1, 1.0], atol=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/export/test_gltf.py -k color0 -v`
Expected: FAIL — `assert prim.attributes.COLOR_0 is not None` (None today).

- [ ] **Step 3: Write minimal implementation**

In `src/palubicki/export/gltf.py`:

(a) Add the glTF type constant near the others (after `_TYPE_SCALAR`):

```python
_TYPE_VEC4 = pygltflib.VEC4
```

(b) Change `_add_material` to accept a `neutralize_base_color` flag:

```python
def _add_material(
    mat: Material,
    buffer_data: bytearray,
    buffer_views: list,
    materials: list,
    textures: list,
    images: list,
    samplers: list,
    *,
    neutralize_base_color: bool = False,
) -> int:
    base_color = (1.0, 1.0, 1.0, 1.0) if neutralize_base_color else list(mat.base_color)
    pbr = pygltflib.PbrMetallicRoughness(
        baseColorFactor=list(base_color),
        metallicFactor=mat.metallic,
        roughnessFactor=mat.roughness,
    )
    if mat.base_color_texture_png is not None:
        tex_idx = _add_texture(mat.base_color_texture_png, buffer_data, buffer_views,
                               textures, images, samplers)
        pbr.baseColorTexture = pygltflib.TextureInfo(index=tex_idx)
    gltf_mat = pygltflib.Material(
        name=mat.name,
        pbrMetallicRoughness=pbr,
        alphaMode=mat.alpha_mode,
        alphaCutoff=mat.alpha_cutoff if mat.alpha_mode == "MASK" else None,
        doubleSided=mat.double_sided,
    )
    materials.append(gltf_mat)
    return len(materials) - 1
```

(c) In `write_glb_to_bytes`, inside the `for prim in mesh.primitives:` loop, after the `uv_acc = ...` line and before `idx_acc = ...`, add the COLOR_0 accessor; then pass the flag and attribute:

```python
        col_acc = None
        if prim.colors is not None and prim.colors.shape[0] == prim.positions.shape[0]:
            col_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.colors,
                                    _COMPONENT_FLOAT, _TYPE_VEC3, _TARGET_ARRAY, with_minmax=False)
        idx_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.indices, _COMPONENT_UINT,
                                _TYPE_SCALAR, _TARGET_ELEMENT_ARRAY, with_minmax=False)

        mat_idx = _add_material(prim.material, buffer_data, buffer_views, materials,
                                textures, images, samplers,
                                neutralize_base_color=col_acc is not None)

        gltf_primitives.append(pygltflib.Primitive(
            attributes=pygltflib.Attributes(
                POSITION=pos_acc, NORMAL=nor_acc, TEXCOORD_0=uv_acc, COLOR_0=col_acc,
            ),
            indices=idx_acc,
            material=mat_idx,
        ))
```

(Remove the old `idx_acc`, `mat_idx`, and `gltf_primitives.append(...)` lines that this replaces.)

(d) Apply the same change inside `write_glb_forest._emit_mesh`. After its `uv_acc = ...` line:

```python
            col_acc = None
            if prim.colors is not None and prim.colors.shape[0] == prim.positions.shape[0]:
                col_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.colors,
                                        _COMPONENT_FLOAT, _TYPE_VEC3, _TARGET_ARRAY, with_minmax=False)
            idx_acc = _add_accessor(buffer_data, buffer_views, accessors, prim.indices,
                                    _COMPONENT_UINT, _TYPE_SCALAR, _TARGET_ELEMENT_ARRAY, with_minmax=False)
            mat_idx = _add_material(prim.material, buffer_data, buffer_views,
                                    materials, textures, images, samplers,
                                    neutralize_base_color=col_acc is not None)
            gltf_prims.append(pygltflib.Primitive(
                attributes=pygltflib.Attributes(POSITION=pos_acc, NORMAL=nor_acc,
                                                TEXCOORD_0=uv_acc, COLOR_0=col_acc),
                indices=idx_acc,
                material=mat_idx,
            ))
```

(Replace the existing `idx_acc`/`mat_idx`/`gltf_prims.append(...)` lines.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/export/test_gltf.py -v`
Expected: PASS (existing gltf tests + 2 new). `_TYPE_VEC4` is added for completeness but COLOR_0 uses VEC3.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/export/gltf.py tests/export/test_gltf.py
git commit -m "export(gltf): emit COLOR_0 + neutral baseColor when bark tinted (#9)"
```

---

### Task 7: Internal renderer honors per-vertex colors

`_flatten` uses the mean of each triangle's vertex colors as the face color when `Primitive.colors` is set; otherwise unchanged.

**Files:**
- Modify: `src/palubicki/render/renderer.py:19-48` (`_flatten`)
- Test: `tests/render/test_renderer.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/render/test_renderer.py
import numpy as np

from palubicki.geom.mesh import Material, Mesh, Primitive
from palubicki.render.renderer import _flatten


def _mat(base):
    return Material(name="bark", base_color=base, metallic=0.0, roughness=1.0,
                    base_color_texture_png=None, alpha_mode="OPAQUE",
                    alpha_cutoff=0.5, double_sided=False)


def _one_tri(colors=None):
    return Primitive(
        positions=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], np.float32),
        normals=np.tile([0, 0, 1], (3, 1)).astype(np.float32),
        uvs=np.zeros((3, 2), np.float32),
        indices=np.array([0, 1, 2], np.uint32),
        material=_mat((0.9, 0.1, 0.1, 1.0)),
        colors=colors,
    )


def test_flatten_uses_base_color_without_vertex_colors():
    _, _, cols = _flatten(Mesh(primitives=[_one_tri()]))
    np.testing.assert_allclose(cols[0], [0.9, 0.1, 0.1], atol=1e-6)


def test_flatten_uses_mean_vertex_color():
    vc = np.array([[0.0, 0.0, 0.0], [0.6, 0.6, 0.6], [0.6, 0.6, 0.6]], np.float32)
    _, _, cols = _flatten(Mesh(primitives=[_one_tri(colors=vc)]))
    np.testing.assert_allclose(cols[0], [0.4, 0.4, 0.4], atol=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/render/test_renderer.py -k flatten -v`
Expected: FAIL — `test_flatten_uses_mean_vertex_color` gets `[0.9, 0.1, 0.1]` (base color) not `[0.4, 0.4, 0.4]`.

- [ ] **Step 3: Write minimal implementation**

In `src/palubicki/render/renderer.py`, in `_flatten`, replace the face-color block inside the `for p in mesh.primitives:` loop:

```python
        # Face color: mean of triangle's vertex colors when present, else primitive base_color.
        if p.colors is not None and p.colors.shape[0] == p.positions.shape[0]:
            face_rgb = p.colors[idx].astype(np.float32, copy=False).mean(axis=1)
            cols.append(face_rgb)
        else:
            rgb = np.asarray(p.material.base_color[:3], dtype=np.float32)
            cols.append(np.broadcast_to(rgb, (idx.shape[0], 3)).copy())
```

(This replaces the existing two lines that compute `rgb` and append the broadcast.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/render/test_renderer.py -k flatten -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/render/renderer.py tests/render/test_renderer.py
git commit -m "render: per-face color from per-vertex bark tint (#9)"
```

---

### Task 8: `_glb_to_mesh` reads `COLOR_0` into `Primitive.colors`

Without this, a GLB round-trip render (`palubicki render tree.glb`) of a tinted tree shows **white bark**, because blend-on sets `baseColorFactor=white` and `_glb_to_mesh` only reads that factor.

**Files:**
- Modify: `src/palubicki/render/io.py:_glb_to_mesh` (the `primitives.append(Primitive(...))` block, ~line 118)
- Test: `tests/render/test_io.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/render/test_io.py
import numpy as np

from palubicki.export.gltf import write_glb
from palubicki.geom.mesh import Material, Mesh, Primitive
from palubicki.render.io import _glb_to_mesh


def _tinted_tri_mesh():
    mat = Material(name="bark", base_color=(0.3, 0.2, 0.1, 1.0), metallic=0.0, roughness=1.0,
                   base_color_texture_png=None, alpha_mode="OPAQUE", alpha_cutoff=0.5,
                   double_sided=False)
    prim = Primitive(
        positions=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], np.float32),
        normals=np.tile([0, 0, 1], (4, 1)).astype(np.float32),
        uvs=np.zeros((4, 2), np.float32),
        indices=np.array([0, 1, 2, 1, 3, 2], np.uint32),
        material=mat,
        colors=np.array([[0.8, 0.7, 0.6]] * 4, np.float32),
    )
    return Mesh(primitives=[prim])


def test_glb_roundtrip_preserves_vertex_colors(tmp_path):
    out = tmp_path / "tinted.glb"
    write_glb(_tinted_tri_mesh(), out, asset_meta={"seed": 1})
    mesh = _glb_to_mesh(out)
    cols = mesh.primitives[0].colors
    assert cols is not None
    # tint recovered (allow trimesh's 8-bit color quantization)
    np.testing.assert_allclose(cols.mean(axis=0), [0.8, 0.7, 0.6], atol=0.02)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/render/test_io.py -k roundtrip_preserves -v`
Expected: FAIL — `assert cols is not None` (always None today).

- [ ] **Step 3: Write minimal implementation**

In `src/palubicki/render/io.py`, inside `_glb_to_mesh`, just before the `material = Material(...)` construction, extract vertex colors from the trimesh visual:

```python
        # Per-vertex colors (glTF COLOR_0). trimesh exposes them on ColorVisuals
        # as uint8 RGBA in geom.visual.vertex_colors. None when absent.
        vertex_colors = None
        vc = getattr(visual, "vertex_colors", None) if visual is not None else None
        if vc is not None and len(vc) == verts.shape[0]:
            vc_arr = np.asarray(vc, dtype=np.float32)
            if vc_arr.ndim == 2 and vc_arr.shape[1] >= 3:
                rgb = vc_arr[:, :3]
                if rgb.max() > 1.5:   # uint8 0..255 -> 0..1
                    rgb = rgb / 255.0
                vertex_colors = rgb.astype(np.float32)
```

Then add `colors=vertex_colors` to the `Primitive(...)` constructor:

```python
        primitives.append(Primitive(
            positions=verts_w,
            normals=norms.astype(np.float32),
            uvs=np.zeros((verts_w.shape[0], 2), dtype=np.float32),
            indices=faces,
            material=material,
            colors=vertex_colors,
        ))
```

> Note: trimesh assigns a default opaque-white `vertex_colors` to some geometries even when the source GLB has no `COLOR_0`. That is harmless here — white vertex colors render identically to the white `baseColorFactor` they'd replace, and untinted exports never set `baseColorFactor=white` unless they also carry real `COLOR_0`. The test asserts the *tinted* path round-trips; no separate "untinted stays correct" assertion is needed because untinted bark keeps its real `base_color` in the material.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/render/test_io.py -v`
Expected: PASS (existing io tests + the new one)

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/render/io.py tests/render/test_io.py
git commit -m "render(io): carry COLOR_0 vertex colors through glb roundtrip (#9)"
```

---

### Task 9: Per-species bark tints + stops (on by default)

Enable the blend in all five species YAMLs. Mature tint = each species' current `bark_color` so the mid-trunk look is preserved.

**Files:**
- Modify: `src/palubicki/configs/species/oak.yaml`, `pine.yaml`, `birch.yaml`, `maple.yaml`, `fir.yaml` (the `geom:` block)
- Test: `tests/test_config_species.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_config_species.py — follow the file's existing species-load pattern.
import pytest

from palubicki.config import load_config
from palubicki.geom.builder import _bark_blend_stops


@pytest.mark.parametrize("species", ["oak", "pine", "birch", "maple", "fir"])
def test_species_enables_bark_blend(species, tmp_path):
    cfg = load_config(species=species, config_path=None, cli_overrides={}, output=tmp_path / "x.glb")
    stops = _bark_blend_stops(cfg.geom)
    assert stops is not None, f"{species} should enable bark blend"
    assert stops.d_young <= stops.d_mature <= stops.d_senescent
```

> Before writing, open `tests/test_config_species.py` and match its existing `load_config(...)` call signature exactly (argument names/order may differ from the sketch above). Use whatever helper the file already uses to load a species.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config_species.py -k bark_blend -v`
Expected: FAIL — `stops is not None` fails for every species (YAMLs don't set tints yet).

- [ ] **Step 3: Add the tint blocks to each species YAML**

In each file's `geom:` block, add the six keys. Use `bark_tint_mature` equal to that file's existing `bark_color`. Values below are starting points — finalize against rendered output in Task 11.

`oak.yaml` (bark_color `[0.32, 0.22, 0.14]`):
```yaml
  bark_tint_young: [0.46, 0.40, 0.32]
  bark_tint_mature: [0.32, 0.22, 0.14]
  bark_tint_senescent: [0.22, 0.20, 0.16]
  bark_blend_diameter_young: 0.02
  bark_blend_diameter_mature: 0.10
  bark_blend_diameter_senescent: 0.30
```

`pine.yaml` (use that file's `bark_color` for mature):
```yaml
  bark_tint_young: [0.62, 0.45, 0.32]
  bark_tint_mature: <pine bark_color>
  bark_tint_senescent: [0.34, 0.30, 0.27]
  bark_blend_diameter_young: 0.02
  bark_blend_diameter_mature: 0.10
  bark_blend_diameter_senescent: 0.30
```

`birch.yaml` (paper-white young → dark fissured senescent; use file's `bark_color` for mature):
```yaml
  bark_tint_young: [0.90, 0.89, 0.85]
  bark_tint_mature: <birch bark_color>
  bark_tint_senescent: [0.28, 0.26, 0.24]
  bark_blend_diameter_young: 0.02
  bark_blend_diameter_mature: 0.10
  bark_blend_diameter_senescent: 0.30
```

`maple.yaml` (use file's `bark_color` for mature):
```yaml
  bark_tint_young: [0.55, 0.52, 0.46]
  bark_tint_mature: <maple bark_color>
  bark_tint_senescent: [0.26, 0.24, 0.22]
  bark_blend_diameter_young: 0.02
  bark_blend_diameter_mature: 0.10
  bark_blend_diameter_senescent: 0.30
```

`fir.yaml` (use file's `bark_color` for mature):
```yaml
  bark_tint_young: [0.58, 0.55, 0.50]
  bark_tint_mature: <fir bark_color>
  bark_tint_senescent: [0.30, 0.28, 0.26]
  bark_blend_diameter_young: 0.02
  bark_blend_diameter_mature: 0.10
  bark_blend_diameter_senescent: 0.30
```

For each file, read its current `bark_color` value and paste it literally where `<species bark_color>` appears.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config_species.py -k bark_blend -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/configs/species/ tests/test_config_species.py
git commit -m "configs(species): per-species bark tint defaults, blend on (#9)"
```

---

### Task 10: Extend golden hashes to include `COLOR_0`; regenerate species goldens

The buffer-hash goldens currently ignore `COLOR_0`, so they can't catch tint drift. Add `COLOR_0` to the hash (no-op for the blend-off `ellipsoid` golden → it stays valid; the five species goldens now change and must be regenerated after visual review).

**Files:**
- Modify: `tests/golden/test_goldens.py:_hash_buffers` and `tests/golden/test_species_goldens.py:_hash_buffers`
- Modify (regenerated): `tests/golden/data/species_*.sha256`

- [ ] **Step 1: Add `COLOR_0` to both `_hash_buffers`**

In **both** files, change the accessor tuple to include `COLOR_0`:

`tests/golden/test_species_goldens.py`:
```python
            for acc_idx in (prim.attributes.POSITION, prim.attributes.NORMAL,
                            prim.attributes.TEXCOORD_0, prim.attributes.COLOR_0,
                            prim.indices):
                if acc_idx is None:
                    continue
```

`tests/golden/test_goldens.py` (this one has no `if acc_idx is None` guard — add it):
```python
    for prim in loaded.meshes[0].primitives:
        for acc_idx in (prim.attributes.POSITION, prim.attributes.NORMAL,
                        prim.attributes.TEXCOORD_0, prim.attributes.COLOR_0,
                        prim.indices):
            if acc_idx is None:
                continue
            acc = loaded.accessors[acc_idx]
            bv = loaded.bufferViews[acc.bufferView]
            blob = loaded.binary_blob()[bv.byteOffset : bv.byteOffset + bv.byteLength]
            sha.update(blob)
```

- [ ] **Step 2: Verify the blend-off ellipsoid golden still passes**

Run: `.venv/bin/pytest tests/golden/test_goldens.py -m slow -v`
Expected: PASS — `test_golden_ellipsoid` uses `GeomConfig()` (blend off ⇒ no `COLOR_0`), so the hash is unchanged.

- [ ] **Step 3: Confirm the species goldens now fail (tint changed the buffers)**

Run: `.venv/bin/pytest tests/golden/test_species_goldens.py -m slow -v`
Expected: FAIL for all five species (`golden mismatch`) — the new `COLOR_0` data changes the hash. This is the intended trigger for a deliberate, reviewed regen.

- [ ] **Step 4: Regenerate the species goldens**

Run: `.venv/bin/pytest tests/golden/test_species_goldens.py -m slow --update-goldens`
Expected: 5 skipped ("golden written…").

Then re-verify:
Run: `.venv/bin/pytest tests/golden/test_species_goldens.py -m slow -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add tests/golden/test_goldens.py tests/golden/test_species_goldens.py tests/golden/data/
git commit -m "test(golden): hash COLOR_0; regenerate species goldens for bark blend (#9)"
```

---

### Task 11: Visual verification + full suite + spec acceptance

End-to-end check: render each species and confirm twigs are paler than the trunk base, then run the whole suite.

**Files:** none (verification only); may re-tune Task 9 RGB values if a species looks wrong.

- [ ] **Step 1: Generate + render each species and eyeball the gradient**

Run (oak shown; repeat for pine/birch/maple/fir):
```bash
.venv/bin/palubicki generate --species oak --seed 42 --iterations 12 -o /tmp/oak.glb
.venv/bin/palubicki render /tmp/oak.glb -o /tmp/oak.png --size 800x800
```
Expected: `/tmp/oak.png` shows pale bark on thin twigs grading to dark bark at the thick trunk base. (If a render subcommand/flag differs, run `.venv/bin/palubicki --help` and `.venv/bin/palubicki render --help` to confirm the exact invocation.)

If any species looks washed-out or wrong, adjust its RGB triples in Task 9's YAML, re-commit that file, and re-run Task 10 Step 4 to regenerate that species' golden.

- [ ] **Step 2: Verify acceptance criterion — blend off is byte-identical**

Run:
```bash
.venv/bin/pytest tests/geom/test_builder.py::test_blend_off_no_colors tests/export/test_gltf.py -k "no_color0 or roundtrip" -v
```
Expected: PASS — untinted path emits no `COLOR_0` and preserves the original `baseColorFactor`.

- [ ] **Step 3: Run the full test suite (including slow)**

Run: `.venv/bin/pytest -q` then `.venv/bin/pytest -m slow -q`
Expected: all green. (Ruff, if wired into CI: `.venv/bin/ruff check src tests` — fix any lint.)

- [ ] **Step 4: Commit any re-tuning**

```bash
git add -A
git commit -m "configs(species): final bark tint tuning after visual review (#9)"
```
(Skip if no changes were needed.)

- [ ] **Step 5: Mark the PR ready**

The draft PR (#22) body is `Closes #9`. Flesh out the PR description with a short summary and a before/after note, then:
```bash
gh pr ready 22 -R julien-riel/palubicki
```
(Do this only when the user confirms they're ready to mark it for review.)

---

## Self-Review

**Spec coverage:**
- §1 `bark_tint` helper → Task 1 ✓
- §2 `Primitive.colors` + tubes emit colors → Tasks 2, 3 ✓
- §3 internal renderer honors colors → Task 7 ✓
- §4 glTF `COLOR_0` + `baseColorFactor=white` → Task 6 ✓
- §5 `GeomConfig` fields + gating/fallbacks → Tasks 4, 5 ✓
- §6 per-species defaults, on by default → Task 9 ✓
- §7 unit tests, golden regen, smoke → Tasks 1,3,6,7,8,10,11 ✓
- Spec's `render/io.py` white-bark regression (discovered during planning) → Task 8 ✓ (extends spec; noted in PR)
- Acceptance: blend-off byte-identical → Task 11 Step 2; diameter-only driver → inherent (no sim touched); smoke for all species → Task 11 Step 3 ✓

**Placeholder scan:** No TBD/TODO. Species RGB triples in Task 9 are concrete starting values with an explicit "finalize in Task 11" tuning loop — not placeholders. `<species bark_color>` markers in Task 9 are explicit "paste the file's literal value" instructions, resolved by reading each YAML.

**Type consistency:** `BarkBlendStops` fields and `bark_tint(diameter, stops)->(N,3) float32` are used identically in Tasks 1, 3, 5. `Primitive.colors: np.ndarray | None` consistent across Tasks 2, 3, 6, 7, 8. `_emit_chain_tube`/`_emit_root_cap` return a 5-tuple consistently in Task 3. `_add_material(..., neutralize_base_color=)` and `_bark_blend_stops(geom)` names match between definition and use.

**Scope:** Single render-time feature, no sim changes, one PR. Focused.
