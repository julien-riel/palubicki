L'ordre des issues sur github.

## Fait

- #1 — harness de diagnostic (métriques d'arbre générées)
- #2 — phyllotaxie distique explicite (bourgeon unique, alternance 180°)
- #3 — biais de débourrement (acrotone / mésotone / basitone)
- #4 — blade de feuille paramétrique (forme + marge), avec suivi #18
- Outillage (hors issue) — config ruff + CI GitHub Actions + refactor du simulateur (PR #19)

## Reste à faire (dans l'ordre)

1. #8, #9 — les gains visibles sans dépendance, dans l'ordre que tu préfères.
2. #10 — fondation temporelle (Clock + `birth_time`). À ce stade tu as ressenti où le système actuel coince et tu sais ce que `LeafState` doit contenir.
3. #20 — longueur d'internode pilotée par la vigueur (flux Borchert-Honda continu ; retire `age_factor` + le cap `n_substeps_max`). Rend les quantités de croissance émergentes plutôt qu'imposées. S'appuie sur #10 pour démêler le proxy itération-comme-temps.
4. #14 — promouvoir les feuilles en attribut de `Node` (`Leaf` + `LeafState`). Refactor architectural, débloque tout ce qui suit côté foliage.
5. #6 puis #5, #7 — la suite foliage, construite sur #10 + #14 (donc `LeafState` conçu une seule fois).
6. #11, #12 — beaucoup plus tard.
