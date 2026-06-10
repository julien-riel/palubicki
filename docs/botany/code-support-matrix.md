# Matrice de support botanique — code vs. `plant-structure.md`

Pour chaque concept du primer de morphologie
([plant-structure.md](./plant-structure.md)), ce rapport indique s'il est
**supporté dans le code** (`src/palubicki/`), avec la preuve (module + symbole).
Quand il ne l'est pas, on pointe le **billet** qui le corrige ; à défaut de
billet, on **skip** (avec raison) ou on **suggère d'en créer un** (récapitulés
en fin de document).

> Établi par lecture du code. Complète [`realism-assessment.md`](./realism-assessment.md)
> (qui juge le *réalisme dans le périmètre*) : ici, une lecture **binaire
> support / billet**, structurée concept par concept sur le primer. L'historique
> est dans git.

**Légende statut :** ✅ supporté · 🟡 partiel · ❌ absent.
**Colonne billet :** numéro d'issue qui couvre l'écart · `SKIP` (hors périmètre
assumé) · `SUGGÉRER` (pas de billet, on recommande d'en ouvrir un — voir §
final).

Presets d'espèces livrés (`configs/species/`) : **oak, ash, maple, birch**
(feuillus) · **pine, fir** (conifères).

---

## §2–§3 — Phytomère & méristèmes

| Concept | Statut | Preuve (code) | Billet / décision |
|---|---|---|---|
| Phytomère = nœud + entre-nœud + feuille(s) + bourgeon(s) | ✅ | `sim/tree.py` — `Node`, `Internode`, `Bud`, `Leaf` ; feuilles first-class sur `Node.leaves` | [#14](https://github.com/julien-riel/palubicki/issues/14) livré |
| Méristème apical (bourgeon terminal, croissance primaire) | ✅ | `Node.terminal_bud` ; émission dans `sim/simulator.py::_emit_node` | — |
| Méristèmes axillaires (latéraux → branches) | ✅ | `Node.lateral_buds` ; nouveaux axes `axis_order+1` dans `simulator.py` | — |
| Méristèmes intercalaires (croissance basale, graminées) | ❌ | aucune zone de croissance basale ; croissance uniquement aux apex | [#12](https://github.com/julien-riel/palubicki/issues/12) |
| Cambium / croissance secondaire (épaississement) | ✅ | `sim/radii.py` — pipe-model `r^n = Σ rᵢ^n`, recompute incrémental | — |
| Croissance déterminée vs indéterminée | 🟡 | `sim/sympodial.py` — relais latéral sur **échec de qualité** du terminal, pas sur détermination (fleur terminale) | [#11](https://github.com/julien-riel/palubicki/issues/11) — apex déterminé arrive avec les fleurs |

> **Note croissance secondaire** — pas d'anneaux annuels (`§8.2`) ; le pipe-model
> est un proxy allométrique, pas une activité cambiale datée. Anneaux : `SKIP`
> (faible rendu visuel).

---

## §4 — Architecture de branchaison

| Concept | Statut | Preuve (code) | Billet / décision |
|---|---|---|---|
| Monopodial (leader persistant) | ✅ | `Internode.is_main_axis` ; continuation du terminal | — |
| Sympodial (terminal cède au latéral) | ✅ | `sim/sympodial.py::promote_lateral_if_failing` ; `Node.sympodial_fork` | — |
| Dominance apicale | ✅ | `sim/bh.py` — allocation Borchert-Honda à deux passes, `lambda_apical` ; dominance **émergente** (pas d'hormone explicite — choix de conception) | — |
| Forme macro de couronne émergente (cône conifère) | ✅ | 2ᵉ backend d'exposition config-sélectionnable : `exposure: shadow_propagation` (`shadow.measure: skyview \| pyramid`) — la forme vient de la compétition lumineuse, **pas de l'enveloppe**. Sous `sim.length_banking` (longueur latérale pilotée par l'âge, #94) le sapin (#94) **et le pin** (#96) développent un **vrai cône** sous bornes neutres `half_ellipsoid` : sapin `crown_monotonicity` −0.77 (était +0.31 ovoïde), `silhouette_drift` ~0.17 vs fir-BHse-cône ; pin −0.93, hauteur/couronne/tronc **en bande pin** (16.1 m / 3.63 m / 0.258 m à 30 ans). Le pin (verticillé k=5) exige en plus un **pool de bourgeons borné** — `shadow.mortality_enabled` (kill d'ombre sous shadow mode, latérales bankées protégées) + `q_dormancy` 0.5 — sans quoi il part en vrille (200k+ internodes). Défaut OFF ⇒ byte-identique. Voir realism-assessment §forme émergente | [#56](https://github.com/julien-riel/palubicki/issues/56) (backend) + [#94](https://github.com/julien-riel/palubicki/issues/94) (sapin) + [#96](https://github.com/julien-riel/palubicki/issues/96) (pin + pool borné) livrés ; presets conifères restent `bhse` (golden gelé), émergence prouvée par `tests/integration/test_emergent_cone.py` |
| Forme macro de couronne émergente (couronne feuillue arrondie/décurrente) | ✅ | Pendant feuillu de #94 : sous `exposure: shadow_propagation` mesure **`pyramid`** + le profil **`sim.length_banking.profile: rounded`**, chêne/érable/frêne/bouleau développent une couronne **arrondie** (la plus large au milieu, `crown_widest_frac` ≈ 0.4–0.7), ni cône (~0.05) ni plumeau-inversé (~0.95). `pyramid` étouffe l'intérieur bas (la base se dégage) ; le profil `rounded` **multiplie** la longueur éclairée par un **bosson d'âge** (au lieu de la remplacer — la portée des branches étant cumulative en âge, le creux de bole vient de l'auto-ombrage + mortalité, pas de la longueur seule). Pool borné par `establish_threshold` ≈ q95 de `banked_vigor` (érable/frêne décussés ~25× les bourgeons du chêne → seuil 40–45 vs 2 ; ré-explose en super-linéaire > ~y14, limite de traçabilité). Nouveau diagnostic `crown_widest_frac`. Bouleau = ovale monopodial-pleureur à cime pleine (exception). Défaut `acropetal_ramp` ⇒ byte-identique. **Recettes des 6 espèces expédiées comme presets autonomes** `configs/species/{espèce}_emergent.yaml` (`generate --species X_emergent`, horizon max traçable par espèce : sapin/pin y30 pleine taille, chêne/bouleau y18, érable/frêne y12) — presets de base intouchés sur `bhse`. Voir realism-assessment §#97 | [#97](https://github.com/julien-riel/palubicki/issues/97) livré ; presets feuillus restent `bhse` (golden gelé), émergence prouvée par `tests/integration/test_emergent_broadleaf_crown.py` |
| Acrotonie / mésotonie / basitonie | ✅ | `sim/bud_break_bias.py::position_weight` + `sim.bud_break_bias` (mode + force) | [#3](https://github.com/julien-riel/palubicki/issues/3) livré |
| Orthotropie vs plagiotropie | ✅ | `sim/tropisms.py` — `w_orthotropy_*`, `w_plagiotropism_*` (projection sur XY, ou sur le plan de la branche-mère si `spray_plane_enabled`) | — |
| Plagiotropie par épinastie (arc temporel vers l'horizontale) | ✅ | `sim/tropisms.py` — rampe `1 − exp(−âge/τ)`, `epinasty_tau_years` | [#34](https://github.com/julien-riel/palubicki/issues/34) livré |
| Éventail latéral cohérent (plan de la branche-mère) | ✅ | `sim/tropisms.py` + `sim/phyllotaxy.py` — `spray_plane_enabled` réfère plagiotropie **et** base d'insertion radiale au plan de l'axe parent (normale figée au débourrement) ; diagnostic `out_of_plane_deviation_deg` | [#55](https://github.com/julien-riel/palubicki/issues/55) livré |
| Angles de branchaison par ordre d'axe | ✅ | `phyllotaxy.branch_angle_by_order` (ex. chêne `[60,40,30,25]`) | — |
| Sélection de modèle Hallé–Oldeman (23 modèles) | ❌ | pas d'enum/preset de modèle nommé | `SKIP` — les axes indépendants (mono/sympodial × ortho/plagio × angles par ordre × phyllotaxie) couvrent déjà l'espace ; un catalogue nommé n'ajoute rien |

> **Note spray latéral** — `spray_plane_enabled` ([#55](https://github.com/julien-riel/palubicki/issues/55), livré, actif sur `fir`/`pine`)
> projette la plagiotropie et la base d'insertion sur le **plan de la branche-mère**
> (dérivé au débourrement, hérité le long du frond) plutôt que sur le plan XY mondial,
> et ne décale plus la plagiotropie par `axis_decay` aux ordres supérieurs → les
> branchlets d'ordre 2+ s'aplatissent dans le frond (fir : déviation hors-plan
> ordre-2 ~24°→12°). Désactivé par défaut (legacy XY bit-identique).

---

## §5 — Phyllotaxie

| Concept | Statut | Preuve (code) | Billet / décision |
|---|---|---|---|
| Distique (alterne, 2-rangs, 180°) | ✅ | `sim/phyllotaxy.py` mode `distichous` ; `distichous_on_plagiotropic` | [#2](https://github.com/julien-riel/palubicki/issues/2) livré |
| Opposée-décussée (paires à 90° de la précédente) | ✅ | `sim/phyllotaxy.py` mode `decussate` (demi-pas `π/2`) | — |
| Verticillée (n feuilles/nœud + rotation inter-verticille) | ✅ | `sim/phyllotaxy.py` mode `whorled`, `whorl_count`, offset `(π/k)·(i%2)` | [#35](https://github.com/julien-riel/palubicki/issues/35) livré |
| Spiralée / angle d'or (137,5°) | ✅ | `divergence_angle_deg` défaut 137.5 | — |
| Jitter de divergence | ✅ | `sim/phyllotaxy.py` — gaussienne ; `divergence_jitter_deg` | — |
| Livraison **par axe** de la divergence | ✅ | `Bud.axis_node_ordinal` (remplace le `node_index` global) | [#24](https://github.com/julien-riel/palubicki/issues/24) livré |

---

## §6 — Feuilles

| Concept | Statut | Preuve (code) | Billet / décision |
|---|---|---|---|
| Anatomie : lame, pétiole, angle d'insertion, rotation | ✅ | `geom/leaf_blade.py` (lame 2D, **éventail subdivisé** sur la lame héro) + **lame héro 3D** courbée/pliée `geom/leaf_blade3d.py` (pli médian **ou pli par nervure de lobe** palmé + **cuvette transversale** `leaf_blade_cup` + recourbure, normales/tangentes lissées) sur les feuillus ; orientation **diahéliotropique** `leaf_skyface` (`geom/leaves.py::leaf_basis` — la face adaxiale se présente vers le ciel, rotation autour de l'axe pétiole donc attache préservée) ; pétiole effilé `geom/compound_leaf.py` ([#5](https://github.com/julien-riel/palubicki/issues/5)) ; `leaf_splay_deg` ; `Leaf.azimuth` | [#5](https://github.com/julien-riel/palubicki/issues/5) + [#73](https://github.com/julien-riel/palubicki/issues/73) (lame héro) livrés ; cuvette + pli-par-nervure + face-ciel livrés |
| Nervation géométrique (parallèle/pennée/palmée/dichotome) | 🟡 | relief de nervure via **normal map** + masque de translucence dérivés du **contour réel** de la lame (médiane/éventail alignés sur les lobes via `leaf_blade.palmate_lobe_axes`, base ancrée au pétiole) : `geom/maps.py` + `_textures.leaf_vein_mask` ; relief géométrique **par nervure de lobe** sur la lame héro palmée (`leaf_blade3d._rib_distance`) ; pas de géométrie par-veine indépendante (tube) | [#73](https://github.com/julien-riel/palubicki/issues/73) livré (relief carte) ; pli-par-nervure palmé + nervures dérivées-du-contour livrés ; géométrie par-veine indépendante hors scope (`SKIP` structurel) |
| Simple vs composée (pennée/palmée/bipennée) | ✅ | `leaf_kind` + `geom/compound_leaf.py` (`_pinnate`/`_palmate`/`_bipinnate`, rachis) | [#6](https://github.com/julien-riel/palubicki/issues/6) livré |
| Lame paramétrique : forme + marge | ✅ | `leaf_shape` (6 formes) + `leaf_margin` (entire/serrate/dentate/lobed) ; `geom/leaf_blade.py` | [#4](https://github.com/julien-riel/palubicki/issues/4) livré |
| Durée de vie : caducité / persistance / marcescence | ✅ | `sim/caducity.py::advance_leaf_states` (âge/saison → `LeafState`, déterministe) ; l'entrée en dormance lit le driver partagé `clock.phenology_activity` (même seuil que l'arrêt de croissance, #65) ; `leaf_phenology` (decidu/persistant, lifespan, marcescence) ; couleur d'automne via `leaf_autumn_color` (COLOR_0) ; renderer rend `ACTIVE`+`SENESCENT`, filtre `ABSCISSED` | [#61](https://github.com/julien-riel/palubicki/issues/61) livré — caducité saisonnière à dt sous-annuel ; re-flush sur vieux bois + turnover aiguilles reportés (voir roadmap) |
| Hétérophyllie soleil/ombre | ✅ | `geom/leaves.py::compute_effective_leaf_size`, `leaf_sun_shade_k` | — |
| Aiguilles de conifère, fascicules (2–5) | ✅ | `geom/config` `fascicle_count` (pin = 5 aiguilles/fascicule) : chaque position d'aiguille (`needle_cluster_spacing`) émet N aiguilles évasées 360/N autour de l'axe du faisceau (`leaf_basis`, helper partagé `fascicle_offsets`), gainées par une gaine basale brune (`build_sheath_primitive`, réutilise le tube tapéré #5) ; aiguille seule (`fascicle_count` 1) pour le sapin (2-rangs) et les feuillus → byte-identique | [#7](https://github.com/julien-riel/palubicki/issues/7) livré |

---

## §7 — Racines

| Concept | Statut | Preuve (code) | Billet / décision |
|---|---|---|---|
| Topologie racinaire (pivot / fasciculée) | ❌ | rien sous le sol (recherché : aucun module racine) | `SKIP` — périmètre **aérien** assumé ([realism-assessment](./realism-assessment.md)) |
| Évasement racinaire / contreforts | ✅ | `geom/tubes.py` — `_flare_radius_field` + contreforts ; `root_flare_*`, `root_buttress_*` | [#8](https://github.com/julien-riel/palubicki/issues/8) livré |

---

## §8 — Tiges & croissance secondaire

| Concept | Statut | Preuve (code) | Billet / décision |
|---|---|---|---|
| Croissance primaire (élongation progressive) | ✅ | `sim/elongation.py` (rampe sigmoïde) ; longueur pilotée par la vigueur ([#20](https://github.com/julien-riel/palubicki/issues/20)) | [#20](https://github.com/julien-riel/palubicki/issues/20) livré |
| Croissance secondaire (pipe-model, règle de da Vinci) | ✅ | `sim/radii.py` — `r^n = Σ rᵢ^n`, `pipe_exponent` (~2.35–3.40 par espèce) + graine de vigueur | — |
| Anneaux annuels | ❌ | non suivis | `SKIP` — faible rendu visuel |
| Texture/variation d'écorce par diamètre | ✅ | `geom/bark_blend.py` (gradient 3 arrêts young→mature→senescent) ; textures procédurales `geom/_textures.py` | [#9](https://github.com/julien-riel/palubicki/issues/9) livré |
| Relief d'écorce (normal/height maps) | ✅ | écorce PBR complète : normale tangent-space Sobel (OpenGL +Y) depuis un champ de hauteur **propre** par espèce + ORM packé (`geom/maps.py`, `_textures.*_bark_height`) ; specular cuticule | [#73](https://github.com/julien-riel/palubicki/issues/73) livré (P2 de [#53](https://github.com/julien-riel/palubicki/issues/53)) |

---

## §9 — Structures reproductives

| Concept | Statut | Preuve (code) | Billet / décision |
|---|---|---|---|
| Fleurs (calice/corolle/androcée/gynécée) | ❌ | aucun module (recherché : sepal/petal/stamen/carpel…) | [#11](https://github.com/julien-riel/palubicki/issues/11) |
| Inflorescences (grappe, panicule, ombelle, capitule…) | ❌ | aucun module | [#11](https://github.com/julien-riel/palubicki/issues/11) |
| Cônes (gymnospermes) | ❌ | « cone » n'existe que comme **forme d'enveloppe** (`shape: cone`), pas comme structure botanique | `SUGGÉRER` — équivalent gymnosperme de [#11](https://github.com/julien-riel/palubicki/issues/11), non couvert par son intitulé (fleurs/inflorescences) |
| Fruits (baie, drupe, akène, samare…) | ❌ | aucun module | `SUGGÉRER` — suite naturelle de [#11](https://github.com/julien-riel/palubicki/issues/11) (un fruit est un ovaire mûri) |

---

## §10 — Groupes de plantes (modes de croissance)

| Concept | Statut | Preuve (code) | Billet / décision |
|---|---|---|---|
| Arbres feuillus décidus | ✅ | presets `oak`, `ash`, `maple`, `birch` | — |
| Conifères (couronne excurrente, aiguilles) | ✅ | presets `pine`, `fir` ; aiguilles linéaires + `needle_cluster_spacing` | — |
| Arbustes (multi-tiges, basitone) | 🟡 | biais basitone configurable (`bud_break_bias`), mais **aucun preset arbuste** | `SUGGÉRER` — livrer un preset (lilas/cornouiller) ; pas de changement moteur |
| Graminées (méristème intercalaire, tallage, chaumes) | ❌ | absent | [#12](https://github.com/julien-riel/palubicki/issues/12) |
| Herbacées (forbs) | ❌ | pas de distinction herbacé/ligneux | `SKIP` — dépend de la croissance déterminée ([#11](https://github.com/julien-riel/palubicki/issues/11)) + graminées ([#12](https://github.com/julien-riel/palubicki/issues/12)) |
| Lianes / vignes (thigmotropisme, recherche de support) | ❌ | absent | [#44](https://github.com/julien-riel/palubicki/issues/44) |
| Bulbes / cormes / rosettes / succulentes | ❌ | absent | `SKIP` — formes à paramètres extrêmes, hors trajectoire |

---

## §11 — Patterns quantitatifs

| Concept | Statut | Preuve (code) | Billet / décision |
|---|---|---|---|
| Allométrie (pipe-model, exposant) | ✅ | `sim/radii.py`, `pipe_exponent` | — |
| Loi de flambement `H ∝ D^(2/3)` (McMahon) | 🟡 | non imposée comme contrainte ; le fuselage **émerge** du pipe-model + vigueur | `SKIP` — émergent, pas un levier direct |
| Dimension fractale (densité de couronne) | ❌ | pas de paramètre dédié | `SKIP` — émerge des règles, pas un réglage direct |
| Ordres de branchaison Strahler / Horton | ✅ | `sim/diagnostics.py` — `_strahler_orders`, ratios de bifurcation | [#1](https://github.com/julien-riel/palubicki/issues/1) livré |
| Angles de divergence (spiral/décussé/distique/verticillé) | ✅ | génération `sim/phyllotaxy.py` (voir §5) ; **mesure** diagnostic désormais **par mode** (`_divergence_angle_metrics` : rotation inter-nœud mod `360/k` pour spiral/décussé, espacement intra-verticille plus-proche-voisin `360/k` pour le verticillé) | [#83](https://github.com/julien-riel/palubicki/issues/83) livré (mesure) |
| Angle d'insertion des branches (par ordre) | ✅ | `branch_angle_by_order` (génération) ; **mesuré au point de branchement** dans `sim/diagnostics.py` (#83 — internode fondateur de chaque axe, plus dilué par la courbure intra-axe) | [#83](https://github.com/julien-riel/palubicki/issues/83) livré (mesure) |
| Conformité aux bornes `literature.yaml` **vérifiée (multi-graines)** | ✅ | `tests/integration/test_botanical_guardrail.py` — chaque espèce simulée sur graines {0,1,2} ; `sim/diagnostics.py::check_bounds` / `gated_fields` échoue si la **moyenne** d'une métrique **bornée** dérive hors de sa bande citée (hauteur/tronc/couronne/continuation/leader/Horton/divergence+insertion ordre-1). Consolide les 5 gardes mono-graine #83/#48/#7. Marqué `slow` → tourne dans la **suite lente complète** (locale / pré-merge), **pas** dans la matrice GitHub (`-m 'not slow'`) — choix d'envergure #87 (balayage de plusieurs minutes, pin). In-band : chêne `shedding.quality_threshold` 0.15→0.08 (Horton 2.95→3.29) ; bouleau bande couronne 4.0→4.8 (mesure *max-extent*, valeur 4.46m réaliste). **Vérif finale #85** : avec #83 (mesure ordre-1) livré, le balayage `diagnose --seed 0,1,2` sur les 6 espèces **+** ce garde-fou sont **tout en bande** — les 8 résidus #84 étaient des **artefacts de mesure #83** (insertion/divergence ordre-1 ✓ partout), zéro vraie dérive restante. | [#87](https://github.com/julien-riel/palubicki/issues/87) + [#85](https://github.com/julien-riel/palubicki/issues/85) livrés |
| Compétition lumineuse (Beer-Lambert), forêts, obstacles | ✅ | `sim/light.py` / `light_perception.py` (ray-marching, grille LAI **scale-aware** dérivée de `voxel_edge_m`, #84) ; `sim/forest.py`, `sim/obstacles.py`. **Contrat de calibration** : les constantes optiques (`k_absorption`/`leaf_area_scale`/`needle_area_scale`) sont réglées pour `voxel_edge_m=0.04` (profondeur optique par feuille ∝ `1/voxel_edge_m²`) ; changer la taille de voxel les invalide → re-régler + re-vérifier (garde-fou #87). Découvrable : commentaire `light:` des 6 presets + champ `config.py` + section dédiée de [`realism-assessment.md`](./realism-assessment.md). | [#85](https://github.com/julien-riel/palubicki/issues/85) livré |

---

## Réalisme fonctionnel (angles morts dans le périmètre)

Au-delà de la morphologie, les écarts **physiologiques** relevés par
[`realism-assessment.md`](./realism-assessment.md) ont chacun un billet :

| Écart | Statut | Billet / décision |
|---|---|---|
| Vigueur abstraite (pas de budget carbone source→puits) | ❌ | [#66](https://github.com/julien-riel/palubicki/issues/66) **fermé `NOT_PLANNED`** — refonderait le moteur ; frontière de conception assumée |
| Surface foliaire réelle injectée dans la grille de lumière | ✅ | **Feuillus** : `sim/light.py` dépose l'aire de lame réelle par feuille (`geom/leaves.py` `leaf_area_records`, source partagée avec `total_leaf_area`) ; `light.leaf_area_scale` = multiplicateur. [#62](https://github.com/julien-riel/palubicki/issues/62) livré. **Conifères** : idem via `leaf_area_records` (multiplicité de fascicule incluse), `light.needle_area_scale` (0.5 = correction du proxy carte-plate) — le scalaire `leaf_area` par bourgeon terminal est retiré ; la dominance apicale est **re-calibrée** sur ce dépôt physique (`lambda_apical` pin 0.65→0.85, sapin 0.88 inchangé ; leader conservé). [#7](https://github.com/julien-riel/palubicki/issues/7) livré (couplage reporté de #62) |
| Pas de re-flush foliaire sur le vieux bois (feuilles émises une fois, jamais renouvelées) | ❌ | surgi de [#61](https://github.com/julien-riel/palubicki/issues/61) (livré) — bloque un vrai cycle décidu/persistant annuel ; le driver saisonnier partagé existe désormais ([#65](https://github.com/julien-riel/palubicki/issues/65) livré), reste à coupler avec le débourrement (voir roadmap) |
| Ombre : réduit l'**initiation** des latéraux (pas seulement l'élagage *a posteriori*) | ✅ | `sim/shade_avoidance.py::lateral_break_probability` — à l'émission, chaque latéral ne débourre ACTIF qu'avec une probabilité `1 − strength·(1 − light_factor)` (lue sur le bourgeon-mère) ; sinon il démarre **RESERVE** (`dormant_reserve_buds`, réactivable par la réitération existante `activate_reserves_on_shed`). `sim.shade_avoidance.strength` ∈ [0,1] = fraction de latéraux retenus à l'ombre pleine ; `strength=0` / `enabled=False` / plein soleil ⇒ aucun tirage RNG (**byte-identique**). Complète `shade_mortality` : celui-ci **retient** l'investissement à l'initiation, celui-là **élague** les survivants. **#86 (livré)** : activé + **calibré par espèce** sur un gradient de tolérance — `maple` 0.55, `fir` 0.45, `oak`/`ash` 0.40, `pine` 0.35 (**intermédiaire** — Niinemets & Valladares ~3.2 —, pas « intolérante » comme le libellé du billet), `birch` **désactivée** (pionnière à canopée clairsemée `total_leaf_area` ~10 : tout `strength`>0 remonte la lumière, freine l'élagueur et pousse le `crown_radius` chaotique au-delà du plafond 4.8 ; plancher zéro du gradient, golden inchangé). Les deux leviers sont **co-réglés, pas empilés** (le `shade_mortality` de l'espèce est détendu quand `strength` monte, sinon la rétention double-compte la suppression d'ombre → sous-estime couronne/tronc/Horton) ; `fir` `reactivation_count` 0→1 (réserves réactivables, vraie banque). Diagnostic `lateral_reserve_fraction` (advisory, non borné). Critère « l'initiation répond à la lumière » : `tests/integration/test_shade_relief_differential.py` (à `strength` fixe + élagueur coupé, `lateral_reserve_fraction` suit le champ lumineux ; la réactivation reste couverte par le test unitaire #63, la boucle lumière→réactivation différée #61). Garde-fou #87 vert (6 espèces × {0,1,2}, deux mécanismes actifs) ; goldens `oak`/`maple`/`fir`/`pine` re-épinglés (`birch`/`ash` inchangés). [#63](https://github.com/julien-riel/palubicki/issues/63) + [#86](https://github.com/julien-riel/palubicki/issues/86) livrés |
| Pas de mémoire mécanique du bois (bois de réaction, fluage) | ❌ | [#64](https://github.com/julien-riel/palubicki/issues/64) |
| Phénologie graduée (rampe saisonnière continue, pas seulement une porte binaire) | ✅ | `sim/clock.py::phenology_activity` — trapèze symétrique `[0,1]` sur `annual_growth_period`, rampes `sim.growth_period_shoulder` (débourrement / cessation) ; `shoulder=0` (défaut livré) = porte binaire legacy **byte-identique** (goldens inchangés). **Source unique partagée** : la croissance multiplie la longueur d'entre-nœud émise par l'activité, la sénescence (#61) entre en dormance au **même** seuil `activity==0`, la floraison (#11, à venir) lira le même driver. Diagnostics `mean_growth_activity` / `shoulder_internode_fraction`. Degrés-jours (GDD) et fenêtres wrap-around différés (pas de plomberie température ; `dt` annuel par défaut ne résout pas le sous-annuel). [#65](https://github.com/julien-riel/palubicki/issues/65) livré |

---

## Billets à créer (suggestions)

Écarts **sans billet** où la création d'un ticket est recommandée (plutôt que
`SKIP`) :

1. **Cônes de gymnospermes** (§9.3) — structure de cône réelle (écailles en
   phyllotaxie spiralée), distincte de la forme d'enveloppe `cone`. Équivalent
   gymnosperme de [#11](https://github.com/julien-riel/palubicki/issues/11), non
   couvert par son intitulé.
2. **Fruits** (§9.4) — suite de [#11](https://github.com/julien-riel/palubicki/issues/11) :
   un fruit est un ovaire mûri, donc dépend des fleurs ; à ouvrir une fois
   [#11](https://github.com/julien-riel/palubicki/issues/11) atterri.
3. **Preset d'arbuste** (§10.3) — le biais basitone existe déjà ; livrer un
   preset (lilas, cornouiller) est peu coûteux et n'exige aucun changement
   moteur.

> **Déjà créé** — [#94](https://github.com/julien-riel/palubicki/issues/94)
> (forme cône émergente : dynamique de longueur de branche + contrôle apical),
> issu du constat de calibration de [#56](https://github.com/julien-riel/palubicki/issues/56) ;
> et [#96](https://github.com/julien-riel/palubicki/issues/96) (port du cône au
> pin + pool de bourgeons borné) ; et [#97](https://github.com/julien-riel/palubicki/issues/97)
> (pendant feuillu : couronne arrondie/décurrente émergente, profil `rounded` +
> mesure `pyramid`) — tous **livrés**.

Les autres absences sont des **`SKIP` assumés** : topologie racinaire
souterraine, anneaux annuels, dimension fractale, loi de flambement,
bulbes/rosettes/succulentes, modèles nommés Hallé–Oldeman, nervation
structurelle — tous hors trajectoire ou émergents, documentés ci-dessus.
