"""Подробности одной статьи карты потерь: формула, исходные величины, состав.

Страница открывается по клику на столбец карты потерь. Ключ статьи — канон
``shared/loss-labels.json`` (``nominal``, ``pump_bg``, ``friction``, ``choke``…).
Значения берутся из уже рассчитанных результатов: декомпозиции агрегата,
сценарного баланса цепочки (``network_losses``), расчёта разводящей сети по
фактической закачке (``network_view``) и адресной диагностики
(``services.diagnostics``).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from ..config import project_root
from ..core.audit import AuditResult
from ..core.pump import KnsDecomposition, PumpingDecomposition


# Ключи, которые не являются потерями: по ним страница подробностей не строится.
NOT_LOSSES = {"input", "bg", "output", "useful"}

# Правила адресной диагностики (``services.diagnostics``), относящиеся к статье.
_CHECKS = {
    "efficiency": [
        "pump_efficiency_low",
        "annual_efficiency_loss",
        "daily_efficiency_high",
        "specific_energy_low",
        "head_low",
        "head_high",
    ],
    "pump_bg": ["pressure_drop_high", "pressure_order", "annual_throttle_loss"],
    "na_throttle": ["pressure_drop_high", "annual_throttle_loss"],
    "hydraulic_bg": ["pressure_drop_high", "pressure_order"],
    "motor": ["motor_underload", "motor_overload"],
    "vfd": ["motor_underload", "motor_overload"],
    "transmission": [],
    "pump": [
        "pump_efficiency_low",
        "head_low",
        "head_high",
        "flow_low",
        "flow_high",
        "suboptimal_flow_loss",
    ],
    "wear": ["pump_efficiency_low", "head_low", "head_high"],
    "suboptimal": ["flow_low", "flow_high", "suboptimal_flow_loss"],
}
_DEFECT_KEYS = {"efficiency", "pump", "wear", "motor", "suboptimal"}
_STAGE = {
    "nominal": "hall",
    "efficiency": "hall",
    "wear": "hall",
    "suboptimal": "hall",
    "pump_bg": "hall",
    "na_throttle": "hall",
    "hydraulic_bg": "hall",
    "vfd": "hall",
    "motor": "hall",
    "transmission": "hall",
    "pump": "hall",
    "pipes": "pipes",
    "friction": "pipes",
    "local": "pipes",
    "choke": "wells",
    "bore": "wells",
}


@cache
def _labels() -> dict:
    path = project_root() / "shared" / "loss-labels.json"
    return json.loads(Path(path).read_text(encoding="utf-8"))


def loss_key(name: str) -> str | None:
    """Канонический ключ статьи по её имени на любой из карт."""
    labels = _labels()
    if name in labels["labels"]:
        return name
    return labels["aliases"].get(name)


def loss_title(key: str) -> str:
    return _labels()["labels"].get(key, key)


def _round(value):
    if not isinstance(value, float):
        return value
    size = abs(value)
    return round(value, 0 if size >= 1000 else 2 if size >= 10 else 3)


def _ru(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def _row(label: str, value, unit: str = "", source: str = "") -> dict:
    return {"label": label, "value": _round(value), "unit": unit, "source": source}


def _network_item(network: dict | None, name: str) -> float | None:
    if not network or network.get("status") != "scenario":
        return None
    for item in network.get("items", []):
        if item["name"] == name:
            return item["power_kw"]
    return None


def _pipes_group(network: dict | None) -> float | None:
    balance = (network or {}).get("operator_balance") or {}
    for group in balance.get("groups", []):
        if group["id"] == "pipes":
            return group["power_kw"]
    return None


def _power(key: str, audit: AuditResult, network: dict | None) -> float | None:
    decomposition = audit.decomposition
    if isinstance(decomposition, KnsDecomposition):
        values = {
            "nominal": decomposition.dp_nominal,
            "efficiency": decomposition.dp_efficiency,
            "pump_bg": decomposition.dp_throttle,
            "na_throttle": decomposition.dp_na_throttle,
            "hydraulic_bg": decomposition.dp_hydraulic,
        }
        if key in values:
            return values[key]
    if isinstance(decomposition, PumpingDecomposition):
        values = {
            "nominal": decomposition.dp_nominal,
            "efficiency": decomposition.dp_efficiency,
            "wear": decomposition.dp_wear,
            "suboptimal": decomposition.dp_suboptimal,
            "motor": decomposition.dp_motor,
        }
        if key in values:
            return values[key]
    names = {
        "friction": "Трение в трубопроводах",
        "local": "Арматура сети и скважин",
        "choke": "Штуцирование скважин",
        "bore": "Трение в стволах скважин",
        "vfd": "Потери ПЧ",
        "motor": "Потери ЭД",
        "transmission": "Потери передачи",
        "pump": "Потери насоса",
    }
    if key == "pipes":
        return _pipes_group(network)
    if key in names:
        return _network_item(network, names[key])
    return None


def _nominal(audit: AuditResult) -> dict:
    spec, regime = audit.spec, audit.regime
    decomposition = audit.decomposition
    useful = (
        decomposition.p_bg_useful
        if isinstance(decomposition, KnsDecomposition)
        else regime.p_hydraulic
    )
    pump_eta = spec.pump.eta_nom if spec else None
    motor_eta = spec.motor.eta_nom if spec else None
    transmission = spec.transmission.efficiency if spec else 1.0
    inputs = [
        _row(
            "Полезная мощность на БГ"
            if isinstance(decomposition, KnsDecomposition)
            else "Гидравлическая мощность",
            useful,
            "кВт",
        ),
        _row("КПД насоса паспортный η_нас.ном", pump_eta, "о.е.", "паспорт"),
        _row("КПД ЭД паспортный η_ЭД.ном", motor_eta, "о.е.", "паспорт"),
        _row("КПД передачи η_пер", transmission, "о.е.", "паспорт"),
        _row("КПД установки номинальный η_ном", regime.eta_nom, "о.е.", "(14)"),
    ]
    rows = []
    if pump_eta and motor_eta and transmission:
        shaft = useful / pump_eta
        coupling = shaft / transmission
        rows = [
            {"name": "Насос при паспортном КПД", "power_kw": shaft - useful},
            {"name": "Передача", "power_kw": coupling - shaft},
            {
                "name": "Электродвигатель при паспортном КПД",
                "power_kw": useful / regime.eta_nom - coupling,
            },
        ]
    return {
        "formula": "ΔP_ном = P_БГ / η_ном − P_БГ  (35); η_ном = η_ЭД.ном · η_пер · η_нас.ном",
        "inputs": inputs,
        "components": {
            "title": "Где возникают номинальные потери",
            "columns": [
                {"key": "name", "label": "Элемент"},
                {"key": "power_kw", "label": "Мощность, кВт", "digits": 1},
            ],
            "rows": rows,
        },
        "notes": ["Снижаются только заменой на оборудование с более высоким паспортным КПД."],
    }


def _efficiency(audit: AuditResult) -> dict:
    regime = audit.regime
    spec = audit.spec
    decomposition = audit.decomposition
    motor_eta = spec.motor.eta_nom if spec else None
    inputs = [
        _row("Потреблённая мощность P_эл", regime.p_electric, "кВт"),
        _row("КПД установки фактический η_НА", regime.eta_unit, "о.е.", "(13)"),
        _row("КПД установки номинальный η_ном", regime.eta_nom, "о.е.", "(14)"),
        _row("КПД ЭД расчётный η_эд.р", audit.eta_motor_real, "о.е.", "(25)–(26)"),
        _row("КПД ЭД паспортный", motor_eta, "о.е.", "паспорт"),
        _row("КПД насоса расчётный η_нас", audit.eta_pump, "о.е.", "(27)"),
        _row("Коэффициент загрузки ЭД K_з", audit.load_factor, "о.е.", "(24)"),
    ]
    rows = []
    total = _power("efficiency", audit, None)
    if total is not None and motor_eta and audit.eta_motor_real:
        motor_part = max(regime.p_electric * (1 - audit.eta_motor_real / motor_eta), 0.0)
        motor_part = min(motor_part, max(total, 0.0))
        rows = [
            {
                "name": "Электродвигатель ниже паспортного КПД (недогрузка, износ)",
                "power_kw": motor_part,
            },
            {
                "name": "Насос ниже паспортного КПД (износ проточной части, режим)",
                "power_kw": total - motor_part,
            },
        ]
    formula = (
        "ΔP_КПД = P_эл − ΔP_ном − ΔP_др − P_БГ  (36)"
        if isinstance(decomposition, KnsDecomposition)
        else "ΔP_КПД = P_гидр · (1/η_НА − 1/η_ном)  (38)"
    )
    return {
        "formula": formula,
        "inputs": inputs,
        "components": {
            "title": "Распределение между электродвигателем и насосом (оценка)",
            "columns": [
                {"key": "name", "label": "Составляющая"},
                {"key": "power_kw", "label": "Мощность, кВт", "digits": 1},
            ],
            "rows": rows,
        },
        "notes": ["Доля ЭД — экономия при паспортном КПД двигателя; остаток отнесён к насосу."],
    }


def _throttle(audit: AuditResult) -> dict:
    regime = audit.regime
    decomposition = audit.decomposition
    rows = []
    if isinstance(decomposition, KnsDecomposition):
        rows = [
            {
                "name": "Гидравлическая мощность, теряемая на задвижке ΔP_гидр (31)",
                "power_kw": decomposition.dp_hydraulic,
            },
            {
                "name": "Дополнительная мощность НА на дросселирование ΔP_НАдр (33)",
                "power_kw": decomposition.dp_na_throttle,
            },
        ]
    drop = regime.dp_valve
    return {
        "formula": "Δp_задв = p_вых − p_БГ (9); ΔP_гидр = Δp_задв·Q/3,6 (31); "
        "ΔP_др = ΔP_гидр/η_ном (32); ΔP_НАдр = ΔP_др − ΔP_гидр (33)",
        "inputs": [
            _row("Давление на выходе насоса p_вых", regime.p_out, "МПа", "телеметрия/замер"),
            _row("Давление на БГ p_БГ", regime.p_bg, "МПа", "телеметрия/замер"),
            _row("Перепад насос — БГ Δp_задв", drop, "МПа"),
            _row("Перепад насос — БГ", drop / 0.098 if drop is not None else None, "атм"),
            _row("Подача Q", regime.q, "м³/ч"),
            _row("КПД установки номинальный η_ном", regime.eta_nom, "о.е."),
        ],
        "components": {
            "title": "Состав потерь на участке насос — БГ",
            "columns": [
                {"key": "name", "label": "Составляющая"},
                {"key": "power_kw", "label": "Мощность, кВт", "digits": 1},
            ],
            "rows": rows,
        },
        "notes": [],
    }


def _pipelines(network: dict | None, measured: dict | None) -> dict:
    rows: dict[str, dict] = {}
    for segment in (network or {}).get("segments", []):
        row = rows.setdefault(
            segment["pipeline_id"],
            {
                "name": segment["name"],
                "length_m": 0.0,
                "inner_mm": segment["inner_diameter_mm"],
                "roughness_mm": segment.get("roughness_mm"),
                "flow_m3h": segment["flow_m3h"],
                "dp_mpa": 0.0,
                "power_kw": 0.0,
            },
        )
        row["length_m"] += segment["length_m"]
        row["inner_mm"] = min(row["inner_mm"], segment["inner_diameter_mm"])
        row["dp_mpa"] += segment["pressure_loss_mpa"]
        row["power_kw"] += segment["power_kw"]
    ordered = sorted(rows.values(), key=lambda item: item["power_kw"], reverse=True)
    notes = [
        "Подача выбранного агрегата распределена по скважинам пропорционально фактической "
        "закачке АРМИТС; шероховатость справочная."
    ]
    if measured and "error" not in measured:
        totals = measured["totals"]
        notes.append(
            f"Вся станция по фактической закачке («Разводящая сеть»): трение "
            f"{_ru(totals['friction_kw'])} кВт при {_ru(totals['q_m3h'])} м³/ч."
        )
    return {
        "formula": "Δp = λ·(L/d)·ρv²/2 (Дарси–Вейсбах), λ — Свами–Джейн по Re и Δэ/d; P = Δp·Q/3,6",
        "inputs": [],
        "components": {
            "title": "Трубопроводы с наибольшими потерями на трение",
            "columns": [
                {"key": "name", "label": "Трубопровод"},
                {"key": "length_m", "label": "Длина, м", "digits": 0},
                {"key": "inner_mm", "label": "Dвн, мм", "digits": 0},
                {"key": "roughness_mm", "label": "Δэ, мм", "digits": 2},
                {"key": "flow_m3h", "label": "Q, м³/ч", "digits": 1},
                {"key": "dp_mpa", "label": "Δp, МПа", "digits": 2},
                {"key": "power_kw", "label": "Потери, кВт", "digits": 1},
            ],
            "rows": ordered[:25],
        },
        "notes": notes,
    }


def _wells(key: str, network: dict | None, measured: dict | None) -> dict:
    field = {"choke": "choke_loss_kw", "local": "armature_loss_kw", "bore": "well_loss_kw"}[key]
    measured_wells = {
        row["well"].upper(): row for row in (measured or {}).get("wells", []) if "well" in row
    }
    rows = []
    for well in (network or {}).get("wells", []):
        row = {"well": well["id"], "flow_m3h": well["flow_m3h"], "power_kw": well.get(field)}
        if key == "choke":
            fact = measured_wells.get(str(well["id"]).upper())
            row["dp_choke_fact_mpa"] = fact.get("dp_choke_mpa") if fact else None
            row["choke_fact_kw"] = fact.get("choke_kw") if fact else None
        rows.append(row)
    rows.sort(key=lambda item: item["power_kw"] or 0.0, reverse=True)
    columns = [
        {"key": "well", "label": "Скважина"},
        {"key": "flow_m3h", "label": "Q, м³/ч", "digits": 2},
        {"key": "power_kw", "label": "Потери (сценарий), кВт", "digits": 2},
    ]
    if key == "choke":
        columns += [
            {"key": "dp_choke_fact_mpa", "label": "Δp штуцера по замеру, МПа", "digits": 2},
            {"key": "choke_fact_kw", "label": "Потери по замеру, кВт", "digits": 2},
        ]
    formulas = {
        "choke": "Сценарий: избыток давления после сопротивлений пути и требуемого давления; "
        "замер: Δp = p_до_шт − p_после_шт (карточки АРМИТС); P = Δp·Q/3,6",
        "local": "Δp = K·ρv²/2 по скорости в НКТ; P = Δp·Q/3,6",
        "bore": "Δp = λ·(L/d)·ρv²/2 в НКТ (длина и диаметр — сценарные); P = Δp·Q/3,6",
    }
    return {
        "formula": formulas[key],
        "inputs": [],
        "components": {"title": "По скважинам", "columns": columns, "rows": rows},
        "notes": [],
    }


def _motor(key: str, audit: AuditResult, network: dict | None) -> dict:
    regime = audit.regime
    spec = audit.spec
    inputs = [
        _row("Потреблённая мощность P_эл", regime.p_electric, "кВт"),
        _row("Номинальная мощность ЭД", spec.motor.p_nom if spec else None, "кВт", "паспорт"),
        _row("Коэффициент загрузки K_з", audit.load_factor, "о.е.", "(24)"),
        _row("КПД ЭД расчётный η_эд.р", audit.eta_motor_real, "о.е.", "(25)–(26)"),
        _row("КПД ЭД паспортный", spec.motor.eta_nom if spec else None, "о.е.", "паспорт"),
        _row("КПД передачи", spec.transmission.efficiency if spec else None, "о.е.", "паспорт"),
        _row("Частотный преобразователь", "есть" if spec and spec.vfd else "нет", ""),
    ]
    rows = [
        {"name": item["name"], "power_kw": item["power_kw"]}
        for item in (network or {}).get("items", [])
        if item["name"] in {"Потери ПЧ", "Потери ЭД", "Потери передачи"}
    ]
    return {
        "formula": "P_вала = P_эл · η_ПЧ · η_эд.р · η_пер; потери ступени — разность "
        "мощностей на входе и выходе",
        "inputs": inputs,
        "components": {
            "title": "Потери в приводе",
            "columns": [
                {"key": "name", "label": "Ступень"},
                {"key": "power_kw", "label": "Мощность, кВт", "digits": 1},
            ],
            "rows": rows,
        },
        "notes": [],
    }


def _pump(audit: AuditResult) -> dict:
    regime = audit.regime
    pump = audit.spec.pump if audit.spec else None
    return {
        "formula": "η_нас = η_НА / (η_эд.р · η_ПЧ · η_пер)  (27); потери насоса = P_вала − P_гидр",
        "inputs": [
            _row("Подача Q", regime.q, "м³/ч"),
            _row("Номинальная подача Q_ном", pump.q_nom if pump else None, "м³/ч", "паспорт"),
            _row("Напор фактический H_ф", regime.h_fact, "м", "(8)"),
            _row("Напор должный H_д", audit.h_due, "м", "паспортная кривая Q–H"),
            _row("Гидравлическая мощность P_гидр", regime.p_hydraulic, "кВт", "(11)"),
            _row("КПД насоса расчётный η_нас", audit.eta_pump, "о.е.", "(27)"),
        ],
        "components": {"title": "", "columns": [], "rows": []},
        "notes": [],
    }


def build_loss_detail(
    key: str,
    audit: AuditResult,
    *,
    tariff: float,
    t_year: float,
    network: dict | None = None,
    measured: dict | None = None,
    recs: dict | None = None,
) -> dict:
    """Подробности статьи ``key`` для выбранного режима агрегата."""
    if key in NOT_LOSSES or key not in _labels()["labels"]:
        raise ValueError(f"Неизвестная статья потерь: {key}")
    recs = recs or {}
    power = _power(key, audit, network)
    p_el = audit.regime.p_electric
    if key == "nominal":
        body = _nominal(audit)
    elif key == "efficiency":
        body = _efficiency(audit)
    elif key in {"pump_bg", "na_throttle", "hydraulic_bg"}:
        body = _throttle(audit)
    elif key in {"friction", "pipes"}:
        body = _pipelines(network, measured)
    elif key in {"choke", "local", "bore"}:
        body = _wells(key, network, measured)
    elif key in {"vfd", "motor", "transmission"}:
        body = _motor(key, audit, network)
    else:  # pump, wear, suboptimal
        body = _pump(audit)
    check_ids = _CHECKS.get(key, [])
    rules = (recs.get("diagnostics") or {}).get("rules", [])
    checks = [rule for rule in rules if rule["id"] in check_ids]
    # Где методика задаёт годовую формулу (44)/(45), берётся она: в ней годовой
    # объём закачки, а не мощность выбранного момента × наработка.
    methodology = {"efficiency": audit.dw_efficiency, "pump_bg": audit.dw_throttle}
    annual = methodology.get(key)
    if annual is None:
        annual = power * t_year if power is not None else None
    return {
        "key": key,
        "title": loss_title(key),
        "stage": _STAGE.get(key, "hall"),
        "power_kw": power,
        "share": power / p_el if power is not None and p_el else None,
        "annual_kwh": annual,
        "annual_money_krub": annual * tariff / 1000 if annual is not None else None,
        "t_year": t_year,
        "tariff": tariff,
        **body,
        "checks": checks,
        "defects": recs.get("defects") if key in _DEFECT_KEYS else None,
        "motor_benchmark": recs.get("motor_benchmark")
        if key in {"nominal", "motor", "efficiency"}
        else None,
        "pump_benchmark": recs.get("pump_benchmark")
        if key in {"nominal", "pump", "efficiency", "wear"}
        else None,
        "network_status": (network or {}).get("status"),
    }
