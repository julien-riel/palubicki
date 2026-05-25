# V2 — BHls hybride : ombrage lumineux voxelisé

**Statut** : Spec
**Date** : 2026-05-25
**Préalable** : V1 BHse livré et stable (commit `5cebf27`).
**Référence papier** : Palubicki et al. 2009, §5 (light competition).

## Objectif

Étendre V1 (BHse — perception des markers spatiaux) avec un modèle physique
de lumière 3D voxelisé. La qualité d'un bud devient le produit
`Q_b = nb_markers_perçus × light_factor_b`, ce qui couple compétition pour
l'espace (V1) et compétition pour la lumière (V2). Le shedding et le
phototropisme utilisent aussi la lumière locale.

Quand `light.enabled=False`, V2 retombe sur V1 bit-exact (les goldens V1 ne
bougent pas).

## Décisions de design

| Décision | Choix | Raison |
|---|---|---|
| Modèle de perception lumière | Hémisphérique échantillonné (K=16, cosine-weighted) | Plus physique que cône-discret du papier, capture la diffusion du ciel uniforme |
| Atténuation par voxel | Beer-Lambert sur LAI cumulée (feuilles + internodes pondérés par surface latérale) | Modèle physique propre, paramètre unique `k_absorption` |
| Bornes / résolution grille | Explicites en config, avec défauts auto-fit (envelope AABB + marge sup 30%) | V3-ready (forest = grille partagée), mais bonne UX au démarrage |
| Mise à jour grille | Rebuild complet à chaque step | Simple, robuste, pas de drift incrémental |
| Portée de la lumière | BH allocation + shedding + tropisme local | Réalisme maximum (le bud sous l'ombre meurt et oriente sa croissance vers la lumière) |
| Découpage code | 2 modules : `sim/light.py` (grille + injection + sampling) et `sim/light_perception.py` (orchestration per-bud) ; extension de `sim/tropisms.py` | Cohérent avec V1 (un concept = un fichier) |
| Formule Q | Multiplicatif : `Q = nb_markers × light_factor` | Unités cohérentes (factor ∈ [0,1] module la quantité de markers) ; ombre totale → Q=0 → bud dormant |
| Couplage tropisme | Réutilise `w_phototropism` ; quand `light.enabled=True`, le terme photo prend le gradient local au lieu de `photo_direction` | Pas de nouveau poids, sémantique propre |

## Architecture

### Nouveau bloc config

```python
@dataclass
class LightConfig:
    enabled: bool = False                              # défaut: V1 bit-exact
    grid_origin: tuple[float,float,float] | None = None
    grid_size:   tuple[float,float,float] | None = None
    grid_resolution: tuple[int,int,int] = (64, 64, 64)
    k_absorption: float = 0.5                          # Beer-Lambert
    leaf_area: float = 0.04                            # surface foliaire / feuille (m²)
    internode_area_scale: float = 1.0                  # pondère la surface latérale dans LAI
    n_rays: int = 16
    light_direction: tuple[float,float,float] = (0.0, 1.0, 0.0)
```

Quand `grid_origin` / `grid_size` sont `None` : auto-fit, calculé depuis
`cfg.envelope.center` + `cfg.envelope.radii` + `cfg.envelope.kind`. Pour
chaque kind on dérive l'AABB :
- `sphere` : centre ± `radii[0]` sur les 3 axes.
- `ellipsoid` / `half_ellipsoid` : centre ± `radii[i]` sur l'axe i (y commence
  à 0 pour `half_`).
- `cone` : x/z ∈ centre ± `radii[0]` ; y ∈ [centre.y, centre.y + radii[1]].

Puis :
- `origin = aabb_min - 0.1 * extent`
- `size  = aabb_extent + (0, 0.3·height, 0) + (0.2·ext_x, 0, 0.2·ext_z)`

### Modules nouveaux

#### `sim/light.py`

```python
class LightGrid:
    origin: np.ndarray           # (3,)
    cell_size: np.ndarray        # (3,) = size / resolution
    resolution: tuple[int,int,int]
    lai: np.ndarray              # (nx, ny, nz) float32

    @classmethod
    def from_config(cls, light_cfg, envelope_cfg) -> "LightGrid": ...

    def world_to_cell(self, p: np.ndarray) -> tuple[int,int,int] | None: ...
    def cell_to_world_center(self, i: int, j: int, k: int) -> np.ndarray: ...

    def rebuild_from_tree(self, tree, light_cfg) -> None:
        """Full rebuild. Zero LAI, then inject leaves + internodes."""
        # 1. lai[:] = 0
        # 2. Calcul provisionnel des rayons : appel à compute_radii(tree, geom_cfg)
        #    (même logique que geom/radii.py — pipe model post-order walk). Pas
        #    cher (O(N_internodes)), nécessaire car les rayons n'existent pas
        #    pendant la sim en V1. Cette fonction est extraite/partagée entre
        #    sim et geom (refacto léger de geom/radii.py vers un helper pur).
        # 3. Tips (terminal buds vivants, non shed): lai[cell(bud.pos)] += leaf_area / voxel_volume
        # 4. Internodes: segmenter en sub-segs de taille ≈ min(cell_size),
        #    chaque sub-seg dépose (2π·r·len_sub × internode_area_scale) / voxel_volume
        #    où r est le rayon provisionnel calculé en étape 2.

    def sample_transmission(self, p: np.ndarray, direction: np.ndarray) -> float:
        """Ray-march Beer-Lambert depuis p le long de direction.
           Pas = min(cell_size). T = exp(-Σ k * lai[cell] * step)."""

    def sample_hemisphere(self, p, n_rays, light_direction) -> tuple[float, np.ndarray]:
        """K directions cosine-weighted autour de light_direction (concentric
           disk + projection). Pour chaque dir_k: T_k = sample_transmission(p, dir_k).
           Retourne:
             light_factor = mean(T_k)
             gradient     = normalize(Σ T_k · dir_k)"""
```

Vectorisation cible : `rebuild_from_tree` vectorisé via `np.add.at` ; `sample_transmission` peut être batché par K rayons partageant la même origine.

#### `sim/light_perception.py`

```python
@dataclass
class LightPerception:
    light_factor: dict[Bud, float]    # ∈ [0,1]
    gradient: dict[Bud, np.ndarray]   # unit vector ou zéro

def perceive_light(buds, grid: LightGrid, cfg: LightConfig) -> LightPerception:
    for bud in buds:
        lf, grad = grid.sample_hemisphere(bud.position, cfg.n_rays, cfg.light_direction)
        result.light_factor[bud] = lf
        result.gradient[bud] = grad
    return result
```

### Modules étendus

#### `sim/tropisms.py`

```python
def growth_direction(
    *, v_perception, current_direction, cfg, light_gradient=None,
) -> np.ndarray:
    if light_gradient is not None and np.linalg.norm(light_gradient) > 1e-12:
        photo = light_gradient / np.linalg.norm(light_gradient)
    else:
        photo = normalize(cfg.photo_direction)   # V1 fallback
    blend = (cfg.w_perception * v_perception
           + cfg.w_gravity * _UP
           + cfg.w_phototropism * photo
           + cfg.w_direction_inertia * current_direction)
    # ... fin identique à V1 (normalisation + fallbacks)
```

#### `sim/simulator.py` — boucle modifiée

```python
def simulate(cfg: Config) -> Tree:
    rng = ...
    markers = MarkerCloud(sample_markers(cfg.envelope, rng))
    tree = ...
    light_grid = LightGrid.from_config(cfg.light, cfg.envelope) if cfg.light.enabled else None

    for iteration in range(cfg.sim.max_iterations):
        if not tree.active_buds: break

        if light_grid is not None:
            light_grid.rebuild_from_tree(tree, cfg.light)
            light_info = perceive_light(tree.active_buds, light_grid, cfg.light)
        else:
            light_info = None

        res = perceive(tree.active_buds, markers, ...)   # V1 markers

        if light_info is not None:
            quality = {b: res.quality[b] * light_info.light_factor[b] for b in tree.active_buds}
        else:
            quality = res.quality

        n_by_bud = allocate(tree, quality=quality, alpha=..., lambda_apical=...)
        record_qualities(tree, quality=quality)

        for bud_old in list(tree.active_buds):
            ...
            light_grad = light_info.gradient[current_bud] if light_info else None
            d = growth_direction(v_perception=..., current_direction=...,
                                 cfg=cfg.tropism, light_gradient=light_grad)
            ...
            # re-perceive substep : sample_hemisphere local pour le terminal
            # (la grille N'EST PAS rebuilt entre substeps).
```

## Flow de données

```
step n :
  1. light_grid.rebuild_from_tree(tree, cfg.light)        # O(N_geom)
  2. light_info = perceive_light(buds, grid, cfg.light)   # O(N_buds × K × ray_len)
  3. res = perceive(buds, markers, ...)                   # V1, inchangé
  4. quality = res.quality × light_info.light_factor      # produit per-bud
  5. n_by_bud = allocate(tree, quality, ...)              # BH avec Q hybride
  6. record_qualities(tree, quality)                      # shedding voit Q hybride
  7. growth loop : growth_direction(..., light_gradient=...) → croissance biaisée
  8. markers.kill_near(...) ; shed_low_quality(tree, ...)
```

Quand `light.enabled=False` : étapes 1-2 skippées, étape 4 dégénère (`quality = res.quality`), étape 7 retombe sur V1.

## Error handling

| Cas | Comportement |
|---|---|
| `light_factor = 0` (ombre totale) | `Q_b = 0` → BH alloue 0 → bud DORMANT (V1 path) |
| `gradient ≈ 0` (ombre uniforme) | Fallback à `cfg.tropism.photo_direction` (V1) |
| Bud hors grille | `sample_hemisphere` retourne `(1.0, light_direction)` → fail-open (plein soleil) |
| Tree vide ou tout shed | Boucle se termine via le break V1 `if not tree.active_buds` |
| Internode très long sur grille fine | Segmenté en sub-segs ≤ `min(cell_size)` à l'injection |
| `k_absorption = 0` | Grille transparente → `light_factor = 1.0` partout → équivalent à `enabled=False` |

## Tests

### Unitaires

**`tests/sim/test_light_grid.py` (nouveau)**
- `world_to_cell` : aller-retour cohérent ; None hors grille.
- `rebuild_from_tree` avec 1 leaf isolée → 1 voxel `LAI = leaf_area / cell_volume`.
- `rebuild_from_tree` avec un internode vertical → N voxels chacun avec une fraction de la surface latérale.
- `sample_transmission` grille vide → T = 1.0.
- `sample_transmission` LAI uniforme L → T ≈ exp(-k·L·dist).
- `sample_hemisphere` ciel ouvert → `light_factor = 1.0`, gradient = `light_direction`.
- `sample_hemisphere` sous couche dense uniforme → `light_factor` < 1, gradient ≈ `light_direction`.

**`tests/sim/test_light_perception.py` (nouveau)**
- Bud sous une feuille unique → `light_factor` < 1 ET > 0, gradient pointe vers une zone non ombragée.

**`tests/sim/test_tropisms.py` (étendu)**
- `growth_direction(light_gradient=v)` utilise `v` au lieu de `cfg.photo_direction`.
- `growth_direction(light_gradient=None)` = V1 verbatim.
- `growth_direction(light_gradient=zéro)` retombe sur V1.

**`tests/sim/test_simulator.py` (étendu)**
- `cfg.light.enabled=False` → tree bit-exact V1 (hash positions, radii).
- `cfg.light.enabled=True` + `k_absorption=0` → équivalent fonctionnel à V1 (à l'epsilon flottant près sur la multiplication par 1.0).
- 2 runs identiques (même seed + cfg) → trees identiques.

### Intégration

- `tests/integration/test_smoke.py` (étendu) : un cas `light_enabled=True` par enveloppe (sphère, ellipsoïde, cône).
- `tests/golden/test_goldens.py` (étendu) : nouveau golden hash pour `light_enabled=True` seed 42 ellipsoïde standard.

### Comportementaux

**`tests/integration/test_light_behavior.py` (nouveau)**
- Deux trees mêmes paramètres sauf `light.enabled` → tree V2 a moins de buds actifs au final ET son centroïde de feuillage est en y plus haut (compétition lumière favorise le haut).
- Bud directement sous une masse foliaire dense → DORMANT/DEAD plus tôt que son voisin en pleine lumière (shedding visible).

## Critères d'acceptation

1. Tous tests V1 passent inchangés (rétrocompat bit-exact `enabled=False`).
2. Nouveaux tests V2 passent.
3. Golden V2 hash stable.
4. `palubicki generate --light-enabled -o tree.glb` génère un arbre dont la silhouette est visuellement plus "ramassée vers le haut" qu'un V1 équivalent (ellipsoïde seed 42).
5. Coverage ≥ 85% sur `sim/light.py` et `sim/light_perception.py`.
6. Aucune régression de perf > 5× sur un tree V1 typique avec `enabled=False`.
7. Le `.glb` produit embarque `cfg.light` dans `asset.extras.config` (reproductibilité).

## Hors scope V2

- Soleil mobile / cycle jour-nuit.
- Lumière directionnelle dure (vs diffuse de ciel) — l'hémisphérique cosine-weighted est suffisant.
- Obstacles externes qui bloqueraient la lumière → V3.
- Lumière partagée entre plusieurs arbres → V3.

## Risques / questions ouvertes

- **Coût** : 1000 buds × K=16 rayons × ~80 cellules/rayon = 1.3M cell touches/step. Vérifier au benchmark que ça tient en numpy vectorisé. Si dépassement, premier levier : `n_rays` à 8.
- **Mémoire** : 64³ float32 = 1 Mo, OK. 128³ = 8 Mo, OK. 256³ = 64 Mo, à surveiller.
- **Substep sans rebuild** : les feuilles créées dans le step courant n'ombragent pas les substeps suivants du même step. Acceptable (résolu au step suivant). À documenter dans le tuning README.
- **Calibration `w_phototropism`** : défaut V1 est `0.0` ; il faudra le bumper (suggérer `0.3`) quand `light.enabled=True`, sinon le gradient calculé est ignoré. À documenter.
- **Re-perception substep** : on resample la lumière pour le terminal créé en substep, ce qui revalide `light_factor` et `gradient`. C'est nécessaire pour éviter les spikes hors zone éclairée (analogue à `re_perceive_per_substep` markers V1).
