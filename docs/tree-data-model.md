# Structure de données — `sim/tree.py`

Le graphe arborescent du FSPM par colonisation de l'espace : un squelette
`Node` ↔ `Internode`, avec `Bud` (méristèmes) et `Leaf` accrochés aux nœuds.

```mermaid
classDiagram
    direction LR

    class BudState {
        <<enumeration>>
        ACTIVE
        DORMANT
        DEAD
        RESERVE
    }

    class LeafState {
        <<enumeration>>
        ACTIVE
        SENESCENT
        ABSCISSED
    }

    class Bud {
        <<dataclass eq=False>>
        +np.ndarray position
        +np.ndarray direction
        +int axis_order
        +BudState state = ACTIVE
        +int low_quality_steps = 0
        +int low_light_steps = 0
        +int axis_node_ordinal = 0
        +float recent_vigor = 0.0
    }

    class Leaf {
        <<dataclass eq=False>>
        +float azimuth
        +float birth_time
        +LeafState state = ACTIVE
        +position() np.ndarray
        +age(clock) float
    }

    class Node {
        <<dataclass eq=False>>
        +np.ndarray position
        +bool sympodial_fork = False
        +np.ndarray sag_offset = zeros(3)
    }

    class Internode {
        <<dataclass eq=False>>
        +float length
        +bool is_main_axis
        +float diameter = 0.0
        +int window = 5
        +float light_factor = 1.0
        +float birth_time = 0.0
        +float length_target = 0.0
        +float vigor = 0.0
        +de~float~ quality_history
        +push_quality(q) None
        +average_quality() float
    }

    class Tree {
        <<dataclass>>
        +all_leaves() Iterator~Leaf~
    }

    %% Squelette : chaîne Node <-> Internode <-> Node
    Internode "1" --> "1" Node : parent_node
    Internode "1" --> "1" Node : child_node
    Node "1" o-- "0..*" Internode : children_internodes
    Node "0..1" --> "0..1" Internode : parent_internode

    %% Méristèmes accrochés au nœud
    Node "1" *-- "0..1" Bud : terminal_bud
    Node "1" *-- "0..*" Bud : lateral_buds
    Node "1" *-- "0..*" Bud : dormant_reserve_buds
    Bud "0..*" --> "1" Node : parent_node

    %% Feuilles
    Node "1" *-- "0..*" Leaf : leaves
    Leaf "0..*" --> "1" Node : parent_node

    %% Agrégat racine
    Tree "1" o-- "1" Node : root
    Tree "1" o-- "0..*" Bud : active_buds
    Tree "1" o-- "0..*" Internode : all_internodes

    %% États
    Bud ..> BudState
    Leaf ..> LeafState
```

## Notes

- **`Bud`** (méristème-agent) — `axis_order` : 0 = tronc, +1 par ordre de
  branchaison. `axis_node_ordinal` : rang phyllotaxique **par axe** (pilote
  l'azimut de divergence, #24). `recent_vigor` : EMA du flux Borchert-Honda
  `v_b` → décision de dormance par hystérésis.
- **`Leaf`** — `position` est **dérivée** : `parent_node.position +
  parent_node.sag_offset` (suit automatiquement le ploiement / l'élongation).
- **`Internode`** — `vigor` est le flux `v_b` qui a produit l'entre-nœud
  (→ rayon de pointe pipe-model + diagnostics). `length` vs `length_target` :
  élongation progressive (sigmoïde). `quality_history` : fenêtre glissante
  → abscission (shedding).
- **`Tree`** — `active_buds` est la file de travail de la boucle de
  croissance ; `all_internodes` est un index plat pour `radii` / `sag` /
  diagnostics.
