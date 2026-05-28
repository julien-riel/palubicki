# V2 — BHls : ombrage lumineux voxelisé

**Statut** : Roadmap (pas encore designé)
**Préalable** : V1 BHse livré et stable.
**Référence papier** : Palubicki et al. 2009, §5 (light competition).

## Objectif

Remplacer le phototropisme directionnel global de V1 par un modèle de lumière 3D où :
- Chaque bourgeon perçoit la lumière disponible dans son voisinage en fonction de l'auto-occlusion par le feuillage et les branches.
- L'ombrage propagé module à la fois la qualité `Q` (et donc l'allocation BH) et le critère de shedding.

## Idée d'implémentation

- Grille de voxels uniforme englobant l'enveloppe.
- Après chaque step de croissance, chaque internode/leaf injecte une atténuation dans son voxel et propage vers le bas (cône d'ombre approché).
- `Q(b)` redéfini : combine markers perçus (espace) + lumière reçue dans le voxel du bud (BHse + BHls = BHlse hybride).
- `light_direction` reste un paramètre (soleil zenithal par défaut).

## Impact sur V1

- Nouveau module `sim/light.py` (grille voxels, injection, query).
- Modification de `simulator.py` : étape "perception" devient "perception spatiale + perception lumière".
- Nouveau bloc de config `LightConfig` (grid resolution, attenuation per cell, light direction).
- Goldens V1 inchangés si `light.enabled=False` (rétrocompat par défaut).

## Risques / questions ouvertes

- Coût mémoire grille : résolution 128³ × float32 = 8 Mo, acceptable. 256³ = 64 Mo, à surveiller.
- Stabilité : injecter/effacer la lumière entre steps sans drift numérique.
- Tests : difficile sans goldens visuels — peut nécessiter un harness de comparaison statistique (densité moyenne par octant, etc.).
