"""Addressable loss detail, independent of downstream geometry for the machine block."""

from __future__ import annotations

import math

from ..core.audit import ETA_VFD_DEFAULT, AuditResult
from .formula_view import loss_equations
from .loss_requirements import HALL_REQUIREMENT_KEYS, data_requirements


PHYSICAL = {
    "vfd_loss": "Потери в ПЧ",
    "motor_chain_loss": "Потери в электродвигателе",
    "transmission_loss": "Потери в передаче",
    "pump_loss": "Потери в насосе",
    "hydraulic_bg_loss": "Перепад гидравлической мощности насос–БГ",
}
CAUSAL = {
    "efficiency_loss": ("Отклонение от номинального КПД", "36", "dp_efficiency"),
    "nominal_loss": ("Потери при номинальном КПД", "35", "dp_nominal"),
    "throttle_loss": ("Дополнительные потери НА от повышенного напора", "33", "dp_na_throttle"),
    "wear_loss": ("Износ", "42", "dp_wear"),
    "suboptimal_loss": ("Неоптимальная подача", "39", "dp_suboptimal"),
    "motor_loss": ("Потери из-за загрузки ЭД", "41", "dp_motor"),
    "viscosity_loss": ("Вязкость", "40", "dp_viscosity"),
}
DOWNSTREAM = {
    "pipes",
    "wells",
    "pipes_loss",
    "friction_loss",
    "local_loss",
    "choke_loss",
    "bore_loss",
}
SUPPORTED_KEYS = {
    "hall",
    "hall_causal",
    "efficiency_causes",
    "pump_bg_loss",
    *PHYSICAL,
    *CAUSAL,
    *DOWNSTREAM,
}


def _n(value):
    return "—" if value is None else f"{value:g}"


def _valid_eta(value):
    return value is not None and math.isfinite(value) and 0 < value <= 1


def _causal_expression(audit, key, bg_power):
    r, agg = audit.regime, audit.spec
    eta_due = audit.eta_pump_due
    if eta_due is None and not agg.pump.curve_qeta and audit.branch == "перекачка":
        eta_due = agg.pump.eta_nom
    nominal = ["pump_eta_nom", "motor_eta_nom", "eta_gear", "eta_vfd", "eta_nom"]
    hydraulic = ["q", "p_in", "p_out"]
    kns = audit.branch == "кнс"
    reference = bg_power if kns else r.p_hydraulic
    reference_name = "P_БГ" if kns else "P_гидр"
    expressions = {
        "nominal_loss": (
            f"{reference_name}·(1/η_ном−1)",
            f"{_n(reference)}·(1/{_n(r.eta_nom)}−1)",
            (["q", "p_in", "p_bg"] if kns else hydraulic) + nominal,
        ),
        "efficiency_loss": (
            "P_эл−P_гидр/η_ном",
            f"{_n(r.p_electric)}−{_n(r.p_hydraulic)}/{_n(r.eta_nom)}",
            ["p_electric", *hydraulic, *nominal],
        ),
        "throttle_loss": (
            "Q·(p_вых−p_БГ)/3,6·(1/η_ном−1)",
            f"{_n(r.q)}·({_n(r.p_out)}−{_n(r.p_bg)})/3,6·(1/{_n(r.eta_nom)}−1)",
            ["q", "p_out", "p_bg", *nominal],
        ),
        "suboptimal_loss": (
            "P_гидр·(1/(η_д·η_ЭД.ном)−1/η_ном)",
            f"{_n(r.p_hydraulic)}·(1/({_n(eta_due)}·{_n(agg.motor.eta_nom)} )−1/{_n(r.eta_nom)})",
            [*hydraulic, "eta_due", *nominal],
        ),
        "wear_loss": (
            "P_гидр/η_ЭД.ном·(1/η_нас−1/η_д.в)",
            f"{_n(r.p_hydraulic)}/{_n(agg.motor.eta_nom)}·(1/{_n(audit.eta_pump)}−1/{_n(eta_due)})",
            [*hydraulic, "eta_pump", "eta_due", "motor_eta_nom"],
        ),
        "motor_loss": (
            "P_эл−P_гидр/(η_нас·η_ЭД.ном)",
            f"{_n(r.p_electric)}−{_n(r.p_hydraulic)}/({_n(audit.eta_pump)}·{_n(agg.motor.eta_nom)})",
            [
                "p_electric",
                *hydraulic,
                "eta_pump",
                "motor_eta_nom",
                "motor_p_nom",
                "alpha",
                "load_factor",
            ],
        ),
        "viscosity_loss": (
            "P_гидр/η_ЭД.ном·(1/η_д.в−1/η_д)",
            f"{_n(r.p_hydraulic)}/{_n(agg.motor.eta_nom)}·(1/{_n(eta_due)}−1/{_n(eta_due)})",
            [*hydraulic, "eta_due", "motor_eta_nom"],
        ),
    }
    return expressions[key]


def build_loss_detail(
    audit: AuditResult,
    key: str,
    *,
    tariff: float,
    provenance: dict | None = None,
    sources: dict | None = None,
    scenario: bool = False,
    network: dict | None = None,
    network_analysis: dict | None = None,
) -> dict:
    if key not in SUPPORTED_KEYS:
        raise ValueError("Неизвестная составляющая потерь")
    if audit.spec is None or audit.spec.regime is None:
        raise ValueError("Для разбора нужен выбранный режим")
    agg, r = audit.spec, audit.regime
    requirements = data_requirements(
        agg, audit=audit, provenance=provenance, scenario=scenario, network=network
    )
    states = {row["key"]: row["status"] for row in requirements}
    sources = sources or {}
    field_sources = (provenance or {}).get("field_sources", {})
    regime_note = (
        sources.get("Ручной замер") or sources.get("YAML") or "Выбранный режим; источник не указан"
    )
    rm = agg.regime
    inputs = {}

    def add_input(name, label, value, unit, origin, source):
        inputs[name] = {
            "key": name,
            "label": label,
            "value": value,
            "unit": unit,
            "origin": origin if value is not None else "unavailable",
            "source": source,
        }

    for name, label, value, unit, source_key in (
        ("q", "Подача", r.q, "м³/ч", "Q"),
        ("p_in", "Давление приёма", r.p_in, "МПа", "p_вх"),
        ("p_out", "Давление выкида", r.p_out, "МПа", "p_вых"),
        ("p_bg", "Давление БГ", r.p_bg, "МПа", "p_БГ"),
        ("p_electric", "Электрическая мощность", r.p_electric, "кВт", "P_эл"),
    ):
        derived = (
            name == "q" and rm.q_fact is None or name == "p_electric" and rm.p_electric is None
        )
        basis = (
            "Q_сут / T_сут; не мгновенная подача"
            if name == "q" and derived
            else "W_сут / T_сут; средняя за часы работы"
            if derived
            else regime_note
        )
        add_input(
            name,
            label,
            value,
            unit,
            "calculated" if derived else "measured",
            sources.get(source_key) or basis,
        )
    eta_vfd = ETA_VFD_DEFAULT if agg.vfd else 1.0
    eta_motor = audit.eta_motor_real if _valid_eta(audit.eta_motor_real) else None
    eta_gear = agg.transmission.efficiency if _valid_eta(agg.transmission.efficiency) else None
    add_input(
        "eta_vfd",
        "КПД ПЧ / обход ПЧ",
        eta_vfd,
        "доля",
        "assumed" if agg.vfd or states["vfd"] != "ready" else "calculated",
        "По Методике принят 0,97" if agg.vfd else "По записанному признаку ПЧ отсутствует",
    )
    add_input(
        "eta_motor",
        "КПД ЭД при текущей загрузке",
        eta_motor,
        "доля",
        "calculated",
        "Формулы 24–26; это расчёт, не измерение КПД",
    )
    for name, label, value, unit, req in (
        ("motor_p_nom", "Номинальная мощность ЭД", agg.motor.p_nom, "кВт", "motor.p_nom"),
        ("motor_eta_nom", "Номинальный КПД ЭД", agg.motor.eta_nom, "доля", "motor.eta_nom"),
        ("eta_gear", "КПД передачи", eta_gear, "доля", "transmission.efficiency"),
        ("pump_eta_nom", "Номинальный КПД насоса", agg.pump.eta_nom, "доля", "pump.eta_nom"),
    ):
        field_source = field_sources.get(req)
        source_note = (
            f"{field_source['source']}; внёс: {field_source['author']}"
            if field_source
            else "Источник именно этого параметра не установлен; см. историю паспорта"
        )
        if scenario:
            source_note = "Временное значение сценария, не паспорт"
        add_input(
            name,
            label,
            value,
            unit,
            "assumed" if scenario or states[req] != "ready" else "calculated",
            source_note,
        )
    add_input(
        "eta_nom",
        "Номинальный КПД установки",
        r.eta_nom,
        "доля",
        "calculated",
        "η_нас.ном·η_ЭД.ном·η_передачи·η_ПЧ; см. источники отдельных множителей",
    )
    add_input(
        "alpha",
        "Коэффициент типа ЭД",
        agg.motor.alpha,
        "",
        "calculated" if states["motor.synchronous"] == "ready" else "assumed",
        "α=2 у синхронного ЭД, иначе 1; тип требует подтверждения по паспорту",
    )
    add_input(
        "load_factor",
        "Коэффициент загрузки ЭД",
        audit.load_factor,
        "доля",
        "calculated",
        "P_эл/(P_ЭД.ном/η_ЭД.ном), формула 24",
    )
    add_input(
        "eta_pump",
        "КПД насоса расчётный",
        audit.eta_pump,
        "доля",
        "calculated",
        "η_установки/(η_ПЧ·η_ЭД.расч·η_передачи), формула 27; не отдельный замер",
    )
    eta_due = audit.eta_pump_due
    due_source = (
        agg.pump.curve_source.reference
        if agg.pump.curve_source
        else "Источник характеристики не подтверждён"
    )
    if eta_due is None and not agg.pump.curve_qeta and audit.branch == "перекачка":
        eta_due = agg.pump.eta_nom
        due_source = (
            "В декомпозиции вместо отсутствующей Q–η принят номинальный КПД; "
            "допущение исходной модели"
        )
    add_input("eta_due", "Опорный КПД при текущей подаче", eta_due, "доля", "assumed", due_source)
    bg_power = (r.p_bg - r.p_in) * r.q / 3.6 if r.p_bg is not None else None
    after_vfd = r.p_electric * eta_vfd
    after_motor = after_vfd * eta_motor if eta_motor is not None else None
    shaft = after_motor * eta_gear if after_motor is not None and eta_gear is not None else None
    conflict = next(
        (row["reason"] for row in requirements if row["key"] == "regime.consistency"), None
    )
    raw = (
        (
            "vfd_loss",
            r.p_electric,
            after_vfd,
            "P_эл·(1−η_ПЧ)",
            f"{_n(r.p_electric)}·(1−{_n(eta_vfd)})",
            ["p_electric", "eta_vfd"],
            "Оценка по принятому КПД ПЧ; не отдельный замер.",
        ),
        (
            "motor_chain_loss",
            after_vfd,
            after_motor,
            "P_послеПЧ·(1−η_ЭД.расч)",
            f"{_n(after_vfd)}·(1−{_n(eta_motor)})",
            [
                "p_electric",
                "eta_vfd",
                "eta_motor",
                "motor_p_nom",
                "motor_eta_nom",
                "alpha",
                "load_factor",
            ],
            "КПД ЭД вычислен по загрузке и номинальному КПД; "
            "не потери только от завышенной мощности.",
        ),
        (
            "transmission_loss",
            after_motor,
            shaft,
            "P_послеЭД·(1−η_передачи)",
            f"{_n(after_motor)}·(1−{_n(eta_gear)})",
            ["p_electric", "eta_vfd", "eta_motor", "eta_gear"],
            "Разность мощности до и после передачи; "
            "учитывает расчётный КПД двигателя и наличие ПЧ.",
        ),
        (
            "pump_loss",
            shaft,
            r.p_hydraulic,
            "P_навалу−Q·(p_вых−p_вх)/3,6",
            f"{_n(shaft)}−{_n(r.q)}·({_n(r.p_out)}−{_n(r.p_in)})/3,6",
            ["p_electric", "eta_vfd", "eta_motor", "eta_gear", "q", "p_in", "p_out"],
            "Остаток между мощностью вала и гидравлической мощностью. "
            "Это не доказательство износа и не только устранимые потери.",
        ),
        (
            "hydraulic_bg_loss",
            r.p_hydraulic,
            bg_power,
            "Q·(p_вых−p_БГ)/3,6",
            f"{_n(r.q)}·({_n(r.p_out)}−{_n(r.p_bg)})/3,6",
            ["q", "p_out", "p_bg"],
            "Эквивалент перепада давления. Без геометрии не разделяется на трубу, "
            "арматуру, высотную и скоростную составляющие.",
        ),
    )
    allocation_conflict = next(
        (row["reason"] for row in requirements if row["key"] == "equipment.consistency"), None
    )
    notes = [
        "Разбиение по оборудованию и разбиение по причинам — альтернативные представления, "
        "их составляющие не складываются между собой.",
        "Годовые энергия и стоимость — экстраполяция выбранного режима на указанную наработку, "
        "не измеренная годовая потеря и не достигнутая экономия.",
    ]
    if scenario:
        notes.append("Временные паспортные допущения: рабочая БД не изменена.")
    if conflict:
        notes.append(conflict)
    if allocation_conflict:
        notes.append(allocation_conflict)
    components = []

    def component(code, name, power, origin, formula, substitution, basis, selected_inputs):
        if power is not None and math.isclose(power, 0, abs_tol=1e-9):
            power = 0.0
        return {
            "key": code,
            "name": name,
            "power_kw": power,
            "share_pct": power / r.p_electric * 100 if power is not None else None,
            "annual_kwh": power * audit.annual_runtime_hours if power is not None else None,
            "annual_rub": power * audit.annual_runtime_hours * tariff
            if power is not None
            else None,
            "origin": "unavailable" if power is None else origin,
            "formula": formula,
            "substitution": substitution,
            **loss_equations(formula, substitution, power),
            "basis": basis,
            "inputs": selected_inputs,
        }

    for code, before, after, formula, substitution, names, basis in raw:
        available = not conflict and (
            not allocation_conflict or code in {"vfd_loss", "hydraulic_bg_loss"}
        )
        power = before - after if before is not None and after is not None and available else None
        selected_inputs = [inputs[name] for name in names]
        origin = (
            "assumed" if any(i["origin"] == "assumed" for i in selected_inputs) else "calculated"
        )
        components.append(
            component(
                code, PHYSICAL[code], power, origin, formula, substitution, basis, selected_inputs
            )
        )
    total = r.p_electric - bg_power if bg_power is not None and not conflict else None
    incoming, outgoing = r.p_electric, bg_power
    title = "Машинный блок и обвязка до БГ"
    boundary = (
        "Электрический ввод выбранного НА → прирост гидравлической мощности на БГ "
        "относительно приёма"
    )
    relevant = HALL_REQUIREMENT_KEYS | {"equipment.consistency"}
    if key in PHYSICAL:
        electrical = {"vfd", "vfd.efficiency", "regime.p_electric"}
        motor = electrical | {
            "motor.p_nom",
            "motor.eta_nom",
            "motor.synchronous",
            "equipment.consistency",
        }
        relevant = {
            "vfd_loss": electrical,
            "motor_chain_loss": motor,
            "transmission_loss": motor | {"transmission.efficiency"},
            "pump_loss": motor
            | {"transmission.efficiency", "regime.q_fact", "regime.p_in", "regime.p_out"},
            "hydraulic_bg_loss": {"regime.q_fact", "regime.p_out", "regime.p_bg", "hall.geometry"},
        }[key] | {"regime.t_year", "regime.consistency"}
        components = [c for c in components if c["key"] == key]
        total = components[0]["power_kw"]
        _, incoming, outgoing, *_ = next(row for row in raw if row[0] == key)
        title = PHYSICAL[key]
        boundary = (
            "Составляющая физической цепочки выбранного НА; "
            "доля указана от его электрического ввода"
        )
    elif key in CAUSAL or key in {"pump_bg_loss", "hall_causal", "efficiency_causes"}:
        if key == "hall_causal":
            selected = ["nominal_loss", "efficiency_loss"]
            if audit.branch == "кнс":
                selected += ["throttle_loss", "hydraulic_bg_loss"]
            title = "Причинное разложение машинного блока"
        elif key == "efficiency_causes":
            selected = ["suboptimal_loss", "wear_loss", "motor_loss", "viscosity_loss"]
            title = "Составляющие отклонения КПД"
        else:
            selected = ["throttle_loss", "hydraulic_bg_loss"] if key == "pump_bg_loss" else [key]
            title = "Потери на участке Насос–БГ" if key == "pump_bg_loss" else CAUSAL[key][0]
        components = []
        for code in selected:
            if code == "hydraulic_bg_loss":
                components.append(
                    component(
                        code,
                        PHYSICAL[code],
                        r.p_hydraulic - bg_power if bg_power is not None and not conflict else None,
                        "calculated",
                        "Q·(p_вых−p_БГ)/3,6",
                        f"{_n(r.q)}·({_n(r.p_out)}−{_n(r.p_bg)})/3,6",
                        "Гидравлическая часть (31); не электрический эквивалент всего перепада.",
                        [inputs[n] for n in ("q", "p_out", "p_bg")],
                    )
                )
                continue
            name, _, field = CAUSAL[code]
            value = getattr(audit.decomposition, field, None) if not conflict else None
            formula, substitution, input_names = _causal_expression(audit, code, bg_power)
            basis = (
                "Точная составляющая исходного причинного разложения; "
                "не раскладывается повторно по оборудованию "
                "и сама не доказывает конкретную неисправность."
            )
            if code == "viscosity_loss":
                basis += (
                    " Вязкостная поправка в текущем расчёте не задана: η_д.в=η_д; "
                    "ноль не доказывает отсутствия влияния вязкости."
                )
            if value is None:
                basis += " Для этой ветки и имеющихся данных составляющая отдельно не определена."
            components.append(
                component(
                    code,
                    name,
                    value,
                    "assumed",
                    formula,
                    substitution,
                    basis,
                    [inputs[n] for n in dict.fromkeys(input_names)],
                )
            )
        total = (
            sum(c["power_kw"] for c in components)
            if all(c["power_kw"] is not None for c in components)
            else None
        )
        incoming, outgoing = r.p_electric, None
        boundary = (
            "Причинное разложение исходной карты потерь, "
            "не последовательный баланс отдельных устройств"
        )
        if key == "hall_causal":
            outgoing = bg_power if audit.branch == "кнс" else r.p_hydraulic
            total = incoming - outgoing if outgoing is not None and not conflict else None
            boundary = (
                "Электрический ввод → прирост гидравлической мощности на БГ"
                if audit.branch == "кнс"
                else "Электрический ввод → гидравлическая мощность на выходе насоса"
            )
        elif key == "efficiency_causes":
            total = getattr(audit.decomposition, "dp_efficiency", None) if not conflict else None
            boundary = "Уточнение отклонения КПД, не дополнительные потери сверх него"
            if audit.branch == "кнс":
                boundary += (
                    ". Для КНС исходная модель не выделяет эти частные причины; "
                    "общая оценка отклонения сохранена, его распределение неизвестно."
                )
        motor_dependencies = {
            "motor.p_nom",
            "motor.eta_nom",
            "motor.synchronous",
            "regime.p_electric",
        }
        nominal_dependencies = {
            "pump.eta_nom",
            "motor.eta_nom",
            "transmission.efficiency",
            "vfd",
            "vfd.efficiency",
        }
        dependencies = {
            "q": {"regime.q_fact"},
            "p_in": {"regime.p_in"},
            "p_out": {"regime.p_out"},
            "p_bg": {"regime.p_bg"},
            "p_electric": {"regime.p_electric"},
            "pump_eta_nom": {"pump.eta_nom"},
            "motor_eta_nom": {"motor.eta_nom"},
            "motor_p_nom": {"motor.p_nom"},
            "eta_gear": {"transmission.efficiency"},
            "eta_vfd": {"vfd", "vfd.efficiency"},
            "eta_nom": nominal_dependencies,
            "alpha": {"motor.synchronous"},
            "load_factor": motor_dependencies,
            "eta_motor": motor_dependencies,
            "eta_pump": motor_dependencies
            | {
                "transmission.efficiency",
                "vfd",
                "vfd.efficiency",
                "regime.q_fact",
                "regime.p_in",
                "regime.p_out",
                "equipment.consistency",
            },
            "eta_due": {
                "pump.curve_qeta",
                "pump.curve_source",
                "pump.n_rpm",
                "pump.model",
                "pump.eta_nom",
            },
        }
        relevant = {"regime.t_year", "regime.consistency"}
        for part in components:
            for item in part["inputs"]:
                relevant.update(dependencies.get(item["key"], ()))
        if "hydraulic_bg_loss" in selected:
            relevant.add("hall.geometry")
        if total is not None and total < 0:
            notes.append(
                "Отрицательное отклонение от номинала сохранено: "
                "это не положительная физическая потеря и не подтверждённая экономия."
            )
    elif key in DOWNSTREAM:
        detail = _downstream_components(network_analysis, key, component)
        components, title, boundary = detail
        incoming, outgoing = None, None
        total = (
            sum(c["power_kw"] for c in components)
            if components and all(c["power_kw"] is not None for c in components)
            else None
        )
        notes.extend((network_analysis or {}).get("warnings", []))
        notes.append(
            "Расходы по ветвям, шероховатость и сопротивления — сценарные допущения, "
            "не одновременные измерения. Трение в стволах находится "
            "за границей баланса до устьев."
        )
        relevant = {"network.geometry", "regime.q_fact", "regime.rho"}
    known = sum(c["power_kw"] for c in components if c["power_kw"] is not None)
    missing = any(c["power_kw"] is None for c in components)
    unallocated = (
        total - known if total is not None and missing else 0.0 if total is not None else None
    )
    residual = total - known if total is not None and not missing else None
    status = (
        "ready"
        if total is not None and not missing
        else "partial"
        if total is not None or any(c["power_kw"] is not None for c in components)
        else "unavailable"
    )
    if (
        key in DOWNSTREAM
        and (network_analysis or {}).get("status") != "scenario"
        and status == "ready"
    ):
        status = "partial"
    if not components:
        notes.append(
            "Для выбранной составляющей нет достаточных исходных данных; "
            "отсутствие результата не означает нулевую потерю."
        )
    if (key == "hall" or (key == "hall_causal" and audit.branch == "кнс")) and r.p_bg is None:
        notes.append(
            "Нет давления БГ: общая потеря до этой границы и нераспределённый остаток "
            "не определены; известные внутренние составляющие показаны отдельно."
        )
    if audit.annual_runtime_is_assumed:
        notes.append("Годовая наработка принята равной 8760 ч; это допущение.")
    return {
        "key": key,
        "title": title,
        "boundary": boundary,
        "status": status,
        "total_kw": total,
        "input_kw": incoming,
        "output_kw": outgoing,
        "annual_runtime_hours": audit.annual_runtime_hours,
        "annual_runtime_is_assumed": audit.annual_runtime_is_assumed,
        "tariff": tariff,
        "annual_kwh": total * audit.annual_runtime_hours if total is not None else None,
        "annual_rub": total * audit.annual_runtime_hours * tariff if total is not None else None,
        "unallocated_kw": unallocated,
        "balance_residual_kw": residual,
        "components": components,
        "requirements": [row for row in requirements if relevant is None or row["key"] in relevant],
        "notes": notes,
    }


def _downstream_components(data, key, component):
    """Keep operator boundary (wellheads after chokes), not legacy full-bore totals."""
    data = data or {}
    segments, wells = data.get("segments", []), data.get("wells", [])
    title = {
        "pipes": "От БГ до устьев",
        "wells": "Штуцирование нагнетательных скважин",
        "pipes_loss": "Трение и местные сопротивления до устьев",
        "friction_loss": "Трение в трубопроводах",
        "local_loss": "Местные сопротивления",
        "choke_loss": "Штуцирование скважин",
        "bore_loss": "Трение в стволах скважин",
    }[key]
    rows = []
    if key in {"pipes", "pipes_loss"}:
        for child_key, name, values in (
            ("friction_loss", "Трение в трубопроводах", [p.get("power_kw") for p in segments]),
            ("local_loss", "Местные сопротивления", [w.get("armature_loss_kw") for w in wells]),
        ):
            power = sum(values) if values and all(v is not None for v in values) else None
            rows.append(
                component(
                    child_key,
                    name,
                    power,
                    "assumed",
                    "Σ Q_i·Δp_i/3,6",
                    "Сумма расчётных сопротивлений соответствующих участков",
                    "Граница до устьев; штуцирование отдельно. Достижимость сетевого режима "
                    "проверяется независимо от известных сопротивлений.",
                    [],
                )
            )
    elif key == "friction_loss":
        for part in segments:
            source = (
                f"{part['source_sheet']}, строка {part['source_row']}"
                if part.get("source_sheet")
                else "Сетевой сценарий"
            )
            values = [
                {
                    "key": name,
                    "label": label,
                    "value": part.get(name),
                    "unit": unit,
                    "origin": "assumed",
                    "source": source,
                }
                for name, label, unit in (
                    ("length_m", "Длина", "м"),
                    ("inner_diameter_mm", "Внутренний диаметр", "мм"),
                    ("flow_m3h", "Сценарный расход", "м³/ч"),
                    ("pressure_loss_mpa", "Потеря давления Darcy–Weisbach", "МПа"),
                )
            ]
            rows.append(
                component(
                    "segment:" + str(part["id"]),
                    str(part.get("name") or part["id"]),
                    part["power_kw"],
                    "assumed",
                    "ΔP_i=Q_i·Δp_Darcy–Weisbach/3,6",
                    f"{_n(part['flow_m3h'])}·{_n(part['pressure_loss_mpa'])}/3,6",
                    part.get("basis", "Сценарный расчёт сопротивления"),
                    values,
                )
            )
    else:
        field = (
            "armature_loss_kw"
            if key == "local_loss"
            else "well_loss_kw"
            if key == "bore_loss"
            else "choke_loss_kw"
        )
        for well in wells:
            values = [
                {
                    "key": "q",
                    "label": "Сценарная подача в скважину",
                    "value": well["flow_m3h"],
                    "unit": "м³/ч",
                    "origin": "assumed",
                    "source": "Распределение расхода сценария, не замер по скважине",
                }
            ]
            power = well.get(field)
            dp = (
                power * 3.6 / well["flow_m3h"]
                if power is not None and well["flow_m3h"] > 0
                else None
            )
            rows.append(
                component(
                    "well:" + str(well["id"]),
                    str(well["id"]),
                    power,
                    "assumed",
                    "ΔP_i=Q_i·Δp_i/3,6",
                    f"{_n(well['flow_m3h'])}·{_n(dp)}/3,6",
                    "Синтетическое распределение расхода и сопротивлений; "
                    "не отдельное измерение потерь.",
                    values,
                )
            )
    boundary = (
        "До устьев после штуцеров"
        if key != "bore_loss"
        else "Стволы скважин; вне баланса до устьев"
    )
    return rows, title, boundary
