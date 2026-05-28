# V3 — Obstacles & interaction inter-arbres

**Statut** : Roadmap
**Préalable** : V2 BHls livré (les obstacles atténuent la lumière, pas juste l'espace).

## Objectif

Permettre à la simulation de tenir compte d'obstacles statiques (murs, bâtiments, terrain) et de simuler plusieurs arbres partageant le même volume de croissance, qui se concurrencent mutuellement pour l'espace et la lumière.

## Sous-objectifs

1. **Obstacles** :
   - Représentation : AABB, sphères, mesh OBJ chargé.
   - Markers à l'intérieur des obstacles supprimés à l'init.
   - Voxels de lumière (V2) bloqués par les obstacles.
   - Branches en croissance qui pénétreraient un obstacle → bourgeon DORMANT/DEAD.

2. **Simulation multi-arbres** :
   - Liste de seeds (positions + configs possiblement différentes).
   - `MarkerCloud` partagé.
   - Compétition closest-bud naturelle entre arbres (déjà supportée par le mécanisme V1).
   - Compétition lumineuse via grille voxels commune.
   - Export : un nœud glTF par arbre sous une scène commune.

## Impact

- Nouveau module `sim/obstacles.py`.
- `Simulator` orchestre N arbres au lieu d'1, structure interne refactorée.
- CLI : `palubicki forest [--seeds positions.yaml] [--obstacles scene.obj]`.

## Questions ouvertes

- Format de spécification de scène (YAML inline ? fichier dédié ?).
- Comportement quand 2 arbres se touchent : fusion visuelle indésirable, ou bonus réaliste ?
- Coût : forêt de 50 arbres = 50× la sim V1, KDTree global devient le goulot. Vectorisation à prévoir.
