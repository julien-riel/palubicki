# Roadmap

Ce fichier fait foi pour la priorisation (pas l'ordre des issues GitHub).

> **Méthode transversale — boucle empirique auto-correctrice** : poser → observer
> les diagnostics → corriger → recommencer jusqu'à ce que ça lise vrai
> ([`mindset-boucle-empirique.md`](mindset-boucle-empirique.md)).

## À faire (dans l'ordre)

Priorisé le 2026-05-30. Principe : **correctness → filet de mesure de la boucle →
réalisme qu'il révèle → outillage → nouveaux gros systèmes.**

1. **#34 — épinastie** · *en cours (branche `issue-34-…`)*. Le poids plagiotrope monte avec l'âge de la branche (`t - birth_time`) au lieu d'être plein dès le 1ᵉʳ nœud → ramure mature arquée. À finir et fusionner.
2. **#41 — bug forêt : anti-crown-shyness** · `bug`, **bloque un test** (xfail). Les marqueurs sont additifs là où les envelopes se chevauchent (~3:1 côté voisin) → les couronnes poussent *l'une vers l'autre*. Fix : densité spatiale **uniforme** sur la région d'union. (cf. mémoire `project_forest_marker_density.md`)
3. **#40 — métrique de continuation d'axe principal** · arme le filet ✓/✗ : `main_axis_continuation_rate` + borne par espèce dans `literature.yaml`, pour qu'un conifère décapité soit flaggé. Extension de #32 ; **fournit la mesure pour valider #36**.
4. **#36 — couronne de pin clairsemée** · réalisme. BH winner-take-all → ~90 % des latéraux du pin reçoivent zéro flux. À regarder : split acropète en cône étroit, `shedding`/`k_absorption`, plancher de flux éventuel. Mesuré par #40.
5. **#37 — light grid en diamètres pure-pipe** · cohérence light↔geom, second-ordre, petit. Passer `vigor_diameter_gain` à travers `rebuild_from_*`. Bon « warm-up ».
6. **#29 — visualiseur des internes de sim** · observabilité de la boucle (marqueurs/envelope/bourgeons/light, timeline). Capture opt-in. Aurait aidé #24 ; accélère #36/#41.
7. **#14 → #6, #5, #7 — foliage** · #14 (feuilles en attribut de `Node`, `LeafState` avec `leaf_age`) débloque la suite : composées (#6), pétiole (#5), fascicules d'aiguilles (#7).
8. **#44 — vignes / lianas** · gros nouveau système : obstacle comme **attracteur** (aujourd'hui purement répulsif) + thigmotropisme + état cherche/accroché. Seulement si scènes de paysage avec structures.
9. **#11, #12 — beaucoup plus tard** · croissance déterminée + fleurs (#11), tallage + graminées (#12). Nouveaux modes hors trajectoire actuelle.

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
| — | Outillage : ruff + CI + refactor simulateur | #19 |

> **Notes de boucle empirique** (les bugs « corrects dans la fonction, faux sur l'arbre ») :
> #24 — `node_index` global entrelacé entre chaînes (refactor step-major) ; correctif : ordinal par axe (`Bud.axis_node_ordinal`).
> #35 — entrelacement corrigé sur la primitive mais **invisible** au rendu du pin (azimut poussé gouverné par `w_perception`, golden inchangé).
> #20 a engendré #36/#37 et motivé #40.
