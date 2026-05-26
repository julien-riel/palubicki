# V3 — Obstacles & forêt multi-arbres

**Statut** : Spec
**Date** : 2026-05-25
**Préalable** : V2 BHls livré et stable (commit `b809248`).
**Référence papier** : Palubicki et al. 2009, §6 (obstacles & interaction).

## Objectif

Étendre V2 avec (a) obstacles statiques (AABB, sphère, OBB, mesh OBJ) qui
bloquent espace, lumière et croissance, et (b) simulation multi-arbres sur un
`MarkerCloud` et une `LightGrid` partagés, avec ombrage et compétition
spatiale mutuels. Quand `forest.seeds == ()` ET `forest.obstacles == ()`, V3
retombe sur V2 bit-exact (les goldens V1/V2 ne bougent pas).

## Décisions de design

| Décision | Choix | Raison |
|---|---|---|
| Types d'obstacles | AABB + Sphère + OBB + MeshOBJ (tous) | Réalisme maximal ; `trimesh` ajouté comme dépendance pour le mesh |
| Effets obstacles | Markers killed à init + croissance segment-blocked + voxels lumière opaques + buds inside DEAD | 4 mécanismes redondants — chacun couvre un mode défaillance différent (compétition, croissance, lumière, sécurité) |
| Bud bloqué par obstacle | DORMANT (pas DEAD) | Permet la récupération si la dynamique change ; participe au shedding |
| Format scène | Sections `forest:` et obstacles intégrés dans `forest.obstacles:` du YAML principal | Un seul fichier, lisible, cohérent avec `dump-defaults` / `dump-config` |
| Config par arbre | Overrides arbitraires (n'importe quelle section) via clés dotted | Permet forêts mixtes (chêne + pin) sans dupliquer 200 lignes |
| Ressources partagées | `MarkerCloud` commun (concat des samples par-arbre) + `LightGrid` commune (couvre AABB union envelopes + obstacles) | Compétition spatiale et lumineuse vraies entre arbres |
| Boucle sim | `_iteration_step()` extrait ; deux entry points publics (`simulate`, `simulate_forest`) | Backward-compat V2 bit-exact ; testabilité par étape ; le `simulate` actuel a ~140 lignes denses, refactor nécessaire |
| CLI | `palubicki forest -o scene.glb --config scene.yaml` | Sous-commande dédiée, `generate` reste mono-arbre strict |
| Export glb | Une scène glTF avec N+1 nodes (`tree_0`, ..., `tree_{N-1}`, `obstacles`) | Sélection par arbre dans les viewers ; obstacles en triangles semi-transparents (alphaMode=BLEND, alpha=0.3) pour debug visuel |

## Architecture

### Nouveau bloc config

```python
# src/palubicki/config.py

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
    # row-major orthonormal rotation matrix, packed as 9 floats
    axes: tuple[float, ...] = (1, 0, 0, 0, 1, 0, 0, 0, 1)

@dataclass(frozen=True)
class ObstacleMesh:
    kind: Literal["mesh"] = "mesh"
    path: Path = field(default_factory=lambda: Path("obstacle.obj"))
    translate: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: float = 1.0

@dataclass(frozen=True)
class ForestSeed:
    position: tuple[float, float, float]
    seed: int | None = None                          # default: cfg.seed + tree_index
    overrides: dict = field(default_factory=dict)    # dotted-keys e.g. {"envelope.shape": "cone"}

@dataclass(frozen=True)
class ForestConfig:
    seeds: tuple[ForestSeed, ...] = ()               # empty → single-tree mode
    obstacles: tuple = ()                            # discriminated union of Obstacle*
    export_obstacles_geometry: bool = True
```

Le `Config` racine reçoit `forest: ForestConfig = field(default_factory=ForestConfig)`.

**Chargement YAML des obstacles (union discriminée)** : le mécanisme actuel `_SECTION_TYPES` instancie une dataclass par section. Pour `forest.obstacles`, qui est une liste de types hétérogènes, on ajoute un helper `_load_obstacle(d: dict) -> ObstacleAABB|Sphere|OBB|Mesh` qui dispatche sur `d["kind"]` et appelle le constructeur correspondant. Validation : `kind` manquant ou inconnu → `ConfigError`. Pour `forest.seeds`, mêmes mécanique (list of ForestSeed). L'ajout vit dans `config.py` à côté de `_set_dotted`.

**Modes** :
- `forest.seeds == ()` ET `forest.obstacles == ()` → V2 bit-exact.
- `forest.seeds == ()`, `forest.obstacles ≠ ()` → single-tree avec obstacles (le `Forest` retourné contient 1 arbre).
- `forest.seeds ≠ ()`, `forest.obstacles == ()` → multi-tree sans obstacles ; voxelisation skippée.
- Les deux non-vides → V3 plein.

### Nouveaux modules

```
src/palubicki/
├── sim/
│   ├── obstacles.py             NOUVEAU — Obstacle protocol + 4 implémentations + helpers
│   ├── forest.py                NOUVEAU — Forest dataclass + build_forest + per_tree_config
│   ├── light.py                 MODIFIÉ — rebuild_from_forest, obstacle_mask
│   └── simulator.py             MODIFIÉ — _iteration_step extrait, simulate_forest
├── geom/
│   └── obstacle_geom.py         NOUVEAU — triangulation AABB/Sphere/OBB + load mesh
├── export/
│   └── gltf.py                  MODIFIÉ — write_glb_forest (multi-node scene)
├── config.py                    MODIFIÉ — ForestConfig, Obstacle*, ForestSeed
└── cli.py                       MODIFIÉ — sous-commande `forest`
```

### `sim/obstacles.py`

```python
from typing import Protocol

LAI_OPAQUE = 1e6   # combiné à k_absorption≈0.5 et step_len≈0.1: exp(-5e4) = 0

class Obstacle(Protocol):
    def contains(self, points: np.ndarray) -> np.ndarray:
        """Vectorized point-in-obstacle test. (N,3) -> (N,) bool."""
    def segment_intersects(self, p0: np.ndarray, p1: np.ndarray) -> bool:
        """Does segment [p0, p1] enter the obstacle?"""
    def aabb(self) -> tuple[np.ndarray, np.ndarray]:
        """World-space AABB for grid bounds & broad-phase."""
    def voxelize(self, grid: "LightGrid") -> np.ndarray:
        """Bool mask (nx, ny, nz) — cells whose center is inside obstacle."""

class AABBObstacle: ...
class SphereObstacle: ...
class OBBObstacle: ...
class MeshObstacle:
    def __init__(self, mesh: "trimesh.Trimesh"): self._mesh = mesh
    def contains(self, points): return self._mesh.contains(points)
    def segment_intersects(self, p0, p1):
        # Use trimesh.ray.RayMeshIntersector.intersects_first to find the first hit
        # along (p1 - p0) direction starting at p0. Compute the hit distance and compare
        # with ||p1 - p0||. Hit iff 0 <= dist <= seg_len. Endpoint inside (contains(p0)
        # or contains(p1)) also counts as intersect.
        ...

def build_obstacles(cfg: ForestConfig) -> list[Obstacle]:
    """Instantiate concrete obstacles from config dataclasses."""

def filter_markers(positions: np.ndarray, obstacles: list[Obstacle]) -> np.ndarray:
    """Drop positions inside any obstacle (broad-phase AABB → fine test)."""

def segment_blocked(p0, p1, obstacles: list[Obstacle]) -> bool:
    """True iff any obstacle blocks the segment."""

def any_contains(point: np.ndarray, obstacles: list[Obstacle]) -> bool:
    """True iff point is inside any obstacle. Scalar wrapper for growth-time."""
```

### `sim/forest.py`

```python
@dataclass
class Forest:
    trees: list[Tree]
    seeds: list[ForestSeed]                          # parallel to trees
    obstacles: list[Obstacle]
    markers: MarkerCloud                             # shared
    light_grid: LightGrid | None                     # shared, None if light disabled
    obstacle_voxel_mask: np.ndarray | None           # (nx,ny,nz) bool, precomputed

def build_forest(cfg: Config) -> Forest:
    """Build initial Forest from cfg.
       - If forest.seeds is (), build a single-tree Forest with envelope at cfg.envelope.
       - Else, for each seed: derive per_tree_config(cfg, seed), sample its markers,
         create its root Bud at seed.position.
       - Concat all marker arrays, then filter via obstacles → MarkerCloud.
       - If cfg.light.enabled: build LightGrid covering union(envelope AABBs + obstacle AABBs).
       - Voxelize obstacles once → obstacle_voxel_mask."""

def per_tree_config(cfg: Config, seed_entry: ForestSeed, tree_index: int) -> Config:
    """Apply dotted-key overrides on a copy of cfg, then translate
       envelope.center to seed_entry.position. Returns a new frozen Config.
       The cfg.seed propagated to the tree is (seed_entry.seed if not None
       else cfg.seed + tree_index)."""

def forest_light_bounds(
    envelopes: list[EnvelopeConfig],
    obstacles: list[Obstacle],
) -> tuple[np.ndarray, np.ndarray]:
    """Auto-fit bounds = AABB(union of envelope AABBs + obstacle AABBs) + sky margin
       (same 10%/30% factors as V2 _autofit_bounds)."""

def all_active_buds(forest: Forest) -> list[Bud]:
    """Flatten union of active buds across all trees, in deterministic order
       (tree_index, then bud index within tree). Order matters for RNG-driven
       perceive ties — we want reproducible runs."""
```

### `sim/light.py` — extensions V3

```python
class LightGrid:
    # V2 unchanged: origin, cell_size, resolution, lai, world_to_cell, sample_*

    def rebuild_from_forest(self, forest: Forest, cfg: LightConfig, *, r_tip, exponent) -> None:
        """Like rebuild_from_tree but iterates forest.trees.
           After leaf+internode injection, applies obstacle mask:
              lai[forest.obstacle_voxel_mask] = LAI_OPAQUE
           (mask is precomputed in build_forest, since obstacles are static)."""
        self.lai.fill(0.0)
        for tree in forest.trees:
            compute_radii(tree, r_tip=r_tip, exponent=exponent)
            self._inject_tree(tree, cfg)
        if forest.obstacle_voxel_mask is not None:
            self.lai[forest.obstacle_voxel_mask] = LAI_OPAQUE
```

`rebuild_from_tree` (V2) reste — devient une enveloppe qui appelle `rebuild_from_forest` avec un `Forest` à 1 arbre sans obstacles. Backward-compat préservée.

### `sim/simulator.py` — refactor

```python
def simulate(cfg: Config) -> Tree:
    """Single-tree entry point. V1/V2 backward-compat.
       Delegates to simulate_forest(cfg), returns forest.trees[0]."""
    forest = simulate_forest(cfg)
    return forest.trees[0]

def simulate_forest(cfg: Config) -> Forest:
    """Multi-tree entry point."""
    forest = build_forest(cfg)
    no_new_streak = 0
    for iteration in range(cfg.sim.max_iterations):
        if not _any_active(forest): break
        nodes_created = _iteration_step(forest, cfg, iteration)
        no_new_streak = 0 if nodes_created > 0 else no_new_streak + 1
        if no_new_streak >= 2: break
    return forest

def _iteration_step(forest: Forest, cfg: Config, iteration: int) -> int:
    """One step on the whole forest. Returns total nodes created across all trees.

       Phases (mirrors V2 but cross-tree where appropriate):
         1. rebuild light grid (if enabled), apply obstacle mask
         2. perceive_light on union(active_buds)
         3. perceive (markers) on union(active_buds) — natural cross-tree competition
         4. quality = res.quality * light_factor (per bud)
         5. for each tree: v_subtree, allocate, record_qualities (each walks
            only its own tree's topology, reading the shared per-bud quality dict)
         6. for each tree: growth substeps — with obstacle checks:
              - segment_blocked(bud.pos, new_pos, obstacles) → bud.state = DORMANT, stop
              - any_contains(new_pos, obstacles) → bud.state = DEAD, stop
              - else: create internode + buds (as V2)
         7. markers.kill_near(all_new_positions, r_kill) — single global call
         8. for each tree: shed_low_quality
    """
```

Le découpage `_iteration_step` permet de tester chaque phase isolément. Quand `len(forest.trees) == 1` ET `forest.obstacles == []` ET `forest.obstacle_voxel_mask is None`, ce code est bit-exact équivalent à la boucle V2 actuelle (mêmes appels, mêmes ordres). On le valide via le golden V2 inchangé.

**Ordre d'itération cross-tree** : `all_active_buds(forest)` retourne les buds en ordre `(tree_index croissant, bud_index_in_tree croissant)`. Cet ordre est stable entre runs et propagé aux dict de résultat de `perceive()` / `perceive_light()`.

**RNG (cohérence V2 bit-exact)** :
- Sampling des markers par arbre : `np.random.default_rng(per_tree_seed)` où `per_tree_seed = seed.seed if not None else cfg.seed + tree_index`. Pour le single-tree path (`forest.seeds == ()`), `per_tree_seed = cfg.seed` (équivalent V2).
- `perceive_light` global (union des buds) : `np.random.SeedSequence([cfg.seed, iteration]).generate_state(1)[0]` — identique V2, indépendant du nombre d'arbres.
- Substep light resample : `np.random.SeedSequence([cfg.seed, iteration, step + 1]).generate_state(1)[0]` — identique V2.
- Aucun nouveau RNG par arbre n'intervient dans la boucle de perception/croissance (l'union des buds est échantillonnée globalement).

### `geom/obstacle_geom.py`

```python
def build_obstacle_primitives(
    obstacles: list[Obstacle],
    material: Material,
) -> list[Primitive]:
    """Triangulate each obstacle:
       - AABB / OBB → 12 triangles (cube)
       - Sphere → UV sphere (16×8 subdivision, ~256 triangles)
       - Mesh → use mesh.triangles directly (after transform)
       All glued into a single primitive per material (or one primitive
       per obstacle if material varies — for V3 a single material suffices)."""
```

Material par défaut : couleur `(0.5, 0.5, 0.55, 0.3)`, alphaMode `BLEND`, doubleSided=True. L'utilisateur peut désactiver via `forest.export_obstacles_geometry=False`.

### `export/gltf.py` — extension

```python
def write_glb_forest(forest: Forest, cfg: Config, path: Path, asset_meta: dict) -> None:
    """Build one glTF scene with:
       - one node 'tree_{i}' per tree, each holding its bark+leaves primitives
       - one optional node 'obstacles' holding the obstacle primitive
       asset.extras.config is the full Config (incl. forest section, obstacles serialized
       with their dataclass dicts)."""

def write_glb(mesh: Mesh, path: Path, *, asset_meta: dict) -> None:
    # V2 entry point unchanged
```

## Flow de données

```
init (build_forest) :
  1. for each seed: per_tree_config + sample_markers (per envelope) + root bud
  2. concat all markers → filter via obstacles → MarkerCloud
  3. if light enabled:
       light_grid = LightGrid.from_bounds(forest_light_bounds(envelopes, obstacles))
       obstacle_voxel_mask = OR(o.voxelize(grid) for o in obstacles)
     else: light_grid = None, obstacle_voxel_mask = None

step n (_iteration_step) :
  1. if light_grid is not None:
       light_grid.rebuild_from_forest(forest, cfg.light, r_tip=..., exponent=...)
       # rebuild includes: zero LAI → inject leaves+internodes per tree → lai[mask] = LAI_OPAQUE
       light_info = perceive_light(all_active_buds(forest), light_grid, cfg.light)
     else:
       light_info = None
  2. res = perceive(all_active_buds(forest), forest.markers, ...)
  3. quality[b] = res.quality[b] * light_info.factor[b]  (or res.quality if no light)
  4. for tree in forest.trees:
       # quality is a dict keyed by Bud objects (identity-keyed). compute_v_subtree
       # and allocate walk only this tree's topology, so they implicitly read only
       # this tree's bud entries — no explicit filtering needed.
       v_subtree = compute_v_subtree(tree, quality)
       n_by_bud = allocate(tree, quality, ...)
       record_qualities(tree, v_subtree=...)
  5. for tree in forest.trees:
       for bud_old in active(tree):
         for substep in range(n):
           d = growth_direction(...)
           new_pos = bud.pos + d * L
           if segment_blocked(bud.pos, new_pos, forest.obstacles):
             bud.state = DORMANT; break
           if any_contains(new_pos, forest.obstacles):
             bud.state = DEAD; break
           # create internode + terminal/lateral as V2
  6. markers.kill_near(concat of all new positions, cfg.sim.r_kill)
  7. for tree: shed_low_quality(tree, cfg.shedding)
```

**Backward-compat V2 bit-exact** : quand `forest.seeds == ()` et `forest.obstacles == ()`, le `build_forest` produit `trees=[1 tree]`, `obstacles=[]`, `obstacle_voxel_mask=None`. Les checks `segment_blocked` et `any_contains` deviennent des no-ops (boucles vides). `rebuild_from_forest` avec 1 arbre = `rebuild_from_tree`. L'ordre d'itération des buds = ordre V2. Tests goldens V2 stables.

## Error handling

| Cas | Comportement |
|---|---|
| `forest.seeds == ()` + `forest.obstacles == ()` | V2 bit-exact (single-tree, no obstacles) |
| `forest.seeds == ()` + obstacles non-vide | Single-tree avec obstacles. `simulate_forest()` retourne `Forest` à 1 arbre |
| `forest.seeds` non-vide + `forest.obstacles == ()` | Multi-tree sans obstacles ; voxelisation skippée |
| `seed.position` à l'intérieur d'un obstacle | `ConfigError` à `load_config()` (validation immédiate) |
| `seed.overrides` contient une clé inconnue | `ConfigError` via le même mécanisme dotted-key que `_set_dotted` actuel |
| Mesh OBJ non chargeable / mal-formé | `ConfigError` à `build_obstacles()` avec le path + l'exception trimesh |
| Deux arbres à la même position | Pas d'erreur ; les root nodes coïncident ; closest-bud désambiguïse |
| Envelope d'un arbre entièrement à l'intérieur d'un obstacle | `filter_markers` retourne `array([])` → arbre meurt au step 0 (perception vide). Warning loggé, pas d'erreur |
| LightGrid bounds dégénérées (1 arbre + 1 obstacle énorme) | Auto-fit prend l'union. Si `min(cell_size) > 2 × cfg.sim.internode_length`, log warning |
| Bud bloqué par obstacle au step 0 | DORMANT direct, comme si sa quality était 0 |
| Mesh OBJ avec normales mal orientées | Hors scope V3 (limitation trimesh.contains documentée) |
| `LAI_OPAQUE × k × step` overflow `exp(-)` | `1e6 × 0.5 × ~0.1 = 5e4` → `exp(-5e4) = 0.0` exactement, pas d'underflow visible |

## Tests

### Unitaires

**`tests/sim/test_obstacles.py` (nouveau)**
- AABB : `contains(centre)` True, `contains(coin extérieur)` False, vectorisation (N,3).
- AABB : `segment_intersects` — traverse entièrement / start-inside / end-inside / pass-along-edge / miss.
- Sphere : `contains` + `segment_intersects` (équation quadratique).
- OBB : `contains` via transform en local frame ; `segment_intersects` idem.
- Mesh : un cube OBJ chargé via fixture → `contains` cohérent avec AABB équivalent.
- `voxelize(grid)` : grille 8³, AABB centrale → mask non vide et conforme au cell-center-inside test.
- `filter_markers([pts], obstacles)` : drop ceux dedans, garde ceux dehors.
- `segment_blocked(p0, p1, obstacles)` : True dès qu'un seul obstacle bloque.

**`tests/sim/test_forest.py` (nouveau)**
- `per_tree_config(cfg, ForestSeed(position=(5,0,5)))` : `envelope.center == (5,0,5)`, autres champs inchangés.
- `per_tree_config` avec `overrides={"envelope.shape": "cone", "tropism.w_gravity": 0.5}` : applique sur la copie, original inchangé.
- `build_forest` avec 2 seeds → `Forest.trees` a 2 arbres, `markers.alive_count` cohérent.
- `forest_light_bounds([env_A_origine, env_B_(10,0,0)], obstacles=[AABB((5,0,-3),(7,4,-1))])` : AABB couvre les 3 + marges sky.

**`tests/sim/test_light_grid.py` (étendu)**
- `rebuild_from_forest(forest_2_trees)` : LAI ≈ somme des injections individuelles aux mêmes cells.
- Application d'`obstacle_voxel_mask` : `lai[mask] == LAI_OPAQUE`, transmission à travers une cellule masquée ≈ 0.

**`tests/sim/test_simulator.py` (étendu)**
- `simulate(cfg)` avec `forest.seeds == ()` ET `obstacles == ()` → tree V2 bit-exact (hash positions, radii).
- `simulate_forest(cfg)` avec 1 seed à origine, pas d'obstacle → résultat identique à `simulate(cfg)` (le wrapper unifie).
- `simulate_forest(cfg)` avec 2 seeds éloignées (envelopes disjoints) → trees indépendants, bit-exact équivalents à 2 `simulate()` séparés à la translation près.
- Bud avec `segment_blocked == True` au premier step → DORMANT, pas d'internode créé.
- Bud avec direction qui finit `inside(obstacle)` → DEAD, sa lignée s'arrête.

### Intégration

**`tests/integration/test_obstacles_behavior.py` (nouveau)**
- Un arbre + un mur AABB à 1m → silhouette "déformée" loin du mur (markers killed côté mur).
- Un arbre + un toit AABB au-dessus → branches contournent vers les côtés, hauteur effective plafonnée.

**`tests/integration/test_forest_behavior.py` (nouveau)**
- 2 arbres côte-à-côte (3m apart, envelopes 2m chacun, donc léger chevauchement) → canopées asymétriques (moins de buds du côté inter-arbre vs côté extérieur) — preuve de compétition.
- 2 arbres + light enabled → transmission moyenne sur les buds de A côté-B < transmission côté-extérieur.

**`tests/integration/test_smoke.py` (étendu)**
- 1 cas `palubicki forest` avec scène minimale (2 seeds + 1 AABB) → glb non vide, valide par pygltflib.

**`tests/golden/test_goldens.py` (étendu)**
- Nouveau golden : forêt 3 arbres déterministe (positions fixes, seeds fixes, light enabled, 1 AABB) → hash stable.

**`tests/test_cli.py` (étendu)**
- `palubicki forest --help` retourne 0.
- `palubicki forest -o /tmp/x.glb --config tests/fixtures/forest_minimal.yaml` génère un .glb.
- Erreur de config (seed inside obstacle) → exit code 2 + message clair.

## Critères d'acceptation

1. Tous tests V1+V2 passent inchangés (rétrocompat bit-exact `forest.seeds == ()` + `obstacles == ()`).
2. Nouveaux tests V3 passent.
3. Golden V3 hash stable.
4. `palubicki forest --config example_forest.yaml -o forest.glb` génère un .glb avec N+1 nodes nommés.
5. Coverage ≥ 85% sur `sim/obstacles.py` et `sim/forest.py`.
6. Aucune régression de perf > 5× sur un single-tree V2 typique.
7. Le `.glb` produit embarque `cfg.forest` (avec obstacles + seeds) dans `asset.extras.config`.
8. `palubicki dump-config forest.glb` extrait la config complète et permet un re-`forest` reproductible.

## Hors scope V3

- Obstacles mobiles ou déformables (statiques only).
- Mesh OBJ avec normales inversées (limitation trimesh.contains).
- Optimisation perf > 50 arbres (KDTree global devient goulot ; benchmark + premiers leviers documentés, pas optimisés).
- Sol implicite (l'utilisateur déclare un AABB explicite pour un sol).
- Vent / forces dynamiques (V4+).

## Risques / questions ouvertes

- **Coût LightGrid forêt** : 5 arbres × 1000 buds × K=16 rayons × ~100 cells/rayon ≈ 8M cell touches/step. À benchmarker. Premier levier : `n_rays=8`.
- **Voxelisation mesh OBJ** : test cell-center-inside cheap mais sous-échantillonne les petits détails. Si problématique, refiner via 8 sub-samples par cell. À documenter.
- **Reproductibilité multi-tree** : chaque arbre reçoit son RNG d'init (`per_tree_seed = seed.seed if not None else cfg.seed + tree_index`) ; les RNG de perception sont globaux et identiques V2 (voir section Architecture / RNG). Re-run avec même cfg = même résultat. Test explicite.
- **Concat des markers** : duplication dans les zones de chevauchement. Quantifier l'effet sur la densité ressentie ; documenter dans le tuning README.
- **Ordre d'itération cross-tree** : `all_active_buds` impose `(tree_index, bud_index)`. Doit rester stable pour reproductibilité et goldens.
