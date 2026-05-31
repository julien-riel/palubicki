# Roadmap

Ce fichier fait foi pour la priorisation (pas l'ordre des issues GitHub).

> **Méthode transversale — boucle empirique auto-correctrice** : poser → observer
> les diagnostics → corriger → recommencer jusqu'à ce que ça lise vrai
> ([`mindset-boucle-empirique.md`](mindset-boucle-empirique.md)).

## À faire (dans l'ordre)

Priorisé le 2026-05-30. Principe : **correctness → filet de mesure de la boucle →
réalisme qu'il révèle → outillage → nouveaux gros systèmes.**
1. **#37 — light grid en diamètres pure-pipe** · cohérence light↔geom, second-ordre, petit. Passer `vigor_diameter_gain` à travers `rebuild_from_*`. Bon « warm-up ».
2. **#29 — visualiseur des internes de sim** · observabilité de la boucle (marqueurs/envelope/bourgeons/light, timeline). Capture opt-in. Aurait aidé #24 ; accélère #41.
3. **#14 → #6, #5, #7 — foliage** · #14 (feuilles en attribut de `Node`, `LeafState` avec `leaf_age`) débloque la suite : composées (#6), pétiole (#5), fascicules d'aiguilles (#7). Note : #7 (fascicules) raffinera les aiguilles de conifères posées par #36.
4. **#44 — vignes / lianas** · gros nouveau système : obstacle comme **attracteur** (aujourd'hui purement répulsif) + thigmotropisme + état cherche/accroché. Seulement si scènes de paysage avec structures.
5. **#11, #12 — beaucoup plus tard** · croissance déterminée + fleurs (#11), tallage + graminées (#12). Nouveaux modes hors trajectoire actuelle.

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
| — | Outillage : ruff + CI + refactor simulateur | #19 |
1. **#34 — épinastie** · *en cours (branche `issue-34-…`)*. Le poids plagiotrope monte avec l'âge de la branche (`t - birth_time`) au lieu d'être plein dès le 1ᵉʳ nœud → ramure mature arquée. À finir et fusionner.


> **Notes de boucle empirique** (les bugs « corrects dans la fonction, faux sur l'arbre ») :
> #24 — `node_index` global entrelacé entre chaînes (refactor step-major) ; correctif : ordinal par axe (`Bud.axis_node_ordinal`).
> #35 — entrelacement corrigé sur la primitive mais **invisible** au rendu du pin (azimut poussé gouverné par `w_perception`, golden inchangé).
> #41 — `sample_markers` correct par envelope, mais concaténer N envelopes **double la densité** dans le chevauchement → marqueurs attracteurs tirent les couronnes l'une vers l'autre. Correctif : amincir chaque marqueur avec proba `1/m` (m = nb d'envelopes le contenant) → densité d'union uniforme, dépletion partagée (vraie crown shyness). Mesuré par un **différentiel contrôlé par baseline solo** (le même arbre seul vs avec voisin), car l'asymétrie phyllotactique intrinsèque (~120 internodes) noie le signal inter-arbre en absolu.
> #20 a engendré #36/#37 et motivé #40.
> #48 — variante : presets **corrects**, mais le **proxy de test faux**. Le golden d'espèce tournait à `--marker-count 1000` fixe ; #43 ayant agrandi ~6,5× les enveloppes conifères, la densité de marqueurs s'effondrait ~18× sous le design → leaders affamés (pin `main_axis`→0,10) ou arqués (bouleau `leader_deviation`→45°). Toucher les poids de tropisme ne corrige rien (le leader est *affamé*, pas mal orienté). Correctif : faire tourner le golden à la densité *de design* (le `marker_count` du preset). À la densité réelle les leaders sont droits (pin 5,8°, sapin 6,3°). Leçon : un proxy de test sous-échantillonné peut faire passer une régression-fantôme pour un bug de preset.
> #36 — **diagnostic périmé + mauvais levier.** Le ticket disait « BH winner-take-all affame les latéraux → couronne clairsemée » ; observation : #43/#48 avaient déjà donné au pin 19k+ nœuds (latéraux *pas* affamés). Le symptôme résiduel était un défaut de *modélisation du feuillage* : aiguilles posées en grappes **aux nœuds** sur les seuls 3 derniers internodes de chaque apex. Hypothèse de conception (réparties le long du rameau) → correcte mais **insuffisante seule** : à `needle_cluster_spacing 0.02` la géométrie explose (pin 214 Mo) et le rendu reste clairsemé, car chaque aiguille est un fil trop fin pour couvrir. Le **levier dominant** s'est révélé être le *footprint* de l'aiguille (`leaf_size`/`leaf_aspect`) — gratuit en géométrie (scale de sommets). Recette finale : grosses aiguilles + peu nombreuses + espacement modéré le long du rameau. Piège outil : `diagnostics._total_leaf_area` recompute les sites de feuillage et appelait `_collect_foliage_sites` **sans** `needle_cluster_spacing` → métrique aveugle aux nouvelles aiguilles (corrigé, gardé par `test_leaf_area_matches_geom_helper`). Leçon : valider l'hypothèse de conception sur le rendu *avant* de calibrer — la boucle a retourné le levier principal.
