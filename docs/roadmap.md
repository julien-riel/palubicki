# Roadmap

Ce fichier fait foi pour la priorisation (pas l'ordre des issues GitHub).

> **Méthode transversale — boucle empirique auto-correctrice** : poser → observer
> les diagnostics → corriger → recommencer jusqu'à ce que ça lise vrai
> ([`mindset-boucle-empirique.md`](mindset-boucle-empirique.md)).

## À faire (dans l'ordre)

Priorisé le 2026-05-30. Principe : **correctness → filet de mesure de la boucle →
réalisme qu'il révèle → outillage → nouveaux gros systèmes.**
1. **#48 — régression de forme du leader conifère** · **correctness**. La recalibration des presets (#43) a fait *pencher* le leader du sapin et *arquer* celui du pin vers l'horizontale → plus excurrent. Bloquant : 3 goldens d'espèce (`fir`/`pine`/`birch`) tenus **rouges** exprès (PR #49) pour ne pas figer la régression. À regarder : poids ortho/plagiotropie + `axis_decay` dans `fir.yaml`/`pine.yaml`. **À coupler** : une métrique *géométrique* de verticalité du leader (le `main_axis_continuation_rate` de #40 est *topologique* → un leader penché reste l'axe principal, donc invisible à #40). Même sous-système que #36 → faire d'abord pour repartir d'un leader droit.
2. **#36 — couronne de pin clairsemée** · réalisme. BH winner-take-all → ~90 % des latéraux du pin reçoivent zéro flux. À regarder : split acropète en cône étroit, `shedding`/`k_absorption`, plancher de flux éventuel. **Le filet ✓/✗ est maintenant armé** (`main_axis_continuation_rate`, #40) pour valider que le leader survit au passage.
3. **#37 — light grid en diamètres pure-pipe** · cohérence light↔geom, second-ordre, petit. Passer `vigor_diameter_gain` à travers `rebuild_from_*`. Bon « warm-up ».
4. **#29 — visualiseur des internes de sim** · observabilité de la boucle (marqueurs/envelope/bourgeons/light, timeline). Capture opt-in. Aurait aidé #24 ; accélère #36/#41.
5. **#14 → #6, #5, #7 — foliage** · #14 (feuilles en attribut de `Node`, `LeafState` avec `leaf_age`) débloque la suite : composées (#6), pétiole (#5), fascicules d'aiguilles (#7).
6. **#44 — vignes / lianas** · gros nouveau système : obstacle comme **attracteur** (aujourd'hui purement répulsif) + thigmotropisme + état cherche/accroché. Seulement si scènes de paysage avec structures.
7. **#11, #12 — beaucoup plus tard** · croissance déterminée + fleurs (#11), tallage + graminées (#12). Nouveaux modes hors trajectoire actuelle.

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
| — | Outillage : ruff + CI + refactor simulateur | #19 |
1. **#34 — épinastie** · *en cours (branche `issue-34-…`)*. Le poids plagiotrope monte avec l'âge de la branche (`t - birth_time`) au lieu d'être plein dès le 1ᵉʳ nœud → ramure mature arquée. À finir et fusionner.


> **Notes de boucle empirique** (les bugs « corrects dans la fonction, faux sur l'arbre ») :
> #24 — `node_index` global entrelacé entre chaînes (refactor step-major) ; correctif : ordinal par axe (`Bud.axis_node_ordinal`).
> #35 — entrelacement corrigé sur la primitive mais **invisible** au rendu du pin (azimut poussé gouverné par `w_perception`, golden inchangé).
> #41 — `sample_markers` correct par envelope, mais concaténer N envelopes **double la densité** dans le chevauchement → marqueurs attracteurs tirent les couronnes l'une vers l'autre. Correctif : amincir chaque marqueur avec proba `1/m` (m = nb d'envelopes le contenant) → densité d'union uniforme, dépletion partagée (vraie crown shyness). Mesuré par un **différentiel contrôlé par baseline solo** (le même arbre seul vs avec voisin), car l'asymétrie phyllotactique intrinsèque (~120 internodes) noie le signal inter-arbre en absolu.
> #20 a engendré #36/#37 et motivé #40.
