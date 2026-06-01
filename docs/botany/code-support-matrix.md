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
| Anatomie : lame, pétiole, angle d'insertion, rotation | ✅ | `geom/leaf_blade.py` (lame 2D) + **lame héro 3D** courbée/pliée `geom/leaf_blade3d.py` (pli médian + recourbure, normales/tangentes lissées) sur les feuillus ; pétiole effilé `geom/compound_leaf.py` ([#5](https://github.com/julien-riel/palubicki/issues/5)) ; `leaf_splay_deg` ; `Leaf.azimuth` | [#5](https://github.com/julien-riel/palubicki/issues/5) + [#73](https://github.com/julien-riel/palubicki/issues/73) (lame héro) livrés |
| Nervation géométrique (parallèle/pennée/palmée/dichotome) | 🟡 | relief de nervure via **normal map** + masque de translucence (lame claire / médiane+nervures sombres) — pennée (chevron) / palmée (éventail) procédurales : `geom/maps.py` + `_textures.leaf_vein_mask` ; pas de géométrie par-veine | [#73](https://github.com/julien-riel/palubicki/issues/73) livré (relief carte) ; géométrie par-veine hors scope (`SKIP` structurel) |
| Simple vs composée (pennée/palmée/bipennée) | ✅ | `leaf_kind` + `geom/compound_leaf.py` (`_pinnate`/`_palmate`/`_bipinnate`, rachis) | [#6](https://github.com/julien-riel/palubicki/issues/6) livré |
| Lame paramétrique : forme + marge | ✅ | `leaf_shape` (6 formes) + `leaf_margin` (entire/serrate/dentate/lobed) ; `geom/leaf_blade.py` | [#4](https://github.com/julien-riel/palubicki/issues/4) livré |
| Durée de vie : caducité / persistance / marcescence | ✅ | `sim/caducity.py::advance_leaf_states` (âge/saison → `LeafState`, déterministe) ; `leaf_phenology` (decidu/persistant, lifespan, marcescence) ; couleur d'automne via `leaf_autumn_color` (COLOR_0) ; renderer rend `ACTIVE`+`SENESCENT`, filtre `ABSCISSED` | [#61](https://github.com/julien-riel/palubicki/issues/61) livré — caducité saisonnière à dt sous-annuel ; re-flush sur vieux bois + turnover aiguilles reportés (voir roadmap) |
| Hétérophyllie soleil/ombre | ✅ | `geom/leaves.py::compute_effective_leaf_size`, `leaf_sun_shade_k` | — |
| Aiguilles de conifère, fascicules (2–5) | 🟡 | aiguilles linéaires + `needle_cluster_spacing` (réparties le long du rameau) ; **pas** de regroupement en fascicule | [#7](https://github.com/julien-riel/palubicki/issues/7) |

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
| Angles de divergence (spiral/décussé/distique/verticillé) | ✅ | `sim/phyllotaxy.py` (voir §5) | — |
| Angle d'insertion des branches (30–60°, par ordre) | ✅ | `branch_angle_by_order` ; mesuré dans `sim/diagnostics.py` | — |
| Compétition lumineuse (Beer-Lambert), forêts, obstacles | ✅ | `sim/light.py` / `light_perception.py` (ray-marching, grille LAI) ; `sim/forest.py`, `sim/obstacles.py` | — |

---

## Réalisme fonctionnel (angles morts dans le périmètre)

Au-delà de la morphologie, les écarts **physiologiques** relevés par
[`realism-assessment.md`](./realism-assessment.md) ont chacun un billet :

| Écart | Statut | Billet / décision |
|---|---|---|
| Vigueur abstraite (pas de budget carbone source→puits) | ❌ | [#66](https://github.com/julien-riel/palubicki/issues/66) **fermé `NOT_PLANNED`** — refonderait le moteur ; frontière de conception assumée |
| Surface foliaire réelle injectée dans la grille de lumière | 🟡 | **Feuillus** : `sim/light.py` dépose l'aire de lame réelle par feuille (`geom/leaves.py` `leaf_area_records`, source partagée avec `total_leaf_area`) ; `light.leaf_area_scale` = multiplicateur. [#62](https://github.com/julien-riel/palubicki/issues/62) livré. **Conifères** : restent sur le scalaire `light.leaf_area` par bourgeon terminal (dominance apicale émerge de ce dépôt) ; couplage des vraies aiguilles reporté à [#7](https://github.com/julien-riel/palubicki/issues/7) (fascicules) — #55 n'a livré que la **forme** de l'éventail (plan de la branche-mère), pas le couplage lumière |
| Pas de re-flush foliaire sur le vieux bois (feuilles émises une fois, jamais renouvelées) | ❌ | surgi de [#61](https://github.com/julien-riel/palubicki/issues/61) (livré) — bloque un vrai cycle décidu/persistant annuel ; à coupler #65 + débourrement (voir roadmap) |
| Ombre : élague *a posteriori*, ne réduit pas l'initiation | ❌ | [#63](https://github.com/julien-riel/palubicki/issues/63) |
| Pas de mémoire mécanique du bois (bois de réaction, fluage) | ❌ | [#64](https://github.com/julien-riel/palubicki/issues/64) |
| Phénologie binaire (pas de degrés-jours / rampe saisonnière) | 🟡 | [#65](https://github.com/julien-riel/palubicki/issues/65) |

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

Les autres absences sont des **`SKIP` assumés** : topologie racinaire
souterraine, anneaux annuels, dimension fractale, loi de flambement,
bulbes/rosettes/succulentes, modèles nommés Hallé–Oldeman, nervation
structurelle — tous hors trajectoire ou émergents, documentés ci-dessus.
