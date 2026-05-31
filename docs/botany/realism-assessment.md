# Évaluation du réalisme botanique — lecture du code

Évaluation faite **uniquement à partir du code** (`src/palubicki/sim/`), pas de
la documentation, puis recoupée avec
[`simulator-gap-analysis.md`](simulator-gap-analysis.md). Le but n'est pas de
lister toutes les absences (le gap-analysis le fait déjà) mais de distinguer
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
   - La surface foliaire réelle (morphologie paramétrée dans `GeomConfig`)
     n'est **pas** injectée dans la grille de lumière — c'est un `light.leaf_area`
     scalaire par bourgeon terminal, découplé du feuillage rendu. L'auto-ombrage
     ne reflète donc pas la morphologie qu'on paramètre.
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

1. **Caducité foliaire** (âge → senescence → abscission). Du câblage, débloque
   le réalisme saisonnier + la résorption automnale.
2. **Coupler la surface foliaire réelle à la grille de lumière**, pour que
   l'auto-ombrage reflète la morphologie déjà paramétrée, au lieu d'un
   `leaf_area` scalaire découplé.

À **ne pas** faire sans changement d'ambition :

- Un vrai **budget carbone**. C'est la bonne façon de réparer l'angle mort #1,
  mais ça refonde le moteur — à réserver pour passer de « plausible » à
  « physiologique ».
