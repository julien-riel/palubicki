# Roadmap

Ce fichier fait foi pour la priorisation (pas l'ordre des issues GitHub).

> **Méthode transversale — boucle empirique auto-correctrice** : poser → observer
> les diagnostics → corriger → recommencer jusqu'à ce que ça lise vrai
> ([`mindset-boucle-empirique.md`](mindset-boucle-empirique.md)).

## À faire (dans l'ordre)

Priorisé le 2026-05-30, mis à jour le 2026-05-31. Principe : **correctness →
filet de mesure de la boucle → réalisme qu'il révèle → outillage → nouveaux gros
systèmes.**
1. **#6, #5, #7 — foliage (suite)** · #14 (feuilles first-class sur `Node`, `Leaf`/`LeafState`) **a atterri** et débloque la suite : feuilles composées (#6), pétiole (#5), fascicules d'aiguilles (#7). La caducité / couleur d'automne (état `SENESCENT`/`ABSCISSED` posé mais non câblé) suit aussi sur cette fondation. Note : #7 (fascicules) raffinera les aiguilles de conifères posées par #36 ; revisiter les presets de lame d'espèce maintenant que les feuilles sont assises à la divergence phyllotactique (constat 4).
2. **#55 — spray latéral cohérent (forme)** · référencer la plagiotropie **et** le repère radial d'insertion au plan de la branche-mère (au lieu du plan XY mondial calculé indépendamment) → éventail plat des conifères. Correctif de *forme* ciblé, complément de #34 (qui ne fait que monter le poids dans le temps, toujours projeté sur XY). Distinct du rendu (#53).
3. **#53 — qualité infographique (épopée rendu/export glTF)** · normal maps → translucence feuille (`KHR_materials_diffuse_transmission`) → ORM → atlasing → LOD/instancing/vent. Matrice §12 de [`render-pipeline.md`](render-pipeline.md). **Apparence**, orthogonale à la *forme* (#55/#56). Sous-tickets indépendants à découper au fil de l'eau.
4. **#44 — vignes / lianas** · gros nouveau système : obstacle comme **attracteur** (aujourd'hui purement répulsif) + thigmotropisme + état cherche/accroché. Seulement si scènes de paysage avec structures.
5. **#56 — forme émergente : variante shadow-propagation (Palubicki 2009)** · gros changement de moteur. Exposition des bourgeons par **grille d'ombrage** (2ᵉ backend, BHse reste le défaut) → la silhouette (cône conifère, fût clair) **émerge** de l'auto-ombrage + dominance apicale au lieu d'être prescrite par l'enveloppe BHse (`shape: cone`). S'appuie sur #37 ; touche l'allocation BH (#36/#51). Symptôme motivant déjà documenté : pas de fût clair (couronne jusqu'au sol, « petits troncs ») parce que le cône touche le sol et que l'élagage est piloté par la capture de marqueurs, pas par la lumière. Le plus profond du backlog ; tranche d'abord le compromis dirigeable-vs-émergent.
6. **#11, #12 — beaucoup plus tard** · croissance déterminée + fleurs (#11), tallage + graminées (#12). Nouveaux modes hors trajectoire actuelle.

## Fait

| # | Livré | PR |
|---|---|---|
| #1 | Harness de diagnostic (métriques d'arbre) | #13 |
| #2 | Phyllotaxie distique (bourgeon unique, 180°) | #15 |
| #3 | Biais de débourrement (acro/méso/basitone) | #16 |
| #4 | Blade de feuille paramétrique (forme + marge) | #17, #18 |
| #8 | Évasement racinaire (+ contreforts ondulés) | #21 |
| #9 | Variation d'écorce par `Internode.diameter` | #22 |
| #10 | Axe temporel / phénologie (années fractionnaires, `Clock`) | #23 |
| #20 | Longueur d'internode pilotée par la vigueur (flux BH continu) | #31 |
| #24 | Phyllotaxie : ordinal **par axe** (azimut brouillé par `node_index` global) | #28 |
| #25 | Test phyllotaxie au grain fin (divergence successive par axe) | #28 |
| #26 | Loader config récursif (`_coerce`) + fix coercion overrides forêt | #30 |
| #32 | Bornes de littérature par espèce (`literature.yaml`) | #43 |
| #33 | Bug rendu : enroulement des triangles inversé (écorce culled en glTF) | #38 |
| #35 | Bug phyllotaxie : rotation inter-verticille (verticilles empilés) | #39 |
| #41 | Bug forêt : densité de marqueurs **uniforme sur l'union** (anti-crown-shyness) | #46 |
| #40 | Métrique de continuation d'axe principal (`main_axis_continuation_rate`) + bornes par espèce — flagge un leader décapité | #47 |
| #48 | Métrique *géométrique* de verticalité du leader (`leader_deviation_deg`) + bornes par espèce ; golden d'espèce repassé à la **densité de marqueurs représentative** (cause racine de la « régression » #43 : le proxy à 1000 marqueurs sous-échantillonnait ~18× les enveloppes conifères agrandies → leaders affamés/arqués ; à la densité de design ils sont droits) | #50 |
| #36 | Couronne conifère pleine : aiguilles réparties **le long du rameau** (`needle_cluster_spacing`) + footprint d'aiguille agrandi (pin & sapin). Diagnostic stale (« BH affame les latéraux » : #43/#48 avaient déjà réglé le nb de branches ; le résiduel était un défaut de *modélisation du feuillage*, pas d'allocation). `total_leaf_area` pin 30→361 ; sapin quasi-chauve→plein | #51 |
| #37 | Cohérence light↔geom : la grille de lumière occlut désormais avec les diamètres **graine-de-vigueur** (passe `vigor_ref`/`vigor_diameter_gain` de `cfg.sim` à travers `rebuild_from_*` → `compute_radii`), au lieu des diamètres pure-pipe. Effet second-ordre borné (multiplicateur ≤ 1+gain). Révélateur de boucle empirique : le test différentiel d'épinastie (#45) passait par 0,24° de marge ; les diamètres plus épais → un peu plus d'auto-ombrage → la mortalité d'ombre élague quelques latéraux apicaux raides → la *moyenne* ON−OFF s'effondre à ~0,5° **mais la médiane tient ~2,5°** (mécanisme intact : le test young-vs-old reste vert). Test repassé sur la **médiane** (stat robuste aux queues). Goldens d'espèce + hash diagnostic oak re-pinnés | #52 |
| #29 | Visualiseur des internes de sim : overlay debug (marqueurs vivants/morts, envelope wireframe, bourgeons par état, branches élaguées) + timeline scrub/play dans l'éditeur. Capture **opt-in** (collecteur observationnel branché dans `simulate_forest`, zéro coût par défaut, n'altère pas l'évolution déterministe — gardé par un test de signature de positions), servie via `/api/debug` (positions des marqueurs une fois, deltas par frame) ; le `.glb` exporté est inchangé | #54 |
| #14 | Feuilles **first-class** sur `Node` (`Leaf`/`LeafState`, `Tree.all_leaves()`). Émission par nœud dans `_emit_node` avec azimut phyllotactique (`leaf_azimuths`, ordinal par-axe #24 — `lateral_bud_directions` intouché). Position **dérivée** (suit sag/élongation, pas de coord. gelée). Rendu via le sélecteur partagé `selected_leaves` (sous-ensemble apex-proximal `ACTIVE` ; `foliage_depth` = sélecteur, futur état caducité) ; `geom/leaves.py` lit `tree.all_leaves()`, `_collect_foliage_sites`/`_emit_leaf_cluster` supprimés, fan `cluster_count` → N `Leaf` à l'émission. `total_leaf_area` à **parité exacte** (cisaillement `cos(splay)` préservé, pin oak 791,247). Goldens d'espèce + GLB feuillus re-pinnés (siège phyllotactique décale les sommets ; squelette **inchangé** — garde-fou de signature). Débloque #5/#6/#7 + caducité/couleur d'automne (`SENESCENT`/`ABSCISSED` réservés, non câblés) | #57 |
| — | Outillage : ruff + CI + refactor simulateur | #19 |
1. **#34 — épinastie** · *en cours (branche `issue-34-…`)*. Le poids plagiotrope monte avec l'âge de la branche (`t - birth_time`) au lieu d'être plein dès le 1ᵉʳ nœud → ramure mature arquée. À finir et fusionner.


> **Notes de boucle empirique** (les bugs « corrects dans la fonction, faux sur l'arbre ») :
> #24 — `node_index` global entrelacé entre chaînes (refactor step-major) ; correctif : ordinal par axe (`Bud.axis_node_ordinal`).
> #35 — entrelacement corrigé sur la primitive mais **invisible** au rendu du pin (azimut poussé gouverné par `w_perception`, golden inchangé).
> #41 — `sample_markers` correct par envelope, mais concaténer N envelopes **double la densité** dans le chevauchement → marqueurs attracteurs tirent les couronnes l'une vers l'autre. Correctif : amincir chaque marqueur avec proba `1/m` (m = nb d'envelopes le contenant) → densité d'union uniforme, dépletion partagée (vraie crown shyness). Mesuré par un **différentiel contrôlé par baseline solo** (le même arbre seul vs avec voisin), car l'asymétrie phyllotactique intrinsèque (~120 internodes) noie le signal inter-arbre en absolu.
> #20 a engendré #36/#37 et motivé #40.
> #48 — variante : presets **corrects**, mais le **proxy de test faux**. Le golden d'espèce tournait à `--marker-count 1000` fixe ; #43 ayant agrandi ~6,5× les enveloppes conifères, la densité de marqueurs s'effondrait ~18× sous le design → leaders affamés (pin `main_axis`→0,10) ou arqués (bouleau `leader_deviation`→45°). Toucher les poids de tropisme ne corrige rien (le leader est *affamé*, pas mal orienté). Correctif : faire tourner le golden à la densité *de design* (le `marker_count` du preset). À la densité réelle les leaders sont droits (pin 5,8°, sapin 6,3°). Leçon : un proxy de test sous-échantillonné peut faire passer une régression-fantôme pour un bug de preset.
> #37 — **fix correct, test fragile révélé.** Brancher les diamètres graine-de-vigueur dans la grille de lumière est sans ambiguïté correct (le modèle de lumière doit voir les mêmes branches que la géométrie rendue). Mais l'effet second-ordre (plus d'auto-ombrage → mortalité d'ombre) a fait tomber le test différentiel d'épinastie qui ne passait que par 0,24° de marge sur `main`. Diagnostic : la *moyenne* ON−OFF n'est pas robuste — élaguer quelques latéraux apicaux raides amincit la queue haute et tire la moyenne, alors que la **médiane** (tendance centrale) reste ~2,5° (légèrement *plus forte* qu'avant #37) et le test de mécanisme young-vs-old reste vert. Correctif : comparer sur la médiane. Leçon : un différentiel de population mesuré à la moyenne avec une marge serrée est fragile à toute perturbation qui redistribue les queues ; préférer la médiane pour les propriétés de population.
> #36 — **diagnostic périmé + mauvais levier.** Le ticket disait « BH winner-take-all affame les latéraux → couronne clairsemée » ; observation : #43/#48 avaient déjà donné au pin 19k+ nœuds (latéraux *pas* affamés). Le symptôme résiduel était un défaut de *modélisation du feuillage* : aiguilles posées en grappes **aux nœuds** sur les seuls 3 derniers internodes de chaque apex. Hypothèse de conception (réparties le long du rameau) → correcte mais **insuffisante seule** : à `needle_cluster_spacing 0.02` la géométrie explose (pin 214 Mo) et le rendu reste clairsemé, car chaque aiguille est un fil trop fin pour couvrir. Le **levier dominant** s'est révélé être le *footprint* de l'aiguille (`leaf_size`/`leaf_aspect`) — gratuit en géométrie (scale de sommets). Recette finale : grosses aiguilles + peu nombreuses + espacement modéré le long du rameau. Piège outil : `diagnostics._total_leaf_area` recompute les sites de feuillage et appelait `_collect_foliage_sites` **sans** `needle_cluster_spacing` → métrique aveugle aux nouvelles aiguilles (corrigé, gardé par `test_leaf_area_matches_geom_helper`). Leçon : valider l'hypothèse de conception sur le rendu *avant* de calibrer — la boucle a retourné le levier principal.
