# Évaluation du réalisme botanique — lecture du code

Évaluation faite **uniquement à partir du code** (`src/palubicki/sim/`), pas de
la documentation, puis recoupée avec
[`code-support-matrix.md`](code-support-matrix.md). Le but n'est pas de
lister toutes les absences (la matrice de support le fait déjà) mais de distinguer
les **choix de périmètre assumés** des **angles morts qui dégradent le réalisme
dans le périmètre actuel**.

## Verdict court

Simulation **solide**, pas un jouet. C'est un FSPM par colonisation de
l'espace qui fait bien son métier : **géométrie et topologie de l'architecture
aérienne**, avec un bon compromis réalisme / vitesse. Les grandes absences
(racines, hormones explicites, reproduction, eau, température) sont des
**décisions de conception légitimes**, déjà documentées.

## Ce qui est vraiment bon

- **Allocation Borchert-Honda** à deux passes (`bh.py`) — dominance apicale
  *émergente*, pas codée en dur.
- **Lumière Beer-Lambert** par ray-marching sur grille de voxels
  (`light.py` / `light_perception.py`) → phototropisme directionnel réel.
- **Pipe model** da Vinci `D^n = Σ Dᵢ^n` idempotent (`radii.py`) + **sag** en
  flexion de poutre cantilever (`sag.py`).
- **Variation inter-espèces** crédible : sympodial vs monopodial, 5 modes de
  phyllotaxie, angles de branchaison par ordre.

## Angles morts qui comptent (dans le périmètre actuel)

1. **La « vigueur » n'est pas du carbone.** `v_b` est un flux d'allocation
   abstrait. Il n'y a pas de boucle source→puits : la lumière **oriente** et
   **tue**, mais une feuille bien éclairée ne **finance** pas son axe. Un rameau
   à l'ombre est puni deux fois indépendamment (mortalité d'ombrage *et* faible
   qualité de marqueurs). C'est l'écart conceptuel le plus structurant.

2. **Le feuillage est décoratif, pas fonctionnel.**
   - ~~La surface foliaire réelle n'est pas injectée dans la grille de lumière.~~
     **Résolu pour les feuillus ([#62](https://github.com/julien-riel/palubicki/issues/62)).**
     `sim/light.py` dépose désormais l'aire de lame **réelle** par feuille (forme,
     taille, lame composée, échelle soleil/ombre), via la fonction partagée
     `geom/leaves.py:leaf_area_records` — même source que le diagnostic
     `total_leaf_area` et le `.glb`. `light.leaf_area_scale` = multiplicateur.
     L'auto-ombrage des feuillus reflète maintenant la morphologie paramétrée.
     **Conifères** : encore sur le scalaire `light.leaf_area` par bourgeon terminal
     — leur dominance apicale *émerge* de ce dépôt « coquille de canopée », et le
     coupler aux vraies aiguilles le casse (le leader du pin s'effondre). Reporté à
     #55 (éventail) + #7 (fascicules), où géométrie d'aiguilles et calibration
     lumière se règlent ensemble.
   - Aucune règle d'âge branchée : `Leaf.birth_time` / `LeafState`
     (`ACTIVE→SENESCENT→ABSCISSED`) existent mais la transition n'arrive jamais.
     Pas de caducité, pas de marcescence. L'infra est là, le fil est débranché.

3. **La mortalité d'ombrage cull, mais ne sculpte pas l'initiation.** L'ombre
   dense devrait *réduire l'émission* de latéraux (évitement d'ombre) ; ici on
   ne fait qu'élaguer a posteriori. La couronne se creuse par élagage, pas par
   parcimonie d'investissement.

4. **Déclencheurs « par échec » au lieu de développement.**
   - Le sympodial se déclenche sur *starvation* du terminal, alors que
     biologiquement l'apex se **détermine** (fleur terminale). Proxy, pas
     mécanisme — tant qu'il n'y a pas de croissance déterminée / reproduction.
   - L'épinastie est une rampe temporelle `1 - exp(-âge/τ)`, pas une réponse à
     l'éthylène ni au poids. Visuellement OK, causalement faux.

5. **Pas de mémoire mécanique du bois.** Le sag est recalculé en statique à
   chaque pas (`D²` comme moment d'inertie). Pas de bois de réaction, pas de
   redressement, pas de fluage, pas d'épaississement induit par le vent
   (Mattheck). Une branche ploie et reste « molle ».

6. **Phénologie binaire.** `annual_growth_period` est un interrupteur on/off :
   pas de degrés-jours, pas de vernalisation, pas de photopériode. La croissance
   ne ralentit jamais aux marges de saison, elle s'arrête net.

## Priorités recommandées

À fort rendement **dans le périmètre existant** (l'infra est déjà là) :

1. ~~**Caducité foliaire** (âge → senescence → abscission).~~ **Livré**
   ([#61](https://github.com/julien-riel/palubicki/issues/61),
   [#67](https://github.com/julien-riel/palubicki/issues/67)).
2. ~~**Coupler la surface foliaire réelle à la grille de lumière.**~~ **Livré pour
   les feuillus** ([#62](https://github.com/julien-riel/palubicki/issues/62)) ;
   conifères reportés à #55/#7 (voir angle mort #2 ci-dessus).

À **ne pas** faire sans changement d'ambition :

- Un vrai **budget carbone**. C'est la bonne façon de réparer l'angle mort #1,
  mais ça refonde le moteur — à réserver pour passer de « plausible » à
  « physiologique ».
