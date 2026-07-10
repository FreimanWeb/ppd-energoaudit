"""Ввод/вывод универсального спеца: yaml ↔ ObjectSpec, конвертер легаси-паспорта.

Источники спеца:
  * нативный yaml ObjectSpec (config/plants/<id>.yaml, сгенерированный парсером);
  * легаси-паспорт dns7s.yaml (reference_regime/aggregates) — конвертируется;
  * парсер «… расчет.xlsx» (ingest/report_calc.py);
  * ручной ввод (передать готовый ObjectSpec).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .config import project_root
from .spec import (AggregateSpec, Branch, MotorSpec, ObjectSpec, PumpSpec,
                   ReferenceOutputs, RegimeMeasurement, WaterType, infer_pump_kind)


def _plants_dir() -> Path:
    return project_root() / "config" / "plants"


def save_object_spec(spec: ObjectSpec, path: Path | None = None) -> Path:
    """Сохранить спец в нативный yaml (формат ручной правки)."""
    path = path or (_plants_dir() / f"{spec.id}.yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = spec.model_dump(mode="json", exclude_none=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return path


def load_object_spec(plant_id: str) -> ObjectSpec:
    """Загрузить спец объекта: нативный ObjectSpec или конвертация легаси-паспорта."""
    path = _plants_dir() / f"{plant_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Паспорт объекта не найден: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if "reference_regime" in raw:        # легаси-формат dns7s
        return _from_legacy(raw)
    return ObjectSpec(**raw)


def _from_legacy(raw: dict) -> ObjectSpec:
    """Конвертация легаси-паспорта (dns7s.yaml) в ObjectSpec."""
    meta = raw["meta"]
    fluid = raw.get("fluid", {})
    ref = raw["reference_regime"]
    inp = ref.get("inputs", {})
    exp = ref.get("expected", {})
    agg_id = ref["aggregate"]

    # паспорт нужного агрегата
    agg_raw = next(a for a in raw["aggregates"] if a.get("id") == agg_id)
    p = agg_raw.get("pump", {})
    m = agg_raw.get("motor", {})

    pump = PumpSpec(
        model=p.get("model", ""), q_nom=p.get("q_nom"), h_nom=p.get("h_nom"),
        eta_nom=p.get("eta_nom"), power_nom=p.get("power_consumed_nom"),
        kind=infer_pump_kind(p.get("model", "")),
        curve_qh=p.get("curve_qh", []), curve_qeta=p.get("curve_qeta", []))
    motor = MotorSpec(
        model=m.get("model", ""), synchronous=(m.get("kind") == "синхронный"),
        p_nom=m.get("p_nom"), eta_nom=m.get("eta_nom"), cos_phi=m.get("cos_phi"),
        voltage_kv=m.get("voltage_kv"))
    regime = RegimeMeasurement(
        rho=inp["rho"], p_in=inp["p_in"], p_out=inp["p_out"],
        q_fact=inp.get("q"), p_electric=inp.get("p_electric"),
        q_day=inp.get("q_day"), t=inp.get("t"), w=inp.get("w"),
        p_bg=inp.get("p_bg"), t_year=inp.get("t_year"))
    reference = ReferenceOutputs(
        h_fact=exp.get("h_fact"), eta_fact=exp.get("eta_fact"), eta_nom=exp.get("eta_nom"),
        sec_fact=exp.get("sec_fact"), sec_calc=exp.get("sec_calc"),
        load_factor=exp.get("load_factor"), p_hydraulic=exp.get("p_hydraulic"),
        p_electric=exp.get("p_electric"), dw_efficiency=exp.get("dw_efficiency"),
        t_year=inp.get("t_year"))

    agg = AggregateSpec(
        id=agg_id, role="работа", pump=pump, motor=motor,
        transmission_eff=agg_raw.get("transmission_eff", 1.0),
        vfd=agg_raw.get("vfd", False), eta_pump_due=inp.get("eta_pump_due"),
        h_pump_due=inp.get("h_pump_due"),
        regime=regime, reference=reference)

    return ObjectSpec(
        id=meta["id"], name=meta["name"],
        water_type=WaterType(fluid.get("type", "пресная")),
        branch=Branch(meta.get("branch", "кнс")),
        source="config/plants/%s.yaml (легаси)" % meta["id"],
        aggregates=[agg])
