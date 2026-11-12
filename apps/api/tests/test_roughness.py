"""Справочная шероховатость: правила по типу трубы, материалу и покрытию."""

from __future__ import annotations

import pytest

from ppd_audit.core.roughness import hydraulic_reference


@pytest.mark.parametrize(
    ("pipe_type", "material", "coating", "rule", "value_mm"),
    [
        ("СПТ", "Стеклопласт", "нет", "fiberglass", 0.01),
        ("СПТ", "Стеклопласт", "Стекло", "fiberglass", 0.01),
        ("ГТ", "Сталь 20", "нет", "polyethylene", 0.01),
        ("ТПС-У", "Сшитый полиэтилен", "ПЭП-585", "polyethylene", 0.01),
        ("ТПС-У", "Сталь 20", "Стекло", "glass_enamel", 0.01),
        ("МПТ", "Сталь 20", "ПЭ", "polymer_lined_steel", 0.02),
        ("ТПС-У", "Сталь 20", "DPC", "polymer_lined_steel", 0.02),
        ("МПТ", "Сталь 20", "нет", "steel_in_service", 0.5),
        ("ТС", "Сталь 20", "", "steel_in_service", 0.5),
        ("ПНИ", "3сп2", "нет", "steel_in_service", 0.5),
    ],
)
def test_rules_follow_type_material_and_coating(pipe_type, material, coating, rule, value_mm):
    found = hydraulic_reference().roughness(pipe_type, material, coating)

    assert found.id == rule
    assert found.value_mm == pytest.approx(value_mm)
    assert found.range_mm[0] <= found.value_mm <= found.range_mm[1]


def test_every_rule_names_its_sources():
    reference = hydraulic_reference()

    view = reference.as_dict()
    assert all(rule["sources"] for rule in view["roughness"])
    assert "Идельчик" in view["roughness"][0]["sources"][0]
    assert view["tubing"]["value_mm"] == pytest.approx(0.1)
