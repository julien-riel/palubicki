# Mindset : la boucle empirique auto-correctrice

Certaines tâches de ce projet ne se livrent pas en posant les bonnes valeurs du
premier coup. Elles se livrent en **bouclant** : on pose un point de départ, on
**observe** ce que l'arbre fait réellement, on **corrige**, et on recommence
jusqu'à ce que ça « lise » vrai. Ce document décrit cette façon de travailler,
parce qu'elle vaut pour bien plus que la recalibration des espèces.

## Le principe

> Les étapes décrivent la **boucle**, pas des valeurs figées.

Quand un comportement émerge d'un système couplé (vigueur → longueur →
diamètre → hauteur → Strahler/Horton), aucune table de constantes ne te donnera
le résultat d'avance. Le bon réflexe n'est pas de *deviner mieux* — c'est de
**fermer la boucle de rétroaction** entre toi et la simulation :

1. **Pose un point de départ plausible**, pas parfait. Une valeur dérivée de
   l'ancien réglage, un ordre de grandeur connu, une borne mesurée. Le but est
   d'avoir quelque chose à observer, pas d'avoir raison.
2. **Fais tourner et observe les diagnostics.** `palubicki diagnose` est l'œil :
   hauteur, longueur d'internode proximale vs distale, diamètre de base,
   Strahler/Horton. Tu lis le réel, pas ton intention.
3. **Compare au sain, pas au paper.** Est-ce que les proportions tiennent ?
   (proximal > distal ; hauteurs crédibles ; internodes dans la plage mesurée du
   repo ~0.015–0.086 m.) C'est le critère d'arrêt — « ça lit vrai » — pas une
   égalité numérique.
4. **Corrige un levier à la fois** et reboucle. `alpha_basipetal` /
   `vigor_ref` pour les hauteurs et les longueurs ; `vigor_diameter_gain` pour
   le fuselage du tronc. Un levier par tour, sinon tu ne sais plus *quoi* a
   bougé le résultat.
5. **Répète jusqu'à ce que chaque cas lise sain.** Pas jusqu'à ce que le code
   compile — jusqu'à ce que l'arbre soit crédible.

## Pourquoi ça marche mieux que viser juste

- **Le système est couplé** : changer la vigueur déplace cinq métriques à la
  fois. La seule manière de connaître l'effet net, c'est de le mesurer.
- **Les diagnostics sont la vérité terrain.** Ce que tu *crois* qu'une valeur
  fait et ce qu'elle *fait* divergent vite. La boucle te garde honnête : tu
  réagis à des nombres observés, pas à un modèle mental.
- **Un point de départ « assez bon » bat une dérivation parfaite** parce que le
  premier tour de boucle t'apprend plus que n'importe quel calcul a priori.

## Quand l'appliquer

Dès qu'un réglage pilote un **comportement émergent** plutôt qu'une sortie
directe :

- recalibration des presets d'espèces (l'exemple canonique),
- accord d'un nouveau terme de vigueur / d'allocation,
- réglage d'un seuil de perception, de débourrement, de phénologie,
- tout paramètre dont tu ne peux **pas** prédire l'effet net à la lecture du
  code.

À l'inverse, n'enrobe pas dans une boucle ce qui a une bonne réponse connue
(une constante physique, un nom de champ, un invariant de format) : là, vise
juste.

## Lien avec les autres réflexes du projet

- **Réalisme plutôt que paper-strict** : le critère d'arrêt de la boucle est
  « est-ce crédible / physiquement plus plein », pas « est-ce le minimum du
  paper ».
- **Mode PoC, pas de rétro-compat** : on a le droit de casser YAML / goldens
  pendant qu'on boucle ; ne te freine pas avec des alias ou des garde-fous de
  compat tant que le réglage n'est pas figé.

## En une phrase

Quand tu ne peux pas calculer la bonne valeur, **construis la boucle qui la
trouve** : pose, observe, corrige, recommence — jusqu'à ce que ça lise vrai.
