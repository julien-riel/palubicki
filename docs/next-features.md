viz/ (debug) — visualisations de l'état interne pour debugger/expliquer : nuage de markers,
  allocation BH par nœud (flèches épaisses), tranches du champ de lumière, cônes de perception.
  Sortie : PNG ou overlays sur le mesh. Dépend de render/. Utile mais pas vital — tu peux faire
  sans pour V3.

  Spéculatif / plus tard

  io/ — sérialiser/désérialiser un Tree (squelette seul, sans mesh) en JSON/msgpack. Permet de
  re-mesher / re-texturer sans refaire la sim. Économise du temps quand tu itères sur geom/ ou
  material/. À considérer quand les sims commenceront à coûter (forêt dense V3).

  physics/ — vent, déflexion de branches, animation glTF skinned. Très utile pour le rendu final
  mais c'est un projet en soi (squelette glTF, modes de cibles, weights). À garder pour après V4.

  sim/lsystem/ — si tu veux vraiment multi-plantes (herbacées, fougères) comme évoqué. Pas avant
  que le modèle actuel soit fini sur son périmètre.