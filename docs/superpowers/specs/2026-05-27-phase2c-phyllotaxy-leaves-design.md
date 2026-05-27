# Phase 2C — Phyllotaxie & feuilles

Date : 2026-05-27
Status : design proposé, en attente de revue utilisateur

Suite de la feuille de route de réalisme botanique. Phase 2C traite les
suggestions Priorité 2 #4 et #5 du document de revue :

1. **Phyllotaxie décussée** — nouveau mode `decussate` : paires opposées
   alternant 90° par node (érable, frêne, dogwood).
2. **Feuilles sun/shade** — la taille des feuilles varie avec
   `light_factor` de l'internode hôte. Feuilles d'ombre plus grandes,
   feuilles de soleil plus petites.

Dépend de : Phase 2A pour `axis_order` dans phyllotaxie. Phase 2B
indépendante.

Phases suivantes (hors scope) :
- Phase 2D : élongation progressive + croissance secondaire dynamique

---

## 1. Motivation

### 1.1 Décussation

Les `mode` actuels (`alternate`, `opposite`, `whorled`) couvrent 3 patterns
botaniques mais ratent un quatrième commun : la **décussation**, où
chaque paire opposée est tournée de 90° par rapport à la précédente.
C'est le pattern de l'érable, du frêne, du marronnier, du dogwood. Avec
le mode `opposite` actuel, toutes les paires restent dans le même plan
→ les feuilles forment des "rangées" alignées peu réalistes.

### 1.2 Feuilles sun/shade

Les feuilles sont actuellement de taille uniforme via `geom.leaf_size`.
Or les feuilles de canopée supérieure (plein soleil) sont plus petites
et plus épaisses, tandis que les feuilles d'ombre sont plus grandes
(jusqu'à 2×) et plus minces pour capter plus de photons. Cette
**hétérophyllie sun/shade** est responsable du dégradé visuel de
densité entre cime brillante et sous-canopée mate.

Le grid de lumière (V2) est déjà calculé — `light_factor` est disponible
par bud. Il suffit de propager cette info aux feuilles au moment du
build geom.

---

## 2. Scope

**In** :
- `PhyllotaxyConfig.mode` : ajout de la valeur `"decussate"`.
- `phyllotaxy.py::lateral_bud_directions` : implémentation du mode décussé.
- `GeomConfig` : nouveau champ `leaf_sun_shade_k: float = 0.0`.
- `Internode` : nouveau champ `light_factor: float = 1.0` (capturé au
  moment de la création depuis le bud parent).
- `geom/leaves.py` : application du facteur sun/shade à la taille de
  chaque feuille.
- Présets oak/birch mis à jour (sun/shade activé pour ces deux feuillus
  + décussation **non** appliquée par défaut — décussation est pour érable
  futur).
- Nouveau préset `maple.yaml` qui montre la décussation à l'œuvre.
- Tests unitaires + intégration.
- Goldens régénérés.

**Out** :
- Pas de variation d'`aspect` (forme) ni `splay` (orientation) avec la
  lumière. Phase 2C couvre **uniquement la taille**.
- Pas de modèle physique de feuille individuelle (toujours quad textured).
- Pas de modification du voxel grid pour tenir compte de la taille
  variable des feuilles (le `leaf_area` reste constant pour Beer-Lambert).
- Pas de nouveau pattern phyllotaxique au-delà de décussation (les
  spiroptactiques 2/5 etc. restent absentes).

---

## 3. Architecture

```
config.py
├─ PhyllotaxyConfig
│   - mode: Literal["alternate", "opposite", "whorled"]
│   + mode: Literal["alternate", "opposite", "whorled", "decussate"]
└─ GeomConfig
    + leaf_sun_shade_k: float = 0.0

sim/tree.py
└─ Internode
    + light_factor: float = 1.0

sim/phyllotaxy.py::lateral_bud_directions
    + branche pour mode "decussate":
        k = 2
        node_decussate_offset = (math.pi/2) * (node_index % 2)
        base_azimuth = divergence * node_index + node_decussate_offset
      (divergence_angle_deg reste utilisé mais s'ajoute à l'offset 90°)

sim/simulator.py
    LORS DE la création d'un Internode, capturer light_factor du bud parent:
        light_factor_for_iod = (
            light_info.light_factor.get(cur, 1.0)
            if light_info is not None else 1.0
        )
        iod = Internode(..., light_factor=light_factor_for_iod, ...)

geom/leaves.py
    Au moment du build d'une feuille sur internode `iod`:
        eff_size = cfg.geom.leaf_size * (
            1 + cfg.geom.leaf_sun_shade_k * (1.0 - iod.light_factor)
        )
        eff_size = max(0.5 * cfg.geom.leaf_size,
                       min(2.0 * cfg.geom.leaf_size, eff_size))
        # ... build quad avec eff_size au lieu de cfg.geom.leaf_size

configs/species/{oak,birch}.yaml
    + leaf_sun_shade_k > 0

configs/species/maple.yaml (NOUVEAU)
    mode: decussate
```

---

## 4. Spécification détaillée

### 4.1 `PhyllotaxyConfig.mode` — ajout de `decussate`

```python
mode: Literal["alternate", "opposite", "whorled", "decussate"] = field(
    default="alternate", metadata={"ui": {"label": "Mode"}}
)
```

### 4.2 `phyllotaxy.py::lateral_bud_directions` — branche décussée

```python
if cfg.mode == "alternate":
    k = 1
    base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index
elif cfg.mode == "opposite":
    k = 2
    base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index
elif cfg.mode == "whorled":
    k = max(1, cfg.whorl_count)
    base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index
elif cfg.mode == "decussate":
    k = 2
    # Chaque node alterne de 90° par rapport au précédent.
    # divergence_angle_deg agit comme un offset cumulatif modulable
    # (typiquement laissé à 90° pour décussation pure ; valeurs autres
    # créent des spirales décussées).
    base_azimuth = (
        math.radians(cfg.divergence_angle_deg) * node_index
        + (math.pi / 2.0) * (node_index % 2)
    )
else:
    raise ValueError(f"unknown phyllotaxy mode: {cfg.mode!r}")
```

Pour décussation pure (canonique), l'utilisateur met `divergence_angle_deg:
0.0` et chaque paire est tournée de 90° exactement. Valeur par défaut
existante (137.5°) crée une spirale décussée — bien pour variation
stylistique mais hors-canon.

Documentation YAML :
```yaml
phyllotaxy:
  mode: decussate
  divergence_angle_deg: 0.0      # 0° = décussation pure
                                 # > 0° = spirale décussée
```

### 4.3 `GeomConfig.leaf_sun_shade_k`

```python
# NOUVEAU champ ajouté à GeomConfig
leaf_sun_shade_k: float = field(
    default=0.0,
    metadata={"ui": {"min": 0.0, "max": 2.0, "step": 0.05}},
)
```

Formule appliquée :
```
eff_size = leaf_size * (1 + k * (1 - light_factor))
```

- `k=0` : taille constante (comportement actuel).
- `k=1` : feuille à light_factor=0 fait 2× la taille de feuille à
  light_factor=1.
- `k=2` : feuille à light_factor=0 fait 3× la taille de feuille à
  light_factor=1.

Clamp dur dans `[0.5*leaf_size, 2.0*leaf_size]` pour éviter les feuilles
pathologiques aux extrêmes de light_factor.

Validation : `0 ≤ k ≤ 2`.

Si `k > 0` mais `cfg.light.enabled = False`, ce n'est pas une erreur (les
`light_factor=1.0` par défaut donnent feuilles de taille standard
partout), mais un avertissement log : "leaf_sun_shade_k>0 sans light
enabled — aucun effet". Pas de raise.

### 4.4 `Internode.light_factor`

```python
@dataclass(eq=False)
class Internode:
    parent_node: Node
    child_node: Node
    length: float
    is_main_axis: bool
    diameter: float = 0.0
    window: int = 5
    light_factor: float = 1.0       # NOUVEAU
    quality_history: deque[float] = field(init=False)
```

Capturé une seule fois à la création de l'internode (au moment où le
bud parent grandit). Pas mis à jour ensuite — c'est la lumière "au moment
où la feuille s'est formée" qui détermine sa taille.

Justification : modéliser la lumière du moment T pour une feuille créée
à T est botaniquement correct (la feuille adapte sa morphologie quand
elle se développe ; elle ne change pas ensuite). Évite aussi un cycle
de recalcul à chaque iteration.

### 4.5 `simulator.py` — capture light_factor

Dans le substep loop, au site de création de l'Internode (l. 210-216) :

```python
lf = (
    float(light_info.light_factor.get(cur, 1.0))
    if light_info is not None else 1.0
)
iod = Internode(
    parent_node=cur.parent_node,
    child_node=new_node,
    length=length,
    is_main_axis=is_main,
    window=cfg.shedding.window,
    light_factor=lf,                  # NOUVEAU
)
```

### 4.6 `geom/leaves.py` — application du facteur

Le fichier construit chaque feuille à partir d'un internode terminal-proximal.
Modification au site où `leaf_size` est utilisé :

```python
# Pseudo-diff
def _emit_leaf(iod: Internode, cfg: GeomConfig, ...) -> ...:
    eff_size = cfg.leaf_size
    if cfg.leaf_sun_shade_k > 0.0:
        eff_size *= 1.0 + cfg.leaf_sun_shade_k * (1.0 - iod.light_factor)
        # clamp
        eff_size = max(0.5 * cfg.leaf_size, min(2.0 * cfg.leaf_size, eff_size))
    # ... utiliser eff_size pour le quad de la feuille (au lieu de cfg.leaf_size) ...
```

`leaf_aspect` et `leaf_splay_deg` restent constants. `leaf_cluster_count`
aussi (le nombre de feuilles par cluster est indépendant de la lumière).

### 4.7 Voxel grid (V2 light) — pas de changement

Le grid de lumière utilise `leaf_area` constant pour Beer-Lambert. On
**ne** met **pas** à jour ce paramètre selon le sun/shade k. Justification :
- Le voxel grid voit l'absorption agrégée par cellule, pas chaque feuille.
- Couplage circulaire (taille feuille → absorption → light_factor → taille
  feuille) introduirait des oscillations ou nécessiterait une passe à
  point fixe.
- L'effet est purement visuel (rendu glTF) pas dynamique.

Ce non-couplage est documenté comme limitation acceptée.

---

## 5. Présets

### 5.1 `oak.yaml`

Ajouts au préset Phase 2A/2B :
```yaml
geom:
  # ... existant ...
  leaf_sun_shade_k: 0.7    # forte hétérophyllie (chêne en sous-bois)
```

### 5.2 `birch.yaml`

```yaml
geom:
  leaf_sun_shade_k: 0.4    # plus modéré (bouleau plus héliophile)
```

### 5.3 `pine.yaml`

```yaml
geom:
  leaf_sun_shade_k: 0.0    # aiguilles ne varient pas (pas de plasticité)
```

### 5.4 `maple.yaml` — NOUVEAU préset

Pour montrer la décussation. Profile : monopodial modéré (érable
champêtre), couronne arrondie, feuilles décussées et largement sun/shade
réactives.

```yaml
envelope:
  shape: ellipsoid
  rx: 4.0
  ry: 5.5
  rz: 4.0
  marker_count: 22000
sim:
  internode_length: 0.16
  internode_length_jitter: 0.10
  lambda_apical: 0.80
  alpha_basipetal: 2.1
  max_iterations: 42
  sympodial:
    enabled: true
    q_threshold: 1.3
    n_consecutive_steps: 3
  shade_mortality:                  # Phase 2B
    enabled: true
    light_threshold: 0.18
    n_consecutive_steps: 3
tropism:
  w_perception: 1.0
  w_orthotropy_main: 0.32
  w_orthotropy_lateral: 0.04
  w_gravitropism_main: 0.0
  w_gravitropism_lateral: 0.0
  w_plagiotropism_main: 0.0
  w_plagiotropism_lateral: 0.28
  w_phototropism: 0.30
  w_direction_inertia: 0.5
  axis_decay: 0.85
phyllotaxy:
  mode: decussate                   # ← caractéristique
  divergence_angle_deg: 0.0         # décussation pure
  whorl_count: 2
  branch_angle_by_order: [55.0, 38.0, 28.0, 22.0]
  divergence_jitter_deg: 4.0
  branch_angle_jitter_deg: 4.0
  dormant_reserve_count: 2          # Phase 2B
shedding:
  quality_threshold: 0.12
  window: 5
  enabled: true
  reactivation_count: 1
sag:
  enabled: true
  k: 0.006
  max_bend_deg: 4.0
  rigid_axis_order: 1
geom:
  pipe_exponent: 2.40
  leaf_size: 0.12
  leaf_aspect: 1.1            # feuilles d'érable plus larges que carrées
  leaf_cluster_count: 2       # paire décussée
  leaf_splay_deg: 30.0
  foliage_depth: 4
  leaf_sun_shade_k: 0.6
```

---

## 6. Tests

### 6.1 Unitaires

**`tests/unit/test_phyllotaxy.py`** (ajouts) :
- `test_decussate_two_buds_per_node` — mode decussate ⇒ 2 directions.
- `test_decussate_alternates_90_per_node` — directions au node n+1 sont
  ~90° tournées par rapport à node n. Vérification via dot product des
  projections horizontales.
- `test_decussate_with_nonzero_divergence` — `divergence_angle_deg=10°` ⇒
  spirale décussée (chaque paire un peu tournée par rapport à la
  précédente, plus 90° par node impair).

**`tests/unit/test_leaves.py`** (ajouts) :
- `test_leaf_size_unchanged_when_k_zero` — k=0 ⇒ taille constante peu
  importe light_factor.
- `test_leaf_size_scales_with_shadow` — k>0, light_factor=0.3 ⇒ taille
  > taille à light_factor=1.0.
- `test_leaf_size_clamped_low` — k=5, light_factor=1 ⇒ taille ≥
  0.5*leaf_size.
- `test_leaf_size_clamped_high` — k=5, light_factor=0 ⇒ taille ≤
  2.0*leaf_size.

**`tests/unit/test_simulator_light_capture.py`** :
- `test_internode_captures_bud_light_factor` — light_info avec value
  0.3 pour bud ⇒ internode créé avec `light_factor=0.3`.
- `test_internode_default_light_factor_one_when_no_light` — sans
  light_info ⇒ `light_factor=1.0`.

### 6.2 Intégration

**`tests/integration/test_decussate_maple.py`** :
- Simuler maple preset 25 iterations.
- Vérifier que les paires de laterals sont approximativement
  décussées : pour 10 nodes consécutifs, mesurer l'angle entre les paires
  successives. Médiane attendue ≈ 90° ± 15°.

**`tests/integration/test_sun_shade_oak.py`** :
- Simuler oak avec light enabled + leaf_sun_shade_k=0.7, 40 iterations.
- Pour les feuilles de canopée supérieure (y > 0.7 * ry) vs inférieure
  (y < 0.3 * ry), calculer la taille moyenne.
- Attendu : taille moyenne basse > 1.3 × taille moyenne haute.

### 6.3 Goldens

Régénération des goldens oak, birch, pine **et** ajout d'un nouveau
golden maple.

---

## 7. Risques et points ouverts

### 7.1 Lecture de la décussation

Quand `divergence_angle_deg` reste à 137.5° par défaut, le mode décussé
crée une **spirale décussée** plutôt qu'une décussation canonique.
Documentation explicite nécessaire dans le YAML des présets pour mettre
`0.0`. Test garantit le comportement attendu.

### 7.2 Clamp leaf_size asymétrique

Le clamp `[0.5×, 2.0×]` est asymétrique de référence : feuilles d'ombre
peuvent grandir 2×, feuilles soleil rapetisser seulement 0.5×. C'est
biologiquement correct (les feuilles soleil n'ont pas besoin de
rapetisser autant que les feuilles d'ombre ont besoin de grandir). Garde
`leaf_size` lisible comme "taille de référence pour pleine lumière".

### 7.3 Internode.light_factor stocké à T_création

Une feuille émise sur un internode profond aura `light_factor` figé à
sa valeur initiale. Si la canopée se ferme ensuite, la feuille ne
"rapetisse" pas. C'est volontaire (cohérent avec la biologie des feuilles
adaptées une fois développées) mais introduit une légère imprécision
visuelle : les feuilles d'un même internode capturé tôt et tard dans la
simulation peuvent légèrement différer. Acceptable.

### 7.4 Performance leaves.py

L'ajout du calcul `eff_size` est O(1) par feuille — négligeable.

### 7.5 Couplage feuille → voxel grid désactivé

Voir 4.7 — ce couplage circulaire est explicitement non implémenté.
L'effet est visuel uniquement. Si on voulait fermer la boucle dans une
phase future, il faudrait une passe à point fixe.

---

## 8. Non-objectifs

- Pas de variation d'aspect ou splay avec la lumière.
- Pas de feuille par feuille — toujours par cluster sur internode.
- Pas de feuilles caduques / sempervirentes (toutes les feuilles sont
  rendues, peu importe l'âge de l'internode).
