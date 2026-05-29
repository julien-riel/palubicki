from dataclasses import dataclass, field
from typing import Literal

from palubicki.edit.schema import _field_descriptor, _type_info, build_schema


def test_build_schema_returns_sections_and_species():
    s = build_schema()
    assert "sections" in s
    assert "species" in s
    assert "top_level" in s
    assert isinstance(s["sections"], list)
    assert isinstance(s["species"], list)


def test_build_schema_section_names_in_declared_order():
    # Even when nothing has `ui` metadata yet, sections that DO have at least one
    # ui-tagged field must appear; sections with none must be omitted.
    s = build_schema()
    expected_order = ["envelope", "sim", "tropism", "phyllotaxy",
                      "shedding", "geom", "light", "sag"]
    names = [sec["name"] for sec in s["sections"]]
    # Whatever sections appear, they must be in this relative order:
    indices = [expected_order.index(n) for n in names]
    assert indices == sorted(indices)


def test_type_info_int_uses_ui_min_max_step():
    @dataclass
    class X:
        n: int = field(default=5, metadata={"ui": {"min": 0, "max": 10, "step": 1}})
    f = next(iter(X.__dataclass_fields__.values()))
    info = _field_descriptor(f, int, f.metadata["ui"])
    assert info == {
        "name": "n",
        "default": 5,
        "type": "int",
        "min": 0,
        "max": 10,
        "step": 1,
    }


def test_type_info_float_default_step():
    info = _type_info(float)
    assert info == {"type": "float"}


def test_type_info_bool():
    info = _type_info(bool)
    assert info == {"type": "bool"}


def test_type_info_literal():
    info = _type_info(Literal["a", "b", "c"])
    assert info == {"type": "enum", "choices": ["a", "b", "c"]}


def test_type_info_tuple_vec3():
    info = _type_info(tuple[float, float, float])
    assert info == {"type": "vec3"}


def test_type_info_unknown_type_returns_unknown():
    from pathlib import Path
    info = _type_info(Path | None)
    assert info == {"type": "unknown"}


def test_species_matches_list_species():
    from palubicki.config import _list_species
    s = build_schema()
    assert s["species"] == _list_species()


def test_envelope_section_exposes_expected_fields():
    s = build_schema()
    env = next(sec for sec in s["sections"] if sec["name"] == "envelope")
    names = [f["name"] for f in env["fields"]]
    assert names == ["shape", "rx", "ry", "rz", "marker_count"]


def test_sim_section_exposes_expected_fields():
    s = build_schema()
    sim = next(sec for sec in s["sections"] if sec["name"] == "sim")
    names = [f["name"] for f in sim["fields"]]
    assert "max_simulation_years" in names
    assert "lambda_apical" in names
    assert "r_perception" in names
    assert "r_kill" in names
    assert "internode_length" in names


def test_top_level_seed_exposed():
    s = build_schema()
    names = [f["name"] for f in s["top_level"]]
    assert "seed" in names


def test_shape_is_enum():
    s = build_schema()
    env = next(sec for sec in s["sections"] if sec["name"] == "envelope")
    shape = next(f for f in env["fields"] if f["name"] == "shape")
    assert shape["type"] == "enum"
    assert set(shape["choices"]) == {"sphere", "ellipsoid", "cone", "half_ellipsoid"}
