# Phase 2A — Architecture de branchement

Date : 2026-05-27
Status : design proposé, en attente de revue utilisateur

Deuxième phase de la feuille de route de réalisme botanique. Phase 2A couvre
les trois améliorations Priorité 1 du document
[`docs/2026-05-27-simulation-review.md`](../../2026-05-27-simulation-review.md)
qui concernent la **topologie et l'orientation** des branches :

1. **Mode sympodial** — l'axe principal abandonne périodiquement la dominance
   et une latérale prend le relais (chêne, érable, tilleul).
2. **Angle de branche par axis_order** — l'angle d'insertion varie selon
   l'ordre de ramification.
3. **Plagiotropisme explicite** — un nouveau terme tropique force les
   latérales vers l'horizontale, indépendamment du tuning gravité/orthotropie.

Phases suivantes (hors scope) :
- Phase 2B : cycle de vie des bourgeons (mortalité à l'ombre, réitération).
- Phase 2C : phyllotaxie décussée + feuilles sun/shade.
- Phase 2D : élongation progressive + croissance secondaire dynamique.

---

## 1. Motivation

### 1.1 Pourquoi le sympodial

L'implémentation actuelle traite tous les arbres comme **monopodiaux** : un
unique `terminal_bud` par node, qui prolonge indéfiniment l'axe principal.
Or les feuillus matures (chêne, érable, frêne, orme, tilleul) sont
**sympodiaux** : l'apex avorte périodiquement, une latérale vigoureuse prend
sa place comme nouveau leader, et l'arbre fork visuellement. C'est *la*
différence visuelle #1 entre conifères (monopodiaux nets) et feuillus
adultes au port étalé. Sans ce mécanisme, nos chênes ressemblent à des
sapins déguisés.

### 1.2 Pourquoi l'angle par ordre

Un seul `branch_angle_deg` global produit une ramification **fractale
régulière** très reconnaissable. En réalité, l'angle d'insertion varie par
ordre : les branches d'ordre 1 (sur le tronc) s'ouvrent à 45–60°, l'ordre 2 à
30–40°, l'ordre 3 à 20–30°. Cette décroissance crée la lecture de **branches
maîtresses massives** vs **ramilles fines et serrées**.

### 1.3 Pourquoi un terme plagiotropisme explicite

Phase 1 a apporté `w_orthotropy_main/_lateral` et
`w_gravitropism_main/_lateral`. C'est suffisant pour faire pleurer un
bouleau, mais la plagiotropie classique (latérales **horizontales**, ni
montantes ni descendantes) demande un équilibre fin entre les deux poids.
Un terme dédié `w_plagiotropism` qui projette directement sur le plan XY
est plus lisible, plus tunable et n'interfère pas avec la gravité réelle
(pour les espèces pendula).

---

## 2. Scope

**In** :
- Nouveau `dataclass` `SympodialConfig` dans `config.py`, exposé via `SimConfig.sympodial`.
- `PhyllotaxyConfig.branch_angle_deg` (scalaire) → `branch_angle_by_order` (tuple de floats).
- `TropismConfig` : nouveaux champs `w_plagiotropism_main` et `w_plagiotropism_lateral`.
- `Bud` : nouveau champ `low_quality_steps: int = 0`.
- `sim/sympodial.py` : nouveau module avec `promote_lateral_if_failing()`.
- `tropisms.py::growth_direction` : ajout du terme plagio dans le blend.
- `phyllotaxy.py::lateral_bud_directions` : nouveau paramètre `axis_order` + lookup dans la liste.
- `simulator.py::_iteration_step` : appel à `promote_lateral_if_failing` après l'allocation BH, transmission de `axis_order` à `lateral_bud_directions`.
- Présets `oak.yaml`, `pine.yaml`, `birch.yaml` réécrits.
- Goldens régénérés complètement.
- Nouveaux tests unitaires (sympodial trigger, promotion logic, angle lookup, plagio horizontal pull).

**Out** :
- Pas de modification du shedding (Phase 2B s'en occupera avec la mortalité à l'ombre).
- Pas de modification des feuilles ni de la phyllotaxie décussée (Phase 2C).
- Pas de dynamique temporelle d'élongation/diamètre (Phase 2D).
- Pas de réitération / bourgeons dormants réveillables (Phase 2B).
- Pas de jitter sur l'angle par ordre — `branch_angle_jitter_deg` reste scalaire.
- **Pas de backward-compat** : mode PoC. Les YAML utilisateurs et tests doivent migrer manuellement.

---

## 3. Architecture

```
config.py
├─ SimConfig
│   + sympodial: SympodialConfig (nouveau sous-dataclass)
├─ PhyllotaxyConfig
│   - branch_angle_deg                  [supprimé]
│   + branch_angle_by_order: tuple[float, ...]
├─ TropismConfig
│   + w_plagiotropism_main: float = 0.0
│   + w_plagiotropism_lateral: float = 0.0
└─ SympodialConfig (nouveau)
    + enabled: bool = False
    + q_threshold: float = 1.0
    + n_consecutive_steps: int = 3

sim/tree.py
└─ Bud
    + low_quality_steps: int = 0

sim/sympodial.py (NOUVEAU)
    + promote_lateral_if_failing(tree, quality, cfg) -> int
      Pour chaque terminal_bud actif :
        si Q < q_threshold : incrémenter low_quality_steps
        sinon              : reset à 0
        si low_quality_steps >= n_consecutive_steps :
          chercher la meilleure latérale sibling avec Q > 0
          si trouvée → promotion (swap dans parent_node, axis_order ajusté)
          sinon       → terminal reste actif (la branche s'arrêtera par
                       elle-même via le mécanisme dormant existant)

sim/tropisms.py::growth_direction
    + nouveau terme dans le blend :
        w_plagio = main si is_main_axis else lateral
        v_plagio = horizontalize(current_direction)
        blend += (w_plagio * decay) * v_plagio

sim/phyllotaxy.py::lateral_bud_directions
    + paramètre obligatoire axis_order: int
    → branch_angle = cfg.branch_angle_by_order[min(axis_order, len-1)]
       (clamp à la dernière valeur si l'ordre dépasse la liste)

sim/simulator.py::_iteration_step
    APRÈS res = perceive(...) et compute quality
    AVANT compute_v_subtree + allocate, DANS la for-loop par tree existante :
        promote_lateral_if_failing(tree, quality, cfg.sim.sympodial)
        # allocation BH voit la nouvelle structure
    DANS le substep loop :
        lateral_bud_directions(..., axis_order=cur.axis_order)

configs/species/{oak,pine,birch}.yaml
    → réécrits avec branch_angle_by_order, w_plagiotropism, et sympodial
```

---

## 4. Spécification détaillée des composants

### 4.1 `SympodialConfig`

```python
@dataclass(frozen=True)
class SympodialConfig:
    """Quand le terminal_bud échoue (Q < seuil) pendant N pas consécutifs,
    la latérale du même node avec la plus haute qualité prend sa place.
    L'ancien terminal meurt. Le nouveau leader, oriente sa direction
    naturellement via les poids tropiques main (plus forts).
    """
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    # Seuil absolu de qualité sous lequel un terminal est considéré "en échec".
    # Q est un nombre de marqueurs claimés ; 1.0 = "le terminal récupère moins
    # d'un marqueur en moyenne". Tuner par espèce.
    q_threshold: float = field(default=1.0, metadata={"ui": {"min": 0.0, "max": 20.0, "step": 0.5}})
    # Nombre de pas consécutifs où Q < q_threshold avant déclenchement.
    # 1 = ultra-sensible (presque chaque échec déclenche fork), 5+ = très
    # patient (seuls les vrais échecs persistants forkent).
    n_consecutive_steps: int = field(default=3, metadata={"ui": {"min": 1, "max": 10, "step": 1}})
```

Validation dans `Config.__post_init__` :
```python
sym = self.sim.sympodial
if sym.q_threshold < 0:
    raise ConfigError(f"sim.sympodial.q_threshold must be >= 0, got {sym.q_threshold}")
if sym.n_consecutive_steps < 1:
    raise ConfigError(f"sim.sympodial.n_consecutive_steps must be >= 1, got {sym.n_consecutive_steps}")
```

### 4.2 `PhyllotaxyConfig`

```python
@dataclass(frozen=True)
class PhyllotaxyConfig:
    mode: Literal["alternate", "opposite", "whorled"] = "alternate"
    whorl_count: int = 3
    divergence_angle_deg: float = 137.5
    # Angle d'insertion (deg) par axis_order. branch_angle_by_order[k] est
    # l'angle des latérales émises par un bourgeon d'axis_order k. Si k
    # dépasse len(list)-1, on clamp à la dernière valeur. Au minimum un
    # élément. Exemple oak : [60, 40, 30, 25].
    branch_angle_by_order: tuple[float, ...] = field(
        default=(45.0,),
        metadata={"ui": {"label": "Branch angles by order"}},
    )
    divergence_jitter_deg: float = 0.0
    branch_angle_jitter_deg: float = 0.0
```

Validation :
```python
if not p.branch_angle_by_order:
    raise ConfigError("phyllotaxy.branch_angle_by_order must have at least one element")
for i, a in enumerate(p.branch_angle_by_order):
    if not (0.0 <= a <= 90.0):
        raise ConfigError(
            f"phyllotaxy.branch_angle_by_order[{i}] must be in [0, 90], got {a}"
        )
```

YAML chargé comme liste, converti en tuple à l'instanciation (cohérent avec
`light.light_direction` et `grid_resolution`). Si l'utilisateur fournit un
scalaire, on raise `ConfigError` — pas de coercition silencieuse (PoC).

### 4.3 `TropismConfig`

```python
@dataclass(frozen=True)
class TropismConfig:
    w_perception: float = 1.0
    w_orthotropy_main: float = 0.3
    w_orthotropy_lateral: float = 0.1
    w_gravitropism_main: float = 0.0
    w_gravitropism_lateral: float = 0.0
    # NOUVEAU : plagiotropisme = poussée vers le plan horizontal.
    # v_plagio = projection de current_direction sur XY, normalisée.
    # Main typiquement 0 (le tronc reste vertical) ; latéral > 0 pour
    # forcer les branches à s'étaler à l'horizontale.
    w_plagiotropism_main: float = 0.0
    w_plagiotropism_lateral: float = 0.0
    w_phototropism: float = 0.0
    w_direction_inertia: float = 0.4
    photo_direction: tuple = (0.0, 1.0, 0.0)
    axis_decay: float = 1.0
```

Validation : ajouter les deux nouveaux champs à la boucle existante de
`Config.__post_init__` qui vérifie ≥ 0.

UI metadata : `{"min": 0.0, "max": 3.0, "step": 0.05}` comme les autres
poids tropiques.

### 4.4 `Bud` — nouveau champ

```python
@dataclass(eq=False)
class Bud:
    position: np.ndarray
    direction: np.ndarray
    axis_order: int
    parent_node: "Node"
    age: int = 0
    state: BudState = BudState.ACTIVE
    low_quality_steps: int = 0     # NOUVEAU
```

Le compteur est incrémenté / reset à chaque iteration par
`promote_lateral_if_failing`. Il n'est jamais persisté hors-mémoire.

### 4.5 `sim/sympodial.py` — nouveau module

```python
# src/palubicki/sim/sympodial.py
from __future__ import annotations

from palubicki.config import SympodialConfig
from palubicki.sim.tree import Bud, BudState, Tree


def promote_lateral_if_failing(
    tree: Tree,
    quality: dict[Bud, float],
    cfg: SympodialConfig,
) -> int:
    """Promeut les latérales qui surpassent leur terminal défaillant.

    Pour chaque ``terminal_bud`` actif dans l'arbre dont Q est sous le
    seuil ``cfg.q_threshold`` pendant ``cfg.n_consecutive_steps`` pas
    consécutifs :
      - cherche le sibling lateral_buds avec le plus haut Q > 0
      - swap dans parent_node : la latérale devient le nouveau terminal_bud,
        l'ancien terminal_bud est retiré et marqué DEAD
      - axis_order de la nouvelle latérale promue est aligné sur celui de
        l'ancien terminal (typiquement décrément de 1)

    Retourne le nombre de promotions effectuées.
    """
    if not cfg.enabled:
        return 0

    promotions = 0
    for bud in list(tree.active_buds):
        if bud.state is not BudState.ACTIVE:
            continue
        node = bud.parent_node
        if node.terminal_bud is not bud:
            continue  # seuls les terminaux sont concernés

        q = quality.get(bud, 0.0)
        if q < cfg.q_threshold:
            bud.low_quality_steps += 1
        else:
            bud.low_quality_steps = 0
            continue

        if bud.low_quality_steps < cfg.n_consecutive_steps:
            continue

        # Chercher la meilleure latérale active
        candidates = [
            lat for lat in node.lateral_buds
            if lat.state is BudState.ACTIVE and quality.get(lat, 0.0) > 0.0
        ]
        if not candidates:
            continue  # pas de successeur ; laisse le mécanisme dormant
                      # existant gérer la fin de cette branche

        best = max(candidates, key=lambda b: quality.get(b, 0.0))

        # Swap : best devient le nouveau terminal_bud
        node.lateral_buds.remove(best)
        node.terminal_bud = best
        best.axis_order = bud.axis_order  # alignement sur main-axis

        # L'ancien terminal meurt
        bud.state = BudState.DEAD

        # Reset compteur sur le nouveau terminal (il vient juste d'être promu)
        best.low_quality_steps = 0

        promotions += 1

    # Nettoyer active_buds : retirer les DEAD
    tree.active_buds = [b for b in tree.active_buds if b.state is not BudState.DEAD]
    return promotions
```

Note d'implémentation : `bud.axis_order = ...` modifie en place un
`dataclass(eq=False)` non frozen, ce qui est cohérent avec le code existant
(`bud.state = BudState.DEAD` etc.).

### 4.6 `tropisms.py::growth_direction`

```python
_UP = np.array([0.0, 1.0, 0.0])
_DOWN = np.array([0.0, -1.0, 0.0])


def growth_direction(
    *,
    v_perception: np.ndarray,
    current_direction: np.ndarray,
    cfg: TropismConfig,
    is_main_axis: bool,
    light_gradient: np.ndarray | None = None,
    axis_order: int = 0,
) -> np.ndarray:
    # ... (code photo inchangé) ...

    decay = float(cfg.axis_decay) ** int(axis_order)
    w_ortho = cfg.w_orthotropy_main if is_main_axis else cfg.w_orthotropy_lateral
    w_gravi = cfg.w_gravitropism_main if is_main_axis else cfg.w_gravitropism_lateral
    w_plagio = cfg.w_plagiotropism_main if is_main_axis else cfg.w_plagiotropism_lateral

    # Plagiotropisme : projection de current_direction sur le plan XY.
    # Si current_direction est presque vertical (dot avec UP > 0.99), la
    # projection est ambigüe → on saute le terme (poids effectif = 0).
    cd = np.asarray(current_direction, dtype=np.float64)
    cd_norm = float(np.linalg.norm(cd))
    if w_plagio > 0.0 and cd_norm > 1e-12:
        cd_unit = cd / cd_norm
        vertical_component = float(np.dot(cd_unit, _UP))
        if abs(vertical_component) < 0.99:
            v_plagio = cd_unit - vertical_component * _UP
            n_plagio = float(np.linalg.norm(v_plagio))
            if n_plagio > 1e-12:
                v_plagio = v_plagio / n_plagio
            else:
                v_plagio = np.zeros(3)
        else:
            v_plagio = np.zeros(3)
    else:
        v_plagio = np.zeros(3)

    blend = (
        cfg.w_perception * v_perception
        + (w_ortho * decay) * _UP
        + (w_gravi * decay) * _DOWN
        + (w_plagio * decay) * v_plagio
        + (cfg.w_phototropism * decay) * photo
        + cfg.w_direction_inertia * current_direction
    )
    # ... (normalisation inchangée) ...
```

Le seuil 0.99 sur la composante verticale évite le cas singulier où une
latérale émerge presque alignée avec le UP du parent (rare mais possible
avec le jitter). Dans ce cas, plagio est éteint pour cette iteration ; il
reprendra dès que les autres termes (gravité, perception) auront incliné
la direction.

### 4.7 `phyllotaxy.py::lateral_bud_directions`

```python
def lateral_bud_directions(
    growth_direction: np.ndarray,
    cfg: PhyllotaxyConfig,
    node_index: int,
    *,
    seed: int,
    axis_order: int,                 # NOUVEAU, obligatoire
) -> np.ndarray:
    # ... (frame perpendicular inchangé) ...

    # Lookup angle par ordre, clamp à la dernière valeur de la liste.
    angles = cfg.branch_angle_by_order
    idx = min(axis_order, len(angles) - 1)
    branch_angle = math.radians(angles[idx])

    base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index

    if cfg.divergence_jitter_deg > 0 or cfg.branch_angle_jitter_deg > 0:
        # ... (jitter inchangé, opère sur base_azimuth et branch_angle) ...
```

Pas de fallback sur `branch_angle_deg` (qui n'existe plus). Si le YAML
fournit `branch_angle_deg`, la validation YAML (unknown key) raise.

### 4.8 `simulator.py::_iteration_step`

Trois modifications dans la boucle d'iteration :

**Site A — dans la for-loop par tree existante (l. 115), AVANT
`compute_v_subtree`** :

```python
for tree in forest.trees:
    if cfg.sim.sympodial.enabled:
        promote_lateral_if_failing(tree, quality, cfg.sim.sympodial)
    v_subtree = compute_v_subtree(tree, quality)
    n_by_bud = allocate(...)
    ...
```

Note : on appelle sympodial AVANT `compute_v_subtree`/`allocate` pour que
l'allocation BH de cette iteration voie déjà la nouvelle structure
(node.terminal_bud swapé, old terminal DEAD et hors de active_buds). Les
valeurs de `quality` calculées plus haut ne changent pas — on promeut sur
la base des marqueurs observés à cette iteration, et compute_v_subtree
walke la structure d'arbre (via terminal_bud / lateral_buds / children
internodes) qui reflète déjà le swap.

**Site B — appel à `lateral_bud_directions`** :

```python
lateral_dirs = lateral_bud_directions(
    d, cfg.phyllotaxy,
    node_index=state.node_index,
    seed=cfg.seed,
    axis_order=cur.axis_order,        # NOUVEAU
)
```

**Pas d'autre site impacté.** `growth_direction` est déjà appelé avec
`is_main_axis` et `axis_order` ; le nouveau terme plagio s'intègre sans
toucher l'appelant.

---

## 5. Présets

Tous trois sont réécrits. Les anciens `branch_angle_deg` (scalaires) sont
supprimés au profit de `branch_angle_by_order` (listes).

### 5.1 `oak.yaml` — sympodial, étalé, plagiotrope modéré

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
  sympodial:
    enabled: true
    q_threshold: 1.5
    n_consecutive_steps: 3
tropism:
  w_perception: 1.0
  w_orthotropy_main: 0.35
  w_orthotropy_lateral: 0.05
  w_gravitropism_main: 0.0
  w_gravitropism_lateral: 0.0
  w_plagiotropism_main: 0.0
  w_plagiotropism_lateral: 0.30
  w_phototropism: 0.35
  w_direction_inertia: 0.5
  axis_decay: 0.85
phyllotaxy:
  mode: alternate
  divergence_angle_deg: 137.5
  branch_angle_by_order: [60.0, 40.0, 30.0, 25.0]
  divergence_jitter_deg: 5.0
  branch_angle_jitter_deg: 4.0
shedding:
  quality_threshold: 0.15
  window: 5
  enabled: true
sag:
  enabled: true
  k: 0.005
  max_bend_deg: 4.0
  rigid_axis_order: 1
geom:
  pipe_exponent: 2.49
  leaf_size: 0.14
  leaf_aspect: 1.0
  leaf_cluster_count: 3
  foliage_depth: 4
```

### 5.2 `pine.yaml` — monopodial strict, whorled, plagiotrope fort

```yaml
envelope:
  shape: cone
  rx: 2.5
  ry: 9.0
  rz: 2.5
  marker_count: 18000
sim:
  internode_length: 0.18
  internode_length_jitter: 0.10
  lambda_apical: 0.85
  alpha_basipetal: 2.5
  max_iterations: 50
  sympodial:
    enabled: false   # pin = monopodial strict
tropism:
  w_perception: 1.0
  w_orthotropy_main: 0.30
  w_orthotropy_lateral: 0.0
  w_gravitropism_main: 0.0
  w_gravitropism_lateral: 0.02
  w_plagiotropism_main: 0.0
  w_plagiotropism_lateral: 0.40
  w_phototropism: 0.20
  w_direction_inertia: 0.8
  axis_decay: 0.9
phyllotaxy:
  mode: whorled
  whorl_count: 5
  divergence_angle_deg: 72.0
  branch_angle_by_order: [75.0, 60.0, 45.0, 35.0]
  divergence_jitter_deg: 3.0
  branch_angle_jitter_deg: 3.0
shedding:
  quality_threshold: 0.20
  window: 5
  enabled: true
sag:
  enabled: false
geom:
  pipe_exponent: 2.30
  leaf_size: 0.06
  leaf_aspect: 0.025
  leaf_cluster_count: 5
  foliage_depth: 3
```

### 5.3 `birch.yaml` — monopodial pleureur, plagiotrope faible

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
  max_iterations: 50
  sympodial:
    enabled: false   # bouleau = monopodial (fort leader central)
tropism:
  w_perception: 1.0
  w_orthotropy_main: 0.40
  w_orthotropy_lateral: 0.05
  w_gravitropism_main: 0.0
  w_gravitropism_lateral: 0.45
  w_plagiotropism_main: 0.0
  w_plagiotropism_lateral: 0.10
  w_phototropism: 0.10
  w_direction_inertia: 0.5
  axis_decay: 0.88
phyllotaxy:
  mode: alternate
  divergence_angle_deg: 137.5
  branch_angle_by_order: [45.0, 35.0, 30.0, 25.0]
  divergence_jitter_deg: 5.0
  branch_angle_jitter_deg: 4.0
shedding:
  quality_threshold: 0.02
  window: 5
  enabled: true
sag:
  enabled: true
  k: 0.010
  max_bend_deg: 6.0
  rigid_axis_order: 1
geom:
  pipe_exponent: 2.25
  leaf_size: 0.05
  leaf_aspect: 0.7
  leaf_cluster_count: 3
  foliage_depth: 3
```

---

## 6. Tests

### 6.1 Tests unitaires nouveaux

**`tests/unit/test_sympodial.py`** :
- `test_promote_skipped_when_disabled` — `enabled=false` ⇒ aucune mutation.
- `test_low_quality_counter_increments` — Q sous seuil incrémente le compteur.
- `test_counter_resets_on_recovery` — Q au-dessus du seuil reset à 0.
- `test_promotion_picks_highest_q_lateral` — parmi 3 laterales avec Q
  différents, la plus haute est promue.
- `test_promotion_swaps_terminal_in_parent` — après promotion, `node.terminal_bud`
  est la latérale promue ; l'ancienne est `DEAD` et plus dans `lateral_buds`.
- `test_promoted_lateral_inherits_axis_order` — `new_terminal.axis_order ==
  old_terminal.axis_order` après promotion.
- `test_no_promotion_without_lateral_candidate` — si aucune latérale active,
  l'ancien terminal reste actif (la branche s'éteindra naturellement).

**`tests/unit/test_phyllotaxy.py`** (ajouts) :
- `test_branch_angle_by_order_lookup` — `axis_order=0` ⇒ premier élément,
  `axis_order=10` (> len) ⇒ dernier élément.
- `test_branch_angle_by_order_single_element` — liste à 1 élément ⇒ même
  angle pour tous les ordres.

**`tests/unit/test_tropisms.py`** (ajouts) :
- `test_plagiotropism_pulls_horizontal` — direction oblique (45°), forte
  plagio, faibles autres poids ⇒ résultat dot avec UP ≈ 0.
- `test_plagiotropism_skipped_when_near_vertical` — direction quasi-verticale
  (89°), plagio forte ⇒ résultat encore presque vertical (le terme s'éteint).
- `test_plagiotropism_main_vs_lateral` — `is_main_axis=true` utilise main,
  `false` utilise lateral.

**`tests/unit/test_config.py`** (ajouts) :
- `test_phyllotaxy_branch_angle_by_order_required` — YAML sans la clé ⇒ utilise default `(45.0,)`.
- `test_phyllotaxy_branch_angle_by_order_empty_raises` — `[]` ⇒ `ConfigError`.
- `test_phyllotaxy_branch_angle_by_order_out_of_range_raises` — `[120.0]` ⇒ `ConfigError`.
- `test_sympodial_q_threshold_negative_raises` — `-1` ⇒ `ConfigError`.

### 6.2 Tests d'intégration nouveaux

**`tests/integration/test_sympodial_emergence.py`** :
- `test_oak_produces_forks` — simuler oak preset 30 iterations ;
  compter les nodes où `parent_node.terminal_bud != original_terminal`
  (proxy : nodes où le main-axis internode partage le node avec un
  autre main-axis internode descendant d'une lateral_bud promue).
  Attendu : ≥ 10 forks sur l'arbre.
- `test_pine_produces_no_forks` — même mesure sur pine ; attendu : 0 forks.

**`tests/integration/test_plagiotropy_horizontalizes.py`** :
- Simuler oak 20 iterations.
- Pour chaque internode `is_main_axis=false` à `axis_order=1`, mesurer
  l'angle entre sa direction et le plan XY.
- Attendu : moyenne < 20° (les latérales s'étalent), médiane < 15°.

### 6.3 Goldens

Régénération **complète** de tous les goldens :
- `tests/golden/oak.glb`, `pine.glb`, `birch.glb`
- `tests/golden/oak.png`, `pine.png`, `birch.png` (preview snapshots)

Procédure post-implémentation :
```
.venv/bin/python -m palubicki generate --species oak --seed 0 -o tests/golden/oak.glb
.venv/bin/python -m palubicki generate --species pine --seed 0 -o tests/golden/pine.glb
.venv/bin/python -m palubicki generate --species birch --seed 0 -o tests/golden/birch.glb
.venv/bin/python -m palubicki preview tests/golden/oak.glb -o tests/golden/oak.png
.venv/bin/python -m palubicki preview tests/golden/pine.glb -o tests/golden/pine.png
.venv/bin/python -m palubicki preview tests/golden/birch.glb -o tests/golden/birch.png
```

Les anciens goldens (Phase 1) sont remplacés. Le diff visuel sera
substantiel — c'est attendu.

---

## 7. Risques et points ouverts

### 7.1 Tuning du `q_threshold` sympodial

`q_threshold: 1.5` pour oak est une estimation. La distribution effective
de Q dépend de la densité de marqueurs, du rayon de perception et du
nombre de buds en compétition. Si on observe :
- **Pas de fork sur oak** ⇒ q_threshold trop bas. Augmenter à 2.5 ou 3.0.
- **Fork à chaque iteration** ⇒ q_threshold trop haut (tout terminal est sous le seuil). Baisser à 0.5.

Mitigation : exécution exploratoire au bout de l'implémentation, ajustement
du préset, puis figement.

### 7.2 Promotion en cascade

Si le bourgeon promu hérite `axis_order` du terminal défaillant et que sa
qualité initiale est elle aussi basse, il pourrait à son tour déclencher
une promotion à la prochaine iteration. Le compteur `low_quality_steps`
est reset à 0 à la promotion, ce qui donne `n_consecutive_steps`
iterations de grâce avant un nouveau fork. Acceptable.

### 7.3 Plagiotropisme et phototropisme en compétition

`w_plagiotropism_lateral=0.30` + `w_phototropism=0.35` (oak) peuvent
tirer dans des directions différentes : plagio pousse vers l'horizontale
de la direction courante, photo pousse vers le gradient lumineux (souvent
plutôt vertical-haut sous un canopée ouverte). Le résultat dépend du
contexte d'éclairage. Pas un bug — c'est l'effet recherché : les latérales
s'étalent par défaut mais peuvent monter pour chercher la lumière dans une
sous-canopée. À valider visuellement.

### 7.4 axis_order après promotion

`bud.axis_order` est modifié en place. Tous les descendants futurs
hériteront de cette nouvelle valeur via `cur.axis_order + 1` au niveau
des latérales émises par phyllotaxy. Les internodes/buds qui existaient
DÉJÀ (i.e. enfants de l'ancien node) ne sont pas touchés. C'est cohérent
avec l'invariant "axis_order = profondeur depuis racine via terminaux au
moment de la création".

### 7.5 Interaction sympodial × shedding

Le shedding utilise `internode.average_quality()` sur une fenêtre. Une
branche promue n'est pas spécialement protégée du shedding — si elle a
hérité d'un sous-arbre faible (peu probable car la latérale n'a pas grandi
au moment de la promotion), elle pourrait être élaguée tôt. À surveiller
mais probablement non-problématique.

---

## 8. Non-objectifs

- Pas de "vraie" sympodie déterministe (cycle fixe tous les N internodes
  comme certains modèles L-system). Notre version est environment-driven.
- Pas de récupération du bourgeon DEAD (Phase 2B avec la réitération).
- Pas de redressement actif du nouveau leader via reprojection forcée. On
  laisse les tropismes faire le travail (`w_orthotropy_main` plus fort que
  `_lateral` suffit).
- Pas d'option pour transformer plusieurs latérales en codominants
  multiples (fork en Y équilibré). Une seule promotion par échec.
