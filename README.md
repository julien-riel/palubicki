# palubicki

Self-organizing 3D tree generator based on Palubicki, Horel, Longay, Runions, Lane, Měch, Prusinkiewicz — *Self-organizing tree models for image synthesis*, SIGGRAPH 2009.

V1 implements the BHse model: marker points distributed in a parametric envelope drive bud competition for space; Borchert-Honda allocation routes resources from the root to the buds; tropisms (gravity, photo direction, inertia) bias growth; low-quality branches are shed. Output is a `.glb` (glTF 2.0 binary) usable in any standard viewer.

## Install

```bash
pip install -e ".[dev]"
```

## Usage

```bash
# Bushy ellipsoid tree (oak-like)
palubicki generate -o oak.glb \
  --envelope half_ellipsoid --envelope-radii 4 6 4 \
  --seed 42

# Conifer
palubicki generate -o pine.glb \
  --envelope cone --envelope-radii 2 8 2 \
  --w-gravity 0.5

# Dump all defaults to start a config file
palubicki dump-defaults > my-config.yaml
palubicki generate -o tree.glb --config my-config.yaml

# Recover the config used to generate an existing .glb
palubicki dump-config tree.glb > used.yaml
```

### Preview — render a `.glb` to PNG

For quick visual iteration without an external glTF viewer:

```bash
# Install the optional render extra (matplotlib)
pip install -e ".[render]"

# Default: 800x800 white background
palubicki preview tree.glb -o tree.png

# Custom view angle and size
palubicki preview tree.glb -o tree.png --size 1200x900 --elevation 15 --azimuth 60

# Transparent background, no leaves (silhouette of bark only)
palubicki preview forest.glb -o forest.png --bg transparent --no-leaves
```

The renderer is **diagnostic level**: silhouette + flat Lambert shading + base
material colors. No textures, no shadows, no anti-aliasing tricks. It exists
so that iterating on configs and species presets doesn't require opening every
`.glb` in an external viewer.

In notebooks, use the underlying API directly:

```python
from palubicki.render import render_glb
import matplotlib.pyplot as plt
plt.imshow(render_glb("oak.glb"))
```

### Editor — tune parameters live in a browser

```bash
pip install -e ".[edit]"
palubicki edit --species oak --seed 42
```

Opens `http://127.0.0.1:8765/` with sliders for the most-tweaked parameters
on the left, a three.js viewer on the right, and a **Régénérer** button to
re-run the simulation with the current values. Use **Export .glb** to save
the current tree and **Export YAML** to dump the current config (re-usable
with `palubicki generate --config`).

### V2 — voxel light shadowing (BHls hybrid)

Enable with `--light-enabled`. The bud's quality becomes
`Q = nb_markers × light_factor`, where `light_factor ∈ [0,1]` is the fraction
of hemispheric rays reaching the bud through accumulated leaf/branch density
(Beer-Lambert). Light also drives local phototropism (the growth direction
biases toward the brightest opening) and shedding (branches in deep shadow
die).

When activating light, the default `tropism.w_phototropism = 0.0` ignores the
gradient — configure it via the YAML config (`tropism.w_phototropism: 0.3`).

Example:

```bash
palubicki generate -o oak_light.glb \
  --envelope ellipsoid --envelope-radii 3 5 3 \
  --light-enabled --seed 42
```

### V3 — obstacles + forêt multi-arbres

Subcommand `palubicki forest -o scene.glb --config scene.yaml`. The YAML adds a
top-level `forest:` section with multiple seeds (each with its own position,
optional `seed`, `species`, and dotted-key `overrides`) and a list of
obstacles (AABB, Sphere, OBB, Mesh OBJ). Trees compete on a shared marker
cloud and a shared light grid; obstacles kill markers, block growth segments,
and occlude light.

### V4 — species presets

Three packaged presets: `oak`, `pine`, `birch`. Each is a YAML in
`src/palubicki/configs/species/` selected with the `--species` flag.

```bash
palubicki generate --species oak --seed 42 -o oak.glb
palubicki generate --species pine --seed 42 -o pine.glb
palubicki generate --species birch --seed 42 -o birch.glb

# Override a preset value (CLI wins over YAML wins over preset)
palubicki generate --species oak --w-gravity 0.5 -o oak_droopy.glb

# Dump a preset to a file as starting point for a custom species
palubicki dump-defaults --species pine > my_pine.yaml
```

Forêts mixtes : ajouter `species: oak` (ou `pine`/`birch`) à chaque entrée
`forest.seeds` du YAML pour appliquer le preset à cet arbre, puis appliquer
les `overrides` par-dessus.

Textures bark + leaf : générateurs procéduraux PIL packagés sous l'URI
`proc:<name>` (e.g. `bark_texture: "proc:oak_bark"`). Pointer vers un PNG
externe reste possible : `bark_texture: ./my_bark.png`.

## Tuning notes

Shedding is sensitive. The default `quality_threshold = 0.0` is permissive — it only removes branches whose subtree Q drops to literal 0 averaged over `window=5` iterations. If you want more aggressive pruning of weak branches, increase the threshold incrementally (try `0.1`, then `0.5`); be aware that high values combined with marker depletion can avalanche and strip the entire tree.

If your tree looks too dense or too sparse:
- **Too dense:** raise `shedding.quality_threshold` (e.g. `0.1`–`0.3`), or lower `marker_count`.
- **Too sparse / single stem:** lower `shedding.quality_threshold` to 0 (or disable with `--no-shed`), and consider lowering `r_kill` so markers persist longer.
- **Branches escaping the envelope:** keep `re_perceive_per_substep=True` (the default) — disable only via `--no-resample` for performance, accepting visual spikes.

### Phase 2A — branching architecture

- **Sympodial mode** (`sim.sympodial.enabled: true`): when an apical bud's
  quality stays below `q_threshold` for `n_consecutive_steps` consecutive
  iterations, the best-Q sibling lateral takes over as the new leader (oak,
  maple, lime). Disable for monopodial species (pine, birch).
- **Branch angle by order** (`phyllotaxy.branch_angle_by_order`): replaces
  the legacy scalar `branch_angle_deg`. The list indexes the insertion angle
  by axis order — e.g. `[60.0, 40.0, 30.0, 25.0]` opens primary laterals
  wide and tightens distal ramification.
- **Explicit plagiotropism** (`tropism.w_plagiotropism_main/_lateral`):
  projects the current direction onto the horizontal plane. Use on laterals
  to splay branches flat without polluting the gravity tuning (pendula
  species can stack gravitropism + plagiotropism independently).

### Phase 2B — bud lifecycle (shade mortality + reiteration)

Two new mechanisms make the canopy carve itself realistically and recover from
branch loss:

- **Shade-induced mortality** (`sim.shade_mortality`): a bud whose `light_factor`
  stays below `light_threshold` for `n_consecutive_steps` consecutive iterations
  dies (state → DEAD). This produces a natural live-crown ratio — lower branches
  in deep shade die off instead of dragging quality down. Requires
  `light.enabled: true` (the config raises `ConfigError` otherwise).
- **Reiteration via dormant reserves** (`phyllotaxy.dormant_reserve_count` +
  `shedding.reactivation_count`): every emitted node carries K pre-formed
  RESERVE buds (state `BudState.RESERVE`, invisible to perception and light).
  When the shedding pass removes a child subtree, `reactivation_count` reserves
  on the parent node flip to ACTIVE and join `tree.active_buds`. This is the
  epicormic-shoot / water-sprout mechanism — strong in oak and poplar, absent
  in conifers.

Species defaults:

| Species | shade_mortality.threshold | reserves / node | activations / shed |
|---------|---------------------------|-----------------|--------------------|
| oak     | 0.20                      | 2               | 1                  |
| pine    | 0.12                      | 0               | 0                  |
| birch   | 0.20                      | 1               | 1                  |

## Architecture

- `src/palubicki/sim/` — pure simulation (markers, buds, BH, tropisms, shedding). No geometry, no glTF.
- `src/palubicki/geom/` — skeleton → tessellated tubes (parallel transport frames) + parametric leaf clusters (1..N cross-quads per bud). Outputs a neutral `Mesh`.
- `src/palubicki/export/` — `Mesh` → `.glb`. Core glTF 2.0, no extensions, max viewer compatibility.
- `src/palubicki/cli.py` — orchestrates.

## Configuration

All parameters are exposed via YAML. CLI flags expose the most-tweaked ones; the rest are YAML-only. Run `palubicki dump-defaults` for the full schema with defaults.

The effective config (including all overrides) is embedded in `asset.extras.config` of the produced `.glb` for reproducibility.

## Tests

```bash
pytest                  # unit tests (fast)
pytest -m slow          # integration + goldens
pytest --cov            # coverage report
```

## Roadmap

- **V2** : voxel light shadowing (BHls).
- **V3** : obstacles + multi-tree forest simulation.
- ~~**V4** : species presets (oak, pine, birch) — livré~~.
- **Phase 1** (livré) : main-vs-lateral tropisms + gaussian jitter on phyllotaxy + stochastic internode length.
- **Phase 2A** (livré) : sympodial branching mode, `branch_angle_by_order`, explicit plagiotropism term.
- **Phase 2B** (livré) : bud life cycle (shade mortality, reiteration via dormant reserves).
- **Phase 2C** : decussate phyllotaxy + sun/shade leaves.
- **Phase 2D** : progressive elongation + dynamic secondary growth.

See `docs/superpowers/roadmap/`.

## References

Palubicki et al., 2009 — [Self-organizing tree models for image synthesis](https://algorithmicbotany.org/papers/selforg.sig2009.html).
