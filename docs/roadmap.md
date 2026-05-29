L'ordre des issues sur github.

## Fait

- #1 — harness de diagnostic (métriques d'arbre générées)
- #2 — phyllotaxie distique explicite (bourgeon unique, alternance 180°)
- #3 — biais de débourrement (acrotone / mésotone / basitone)
- #4 — blade de feuille paramétrique (forme + marge), avec suivi #18
- #8 — évasement racinaire à la base du tronc (expansion radiale + contreforts ondulés optionnels, variation par arbre) ; polish au rendu, couche sim intacte (PR #21)
- #9 — variation d'écorce mélangée par `Internode.diameter` (teinte jeune → mature → sénescente, COLOR_0 par sommet ; pilotée par le diamètre, couche sim intacte) (PR #22)
- #10 — fondation temporelle / axe phénologique : horloge en années fractionnaires (`sim/clock.py`), `max_iterations` → `dt_years` + `max_simulation_years`, `birth_iteration` → `birth_time`, `tau_iterations` → `tau_years`, fenêtre de croissance annuelle `annual_growth_period`, suppression de `Bud.age`. Contrat d'invariance : à `dt_years=1.0` les arbres sont bit-identiques (goldens inchangés) (PR #23)
- Outillage (hors issue) — config ruff + CI GitHub Actions + refactor du simulateur (PR #19)

## Reste à faire (dans l'ordre)

Revue transversale du 2026-05-29 (`2026-05-29-codebase-review.md`) — trois nouvelles priorités passent en tête du backlog existant.

1. #24 — **bug phyllotaxie** : l'azimut de divergence est piloté par un compteur `node_index` **global** (partagé par tout l'arbre, entrelacé entre chaînes depuis le refactor step-major), donc spirale / décussé / distique sont corrects *dans la fonction* mais brouillés *par axe sur l'arbre*. Correctif : un ordinal par axe. Meilleur ratio réalisme/effort ; précondition pour que pin / érable / sapin « lisent » vrai.
2. #25 — test au grain fin : assertion de l'angle de divergence *successif par axe* + parité décussé/distique. Détecte #24 et garde contre la régression — la mesure existe déjà dans `sim/diagnostics.py`, il manque l'assertion dure. Va avec #24.
3. #26 — loader config récursif : effondre les 6 blocs de coercion manuels de `load_config` + le doublon `forest.py` (qui omet `bud_break_bias` et `annual_growth_period` → bug latent forêt vs mono-arbre). Dé-risque tout changement de config ultérieur, donc à faire **avant** #20 et #14.
4. #20 — longueur d'internode pilotée par la vigueur (flux Borchert-Honda continu ; retire `age_factor` + le cap `n_substeps_max`). Rend les quantités de croissance émergentes plutôt qu'imposées. S'appuie sur #10 (fait) pour démêler le proxy itération-comme-temps.
5. #14 — promouvoir les feuilles en attribut de `Node` (`Leaf` + `LeafState`). Refactor architectural, débloque tout ce qui suit côté foliage. La fondation temporelle (#10) étant en place, `LeafState` peut intégrer `leaf_age` en années dès sa conception.
6. #6 puis #5, #7 — la suite foliage, construite sur #10 (fait) + #14 (donc `LeafState` conçu une seule fois).
7. #11, #12 — beaucoup plus tard. La phénologie (#10) étant posée, #11 (croissance déterminée + fleurs, événement saisonnier) n'est plus bloqué côté infrastructure temporelle.
