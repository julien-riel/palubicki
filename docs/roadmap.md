# Roadmap

Ce fichier fait foi pour la priorisation (pas l'ordre des issues GitHub). Il
décrit **ce qui reste à faire** ; l'historique du livré est dans git (commits,
PR) et dans la [matrice de support botanique](botany/code-support-matrix.md).

> **Méthode transversale — boucle empirique auto-correctrice** : poser → observer
> les diagnostics → corriger → recommencer jusqu'à ce que ça lise vrai
> ([`mindset-boucle-empirique.md`](mindset-boucle-empirique.md)).

## En cours

- **#34 — épinastie** (branche `issue-34-…`) · le poids plagiotrope monte avec
  l'âge de la branche (`t - birth_time`) au lieu d'être plein dès le 1ᵉʳ nœud →
  ramure mature arquée.

## À faire (dans l'ordre)

Principe : **correctness → filet de mesure de la boucle → réalisme qu'il révèle
→ outillage → nouveaux gros systèmes.**

1. **#7 — foliage (suite) : fascicules d'aiguilles** · raffine les aiguilles de
   conifères (réparties le long du rameau) en fascicules de 2–5. La caducité /
   couleur d'automne (états `SENESCENT`/`ABSCISSED` posés mais non câblés) suit
   sur la même fondation (feuilles first-class sur `Node`). Revisiter les presets
   de lame d'espèce maintenant que les feuilles sont assises à la divergence
   phyllotactique.
2. **#55 — spray latéral cohérent (forme)** · référencer la plagiotropie **et**
   le repère radial d'insertion au plan de la branche-mère (au lieu du plan XY
   mondial calculé indépendamment) → éventail plat des conifères. Correctif de
   *forme* ciblé, distinct du rendu (#53).
3. **#53 — qualité infographique (épopée rendu/export glTF)** · normal maps →
   translucence feuille (`KHR_materials_diffuse_transmission`) → ORM → atlasing →
   LOD/instancing/vent. Matrice §12 de [`render-pipeline.md`](render-pipeline.md).
   **Apparence**, orthogonale à la *forme* (#55/#56). Sous-tickets indépendants à
   découper au fil de l'eau.
4. **#44 — vignes / lianas** · gros nouveau système : obstacle comme
   **attracteur** (aujourd'hui purement répulsif) + thigmotropisme + état
   cherche/accroché. Seulement si scènes de paysage avec structures.
5. **#56 — forme émergente : variante shadow-propagation (Palubicki 2009)** · gros
   changement de moteur. Exposition des bourgeons par **grille d'ombrage** (2ᵉ
   backend, BHse reste le défaut) → la silhouette (cône conifère, fût clair)
   **émerge** de l'auto-ombrage + dominance apicale au lieu d'être prescrite par
   l'enveloppe BHse (`shape: cone`). S'appuie sur #37 ; touche l'allocation BH.
   Le plus profond du backlog ; tranche d'abord le compromis
   dirigeable-vs-émergent.
6. **#11, #12 — beaucoup plus tard** · croissance déterminée + fleurs (#11),
   tallage + graminées (#12). Nouveaux modes hors trajectoire actuelle.
