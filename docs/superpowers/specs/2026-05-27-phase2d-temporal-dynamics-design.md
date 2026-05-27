# Phase 2D — Dynamique temporelle

Date : 2026-05-27
Status : design proposé, en attente de revue utilisateur

Dernière phase de la feuille de route de réalisme botanique. Phase 2D
traite les suggestions Priorité 2 #6 et Priorité 3 #7 du document de
revue :

1. **Élongation progressive** — chaque internode atteint sa longueur
   cible sur K iterations via courbe en S, au lieu d'être figé à sa
   longueur full à la création. La longueur cible elle-même est scalée
   par un `age_factor` basé sur l'iteration de création (hybride).
2. **Croissance secondaire dynamique** — le diamètre des internodes
   accumule année après année via pipe model incrémental, au lieu d'être
   calculé une seule fois en post-sim.

Dépend de : aucune autre phase. Mais le sag (cantilever bend) interagit
avec les diamètres dynamiques — recomputed chaque iteration.

---

## 1. Motivation

### 1.1 Élongation progressive

Une fois qu'un internode est créé, sa longueur est figée définitivement.
Conséquence : il n'y a pas de différence morphologique entre une jeune
pousse (créée à l'iteration 28) et une vieille branche (créée à
l'iteration 5). Toutes ont la même `internode_length × jitter`.

En réalité :
- Un internode grandit progressivement sur 2-4 saisons (courbe en S :
  lent → rapide → plateau).
- Les pousses initiales (apex jeune) sont **plus vigoureuses** et plus
  longues que les pousses tardives (apex mature, ressources réparties
  sur beaucoup plus de buds).

Modéliser ces deux phénomènes donne un arbre avec une **chronologie
visible** : grosses branches anciennes à la base, ramilles courtes
récentes en périphérie.

### 1.2 Croissance secondaire dynamique

Le diamètre est aujourd'hui calculé une seule fois en post-sim via pipe
model (`r = (Σ r_child^n)^(1/n)`). Conséquence :
- Pas d'historique : on ne peut pas avoir un internode "vieux mais avec
  peu de descendants" qui resterait fin. Tout dérive du subtree final.
- Le sag est calculé une fois sur la géométrie finale, sans dynamique.

En réalité, un internode épaissit chaque année (cernes annuels), en
fonction du flux de sève qui le traverse — proxy : sa taille de subtree
à cette année. Modéliser ça donne :
- Vieux internodes proches du tronc : épais (héritent de l'accumulation
  des années).
- Internodes récents en périphérie : fins.
- Possibilité de sag qui évolue avec l'âge (dynamique entre la portance
  croissante et la charge croissante).

---

## 2. Scope

**In** :
- `Internode` : nouveaux champs `birth_iteration: int`,
  `length_target: float`, `_diameter_history: list[float]`.
- `Internode.length` reste mais devient l'**effective length** (courante)
  recalculée à chaque iteration.
- `SimConfig` : nouveau sous-dataclass `ElongationConfig` exposé via
  `sim.elongation`.
- `sim/elongation.py` : nouveau module avec `update_lengths()` et
  `compute_target_with_age()`.
- `sim/radii.py` : refactor pour pipe model **incrémental** appelé chaque
  iteration. Suppression du call post-sim correspondant.
- `sim/sag.py` : appelé à chaque iteration (ou après l'incrément
  diamètre), pas seulement en post-sim. Le bend angle est recalculé sur
  la géométrie courante.
- `sim/simulator.py` : appels à `update_lengths`, `update_diameters_incremental`
  et `apply_sag_if_enabled` dans la boucle d'itération.
- Présets oak/pine/birch tunés (les longueurs et la cinétique).
- Tests + goldens régénérés.

**Out** :
- Pas de mortalité par âge (Phase 2B couvrait shade-mortality, on n'y
  revient pas).
- Pas de cernes visibles (le diamètre dynamique n'est pas exposé en
  géométrie de coupe, c'est un scalaire `Internode.diameter`).
- Pas de bois de réaction / contraintes mécaniques (sag reste
  cantilever pur).
- Pas de modélisation de l'allométrie globale (rapport hauteur/diamètre
  qui change avec l'âge).
- Pas de modification du shedding par âge.

---

## 3. Architecture

```
config.py
├─ SimConfig
│   + elongation: ElongationConfig
└─ ElongationConfig (nouveau)
    + enabled: bool = False
    + tau_iterations: float = 3.0
    + age_factor_min: float = 0.5
    + age_factor_decay: float = 0.5

sim/tree.py
└─ Internode
    + birth_iteration: int = 0
    + length_target: float = 0.0
    (length devient "effective length", mise à jour chaque iteration)

sim/elongation.py (NOUVEAU)
    + compute_target_with_age(base_length, birth_iteration,
                              max_iterations, cfg) -> float
    + update_lengths(tree, current_iteration, cfg) -> None
      Pour chaque internode :
        elapsed = current_iteration - birth_iteration
        sigma = 1 / (1 + exp(-(elapsed - tau) / (tau/2)))
        length = sigma * length_target

sim/radii.py (REFACTOR)
    + update_diameters_incremental(tree, cfg) -> None
      Replace l'appel post-sim. À chaque iteration:
        recompute pipe model sur l'arbre courant.
        accumule dans une moyenne mobile pondérée par âge ? Non.
        Plus simple: chaque iteration set diameter = pipe(subtree).
        Le résultat de l'iteration finale = ancien comportement.
        Mais l'évolution est observable et utilisable par sag.

sim/sag.py (LÉGER REFACTOR)
    + apply_sag(tree, cfg) reste mais accepte d'être appelé en milieu de
      sim. Idempotent (n'enchaîne pas les bend angles d'iteration en iteration).
      Approche: on stocke `Node.sag_offset: np.ndarray` calculé chaque
      iter, et la position rendue = position_topologique + sag_offset.
      → modification de Node mais pas de la position de référence
      utilisée par compute_v_subtree, perceive, etc.

sim/simulator.py (MODIFIÉ)
    Dans la boucle d'iteration, APRÈS le substep loop et shedding :
        if cfg.sim.elongation.enabled:
            update_lengths(tree, current_iteration=iteration, cfg=cfg.sim.elongation)
        update_diameters_incremental(tree, cfg=cfg.geom)
        if cfg.sag.enabled:
            apply_sag(tree, cfg=cfg.sag)
    Au site de création d'un Internode :
        target = compute_target_with_age(base_length, iteration, max_iter, cfg)
        iod = Internode(..., length=0.0, length_target=target,
                        birth_iteration=iteration, ...)

configs/species/{oak,pine,birch}.yaml
    + sim.elongation: { enabled: true, tau_iterations: 3.0, ... }
```

---

## 4. Spécification détaillée

### 4.1 `ElongationConfig`

```python
@dataclass(frozen=True)
class ElongationConfig:
    """Élongation progressive en S-curve + age_factor sur target_length."""
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    # Temps caractéristique de la courbe sigmoïde (en iterations).
    # length(t) = target * sigmoid((t - birth - tau) / (tau/2))
    # tau=3 → l'internode atteint ~50% à age=3, ~95% à age=6.
    tau_iterations: float = field(
        default=3.0, metadata={"ui": {"min": 0.5, "max": 10.0, "step": 0.1}}
    )
    # Facteur multiplicatif sur target_length pour les internodes créés
    # tard. Au début de la sim (birth=0), facteur = 1.0 ; à la fin
    # (birth=max_iter), facteur = age_factor_min.
    # Décroissance exponentielle : facteur = exp(-decay * birth/max_iter * ln(1/age_factor_min))
    # Plus simple à exposer : age_factor_min = facteur final, decay
    # = vitesse de transition.
    age_factor_min: float = field(
        default=0.5, metadata={"ui": {"min": 0.1, "max": 1.0, "step": 0.05}}
    )
    age_factor_decay: float = field(
        default=0.5, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.1}}
    )
```

Formule de l'age_factor :
```python
def age_factor(birth_iteration: int, max_iterations: int, cfg: ElongationConfig) -> float:
    if max_iterations <= 0:
        return 1.0
    t_norm = min(1.0, birth_iteration / max_iterations)
    # interp exponentiel : factor(0) = 1, factor(1) = age_factor_min
    decay = cfg.age_factor_decay
    base = math.exp(-decay * t_norm)
    # rescale pour que factor(1) atteigne exactement age_factor_min
    # base ∈ [e^-decay, 1] ; on veut [age_factor_min, 1]
    if decay > 0:
        base_min = math.exp(-decay)
        return cfg.age_factor_min + (1.0 - cfg.age_factor_min) * (base - base_min) / (1.0 - base_min)
    return 1.0  # decay=0 ⇒ pas d'effet âge
```

Validation : `tau_iterations > 0`, `0.1 ≤ age_factor_min ≤ 1.0`,
`age_factor_decay ≥ 0`.

### 4.2 `Internode` — nouveaux champs

```python
@dataclass(eq=False)
class Internode:
    parent_node: Node
    child_node: Node
    length: float                       # effective length (recalculée)
    is_main_axis: bool
    diameter: float = 0.0
    window: int = 5
    light_factor: float = 1.0           # Phase 2C
    # NOUVEAUX Phase 2D
    birth_iteration: int = 0
    length_target: float = 0.0
    quality_history: deque[float] = field(init=False)
```

Si `elongation.enabled=false`, `length_target` est ignoré et `length`
reste à sa valeur initiale (comportement pré-Phase 2D). Sinon, `length`
évolue à chaque iteration via `update_lengths`.

### 4.3 `sim/elongation.py`

```python
# src/palubicki/sim/elongation.py
from __future__ import annotations

import math

from palubicki.config import ElongationConfig
from palubicki.sim.tree import Internode, Tree


def compute_target_with_age(
    base_length: float,
    birth_iteration: int,
    max_iterations: int,
    cfg: ElongationConfig,
) -> float:
    """target_length = base_length × age_factor(birth_iteration).

    age_factor décroit exponentiellement de 1.0 (birth=0) à
    cfg.age_factor_min (birth=max_iterations).
    """
    if not cfg.enabled or max_iterations <= 0:
        return base_length
    t_norm = min(1.0, birth_iteration / max_iterations)
    decay = cfg.age_factor_decay
    if decay <= 0:
        return base_length
    base = math.exp(-decay * t_norm)
    base_at_one = math.exp(-decay)
    factor = (
        cfg.age_factor_min
        + (1.0 - cfg.age_factor_min) * (base - base_at_one) / (1.0 - base_at_one)
    )
    return base_length * factor


def update_lengths(tree: Tree, current_iteration: int, cfg: ElongationConfig) -> None:
    """Met à jour Internode.length pour tous les internodes du tree.

    length(t) = length_target × sigmoid((elapsed - tau) / (tau/2))
    """
    if not cfg.enabled:
        return
    tau = cfg.tau_iterations
    if tau <= 0:
        return
    for iod in tree.all_internodes:
        elapsed = max(0, current_iteration - iod.birth_iteration)
        x = (elapsed - tau) / (tau / 2.0)
        sigma = 1.0 / (1.0 + math.exp(-x))
        iod.length = iod.length_target * sigma
```

Note : `update_lengths` modifie `iod.length` en place. Ce changement est
ensuite consommé par :
- `radii.update_diameters_incremental` (le diamètre dépend de la
  géométrie, mais via pipe model qui est len-indépendant — donc pas
  d'impact ici).
- `sag.apply_sag` (le bend dépend du load = volume = length × diameter²
  → length actuelle compte).
- `geom/tubes.py` au moment de l'export glTF final.

**Important** : `length` est utilisé dans plusieurs endroits qui le
considèrent comme stable (par exemple le calcul des positions des
nodes via parent_node.position + direction × length). Or si on modifie
`length` chaque iteration, les positions devraient suivre.

**Décision** : les **positions** des `Node` (utilisées pour perceive,
markers, etc.) restent **figées à leur valeur de création** — l'arbre
"topologique" est stable. La `length` de l'internode est utilisée pour
le rendu final (tube mesh) et pour le calcul du sag. La distance
géométrique réelle entre parent_node et child_node n'est plus égale à
`length` après élongation.

C'est un compromis pragmatique. Les positions des nodes sont consistantes
pour la perception/compétition (l'arbre topologique grandit d'abord),
mais la **géométrie rendue** suit l'élongation progressive. À l'iteration
finale (`length ≈ length_target`), la cohérence position/length est
restaurée.

Documentation explicite de ce compromis dans la docstring du module.

### 4.4 `sim/radii.py` — refactor incrémental

Le pipe model est déjà len-indépendant (basé sur subtree depth). On le
recalcule simplement à chaque iteration au lieu de seulement à la fin :

```python
def update_diameters_incremental(tree: Tree, cfg: GeomConfig) -> None:
    """Recompute pipe model diameters from current tree structure.

    À l'iteration k, donne le diamètre que chaque internode "aurait s'il
    devait porter son subtree actuel". À l'iteration finale, identique à
    l'ancien compute_diameters_pipe.
    """
    _walk_assign_diameter(tree.root, cfg.r_tip, cfg.pipe_exponent)
```

`_walk_assign_diameter` reste identique à l'existant. Le seul changement
est de l'appeler dans la boucle d'iteration.

Le code post-sim qui appelait `compute_diameters_pipe` une fois est
**supprimé** — c'est redondant.

### 4.5 `sim/sag.py` — légère refonte

Le `apply_sag` actuel modifie directement les `Node.position`. Cela
casse l'idempotence (deuxième appel ⇒ double bend). Refactor :

```python
@dataclass(eq=False)
class Node:
    position: np.ndarray              # position topologique (fixe après création)
    sag_offset: np.ndarray = ...      # NOUVEAU : offset cumulé par sag
    ...
```

`apply_sag` calcule `sag_offset` from scratch à chaque appel, en
walkant l'arbre depuis la racine et en accumulant les rotations
parent→enfant. Le résultat écrit dans `sag_offset` ; la position
rendue = `position + sag_offset`.

L'export geom (`tubes.py`, `leaves.py`) consomme `position + sag_offset`
pour les vertex positions.

Justification : on ne veut pas que sag affecte les distances de
perception (markers, lumière) — il s'agit d'un offset visuel pur.

Le bend angle reste calculé via `k * load * sin(θ) / diameter²` comme
avant, avec `load = length × diameter² × density` (proxy biomass).

### 4.6 `sim/simulator.py` — sites modifiés

**Site A — création d'un Internode**

```python
target = compute_target_with_age(
    base_length=length,                       # length déjà jittered
    birth_iteration=iteration,
    max_iterations=cfg.sim.max_iterations,
    cfg=cfg.sim.elongation,
)
iod = Internode(
    parent_node=cur.parent_node,
    child_node=new_node,
    length=target if not cfg.sim.elongation.enabled else 0.0,
    is_main_axis=is_main,
    window=cfg.shedding.window,
    light_factor=lf,                          # Phase 2C
    birth_iteration=iteration,
    length_target=target,
)
```

Si elongation est désactivée, length=length_target directement (comportement
pré-Phase 2D). Sinon length=0.0 initialement (l'internode démarre
infinitésimal et grandit).

Note : `cur.position + d * length` continue d'utiliser `length` (qui est
soit target full, soit 0). Pour cohérence avec la perception (position
des nodes figée), on **doit** placer `new_node.position` à la position
finale géométrique = `cur.position + d * target`, pas `cur.position +
d * length=0`. Sinon le node-enfant naîtrait à la même position que son
parent et corromprait la perception.

Refactor minimal :
```python
new_pos = cur.position + d * target          # position topologique finale
```

et l'élongation progressive est purement un effet **rendu** : le tube
est plus court que la distance entre les positions des deux nodes,
créant un "trou" qui se ferme à mesure que length atteint target.

**Compromis visuel** : on rendrait un tube plus court que la distance
node-à-node, ce qui crée un gap visible. Alternative : **ne pas avancer
la position du child_node tant que length n'a pas atteint target** —
mais ça casse la perception (le node-enfant n'existe pas spatialement
pour les autres buds).

**Décision** : on accepte le compromis. Au début de l'élongation
(iteration de naissance), le child_node existe topologiquement à sa
position finale mais le tube rendu est très court — visuellement, c'est
comme si le node est "en construction" (tip très près du parent). Au
fil des iterations, le tube comble la distance. À l'iteration finale,
tube = distance, comportement standard.

Cette interprétation est cohérente avec la biologie : un bourgeon avorté
"téléportera" un nouveau node à sa position finale, mais l'épaisseur
de matière entre eux croît avec le temps.

**Site B — fin de chaque iteration**

```python
# ... après le substep loop, après shedding ...

# Mise à jour des longueurs effectives
if cfg.sim.elongation.enabled:
    for tree in forest.trees:
        update_lengths(tree, current_iteration=iteration, cfg=cfg.sim.elongation)

# Mise à jour des diamètres (incrémental)
for tree in forest.trees:
    update_diameters_incremental(tree, cfg=cfg.geom)

# Sag dynamique
if cfg.sag.enabled:
    for tree in forest.trees:
        apply_sag(tree, cfg=cfg.sag)
```

**Site C — suppression du call post-sim**

Le `compute_diameters_pipe` et `apply_sag` qui étaient appelés une
seule fois dans le pipeline post-simulate sont supprimés. Tout est
maintenant dans la boucle.

---

## 5. Présets

### 5.1 `oak.yaml`

Ajouts :
```yaml
sim:
  # ... existant ...
  elongation:
    enabled: true
    tau_iterations: 3.0
    age_factor_min: 0.5
    age_factor_decay: 0.8
```

Le chêne montre une chronologie marquée : les premières pousses (jeunesse
vigoureuse) sont à long internode, les dernières sont courtes.

### 5.2 `pine.yaml`

```yaml
sim:
  elongation:
    enabled: true
    tau_iterations: 2.5     # un peu plus rapide (pin pousse fort)
    age_factor_min: 0.4     # contraste plus fort
    age_factor_decay: 0.7
```

### 5.3 `birch.yaml`

```yaml
sim:
  elongation:
    enabled: true
    tau_iterations: 2.0     # bouleau rapide
    age_factor_min: 0.6     # moins contrasté (bouleau jeune-mature stable)
    age_factor_decay: 0.5
```

### 5.4 `maple.yaml`

(Phase 2C introduisait maple.yaml — Phase 2D le met à jour)
```yaml
sim:
  elongation:
    enabled: true
    tau_iterations: 3.0
    age_factor_min: 0.5
    age_factor_decay: 0.7
```

---

## 6. Tests

### 6.1 Unitaires

**`tests/unit/test_elongation.py`** :
- `test_compute_target_no_age_decay` — decay=0 ⇒ target = base.
- `test_compute_target_at_zero_iteration` — birth=0 ⇒ factor=1, target=base.
- `test_compute_target_at_max_iteration` — birth=max_iter ⇒ factor=age_factor_min.
- `test_update_lengths_zero_at_birth` — elapsed=0 ⇒ length ≈ 0 (sigma(-2)).
- `test_update_lengths_approaches_target` — elapsed=10*tau ⇒ length ≈ target.
- `test_update_lengths_sigmoid_midpoint` — elapsed=tau ⇒ length ≈ 0.5*target.

**`tests/unit/test_radii.py`** (ajouts) :
- `test_update_diameters_idempotent_same_state` — appeler 2× sans modif
  arbre donne mêmes diamètres.

**`tests/unit/test_sag.py`** (modifs) :
- `test_apply_sag_idempotent` — appeler 2× donne même résultat (via le
  sag_offset reset à chaque appel).
- `test_sag_offset_separate_from_position` — `Node.position` non modifié
  par sag.

### 6.2 Intégration

**`tests/integration/test_elongation_chronology.py`** :
- Simuler oak avec elongation enabled, 30 iterations.
- Mesurer la longueur moyenne des internodes par `birth_iteration` bin
  (early=0-10, mid=10-20, late=20-30).
- Attendu : longueur moyenne `late < mid < early` (au moins 20% de
  réduction).

**`tests/integration/test_diameter_progression.py`** :
- Snapshot diamètres à iteration=10, 20, 30 (instrumenter).
- Vérifier que les internodes anciens (birth_iteration=0) ont leur
  diamètre croissant entre snapshots (puisque leur subtree grandit).
- Vérifier qu'à iteration finale, diamètres ≈ ancien compute_diameters_pipe
  (régression bit-near).

### 6.3 Goldens

Régénération complète. Diff visuel attendu : structures topologiquement
identiques au snapshot final, mais avec longueurs et diamètres
légèrement différents (effet âge).

---

## 7. Risques et points ouverts

### 7.1 Cohérence position/length

Le compromis "position topologique finale + length progressive" crée un
écart visuel transitoire au moment de la création d'un internode. Si
`tau_iterations=3` et la sim fait 40 iterations, un internode né à
l'iteration 35 ne sera pas vraiment "complet" à la fin (sigma(2) ≈ 0.88
de target). Solution : à l'iteration finale, **forcer** length =
length_target pour tous les internodes (post-sim pass court).

Ajouter dans simulator.py après la boucle :
```python
# Finalisation : tous les internodes atteignent leur target.
if cfg.sim.elongation.enabled:
    for tree in forest.trees:
        for iod in tree.all_internodes:
            iod.length = iod.length_target
        update_diameters_incremental(tree, cfg=cfg.geom)
        if cfg.sag.enabled:
            apply_sag(tree, cfg=cfg.sag)
```

Documentation explicite : pendant la simulation, length est progressive ;
à la **fin**, on snap tout à target. C'est l'état exporté.

Conséquence : l'effet "chronologique visible" ne fait que travers les
internodes nés tardivement (ceux dont la sigma n'a pas eu le temps
d'atteindre 1.0). Si on veut un effet plus marqué, augmenter
`tau_iterations` ou réduire `max_iterations`.

### 7.2 Coût de sag dynamique

`apply_sag` walke l'arbre entier. Si la sim fait 40 iterations sur 5
arbres en forest, c'est 200 walks de sag. Chaque walk est O(N) en
nombre d'internodes. Pour un arbre à ~5000 internodes, c'est 1M ops par
arbre — supportable mais visible.

Mitigation possible : appeler `apply_sag` toutes les K iterations au
lieu de chaque, ou seulement en finalisation. Pour Phase 2D, on
l'appelle chaque iteration (le sag dynamique est l'objectif). Si perf
devient problématique, dégrader à toutes-les-5-iterations.

### 7.3 Couplage sag × élongation

Sag dépend de `length × diameter²`. Si length croît progressivement, le
load croît, donc le bend augmente sur ces vieilles branches. Réaliste !
C'est exactement le phénomène botanique du droop progressif avec le poids.

À iteration finale (sigma → 1), les vieilles branches ont leur load max
et leur bend max. Au début (sigma=0), bend = 0. Évolution naturelle.

### 7.4 Backward-compat pour Internode

`birth_iteration: int = 0` et `length_target: float = 0.0` ont des
defaults. Si quelqu'un instancie un Internode sans les passer, le
`length_target=0` causerait `length=0` à update_lengths. Mais le simulator
le set toujours explicitement. Tests unitaires garantissent ce contrat.

### 7.5 Sag offset = nouveau invariant

`Node.sag_offset` doit être initialisé à zéro pour tous les nodes (pour
que `position + sag_offset = position` quand sag désactivé). Default
`np.zeros(3)`.

### 7.6 Position des feuilles

`geom/leaves.py` place les feuilles à des positions relative à
l'internode. Avec sag dynamique, les feuilles suivent le sag (bien). Avec
élongation progressive, les feuilles d'un internode "tronqué" (length <
target) seraient à la mauvaise distance. Décision : les feuilles ne
sont émises **qu'en finalisation** (après le snap à target), donc
toujours à la bonne position. Cohérent avec leaves comme rendu plutôt
qu'élément dynamique de simulation.

---

## 8. Non-objectifs

- Pas de cernes annuels visibles (mesh de section).
- Pas de bois mort / cicatrices (seul l'élagage normal s'applique).
- Pas de croissance allométrique globale (taux H/D constants au lieu de
  varier avec âge).
- Pas de feedback élongation → perception markers (la perception
  utilise les positions topologiques figées).
