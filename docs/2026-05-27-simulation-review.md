# Revue de la simulation : alignement avec Palubicki 2009 et réalisme biologique

Date : 2026-05-27
Auteur : analyse Claude

Objet : évaluer si l'implémentation actuelle est fidèle au papier
*Self-organizing tree models for image synthesis* (Palubicki et al., SIGGRAPH
2009) et si elle produit des arbres dont la **disposition des branches et des
feuilles** ressemble à ce qu'on trouve dans la nature. Le rendu 3D (textures,
shading) est hors scope.

---

## 1. Fonctionnement haut-niveau

Le code implémente fidèlement le modèle **BHse**
("Borchert-Honda + space competition envelope") du papier. Une itération du
simulateur (`src/palubicki/sim/simulator.py:79-301`) fait :

1. **Perception** (`space_competition.py`) : chaque bourgeon actif requête un
   KDTree pour les marqueurs dans un cône `(r_perception, θ_perception)`.
   Chaque marqueur est attribué au bourgeon **le plus proche** (compétition).
   La qualité `Q = nb_markers` et la direction
   `v_perception = normalize(Σ Δ̂)` sortent de là.
2. **Allocation Borchert-Honda** (`bh.py`) : passe basipétale (somme des Q
   par sous-arbre) puis passe acropétale qui distribue selon la formule
   exacte du papier
   `v_main = v_here · λ·Q_m / (λ·Q_m + (1−λ)·Q_l)` (l.88, 128). Résultat :
   `n_internodes = floor(v_b)` par bourgeon.
3. **Croissance** : pour chaque substep, direction tropique
   (`tropisms.py:45-51`) = somme vectorielle de perception + orthotropie
   (UP) + gravitropisme (DOWN) + phototropisme + inertie, chaque poids
   multiplié par `axis_decay^axis_order`. On extrude un internode, on émet
   le bourgeon terminal + bourgeons latéraux selon la phyllotaxie
   (`phyllotaxy.py`).
4. **Marker kill** : tous les marqueurs dans `r_kill` autour des nouveaux
   nœuds sont supprimés.
5. **Shedding** (`shedding.py`) : moyenne glissante de qualité par internode
   sur `window=5` itérations ; les sous-arbres qui descendent sous le seuil
   sont coupés.

Post-process : `compute_radii` (loi de Murray `r^n = Σ r_child^n`), puis
`apply_sag` qui plie chaque internode selon
`bend = k·load·sinθ/diameter²` (`sag.py:93`).

---

## 2. Alignement avec le papier

**Très bon, fidèle au cœur BHse.** Les formules sont les bonnes. Différences
identifiées :

| Point | Code | Papier | Impact |
|---|---|---|---|
| Quantification ressource | `floor(v)` (`bh.py:98,104,134`) | Accumulation continue + carry-over | Petites pertes ; biais contre les laterals faibles |
| Cap par bud/iter | `n ≤ n_substeps_max` (`simulator.py:123-125`) | Strict 1 internode/bud/iter (BHse) | Conforme — bien noté dans commit récent |
| Tropismes | Somme vectorielle libre, poids indépendants | Idem | OK |
| Phototropisme | Vecteur fixe global OU gradient hémisphérique (V2) | Idem | OK |
| Axis decay | `w · decay^order` | **Pas dans le papier** | Extension utile mais non documentée comme telle |
| Sag mécanique | Post-process avec moment | **Pas dans le papier** | Extension récente |
| Compétition par marqueur | Tri lexicographique pour ordre d'insertion exact | Idem (concept) | Excès d'ingénierie pour goldens, mais correct |

**Bilan** : implémentation rigoureuse du BHse + BHls (light voxel) + des
extensions modernes (sag, axis_decay). Très bien aligné.

---

## 3. Réalisme biologique (branches/feuillage)

Les vrais problèmes pour produire des arbres qui ressemblent à la nature :

### a. `is_main_axis` existe mais n'est pas exploité
`tree.py` marque chaque internode comme main ou latéral, mais **rien dans
`tropisms.py`, `phyllotaxy.py`, ou `shedding.py` ne lit ce flag**. Dans la
réalité :
- Axes d'ordre 1 (primaires) sont souvent **plagiotropes** (horizontaux,
  gravitropisme positif sur le côté = "epinasty").
- Axes d'ordre 2+ sont souvent **orthotropes faibles** ou repartent vers le
  haut.
- Le simple `axis_decay^order` ne capture pas cette **discontinuité main vs
  latéral**, juste une dégradation continue.

### b. Pas de croissance déterminée (préformée) — gros problème pour les conifères
Les pins ont des **flushs annuels préformés** : la longueur de la pousse est
fixée dans le bourgeon de l'année précédente. Résultat visuel : étages
(verticilles) très réguliers et bien espacés. Le modèle simule en continu,
donc les pousses dépendent de la qualité de l'itération — les étages
dérivent. Le whorl phyllotaxy seul ne suffit pas.

### c. Phyllotaxis trop déterministe
`base_azimuth = 137.5° · node_index` (`phyllotaxy.py:30`) — angle
parfaitement constant. Dans la vraie nature : ±5-10° de jitter, et des
sauts plus larges après des bourgeons avortés. Trop régulier = lecture
"synthétique".

### d. Angle de branche scalaire fixe
`branch_angle_deg` est constant par espèce. En réalité : **les jeunes
pousses sortent à 30-50°, puis ouvrent à 60-80° avec l'âge** (poids +
photo). Le sag ne change pas l'angle d'insertion, il plie l'internode
déjà placé.

### e. [ADDRESSED — Phase 2B] Pas de réitération / pas de bourgeons dormants épicormiques
Pas de dormance hivernale → pas de cicatrices d'écailles, pas de relances
après stress. Pour de vieux chênes ou des bouleaux endommagés, c'est ce qui
crée les fourches et les remontées caractéristiques.

### f. Sag du bouleau = hack
Le preset birch note "the real droop comes from post-sim mechanical sag" :
sag compense une architecture qui ne plie pas naturellement. Or
`Betula pendula` est pendula parce que ses **branches secondaires sortent
déjà plagiotropes** au cours du développement, pas par fléchissement
passif. `k=0.015` × `max_bend=8°` × `rigid_axis_order=2` est un patch.

### g. Densité de feuillage
`leaf_cluster_count: 3-5` par node ne reproduit pas la densité d'un vrai
houppier (chêne = milliers de feuilles/m³). Moins critique car le rendu
3D est hors scope.

---

## 4. Suggestions d'amélioration (priorisées)

### Haut impact, effort modéré
1. ~~**Exploiter `is_main_axis` partout.** Ajouter dans `TropismConfig` :
   `w_orthotropy_main` vs `w_orthotropy_lateral`, idem gravitropisme. Et un
   paramètre `plagiotropic_axes: [1, 2]` qui transforme
   `w_orthotropy → w_gravitropism_perpendiculaire` sur ces ordres. C'est *le*
   levier biologique manquant.~~ — **Addressed.** Phase 1 introduced
   `w_orthotropy_main/_lateral` and `w_gravitropism_main/_lateral`. Phase 2A
   adds explicit `w_plagiotropism_main/_lateral` (horizontal projection of
   current direction), making the plagiotropic axis tunable per-species
   without polluting gravity.
2. ~~**Jitter phyllotaxique.** Ajouter `divergence_jitter_deg` (gaussien,
   default ~5°) et `branch_angle_jitter_deg`. Trivial à implémenter, gros
   gain visuel anti-AI.~~ — **Addressed in Phase 1.** Both
   `phyllotaxy.divergence_jitter_deg` and `phyllotaxy.branch_angle_jitter_deg`
   are wired with gaussian draws from a deterministic per-(seed, node_index)
   RNG.
3. **Angle d'insertion qui s'ouvre avec l'âge/le poids.** Au lieu de sag
   postérieur, calculer pour chaque internode une rotation de son insertion
   *à la création*, proportionnelle à `axis_order` et à
   `parent_diameter / own_diameter`.

### Haut impact, effort élevé
4. **Croissance préformée pour conifères.** Ajouter un mode
   `sim.growth_mode: preformed` où chaque "année" (un set d'itérations
   consécutives) tire un nombre fixe d'internodes ± stochastique par
   leader, indépendant de Q. Crée les vrais étages.
5. [ADDRESSED — Phase 2B] **Réitération / bourgeons épicormiques.** Quand le shedding tue une
   branche maîtresse, réveiller un bourgeon dormant proximal et lui donner
   un boost de Q. Capture les fourches naturelles.
6. **Tropisme par poids (plagiotropisme dynamique).** Ce que le README
   appelle "non implémenté pour le saule" : ajouter un terme tropique
   `w_load · normalize(load_vector)` qui pousse la direction de croissance
   vers le bas proportionnellement à la masse subtree accumulée. Ça unifie
   sag et "willow" dans un seul mécanisme physiologique plutôt que
   post-process.

### Faible coût, polish
7. **Stochasticité de `internode_length`** (±10-20%). Constant =
   lisible-IA.
8. **`alpha_basipetal` qui décroît avec l'âge du tree** (carbon use
   efficiency baisse) → ralentissement naturel de la croissance vers la
   maturité.
9. ~~**Validation visuelle automatisée** : silhouettes 2D comparées à une
   banque d'images d'arbres réels (Procrustes ou métriques de fractalité).
   Évite la dérive paramétrique en aveugle.~~ — **Addressed.** Golden
   buffer-hash regression tests (`tests/golden/test_species_goldens.py`)
   plus per-species integration tests
   (`tests/integration/test_sympodial_emergence.py`,
   `tests/integration/test_plagiotropy_horizontalizes.py`) detect
   parametric drift on every commit.

### Pour les presets actuels
- **Oak** : `sag.k=0.005` trop faible — viser 0.01-0.015 sur les ordres
  1-2. Augmenter aussi `phyllotaxy.branch_angle_deg` à 65-70° (les vrais
  chênes ont des branches très ouvertes).
- **Pine** : ajouter croissance préformée (suggestion #4). Réduire
  fortement les axes d'ordre 3+ (un `max_axis_order: 3` global ?).
- **Birch** : remplacer sag agressif par un vrai plagiotropisme latéral
  (suggestion #6). Réduire `rigid_axis_order` à 1.

---

## 5. Verdict global

C'est **une bonne simulation** au sens *fidélité au papier* —
l'implémentation BHse+BHls est solide, propre, et bien testée. Mais
Palubicki 2009 produit des arbres qui ont une **silhouette correcte avec
une architecture interne approximative** : la vraie distinction d'espèce
vient de mécanismes (plagiotropisme par axe, croissance préformée,
réitération) que le papier n'inclut pas et que ce codebase n'a pas non plus
encore.

Les trois leviers les plus rentables :

1. Exploiter `is_main_axis` partout dans tropisms / phyllotaxy / shedding.
2. Jitter stochastique sur phyllotaxie et longueur d'internode.
3. Plagiotropisme par poids comme tropisme à part entière (remplaçant le
   sag post-process).

---

## 6. Phyllotaxie : branches vs feuilles individuelles

Distinction importante quand on parle de "support des modes alternate /
opposite / whorled" :

### Pour les branches (lateral buds) : OUI, supporté

Les trois modes sont implémentés dans
`src/palubicki/sim/phyllotaxy.py:21-28` :

```python
if cfg.mode == "alternate":   k = 1
elif cfg.mode == "opposite":  k = 2
elif cfg.mode == "whorled":   k = max(1, cfg.whorl_count)
```

Configuré via YAML :

```yaml
phyllotaxy:
  mode: whorled        # ou alternate / opposite
  whorl_count: 5
  divergence_angle_deg: 137.5
  branch_angle_deg: 75
```

État des presets :
- `pine.yaml` : `whorled` (verticilles) — correct biologiquement.
- `oak.yaml`, `birch.yaml` : `alternate`.
- **Aucun preset n'utilise `opposite`** — il manque une espèce de référence
  (érable, frêne, lilas, marronnier auraient besoin de ce mode).

### Pour les feuilles individuelles : NON, simplifié

`src/palubicki/geom/leaves.py:48-58` place les feuilles **aux sites de
feuillage** uniquement (bourgeons terminaux + `foliage_depth` nœuds en
arrière), avec `cluster_count` quads croisés disposés en **éventail
azimutal** autour de la direction de croissance
(`_emit_leaf_cluster`, l.119-145).

Conséquences :
- Le mode `alternate` du bouleau ne produit pas une alternance feuille-
  par-feuille le long du rameau — il produit un branchement alterné, et
  les feuilles sont des bouquets à l'extrémité.
- Pas de notion de pétiole, de lame (blade) orientée, ou d'insertion
  réelle au nœud individuel.
- Pas de feuilles distribuées le long des internodes — seulement aux
  sites de feuillage.

### Suggestion : phyllotaxie au niveau feuille

Pour vraiment supporter le schéma ci-dessus à l'échelle de la feuille
individuelle, il faudrait que `leaves.py` :

1. Place des feuilles à **chaque nœud** des derniers internodes (pas
   juste à l'apex), avec le même `mode` et `divergence_angle_deg` que la
   phyllotaxie des branches.
2. Le `cluster_count` deviendrait alors dérivé du mode : 1 pour
   alternate, 2 pour opposite, `whorl_count` pour whorled — au lieu d'un
   paramètre libre.
3. Modèle pétiole simple : un petit offset du nœud le long d'un vecteur
   radial perpendiculaire à l'axe, avec la lame orientée selon la
   lumière ou perpendiculaire à l'axe.

Effort estimé : ~150 lignes dans `leaves.py` + 2-3 paramètres en config.
Effet visuel important pour les rameaux feuillus en gros plan, plus
faible en silhouette de couronne.
