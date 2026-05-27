# Phase 1 — Fondations de réalisme

Date : 2026-05-27
Status : design proposé, en attente de revue utilisateur

Première phase de la feuille de route issue de
[`docs/2026-05-27-simulation-review.md`](../../2026-05-27-simulation-review.md).
Cette phase couvre les suggestions #1, #2 et #7 du document de revue : exploiter
`is_main_axis` dans les tropismes, ajouter du jitter phyllotaxique, et rendre
`internode_length` stochastique. Préset tweaks oak/pine/birch inclus.

Phases ultérieures (hors scope) :
- Phase 2 : plagiotropisme dynamique par poids + angle d'insertion âge-dépendant
- Phase 3 : croissance préformée, réitération, `alpha_basipetal` âge-dépendant
- Phase 4 : phyllotaxie au niveau feuille individuelle
- Phase 5 : validation visuelle automatisée

---

## 1. Motivation

L'implémentation actuelle marque chaque internode `is_main_axis: bool` au moment
de sa création, mais ce flag n'est consommé que par `bh.py`, `tubes.py` et
`sag.py`. Aucun signal main-vs-latéral n'arrive aux tropismes, à la phyllotaxie
ou au shedding. Conséquence : la dégradation par `axis_decay^order` ne capture
qu'une décroissance continue, pas la **discontinuité** biologique entre l'axe
principal (souvent orthotrope strict) et les axes latéraux (souvent
plagiotropes voire négativement gravitropes).

Parallèlement, la phyllotaxie est parfaitement régulière (`base_azimuth =
137.5° * node_index`) et `internode_length` est constant. Ces deux régularités
donnent une lecture "synthétique" très reconnaissable.

Le but de la Phase 1 est de corriger ces trois points avec le minimum de
mécanique nouvelle : pas de nouveau modèle physique, pas de nouvelle passe sur
l'arbre, juste des poids tropiques distincts main/latéral et de la
stochasticité gaussienne contrôlée.

---

## 2. Scope

**In** :
- `TropismConfig` : poids `w_orthotropy_main`/`_lateral` et `w_gravitropism_main`/`_lateral`
- `PhyllotaxyConfig` : `divergence_jitter_deg`, `branch_angle_jitter_deg`
- `SimConfig` : `internode_length_jitter`
- `tropisms.py::growth_direction` : nouveau paramètre `is_main_axis: bool`
- `phyllotaxy.py::lateral_bud_directions` : nouveau paramètre `seed: int` + application du jitter
- `simulator.py` : 3 sites de call modifiés + jitter d'internode_length
- Présets oak/pine/birch mis à jour
- Suppression de `_apply_section_aliases` dans `config.py` (mort)
- Goldens régénérés

**Out** :
- Pas de modification de `shedding.py` (la consommation de `is_main_axis` y est
  laissée à une phase ultérieure si on identifie un mécanisme concret).
- Pas de modification de `phyllotaxy.py` au-delà du jitter (les `branch_angle`
  main vs latéral viendront en Phase 2 avec l'angle d'insertion dynamique).
- Pas de tropisme par poids (Phase 2).
- Le `sag` reste activé pour le birch (atténué) — sa suppression complète au
  profit du tropisme par poids est l'affaire de la Phase 2.
- Pas de backward-compat : le projet est en mode PoC, les YAML existants sont
  réécrits, les goldens sont régénérés.

---

## 3. Architecture

Trois changements de code dans trois modules, plus mise à jour des trois
présets. Aucun fichier nouveau.

```
config.py
├─ TropismConfig
│   - w_orthotropy             [supprimé]
│   - w_gravitropism           [supprimé]
│   + w_orthotropy_main, w_orthotropy_lateral
│   + w_gravitropism_main, w_gravitropism_lateral
├─ PhyllotaxyConfig
│   + divergence_jitter_deg : float = 0.0
│   + branch_angle_jitter_deg : float = 0.0
└─ SimConfig
    + internode_length_jitter : float = 0.0

tropisms.py::growth_direction
    + paramètre obligatoire is_main_axis: bool
    → choisit w_orthotropy_main vs _lateral, idem gravitropism

phyllotaxy.py::lateral_bud_directions
    + paramètre obligatoire seed: int
    → si jitter > 0, dérive un Generator par (seed, "phyllotaxy", node_index)
       perturbe base_azimuth ~ N(0, σ_div) et branch_angle ~ N(0, σ_branch)
       clamp branch_angle dans [0°, 90°]

simulator.py
    → is_main_axis = (cur is cur.parent_node.terminal_bud) passé partout
    → internode_length jittered via SeedSequence([cfg.seed, "ilen", iter, idx])
       factor ~ N(1, σ_ilen) clampé dans [0.5, 1.5]

configs/species/{oak,pine,birch}.yaml
    → réécrits sans w_orthotropy/w_gravitropism, avec les nouveaux _main/_lateral
    → divergence_jitter_deg + branch_angle_jitter_deg + internode_length_jitter
```

---

## 4. Spécification détaillée des composants

### 4.1 `TropismConfig`

```python
@dataclass(frozen=True)
class TropismConfig:
    w_perception: float = 1.0
    w_orthotropy_main: float = 0.3        # axe principal vers UP
    w_orthotropy_lateral: float = 0.1     # latéraux moins orthotropes
    w_gravitropism_main: float = 0.0      # rarement utilisé
    w_gravitropism_lateral: float = 0.0   # >0 pour pendula/willow
    w_phototropism: float = 0.0
    w_direction_inertia: float = 0.4
    photo_direction: tuple = (0.0, 1.0, 0.0)
    axis_decay: float = 1.0
```

Tous les nouveaux champs doivent être ≥ 0 (validé en `Config.__post_init__`).

Métadonnées UI (`metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}}`)
pour chacun des 4 nouveaux champs.

### 4.2 `PhyllotaxyConfig`

```python
@dataclass(frozen=True)
class PhyllotaxyConfig:
    mode: Literal["alternate", "opposite", "whorled"] = "alternate"
    whorl_count: int = 3
    divergence_angle_deg: float = 137.5
    branch_angle_deg: float = 45.0
    divergence_jitter_deg: float = 0.0   # σ gaussien en degrés
    branch_angle_jitter_deg: float = 0.0
```

Validation : `divergence_jitter_deg ≥ 0`, `branch_angle_jitter_deg ≥ 0`.
UI : `{"min": 0.0, "max": 30.0, "step": 0.5}` pour divergence,
`{"min": 0.0, "max": 20.0, "step": 0.5}` pour branch_angle.

### 4.3 `SimConfig`

Ajout d'un seul champ :
```python
internode_length_jitter: float = 0.0  # σ comme fraction de internode_length
```

Validation : `0.0 ≤ internode_length_jitter ≤ 0.5`. Au-delà de 0.5 le RNG
gaussien produit régulièrement des valeurs hors clamp.
UI : `{"min": 0.0, "max": 0.5, "step": 0.01}`.

### 4.4 `tropisms.py::growth_direction`

```python
def growth_direction(
    *,
    v_perception: np.ndarray,
    current_direction: np.ndarray,
    cfg: TropismConfig,
    is_main_axis: bool,                      # nouveau, obligatoire
    light_gradient: np.ndarray | None = None,
    axis_order: int = 0,
) -> np.ndarray:
    ...
    decay = cfg.axis_decay ** axis_order
    w_ortho = cfg.w_orthotropy_main if is_main_axis else cfg.w_orthotropy_lateral
    w_gravi = cfg.w_gravitropism_main if is_main_axis else cfg.w_gravitropism_lateral
    blend = (
        cfg.w_perception * v_perception
        + (w_ortho * decay) * _UP
        + (w_gravi * decay) * _DOWN
        + (cfg.w_phototropism * decay) * photo
        + cfg.w_direction_inertia * current_direction
    )
    ...
```

### 4.5 `phyllotaxy.py::lateral_bud_directions`

```python
def lateral_bud_directions(
    growth_direction: np.ndarray,
    cfg: PhyllotaxyConfig,
    node_index: int,
    *,
    seed: int,                          # nouveau, obligatoire
) -> np.ndarray:
    ...
    base_az = math.radians(cfg.divergence_angle_deg) * node_index
    branch_ang = math.radians(cfg.branch_angle_deg)
    if cfg.divergence_jitter_deg > 0 or cfg.branch_angle_jitter_deg > 0:
        ss = np.random.SeedSequence([seed, "phyllotaxy", node_index])
        rng = np.random.default_rng(ss.generate_state(1)[0])
        base_az += math.radians(rng.normal(0, cfg.divergence_jitter_deg))
        branch_ang += math.radians(rng.normal(0, cfg.branch_angle_jitter_deg))
        branch_ang = max(0.0, min(math.pi / 2, branch_ang))
    ...
```

Court-circuit si les deux σ sont nuls — pas d'appel RNG, comportement
strictement déterministe indépendant de `seed`.

### 4.6 `simulator.py`

Trois sites modifiés dans `_iteration_step` :

**Site A — appel à `growth_direction`** (l. 166-172 actuel) :
```python
is_main = (cur is cur.parent_node.terminal_bud)
d = growth_direction(
    v_perception=res.direction[cur],
    current_direction=cur.direction,
    cfg=cfg.tropism,
    is_main_axis=is_main,
    light_gradient=light_grad,
    axis_order=cur.axis_order,
)
```

**Site B — calcul de la longueur d'internode** (l. 182, 198-204) :
```python
length = cfg.sim.internode_length
if cfg.sim.internode_length_jitter > 0:
    ss = np.random.SeedSequence([cfg.seed, "ilen", iteration, state.node_index])
    rng = np.random.default_rng(ss.generate_state(1)[0])
    factor = max(0.5, min(1.5, rng.normal(1.0, cfg.sim.internode_length_jitter)))
    length = cfg.sim.internode_length * factor
new_pos = cur.position + d * length
iod = Internode(
    parent_node=cur.parent_node,
    child_node=new_node,
    length=length,
    is_main_axis=is_main,
    window=cfg.shedding.window,
)
```

**Site C — appel à `lateral_bud_directions`** (l. 217) :
```python
lateral_dirs = lateral_bud_directions(
    d, cfg.phyllotaxy,
    node_index=state.node_index,
    seed=cfg.seed,
)
```

### 4.7 Suppression de `_apply_section_aliases`

Le helper `_apply_section_aliases` dans `config.py` (l. 277-283) gère un alias
legacy `w_gravity → w_orthotropy`. Puisque les champs `w_orthotropy` et
`w_gravitropism` disparaissent, l'alias devient doublement obsolète. Le helper
et son call site (l. 310) sont supprimés.

---

## 5. Présets

### 5.1 `oak.yaml`

```yaml
envelope:
  shape: half_ellipsoid
  rx: 5.0
  ry: 6.5
  rz: 5.0
  marker_count: 25000
sim:
  internode_length: 0.18
  internode_length_jitter: 0.12
  lambda_apical: 0.75
  alpha_basipetal: 2.2
  max_iterations: 45
tropism:
  w_orthotropy_main: 0.35
  w_orthotropy_lateral: 0.05
  w_gravitropism_main: 0.0
  w_gravitropism_lateral: 0.0
  w_phototropism: 0.35
  w_direction_inertia: 0.5
  axis_decay: 0.65
phyllotaxy:
  mode: alternate
  divergence_angle_deg: 137.5
  divergence_jitter_deg: 6.0
  branch_angle_deg: 60
  branch_angle_jitter_deg: 5.0
shedding:
  quality_threshold: 0.15
light:
  enabled: true
  k_absorption: 0.55
sag:
  enabled: true
  k: 0.005
  max_bend_deg: 5.0
  rigid_axis_order: 1
geom:
  ring_sides: 10
  pipe_exponent: 2.3
  r_tip: 0.008
  bark_color: [0.32, 0.22, 0.14]
  bark_texture: "proc:oak_bark"
  leaf_texture: "proc:oak_leaf"
  leaf_size: 0.14
  leaf_cluster_count: 3
  leaf_aspect: 1.0
  leaf_splay_deg: 25
  foliage_depth: 4
```

### 5.2 `pine.yaml`

```yaml
envelope:
  shape: cone
  rx: 2.5
  ry: 9.0
  rz: 2.5
  marker_count: 18000
sim:
  internode_length: 0.18
  internode_length_jitter: 0.08
  lambda_apical: 0.85
  alpha_basipetal: 1.8
  max_iterations: 40
tropism:
  w_orthotropy_main: 0.30
  w_orthotropy_lateral: 0.05
  w_gravitropism_main: 0.0
  w_gravitropism_lateral: 0.02
  w_phototropism: 0.20
  w_direction_inertia: 0.8
  axis_decay: 0.85
phyllotaxy:
  mode: whorled
  whorl_count: 5
  divergence_angle_deg: 72
  divergence_jitter_deg: 3.0
  branch_angle_deg: 75
  branch_angle_jitter_deg: 4.0
shedding:
  quality_threshold: 0.20
light:
  enabled: true
  k_absorption: 0.65
geom:
  ring_sides: 8
  pipe_exponent: 2.3
  r_tip: 0.007
  bark_color: [0.45, 0.25, 0.18]
  bark_texture: "proc:pine_bark"
  leaf_texture: "proc:pine_needle"
  leaf_size: 0.06
  leaf_cluster_count: 5
  leaf_aspect: 0.025
  leaf_splay_deg: 25
  foliage_depth: 3
```

### 5.3 `birch.yaml`

```yaml
envelope:
  shape: ellipsoid
  rx: 2.5
  ry: 7.0
  rz: 2.5
  marker_count: 20000
sim:
  internode_length: 0.18
  internode_length_jitter: 0.15
  lambda_apical: 0.95
  alpha_basipetal: 2.0
  max_iterations: 45
tropism:
  w_orthotropy_main: 0.40
  w_orthotropy_lateral: 0.10
  w_gravitropism_main: 0.0
  w_gravitropism_lateral: 0.15
  w_phototropism: 0.25
  w_direction_inertia: 0.50
  axis_decay: 0.85
sag:
  enabled: true
  k: 0.010
  max_bend_deg: 6.0
  rigid_axis_order: 2
phyllotaxy:
  mode: alternate
  divergence_angle_deg: 137.5
  divergence_jitter_deg: 5.0
  branch_angle_deg: 45
  branch_angle_jitter_deg: 4.0
shedding:
  quality_threshold: 0.02
light:
  enabled: true
  k_absorption: 0.45
geom:
  ring_sides: 8
  pipe_exponent: 2.25
  r_tip: 0.006
  bark_color: [0.85, 0.82, 0.75]
  bark_texture: "proc:birch_bark"
  leaf_texture: "proc:birch_leaf"
  leaf_size: 0.05
  leaf_cluster_count: 3
  leaf_aspect: 0.7
  leaf_splay_deg: 20
  foliage_depth: 3
```

Le `w_gravitropism_lateral: 0.15` du birch capture une partie de l'effet
pendula directement dans la simulation. Le sag reste activé mais atténué
(`k: 0.010` au lieu de `0.015`) — sa suppression complète viendra en Phase 2.

---

## 6. Validation et modes de défaillance

| Situation | Comportement | Raison |
|---|---|---|
| `seed=0` + jitter activé | Jitter fonctionne, déterministe via `SeedSequence([0, ...])` | `seed=0` est une valeur valide |
| Tous les σ phyllotaxie nuls | Court-circuit, pas d'appel RNG | Économie + identique au comportement pré-jitter |
| `internode_length_jitter=0` | Court-circuit pareil | Idem |
| `branch_angle` hors [0°, 90°] après jitter | Hard clamp à la borne | Évite des branches inversées |
| `internode_length` factor hors [0.5, 1.5] | Hard clamp | Évite longueurs négatives ou démesurées |
| Champ jitter ou poids négatif dans YAML | `ConfigError` à `__post_init__` | Erreur de config explicite |
| `internode_length_jitter > 0.5` dans YAML | `ConfigError` | Au-delà, σ écrase systématiquement le clamp |

---

## 7. Stratégie de tests

### 7.1 Tests à modifier

| Fichier | Changement |
|---|---|
| `tests/sim/test_tropisms.py` | Tous les appels reçoivent `is_main_axis=...`. Nouveau test paramétré main vs lateral. |
| `tests/sim/test_phyllotaxy.py` | Tous les appels reçoivent `seed=...`. Nouveaux tests jitter. |
| `tests/test_config.py` | Mise à jour des champs vérifiés, nouvelles assertions sur les bornes. |
| `tests/test_config_yaml.py` | YAML de test mis à jour si nécessaire. |
| `tests/test_config_species.py` | Les 3 nouveaux présets parsent OK. |

### 7.2 Nouveaux tests

- `test_tropisms.py::test_growth_direction_main_vs_lateral` : avec
  `w_orthotropy_main=1.0`, `w_orthotropy_lateral=0.0`, vérifier que `is_main_axis=True`
  pousse vers +Y et que `is_main_axis=False` ignore l'orthotropie.
- `test_phyllotaxy.py::test_jitter_deterministic` : même seed → mêmes vecteurs.
- `test_phyllotaxy.py::test_jitter_seeds_differ` : seeds différents → vecteurs
  différents.
- `test_phyllotaxy.py::test_jitter_zero_matches_legacy` : jitter=0 quel que
  soit seed → résultats identiques à un calcul sans jitter.
- `test_phyllotaxy.py::test_jitter_clamps_branch_angle` : avec σ très grand,
  l'angle reste dans [0, 90°].
- `test_simulator.py::test_internode_length_jitter_deterministic` : 2 runs même
  seed → mêmes longueurs exactes.
- `test_simulator.py::test_internode_length_jitter_disabled` : `jitter=0` →
  toutes longueurs `== cfg.sim.internode_length`.

### 7.3 Goldens

`tests/golden/test_goldens.py` et `tests/golden/test_species_goldens.py` :
régénération en deux étapes après l'implémentation :

1. `pytest --update-goldens tests/golden/` : régénère les hashes.
2. Inspection visuelle obligatoire : générer un GLB pour chaque preset avant
   et après, valider dans `palubicki edit`. Critères qualitatifs :
   - Chêne : primaires plus horizontaux, divergence moins régulière.
   - Pin : verticilles toujours nets, latéraux peu inclinés.
   - Bouleau : effet pleureur principalement via `w_gravitropism_lateral`, sag
     atténué.
3. Si OK, commit des nouveaux hashes. Sinon retour aux defaults.

---

## 8. Ordre d'exécution

**Stage 1 — Config (séquentiel)**
1. Modifier `TropismConfig`, `PhyllotaxyConfig`, `SimConfig`.
2. Ajouter validations dans `Config.__post_init__`.
3. Supprimer `_apply_section_aliases` et son call site.
4. Mettre à jour `tests/test_config.py`, `test_config_yaml.py`.

**Stage 2 — Logique sim (séquentiel)**
5. `tropisms.py::growth_direction` + `tests/sim/test_tropisms.py`.
6. `phyllotaxy.py::lateral_bud_directions` + `tests/sim/test_phyllotaxy.py`.
7. `simulator.py` (3 sites + jitter d'internode_length) + tests associés.

**Stage 3 — Présets (parallélisable)**
8. `oak.yaml`, `pine.yaml`, `birch.yaml` réécrits.
9. `tests/test_config_species.py` mis à jour.

**Stage 4 — Goldens + validation visuelle (séquentiel, fin)**
10. Lancer `pytest` : tout passe sauf goldens.
11. Inspection visuelle des 3 présets dans `palubicki edit`.
12. `pytest --update-goldens` si OK.

---

## 9. Critères "Done"

- [ ] `pytest` passe à 100% avec goldens régénérés.
- [ ] Les 3 présets produisent des silhouettes qualitativement améliorées,
      validées visuellement.
- [ ] Diff YAML cohérent : pas de champ legacy résiduel.
- [ ] `_apply_section_aliases` supprimé, `config.py` plus court qu'avant.
- [ ] `palubicki edit` expose les nouveaux sliders et la régénération marche.

---

## 10. Hors scope explicite

- `shedding.py` non modifié — la consommation de `is_main_axis` y est laissée à
  une phase ultérieure si un mécanisme concret émerge.
- Plagiotropisme dynamique par poids → Phase 2.
- Angle d'insertion qui s'ouvre avec l'âge/poids → Phase 2.
- Croissance préformée, réitération, `alpha_basipetal` âge-dépendant → Phase 3.
- Phyllotaxie au niveau feuille individuelle → Phase 4.
- Métriques de fractalité / validation par silhouettes → Phase 5.
- Le sag du bouleau reste activé (atténué) — suppression en Phase 2.
- Pas de backward-compat : YAML existants réécrits, goldens régénérés, signatures
  de fonctions internes modifiées sans fallback.
