import math

from palubicki.geom.compound_leaf import CompoundLayout, compound_layout


def _layout(kind, **kw):
    base = {
        "leaflet_count": 5, "leaflet_pair_count": 3, "terminal_leaflet": True,
        "rachis_length": 1.5, "petiole_length": 0.4, "rachis_radius": 0.045,
    }
    base.update(kw)
    return compound_layout(kind, **base)


def test_simple_is_single_blade_no_rachis():
    lay = _layout("simple")
    assert isinstance(lay, CompoundLayout)
    assert len(lay.leaflets) == 1
    origin_uv, axis_angle, scale = lay.leaflets[0]
    assert origin_uv == (0.0, 0.0)
    assert axis_angle == 0.0
    assert scale == 1.0
    assert lay.rachis_segments == []


def test_pinnate_leaflet_count_includes_terminal():
    lay = _layout("pinnate", leaflet_count=7, terminal_leaflet=True)
    assert len(lay.leaflets) == 8  # 7 lateral + 1 terminal
    lay2 = _layout("pinnate", leaflet_count=7, terminal_leaflet=False)
    assert len(lay2.leaflets) == 7
    # rachis present (petiole + rachis = 2 segments)
    assert len(lay.rachis_segments) >= 1


def test_pinnate_pairs_are_opposite():
    lay = _layout("pinnate", leaflet_count=4, terminal_leaflet=False)
    angles = sorted(a for (_uv, a, _s) in lay.leaflets)
    # opposite pairs: equal-magnitude positive/negative axis angles
    assert angles[0] < 0 < angles[-1]
    assert math.isclose(angles[0], -angles[-1], abs_tol=1e-9)


def test_palmate_no_rachis_fan_count():
    lay = _layout("palmate", leaflet_count=5)
    assert len(lay.leaflets) == 5
    assert lay.rachis_segments == [] or len(lay.rachis_segments) == 1  # petiole only
    angles = [a for (_uv, a, _s) in lay.leaflets]
    assert min(angles) < 0 < max(angles)


def test_bipinnate_count_is_pairs_times_leaflets():
    lay = _layout("bipinnate", leaflet_pair_count=3, leaflet_count=4)
    assert len(lay.leaflets) == 3 * 4


def test_growth_is_linear_in_leaflet_count():
    a = len(_layout("pinnate", leaflet_count=4, terminal_leaflet=False).leaflets)
    b = len(_layout("pinnate", leaflet_count=8, terminal_leaflet=False).leaflets)
    assert b == 2 * a


def test_resolve_leaflet_blade_inherits_when_none():
    from palubicki.config import GeomConfig
    from palubicki.geom.compound_leaf import resolve_leaflet_blade
    g = GeomConfig(leaf_shape="ovate", leaf_margin="serrate", leaf_aspect=0.7)
    shape, margin, aspect = resolve_leaflet_blade(g)
    assert (shape, margin, aspect) == ("ovate", "serrate", 0.7)


def test_resolve_leaflet_blade_overrides():
    from palubicki.config import GeomConfig
    from palubicki.geom.compound_leaf import resolve_leaflet_blade
    g = GeomConfig(
        leaf_shape="ovate", leaf_margin="serrate", leaf_aspect=0.7,
        leaflet_shape="lanceolate", leaflet_margin="entire", leaflet_aspect=0.3,
    )
    assert resolve_leaflet_blade(g) == ("lanceolate", "entire", 0.3)


def test_build_rachis_primitive_empty_for_simple():
    from palubicki.geom.compound_leaf import build_rachis_primitive
    from tests.geom.test_leaves import _mat, _tree_with_n_terminal_buds

    tree = _tree_with_n_terminal_buds(3)
    prim = build_rachis_primitive(
        tree, material=_mat(), leaf_size=0.06, foliage_depth=1,
        leaf_kind="simple", leaflet_specs=None, ring_sides=5,
    )
    assert prim.positions.shape[0] == 0


def test_build_rachis_primitive_nonempty_for_pinnate():
    from palubicki.geom.compound_leaf import build_rachis_primitive
    from tests.geom.test_leaves import _mat, _tree_with_n_terminal_buds

    tree = _tree_with_n_terminal_buds(3)
    prim = build_rachis_primitive(
        tree, material=_mat(), leaf_size=0.06, foliage_depth=1,
        leaf_kind="pinnate",
        leaflet_specs={
            "leaflet_count": 6, "leaflet_pair_count": 0, "terminal_leaflet": True,
            "rachis_length": 1.5, "petiole_length": 0.4, "rachis_radius": 0.045,
            "leaflet_shape": "ovate", "leaflet_margin": "entire", "leaflet_aspect": 0.5,
        },
        ring_sides=5,
    )
    assert prim.positions.shape[0] > 0
    assert prim.indices.shape[0] % 3 == 0
