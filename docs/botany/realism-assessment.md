# Évaluation du réalisme botanique — lecture du code

Évaluation faite **uniquement à partir du code** (`src/palubicki/sim/`), pas de
la documentation, puis recoupée avec
[`code-support-matrix.md`](code-support-matrix.md). Le but n'est pas de
lister toutes les absences (la matrice de support le fait déjà) mais de distinguer
les **choix de périmètre assumés** des **angles morts qui dégradent le réalisme
dans le périmètre actuel**.

## Verdict court

Simulation **solide**, pas un jouet. C'est un FSPM par colonisation de
l'espace qui fait bien son métier : **géométrie et topologie de l'architecture
aérienne**, avec un bon compromis réalisme / vitesse. Les grandes absences
(racines, hormones explicites, reproduction, eau, température) sont des
**décisions de conception légitimes**, déjà documentées.

## Ce qui est vraiment bon

- **Allocation Borchert-Honda** à deux passes (`bh.py`) — dominance apicale
  *émergente*, pas codée en dur.
- **Lumière Beer-Lambert** par ray-marching sur grille de voxels
  (`light.py` / `light_perception.py`) → phototropisme directionnel réel.
- **Pipe model** da Vinci `D^n = Σ Dᵢ^n` idempotent (`radii.py`) + **sag** en
  flexion de poutre cantilever (`sag.py`).
- **Variation inter-espèces** crédible : sympodial vs monopodial, 5 modes de
  phyllotaxie, angles de branchaison par ordre.

## Angles morts qui comptent (dans le périmètre actuel)

1. **La « vigueur » n'est pas du carbone.** `v_b` est un flux d'allocation
   abstrait. Il n'y a pas de boucle source→puits : la lumière **oriente** et
   **tue**, mais une feuille bien éclairée ne **finance** pas son axe. Un rameau
   à l'ombre est puni deux fois indépendamment (mortalité d'ombrage *et* faible
   qualité de marqueurs). C'est l'écart conceptuel le plus structurant.

2. **Le feuillage est décoratif, pas fonctionnel.**
   - ~~La surface foliaire réelle n'est pas injectée dans la grille de lumière.~~
     **Résolu pour les feuillus ([#62](https://github.com/julien-riel/palubicki/issues/62)).**
     `sim/light.py` dépose désormais l'aire de lame **réelle** par feuille (forme,
     taille, lame composée, échelle soleil/ombre), via la fonction partagée
     `geom/leaves.py:leaf_area_records` — même source que le diagnostic
     `total_leaf_area` et le `.glb`. `light.leaf_area_scale` = multiplicateur.
     L'auto-ombrage des feuillus reflète maintenant la morphologie paramétrée.
     **Conifères** : couplés (#7) via le *même* `leaf_area_records` (multiplicité de
     fascicule incluse) × `light.needle_area_scale` ; le scalaire `light.leaf_area`
     par bourgeon terminal (l'ancienne « coquille de canopée ») est **retiré**.
     Coupler les vraies aiguilles cassait le leader (la coquille uniforme le
     soutenait), donc la dominance apicale est **re-calibrée** sur ce dépôt physique
     (`lambda_apical` pin relevé) — géométrie d'aiguilles et calibration lumière
     réglées ensemble, comme #55 (éventail) l'avait préparé pour la forme.
   - Aucune règle d'âge branchée : `Leaf.birth_time` / `LeafState`
     (`ACTIVE→SENESCENT→ABSCISSED`) existent mais la transition n'arrive jamais.
     Pas de caducité, pas de marcescence. L'infra est là, le fil est débranché.

3. **La mortalité d'ombrage cull, mais ne sculpte pas l'initiation.** L'ombre
   dense devrait *réduire l'émission* de latéraux (évitement d'ombre) ; ici on
   ne fait qu'élaguer a posteriori. La couronne se creuse par élagage, pas par
   parcimonie d'investissement.

4. **Déclencheurs « par échec » au lieu de développement.**
   - Le sympodial se déclenche sur *starvation* du terminal, alors que
     biologiquement l'apex se **détermine** (fleur terminale). Proxy, pas
     mécanisme — tant qu'il n'y a pas de croissance déterminée / reproduction.
   - L'épinastie est une rampe temporelle `1 - exp(-âge/τ)`, pas une réponse à
     l'éthylène ni au poids. Visuellement OK, causalement faux.

5. **Pas de mémoire mécanique du bois.** Le sag est recalculé en statique à
   chaque pas (`D²` comme moment d'inertie). Pas de bois de réaction, pas de
   redressement, pas de fluage, pas d'épaississement induit par le vent
   (Mattheck). Une branche ploie et reste « molle ».

6. **Phénologie binaire.** `annual_growth_period` est un interrupteur on/off :
   pas de degrés-jours, pas de vernalisation, pas de photopériode. La croissance
   ne ralentit jamais aux marges de saison, elle s'arrête net.

## Priorités recommandées

À fort rendement **dans le périmètre existant** (l'infra est déjà là) :

1. ~~**Caducité foliaire** (âge → senescence → abscission).~~ **Livré**
   ([#61](https://github.com/julien-riel/palubicki/issues/61),
   [#67](https://github.com/julien-riel/palubicki/issues/67)).
2. ~~**Coupler la surface foliaire réelle à la grille de lumière.**~~ **Livré pour
   les feuillus** ([#62](https://github.com/julien-riel/palubicki/issues/62)) ;
   conifères reportés à #55/#7 (voir angle mort #2 ci-dessus).

À **ne pas** faire sans changement d'ambition :

- Un vrai **budget carbone**. C'est la bonne façon de réparer l'angle mort #1,
  mais ça refonde le moteur — à réserver pour passer de « plausible » à
  « physiologique ».

## Pipeline lumière — limites connues & correctifs de l'audit 2026

Un audit de la chaîne lumière (perception → phototropisme → mortalité d'ombrage
→ phyllotaxie) a produit un lot de correctifs ciblés et, tout aussi
important, a **assumé explicitement** certaines limites comme des choix de
modèle plutôt que des bugs. Les champs de config cités vivent dans
[`config.py`](../../src/palubicki/config.py) sous `LightConfig`.

### Correctifs appliqués (ce PR)

| Réf. | Correctif (une ligne) |
| --- | --- |
| #1 | Exclusion de l'auto-ombrage de l'apex : le bourgeon n'occulte plus sa propre cellule lors de la perception. |
| A | Résolution de grille **scale-aware** : `voxel_edge_m` (0.04 m) dérive le nombre de voxels par axe `clamp(ceil(size/voxel_edge_m), 8, 192)` au lieu d'une résolution fixe. |
| B | Bouton `wood_extinction_scale` (défaut 1.0) qui multiplie la LAD du bois (internodes) au dépôt. |
| D | Gradient de lumière **centré** (différences centrées, pas décalées) pour la direction phototrope. |
| E | Phototropisme : plus de **repli sur UP** quand le gradient est nul ; on conserve la direction courante. |
| H | Décussé/verticillé : le terme spiral `divergence*node` n'est plus ajouté (le mode est défini par le seul basculement 90°/π·k), donc le défaut `divergence=137.5` ne corrompt plus la structure. |
| I | Mortalité d'ombrage des **bourgeons dormants** : un bourgeon DORMANT (tissu vivant, ré-évalué chaque itération) accumule l'ombre et meurt comme un ACTIF ; RESERVE/DEAD restent épargnés, le compteur se réinitialise quand le bourgeon est éclairé. |
| #2/#3 | Réserves phyllotaxiques : azimut par-mode partagé (opposé aux latéraux en décussé/verticillé/distique) **+** angle d'insertion indexé par `axis_order` (au lieu de `[0]`). |

### Limites assumées (documentées, **non** modifiées dans le code)

Ces points ne sont **pas** des correctifs : ce sont des décisions de modèle,
notées ici pour qu'on ne les reprenne pas pour des oublis.

- **C — la lumière est une irradiance d'hémisphère cosine-pondérée autour du
  vecteur ciel.** La perception estime l'irradiance diffuse reçue par une
  facette tournée vers le haut ; **l'orientation du bourgeon est volontairement
  ignorée**. C'est l'estimateur d'irradiance diffuse physiquement correct, pas
  un bug : un bourgeon ne « regarde » pas une direction privilégiée, il intègre
  le ciel visible.

- **B — le bois partage le coefficient d'extinction `k` du feuillage.** Le bois
  est modélisé comme un milieu turbide de même `k_absorption` que la lame
  foliaire ; or de vraies branches ne sont quasi opaques qu'au tronc.
  `wood_extinction_scale` (défaut **1.0**) permet de relever l'opacité du bois,
  mais la monter par défaut **composerait** l'auto-ombrage et **décalibrerait**
  les espèces — le défaut reste donc 1.0.

- **F-résiduel — `light_factor` injecte encore la qualité « nombre de marqueurs »
  dans VIGUEUR et SHEDDING.** Seul le **seuil sympodial** voit désormais une
  qualité *marqueurs seuls*. Séparer entièrement les deux monnaies (lumière vs
  marqueurs) dans la vigueur/abscission est **reporté** pour ne pas déstabiliser
  la calibration (c'est l'angle mort #1 ci-dessus, qui demande un budget carbone).

- **A-rationale — les constantes de calibration lumière sont liées à la taille
  physique de cellule.** `k_absorption`, `leaf_area_scale` et `needle_area_scale`
  supposent une taille de voxel donnée ; avec `voxel_edge_m` fixe, elles
  **transfèrent** désormais d'une taille d'enveloppe à l'autre (c'était l'objet
  du correctif A). Un re-réglage reste nécessaire **si** `voxel_edge_m` change —
  ce contrat est désormais explicite ci-dessous (**Contrat de calibration**, #85).

- **#4 (tenté puis ABANDONNÉ) — diagnostic de divergence spray-aware.** L'idée
  était de mesurer les latéraux d'ordre 2+ dans le repère spray (gaucher) où ils
  sont posés, pour corriger le miroir 222,5° → 137,5°. Mais le diagnostic
  reconstruisait le normal spray depuis la **tangente** sans vérifier
  `spray_plane_enabled` ni le `spray_plane_normal` réel du bourgeon : dès que le
  tronc dévie de la verticale (déviation du leader ~10-15°), la mesure basculait
  dans le repère spray **même pour l'ordre-1**, miroitant la `divergence_angle`
  ordre-1 (oak 142 → 198, hors la bande 130-145) — métrique pourtant bandée.
  Reverté ; le miroir d'ordre-2+ (non bandé, cosmétique) reste un quirk connu du
  diagnostic.

### Contrat de calibration — `voxel_edge_m = 0.04` (#85)

**Les six presets d'espèces sont calibrés pour `light.voxel_edge_m = 0.04` m.**
Aucun preset ne fixe `voxel_edge_m` (`grep configs/species/*.yaml` → zéro) : tous
héritent du défaut de `LightConfig`. Les constantes optiques — `k_absorption`
(0.45 `birch` … 0.65 `fir`/`pine`), `leaf_area_scale` (1.0, hérité partout) et
`needle_area_scale` (0.5 sur `fir`/`pine`) — ont été réglées **à cette taille de
cellule**, contre les bandes `literature.yaml` (garde-fou #87).

**Pourquoi changer `voxel_edge_m` invalide ces constantes.** La grille dépose
l'aire de lame réelle en densité surfacique `LAI = aire / volume_cellule`
([`light.py`](../../src/palubicki/sim/light.py) `_inject_tree`), et le ray-march
Beer-Lambert accumule `τ += k · LAI · step_len` avec
`step_len = min(cell_size) ≈ voxel_edge_m`. Les cellules étant ~cubiques d'arête
`e = voxel_edge_m` (`volume ≈ e³`, `step_len ≈ e`), la profondeur optique d'une
feuille déposée vaut `k · aire · e / e³ = k · aire / e²` : **la profondeur optique
par feuille est ∝ 1/voxel_edge_m²**. Diviser `voxel_edge_m` par deux **quadruple**
donc l'auto-ombrage à constantes égales — la couronne se referme, l'élagueur
d'ombre sur-coupe, et hauteur/tronc/couronne/Horton sortent de bande. (Vrai dans
le régime non *clampé* `[8,192]` voxels/axe ; aux très grandes/petites enveloppes
le clamp fait dévier `e` de la cible, donc la relation `1/e²` n'est qu'un guide —
raison de plus pour re-régler **empiriquement** plutôt que par formule.)

**Procédure de re-calibration, si `voxel_edge_m` doit changer** (de `e₀=0.04` à
`e₁`) :

1. Poser la nouvelle valeur — défaut `LightConfig.voxel_edge_m`, ou par-preset.
2. Premier jet analytique : `k_absorption ← k · (e₁/e₀)²` comme **point de départ**
   (annule la mise à l'échelle `1/e²` au premier ordre) ; alternativement bouger
   `leaf_area_scale`/`needle_area_scale` du même facteur si l'on préfère agir sur
   l'aire que sur `k`.
3. Boucle empirique ([`mindset-boucle-empirique.md`](../mindset-boucle-empirique.md)) :
   `palubicki diagnose --species <sp> --seed 0,1,2` par espèce, ajuster jusqu'à ce
   que les métriques **bandées** (hauteur, tronc, couronne, leader, continuation,
   Horton, divergence + insertion ordre-1) rentrent.
4. Verrouiller : `pytest tests/integration/test_botanical_guardrail.py` — vert =
   6 espèces en bande sur graines {0,1,2} (#87).
5. Re-épingler les goldens (`tests/golden`) : la géométrie change.

Tant que `voxel_edge_m` reste à `0.04`, ces constantes **transfèrent** d'une
taille d'enveloppe à l'autre (objet du correctif A : grille *scale-aware*) — c'est
précisément la propriété qui rend ce contrat tenable, et pourquoi le défaut ne
doit pas bouger à la légère.

### Dérive de calibration (vs baseline, FIX #4 reverté)

Les correctifs comportementaux (#1, A, D, E, F, H, I) déplacent le champ lumineux
et la croissance. Mesuré sur seeds 0/1/2, le bilan des métriques **hors-bande
littérature** passe de **11 → 8** — une **amélioration nette**, pas une
régression :

| Espèce | Baseline | Post-correctifs | Détail des hors-bande restants |
| --- | --- | --- | --- |
| oak   | 1 | 1 | `insertion_angle` ordre-1 (27,7° / 30-65) |
| birch | 1 | **0** | — (`crown_radius` rentré en bande) |
| maple | 4 | **2** | `insertion_angle` (18,0°) ; `divergence` décussé (178° / 80-100) |
| ash   | 2 | 2 | `insertion_angle` (17,1°) ; `divergence` décussé (174,8° / 130-145) |
| fir   | 1 | 1 | `insertion_angle` (19,4°) |
| pine  | 2 | 2 | `insertion_angle` (20,3°) ; `divergence` verticillé (93,1° / 130-145) |

Les métriques de **croissance** (`tree_height`, `trunk_base_diameter`,
`crown_radius`, `bif_ratio`) sont désormais **toutes en bande** sur les 6
espèces. Les 8 hors-bande restants sont **tous pré-existants** et relèvent de
**deux bugs de diagnostic** (≠ scope de ce PR, voir issue de suivi) :

1. **`insertion_angle_deg_vs_parent` dilué.** Le diagnostic moyenne l'angle de
   *chaque* internode vs son prédécesseur ; pour un axe d'ordre-1, seul le 1ᵉʳ
   internode mesure la vraie insertion (vs tronc) — les suivants mesurent la
   courbure intra-branche. Sur oak/seed-0 : **29** internodes d'insertion
   (vraie insertion **75,7°**) noyés dans **265** internodes de courbure
   (**20,2°**) → moyenne **25,6°**, sous la bande 30-65 quelle que soit la
   calibration. Systématique (5/6 espèces).
2. **`divergence_angle_deg` ordre-1 pour décussé/verticillé.** La bande de type
   « angle d'or » (130-145) ne correspond pas à la divergence structurelle du
   décussé (~90/180°) ni du verticillé (pine ~72-93°). Question de **bande mal
   typée par mode**, pas de réglage.

### Vérification finale post-#83 (#85) — tout en bande

Les deux bugs de mesure ci-dessus sont **résolus dans #83 (livré)** : l'insertion
est mesurée au seul **internode fondateur** de chaque axe (plus diluée par la
courbure intra-branche) et la divergence **par mode** de phyllotaxie, bandes
re-dérivées post-tropisme (insertion globale `(50,90)` ; divergence alterné
`(130,145)` / décussé `(80,100)` / verticillé pin `(52,78)`). La **vérification
finale de #85** — `palubicki diagnose --species <sp> --seed 0,1,2` sur les
**6 espèces** **+** `tests/integration/test_botanical_guardrail.py` (#87 :
**6 passed**, 958 s, graines {0,1,2}) — confirme que **toutes les métriques
bornées sont en bande** : les 8 résidus du tableau #84 sont **tous résorbés**
(c'étaient bien des **artefacts de mesure**, pas une dérive des constantes
lumière). Valeurs ordre-1 désormais en bande :

| Espèce | insertion ∠ ordre-1 | divergence ∠ ordre-1 (mode) |
| --- | --- | --- |
| oak   | 74,4 ✓ | 141 ✓ (alterné) |
| birch | 82,0 ✓ | 138 ✓ (alterné) |
| maple | 54,7 ✓ | 90,9 ✓ (décussé) |
| ash   | 53,8 ✓ | 89,5 ✓ (décussé) |
| fir   | 75,2 ✓ | 141 ✓ (alterné) |
| pine  | 76,7 ✓ | 66,0 ✓ (verticillé) |

Les métriques de croissance (hauteur, tronc, couronne, leader, continuation,
Horton) restent **toutes en bande** sur les 6 espèces (#84). La calibration
`voxel_edge_m = 0.04` (**Contrat de calibration** ci-dessus) est donc **vérifiée
tout en bande**, graines {0,1,2} — ce qui **clôt #85**.

## Forme émergente — backend shadow-propagation (#56)

`palubicki` propose deux **backends d'exposition** des bourgeons, sélectionnables
par config (`exposure`), tous deux issus de Palubicki et al. 2009 :

| Variante | `exposure` | La forme macro est… | Enveloppe `shape` |
| --- | --- | --- | --- |
| **BHse** (défaut) | `bhse` | **prescrite** — markers échantillonnés *dans* le volume d'enveloppe ; `cone` ⇒ silhouette conique | le volume **est** la forme |
| **Shadow propagation** | `shadow_propagation` | **émergente** — la direction et le sort des bourgeons viennent de la compétition lumineuse ; pas de markers | volume de bornes **neutre/advisory** seulement |

Sous `shadow_propagation`, l'exposition `Q` d'un bourgeon se mesure de deux façons
(`shadow.measure`) : **`skyview`** (défaut) réutilise la transmission hémisphérique
du grid lumière #37 (fraction de ciel ouvert, machinerie d'auto-ombrage calibrée
#85) ; **`pyramid`** utilise le champ d'ombre descendant de Palubicki
(`a · b^(−q)`, `shadow.{a,b,q_max}`), moins cher mais plus grossier. `Q` pilote la
direction (gradient vers le plus éclairé), la dormance (`Q < shadow.q_dormancy`) et
la vigueur BH (`Q · shadow.quality_scale`, mis à l'échelle des comptes de markers
contre lesquels BH est calibré). `shade_mortality` est **désactivé** sous ce backend
(la dormance réversible sur `Q` est le mécanisme de fût clair).

### Constat de calibration : couronne émergente **ovoïde/inversée**, pas un cône

Le **leader est excellent** et émergent (`main_axis_continuation_rate = 1.0`,
`leader_deviation_deg = 0°` — sans enveloppe `cone`). Mais la **couronne latérale**
est, sous toute mesure et tout le levier de calibration, **ovoïde voire inversée**
(profil le plus large vers la **cime**, base étroite) — l'inverse d'un sapin :

| | profil rayon couronne (base→cime) | apex_sharpness | `silhouette_drift` vs fir-BHse cône |
| --- | --- | --- | --- |
| fir BHse (cône, référence) | `[2.99 … 1.93 … 0.84]` (décroissant) | 0,28 | 0,00 |
| fir shadow-prop (sky-view, calibré) | `[0.6 … 3.8 (cime) … 1.6]` | 0,37–0,41 | ≈ 0,38 |

**Cause racine — dynamique de longueur de branche** (pas un défaut de l'une des
mesures d'exposition) : la vigueur pilotée par la lumière fait que les latérales de
**cime** (jeunes mais les plus éclairées → ciel ouvert) poussent **le plus long**,
tandis que les latérales **basses** (sous la canopée → ombragées → faible `Q`)
restent **courtes**. Chez un vrai sapin c'est l'inverse : les branches basses sont
les **plus longues** car elles ont grandi **tôt** (quand elles étaient la cime
éclairée) et **conservent** cette longueur après ombrage (persistance ligneuse) — ce
que ce modèle vigueur-par-itération ne **banque** jamais.

Levier `sim.apical_control_length` (contrôle apical acrotone : la longueur d'internode
latéral est mise à l'échelle par la profondeur sous l'apex) livré dans #56 : il
**affine la cime** (2 bandes du haut) mais ne renverse pas le corps ovoïde — et
pénalise même les futures branches basses pendant leur fenêtre de croissance
précoce. La forme cône réelle exige une **dynamique de longueur de branche**
(banque + persistance) + un contrôle apical qui ne prive pas les branches basses —
**hors périmètre de #56** (backend d'exposition), suivi en **[#94](https://github.com/julien-riel/palubicki/issues/94)**
(territoire dominance apicale #36/#51).

**Livré par #56** : le backend lui-même (config-sélectionnable, `bhse` défaut
**byte-identique**), les deux mesures d'exposition, le diagnostic de silhouette
(`apex_sharpness` / `clear_bole_fraction` / `silhouette_drift`, `sim/diagnostics.py`),
et le levier `apical_control_length`. **Non livré (→ #94)** : la silhouette conique
émergente. Les presets conifères restent sur `bhse` (le cône calibré). Pour essayer
le backend : `exposure: shadow_propagation`, `envelope.shape: half_ellipsoid` (bornes
généreuses non-cône), `shadow.measure: skyview`.

### Contrat de calibration — mesure `pyramid` (#56)

Si `shadow.measure: pyramid`, le dépôt `Δs = (aire · area_weight) · a · b^(−q)` est
**dépendant de `voxel_edge_m`** (`q_max` compte des voxels ; profondeur physique
`= q_max · voxel_edge_m`). Les constantes `shadow.{a,b,q_max}` sont donc liées au
même `voxel_edge_m = 0.04` que le **Contrat de calibration** ci-dessus, et **n'héritent
pas** des constantes Beer-Lambert (`k_absorption`, `needle_area_scale`) — c'est une loi
optique distincte. La mesure `skyview` (défaut) réutilise au contraire la machinerie
#37/#85 déjà calibrée et n'introduit pas de nouveau contrat.
