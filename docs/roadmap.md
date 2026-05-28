L'ordre des issues sur github

1. Finir #1 (harness — déjà en cours sur ta branche)
2. #2, #3, #8, #9 — les gains visibles sans dépendance, dans l'ordre que tu préfères
3. #10 — fondation temporelle (Clock + `birth_time`). À ce stade tu as ressenti où le système actuel coince et tu sais ce que `LeafState` doit contenir.
4. #14 — promouvoir les feuilles en attribut de `Node` (`Leaf` + `LeafState`). Refactor architectural, débloque tout ce qui suit côté foliage.
5. #4, #6 puis #5, #7 — la suite foliage, construite sur #10 + #14 (donc `LeafState` conçu une seule fois).
6. #11, #12 — beaucoup plus tard.