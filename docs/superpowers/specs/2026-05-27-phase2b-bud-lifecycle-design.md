# Phase 2B — Cycle de vie des bourgeons

Date : 2026-05-27
Status : design proposé, en attente de revue utilisateur

Suite de la feuille de route de réalisme botanique
([revue](../../2026-05-27-simulation-review.md), [Phase 2A
](./2026-05-27-phase2a-branching-architecture-design.md)).

Phase 2B traite les suggestions Priorité 1 #3 et Priorité 3 #8 du document
de revue, qui touchent toutes deux à **l'état et la transition des
bourgeons** :

1. **Mortalité à l'ombre** — un bourgeon dont `light_factor` reste sous
   seuil pendant N pas consécutifs meurt (abscission). Donne le "live
   crown ratio" naturel sans tuning fin du shedding par marqueurs.
2. **Réitération via bourgeons dormants de réserve** — chaque node garde
   K bourgeons cachés en plus des latérales émises par phyllotaxie. Ils
   se réveillent quand une branche enfant est élaguée, modélisant les
   epicormic shoots / gourmands.

Dépend de : Phase 2A (utilise le pattern `low_quality_steps` du Bud pour
le compteur `low_light_steps`).

Phases suivantes (hors scope) :
- Phase 2C : décussation + sun/shade leaves
- Phase 2D : élongation progressive + croissance secondaire dynamique

---

## 1. Motivation

### 1.1 Mortalité à l'ombre

Actuellement, le phototropisme **courbe** les branches vers la lumière
mais ne **tue pas** les bourgeons à l'ombre. Le seul mécanisme qui élimine
une branche faiblement éclairée est le shedding sur quality moyenne
(marqueurs claimés sur fenêtre). Or marker-starvation ≠ shade-mortality :
un bourgeon peut récupérer des marqueurs (espace libre) mais sous canopée
fermée (light_factor < 0.2). En réalité ce bourgeon **meurt** (les ressources
ne suffisent pas à entretenir une feuille net-négative en photosynthèse).

Sans ce mécanisme, nos couronnes "vivantes" descendent trop bas — les
chênes simulés ont des branches actives jusqu'au sol, alors qu'un chêne
mature en forêt a un tronc nu sur les 60% inférieurs.

### 1.2 Réitération via réserves dormantes

Un arbre réel garde une **banque** de bourgeons préformés sous l'écorce
qui dorment pendant des années voire des décennies. Lorsqu'une branche
maîtresse casse, est élaguée ou meurt, ces bourgeons se réveillent et
créent des **gourmands** (epicormic shoots / water sprouts). C'est
spectaculaire chez le saule, le tilleul, le chêne et le peuplier.

Notre simulation actuelle n'a aucun mécanisme de récupération post-perte
de branche : si une sous-arbre meurt par shedding, le parent reste muet
à jamais. Conséquence : nos arbres "sculptés" par la lumière ne montrent
jamais cette dynamique réparatrice — ils paraissent figés une fois la
forme atteinte.

---

## 2. Scope

**In** :
- `Bud` : nouveau champ `low_light_steps: int = 0`.
- `Node` : nouveau champ `dormant_reserve_buds: list[Bud]`.
- `BudState` : nouvelle valeur `RESERVE` (distinct de `DORMANT`).
- `config.py` :
  - Nouveau `ShadeMortalityConfig` exposé via `SimConfig.shade_mortality`.
  - Nouveau champ `PhyllotaxyConfig.dormant_reserve_count: int = 0`.
- `sim/shade_mortality.py` : nouveau module avec `kill_shaded_buds()`.
- `sim/reiteration.py` : nouveau module avec `activate_reserves_on_shed()`.
- `sim/shedding.py` : hook pour appeler `activate_reserves_on_shed()` après chaque branche élaguée.
- `sim/simulator.py` :
  - Appel à `kill_shaded_buds` après calcul des `light_factor` et avant l'allocation.
  - Création des `dormant_reserve_buds` à chaque émission de node (alongside terminal + laterals).
- Présets oak/pine/birch mis à jour avec `shade_mortality` et `dormant_reserve_count`.
- Tests unitaires + intégration.
- Goldens régénérés.

**Out** :
- Pas de réactivation des `DORMANT` réguliers (les bourgeons qui ont
  échoué via U-turn, marker-starvation, etc.). Seuls les `RESERVE`
  s'activent. Cette restriction est volontaire — elle évite les boucles
  d'activation/désactivation et garde le state machine simple.
- Pas de gourmands sur le tronc en l'absence de shedding — la
  réactivation est purement réactive à une perte de branche.
- Pas de mortalité programmée par âge (senescence). Les bourgeons ne
  meurent que par cause environnementale (lumière) ou compétition
  (existant : marker-starvation).
- Pas de modification du phototropisme directionnel (toujours juste un
  bias de direction, pas de fate decision via phototropisme).

---

## 3. Architecture

```
config.py
├─ SimConfig
│   + shade_mortality: ShadeMortalityConfig
├─ PhyllotaxyConfig
│   + dormant_reserve_count: int = 0
└─ ShadeMortalityConfig (nouveau)
    + enabled: bool = False
    + light_threshold: float = 0.15
    + n_consecutive_steps: int = 3

sim/tree.py
├─ BudState
│   + RESERVE  (nouveau)
├─ Bud
│   + low_light_steps: int = 0
└─ Node
    + dormant_reserve_buds: list[Bud]

sim/shade_mortality.py (NOUVEAU)
    + kill_shaded_buds(buds, light_factor, cfg) -> int
      Pour chaque bourgeon ACTIVE :
        si light_factor < seuil  : incrémenter low_light_steps
        sinon                    : reset à 0
        si low_light_steps >= N  : state = DEAD

sim/reiteration.py (NOUVEAU)
    + activate_reserves_on_shed(parent_node, n_to_activate) -> list[Bud]
      Retire `n_to_activate` bourgeons RESERVE de parent_node, les
      transitione vers ACTIVE, les ajoute à parent_node.lateral_buds.
      Retourne la liste des bourgeons activés (à ajouter à tree.active_buds).

sim/shedding.py (MODIFIÉ)
    Quand `_walk_and_shed` retire un sous-arbre du node parent, appelle
    `activate_reserves_on_shed(parent, n_to_activate=cfg.reactivation_count)`
    et propage les bourgeons activés vers tree.active_buds.

sim/simulator.py (MODIFIÉ)
    APRÈS perceive_light, AVANT pour-tree-loop sympodial :
        union_buds = all_active_buds(forest)
        if cfg.sim.shade_mortality.enabled and light_info is not None:
            kill_shaded_buds(union_buds, light_info.light_factor,
                             cfg.sim.shade_mortality)
            # nettoyer active_buds dans chaque arbre

    LORS DE l'émission d'un new_node (après le bloc qui crée les laterals) :
        for _ in range(cfg.phyllotaxy.dormant_reserve_count):
            reserve_dir = _reserve_direction(d, state.node_index, cfg.seed)
            res = Bud(position=new_pos.copy(), direction=reserve_dir,
                      axis_order=cur.axis_order + 1, parent_node=new_node,
                      state=BudState.RESERVE)
            new_node.dormant_reserve_buds.append(res)

configs/species/{oak,pine,birch}.yaml
    + shade_mortality (enabled true pour tous; seuils par espèce)
    + dormant_reserve_count par espèce
```

---

## 4. Spécification détaillée

### 4.1 `BudState` — nouvelle valeur

```python
class BudState(Enum):
    ACTIVE = auto()
    DORMANT = auto()    # bourgeon ayant échoué (U-turn, no markers, etc.)
    DEAD = auto()       # bourgeon irrécupérable
    RESERVE = auto()    # NOUVEAU : bourgeon dormant préformé, réactivable
```

`RESERVE` ne participe à **rien** des passes existantes :
- Pas dans `tree.active_buds` (donc pas perçu, pas alloué, pas en compétition pour markers)
- Pas dans le voxel grid de lumière (n'absorbe pas)
- Pas inclus dans `compute_v_subtree` (Q irrelevant)

Seule `activate_reserves_on_shed` peut le transitionner vers `ACTIVE`.

### 4.2 `ShadeMortalityConfig`

```python
@dataclass(frozen=True)
class ShadeMortalityConfig:
    """Tue les bourgeons dont light_factor reste sous seuil N pas consécutifs."""
    enabled: bool = field(default=False, metadata={"ui": {"label": "Enabled"}})
    # Light factor en dessous duquel un bourgeon est considéré "à l'ombre".
    # 0.0 = obscurité totale, 1.0 = plein soleil (selon ton Beer-Lambert).
    # 0.15 = sous-canopée typique en forêt fermée.
    light_threshold: float = field(
        default=0.15, metadata={"ui": {"min": 0.0, "max": 1.0, "step": 0.01}}
    )
    # Pas consécutifs sous seuil avant la mort. 3 = patient (un voile
    # d'ombre passager ne tue pas), 1 = ultra-réactif.
    n_consecutive_steps: int = field(
        default=3, metadata={"ui": {"min": 1, "max": 10, "step": 1}}
    )
```

Validation : `0 ≤ light_threshold ≤ 1`, `n_consecutive_steps ≥ 1`.

Si `enabled=true` mais `cfg.light.enabled=false`, on raise `ConfigError` à
l'instanciation (la mortalité à l'ombre n'a aucun sens sans grille de
lumière calculée).

### 4.3 `PhyllotaxyConfig.dormant_reserve_count`

```python
# NOUVEAU champ ajouté à PhyllotaxyConfig
dormant_reserve_count: int = field(
    default=0,
    metadata={"ui": {"min": 0, "max": 5, "step": 1}},
)
```

`0` = pas de réserves (comportement actuel). `1-2` réaliste pour les
feuillus à fort potentiel de réitération (chêne, peuplier). `0` pour
les conifères (très peu réitérants).

Validation : `≥ 0`.

### 4.4 `Bud.low_light_steps`

```python
@dataclass(eq=False)
class Bud:
    position: np.ndarray
    direction: np.ndarray
    axis_order: int
    parent_node: "Node"
    age: int = 0
    state: BudState = BudState.ACTIVE
    low_quality_steps: int = 0     # Phase 2A
    low_light_steps: int = 0       # NOUVEAU
```

Modifié uniquement par `kill_shaded_buds`. Reset à 0 quand light_factor
remonte au-dessus du seuil — un bourgeon qui voit revenir la lumière a
sa pleine "réserve de patience" restaurée.

### 4.5 `Node.dormant_reserve_buds`

```python
@dataclass(eq=False)
class Node:
    position: np.ndarray
    parent_internode: Optional["Internode"] = None
    children_internodes: list["Internode"] = field(default_factory=list)
    terminal_bud: Optional[Bud] = None
    lateral_buds: list[Bud] = field(default_factory=list)
    dormant_reserve_buds: list[Bud] = field(default_factory=list)   # NOUVEAU
```

Populés une seule fois lors de la création du node (dans la boucle
substep du simulator). Diminuent uniquement via
`activate_reserves_on_shed`.

### 4.6 `sim/shade_mortality.py`

```python
# src/palubicki/sim/shade_mortality.py
from __future__ import annotations

from palubicki.config import ShadeMortalityConfig
from palubicki.sim.tree import Bud, BudState


def kill_shaded_buds(
    buds: list[Bud],
    light_factor: dict[Bud, float],
    cfg: ShadeMortalityConfig,
) -> int:
    """Marque DEAD les bourgeons ACTIVE sous-ombre pendant N pas consécutifs.

    Retourne le nombre de bourgeons tués cette iteration.
    """
    if not cfg.enabled:
        return 0
    killed = 0
    for bud in buds:
        if bud.state is not BudState.ACTIVE:
            continue
        lf = light_factor.get(bud, 1.0)  # par défaut : pleine lumière
        if lf < cfg.light_threshold:
            bud.low_light_steps += 1
            if bud.low_light_steps >= cfg.n_consecutive_steps:
                bud.state = BudState.DEAD
                killed += 1
        else:
            bud.low_light_steps = 0
    return killed
```

Le caller (simulator.py) doit ensuite filtrer `tree.active_buds` pour
retirer les `DEAD` — cohérent avec le pattern existant.

### 4.7 `sim/reiteration.py`

```python
# src/palubicki/sim/reiteration.py
from __future__ import annotations

import numpy as np

from palubicki.sim.tree import Bud, BudState, Node


def activate_reserves_on_shed(
    parent_node: Node,
    n_to_activate: int = 1,
) -> list[Bud]:
    """Active n_to_activate bourgeons RESERVE du parent_node.

    Les bourgeons activés deviennent ACTIVE, sont retirés de
    dormant_reserve_buds, et ajoutés à lateral_buds. Retourne la liste
    des bourgeons activés (à ajouter à tree.active_buds par le caller).

    Si fewer reserves que demandés, active tous ceux disponibles sans
    erreur. Si n_to_activate <= 0, no-op.
    """
    if n_to_activate <= 0 or not parent_node.dormant_reserve_buds:
        return []
    n_actual = min(n_to_activate, len(parent_node.dormant_reserve_buds))
    activated: list[Bud] = []
    for _ in range(n_actual):
        bud = parent_node.dormant_reserve_buds.pop()
        bud.state = BudState.ACTIVE
        bud.low_quality_steps = 0
        bud.low_light_steps = 0
        bud.age = 0  # reset pour comptes futurs
        parent_node.lateral_buds.append(bud)
        activated.append(bud)
    return activated
```

### 4.8 `sim/shedding.py` — hook

`shed_low_quality()` walke l'arbre en pre-order, élague les sous-arbres
faibles. À chaque branche élaguée :

```python
# Pseudo-diff dans _walk_and_shed
for child_internode in list(node.children_internodes):
    if _should_shed(child_internode):
        node.children_internodes.remove(child_internode)
        # NOUVEAU : réveiller des bourgeons de réserve
        activated = activate_reserves_on_shed(
            node, n_to_activate=cfg.reactivation_count
        )
        tree.active_buds.extend(activated)
        continue
    _walk_and_shed(child_internode.child_node, ...)
```

`cfg.reactivation_count` est un nouveau champ de `SheddingConfig` :
```python
reactivation_count: int = field(
    default=1, metadata={"ui": {"min": 0, "max": 5, "step": 1}}
)
```

`0` désactive la réitération même si des reserves existent. `1` = un
gourmand par perte de branche (typique). `2-3` = peuplier ou saule
(forte régénération).

### 4.9 `sim/simulator.py` — sites modifiés

**Site A — mortalité à l'ombre, après perceive_light**

```python
if light_info is not None and cfg.sim.shade_mortality.enabled:
    kill_shaded_buds(
        union_buds, light_info.light_factor, cfg.sim.shade_mortality
    )
    # Nettoyer active_buds
    for tree in forest.trees:
        tree.active_buds = [b for b in tree.active_buds if b.state is not BudState.DEAD]
    # Reconstituer union_buds (pour la suite de l'iteration)
    union_buds = all_active_buds(forest)
```

L'ordre est : light_grid build → perceive_light → kill_shaded_buds →
perceive markers → sympodial (Phase 2A) → BH allocate → substep loop.

**Site B — émission des reserves au niveau de chaque nouveau node**

Dans le substep loop, après le bloc qui crée les `lateral_buds` à partir
de `lateral_dirs` :

```python
# Reserves: directions échantillonnées différemment des laterals.
# On utilise la même base_azimuth mais offset par +π (côté opposé),
# avec branch_angle plus serré (les réserves sont "blotties" contre le node).
if cfg.phyllotaxy.dormant_reserve_count > 0:
    reserve_dirs = _reserve_directions(
        d, cfg.phyllotaxy, node_index=state.node_index,
        seed=cfg.seed, axis_order=cur.axis_order,
        count=cfg.phyllotaxy.dormant_reserve_count,
    )
    for rd in reserve_dirs:
        res = Bud(
            position=new_pos.copy(), direction=rd,
            axis_order=cur.axis_order + 1, parent_node=new_node,
            state=BudState.RESERVE,
        )
        new_node.dormant_reserve_buds.append(res)
```

`_reserve_directions` est une nouvelle fonction de `phyllotaxy.py`,
basée sur `lateral_bud_directions` mais avec :
- azimuth offset par +π par rapport aux laterals (côté opposé du tronc)
- branch_angle plus serré (multiplié par 0.5, ne dépasse pas 30°)
- jitter réduit (la moitié des σ standard)

L'objectif est que les reserves activées émergent dans des directions
"complémentaires" — si une branche meurt à droite, le gourmand qui
remplace pousse à gauche (ou de l'autre côté du node).

### 4.10 Interaction avec light_grid

Les bourgeons `RESERVE` n'absorbent pas de lumière (ne sont pas dans le
voxel grid) — c'est cohérent avec l'idée qu'ils sont sous l'écorce, sans
feuille. Quand ils sont activés, ils rejoignent `active_buds` et seront
voxelisés à la prochaine itération.

Un bourgeon activé peut immédiatement être tué par `kill_shaded_buds`
si l'environnement est encore sombre. C'est correct biologiquement : un
gourmand qui pousse sous canopée fermée meurt aussi. Le compteur
`low_light_steps = 0` à l'activation donne `n_consecutive_steps` de
grâce.

---

## 5. Présets

### 5.1 `oak.yaml` — chêne réitérant fort

Ajouts au préset Phase 2A :
```yaml
sim:
  # ... existant ...
  shade_mortality:
    enabled: true
    light_threshold: 0.20
    n_consecutive_steps: 3
phyllotaxy:
  # ... existant ...
  dormant_reserve_count: 2
shedding:
  # ... existant ...
  reactivation_count: 1
```

Le chêne est connu pour ses gourmands abondants → 2 réserves par node, 1
activation par perte.

### 5.2 `pine.yaml` — pin peu réitérant

```yaml
sim:
  shade_mortality:
    enabled: true
    light_threshold: 0.12
    n_consecutive_steps: 4
phyllotaxy:
  dormant_reserve_count: 0
shedding:
  reactivation_count: 0
```

Pin = très peu de réitération (les conifères perdent la capacité avec
l'âge). 0 reserve, 0 activation. La mortalité à l'ombre est plus
permissive (les aiguilles tolèrent un peu plus l'ombre) — seuil 0.12 vs
0.20.

### 5.3 `birch.yaml` — bouleau modérément réitérant

```yaml
sim:
  shade_mortality:
    enabled: true
    light_threshold: 0.20
    n_consecutive_steps: 3
phyllotaxy:
  dormant_reserve_count: 1
shedding:
  reactivation_count: 1
```

Bouleau intermédiaire : peut former des gourmands mais moins
spectaculairement que le chêne.

---

## 6. Tests

### 6.1 Tests unitaires

**`tests/unit/test_shade_mortality.py`** :
- `test_kill_skipped_when_disabled` — `enabled=False` ⇒ no-op.
- `test_counter_increments_under_threshold` — light_factor < seuil ⇒ counter++.
- `test_counter_resets_above_threshold` — light remonte ⇒ counter=0.
- `test_dies_after_n_consecutive_steps` — N pas sous seuil ⇒ state=DEAD.
- `test_doesnt_kill_reserves_or_dormants` — seuls les ACTIVE sont affectés.

**`tests/unit/test_reiteration.py`** :
- `test_activate_returns_empty_when_no_reserves` — node sans reserves ⇒ [].
- `test_activate_pops_n_buds` — n_to_activate=2, 3 reserves ⇒ 2 activés, 1 reste.
- `test_activated_buds_change_state_to_active` — vérif état post-activation.
- `test_activated_buds_have_counters_reset` — low_light_steps et low_quality_steps = 0.
- `test_activate_caps_at_available_reserves` — n_to_activate > len(reserves) ⇒ all activés.

**`tests/unit/test_phyllotaxy.py`** (ajouts) :
- `test_reserve_directions_offset_from_laterals` — directions des reserves sont approximativement opposées aux laterals (dot < 0 dans plan XY).
- `test_reserve_directions_count` — `dormant_reserve_count=K` ⇒ K directions retournées.

### 6.2 Tests d'intégration

**`tests/integration/test_shade_carves_canopy.py`** :
- Simuler oak preset avec light enabled, 40 iterations.
- Mesurer le ratio de buds DEAD vs ACTIVE dans la moitié inférieure du
  half-ellipsoid envelope.
- Attendu : ≥ 60% des buds dans la moitié basse sont DEAD (live crown
  ratio ≈ 40%).
- Sans shade_mortality (`enabled=False`), attendu : < 20% morts (seul le
  marker-starvation joue).

**`tests/integration/test_reiteration_after_shed.py`** :
- Simuler oak preset, 30 iterations.
- Compter le nombre total de bourgeons activés via réitération
  (instrumentation : compter les retours non-vides de
  `activate_reserves_on_shed`).
- Attendu : ≥ 5 activations sur la simulation (proportionnel au nombre
  de sheds × `reactivation_count`).
- Avec `dormant_reserve_count=0`, attendu : 0 activations même avec
  beaucoup de sheds.

### 6.3 Goldens

Régénération complète des goldens oak/pine/birch.

---

## 7. Risques et points ouverts

### 7.1 Tuning `light_threshold`

`0.15-0.20` est une estimation. Les valeurs effectives de `light_factor`
dépendent du `k_absorption` Beer-Lambert et de la densité foliaire. Si
on observe :
- **Couronne trop ouverte** (peu de morts) ⇒ augmenter seuil à 0.25.
- **Mortalité massive dès iteration 5** ⇒ baisser à 0.10, ou augmenter
  `n_consecutive_steps` à 5.

### 7.2 Cascade de morts post-réitération

Si un gourmand activé pousse sous canopée fermée, il sera tué après
`n_consecutive_steps`. Au prochain shed, un autre gourmand pourrait
s'activer pour mourir à son tour. C'est correct biologiquement (les
réserves s'épuisent) mais peut donner un look "stroboscopique" de
gourmands éphémères. Mitigation : si le problème apparaît, ajouter une
hystérésis sur le seuil de mortalité (un activé récent reçoit `2 *
n_consecutive_steps` de grâce).

### 7.3 Direction des reserves

Les `_reserve_directions` calculées avec offset +π s'orientent côté
opposé du tronc. Mais l'orientation idéale serait "vers la direction de
la branche perdue" (le gourmand remplace réellement la branche manquante).
Implémenter ça demande de connaître quelle branche a été élaguée — info
disponible dans `activate_reserves_on_shed`. **Amélioration future** :
au moment de l'activation, ré-orienter le bud activé vers la direction
de l'internode élagué. Pour Phase 2B, on garde la version simple
(orientation fixée à la création du node).

### 7.4 Interaction avec phototropisme

Un bud activé est immédiatement soumis au phototropisme via
`growth_direction()`. Il courbe naturellement vers la lumière. Pas
d'interaction nouvelle à modéliser.

### 7.5 Comptage `tree.active_buds` après light kill

Le simulateur reconstitue `union_buds` après `kill_shaded_buds` — c'est
nécessaire car les buds tués ne doivent plus apparaître dans les passes
suivantes (perceive markers, sympodial check, allocate). Coût léger
(O(buds)) mais visible si on instrumente.

---

## 8. Non-objectifs

- Pas de réactivation des `DORMANT` (seuls les `RESERVE`).
- Pas d'épuisement des réserves dans le temps (un node garde ses
  reserves indéfiniment jusqu'à activation).
- Pas de mortalité par froid, sécheresse, parasites — uniquement par
  manque de lumière persistant.
- Pas de gourmands sur le tronc en l'absence d'élagage (les reserves
  n'attendent que le shed pour s'activer).
