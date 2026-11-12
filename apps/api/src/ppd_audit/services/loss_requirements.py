"""Shared, calculation-specific requirements; presence is not source confirmation."""

from __future__ import annotations

import math

from ..core.audit import ETA_VFD_DEFAULT, AuditResult
from ..spec import AggregateSpec


EQUIPMENT_REQUIREMENTS = (
    ("pump.model", "Модель и исполнение насоса", "", ["Идентификация оборудования"]),
    ("pump.q_nom", "Номинальная подача насоса", "м³/ч", ["Проверка рабочей точки"]),
    ("pump.h_nom", "Номинальный напор насоса", "м", ["Проверка рабочей точки"]),
    ("pump.eta_nom", "Номинальный КПД насоса", "доля", ["Отклонение от номинального КПД"]),
    (
        "pump.n_rpm",
        "Частота вращения насоса",
        "об/мин",
        ["Применимость характеристики", "Уставки ПЧ"],
    ),
    (
        "motor.p_nom",
        "Номинальная мощность ЭД",
        "кВт",
        ["Потери ЭД", "Потери передачи", "Потери насоса"],
    ),
    (
        "motor.eta_nom",
        "Номинальный КПД ЭД",
        "доля",
        ["Потери ЭД", "Потери передачи", "Потери насоса"],
    ),
    ("motor.synchronous", "Синхронный тип ЭД", "", ["КПД ЭД по загрузке"]),
    ("transmission.efficiency", "КПД передачи", "доля", ["Потери передачи", "Потери насоса"]),
    ("vfd", "Наличие ПЧ", "", ["Потери ПЧ", "Распределение потерь машинного блока"]),
)
REGIME_REQUIREMENTS = (
    ("p_in", "Давление на приёме", "МПа", ["Баланс машинного блока"]),
    ("p_out", "Давление на выкиде", "МПа", ["Потери насоса", "Перепад насос–БГ"]),
    (
        "p_bg",
        "Давление БГ той же гидравлической группы",
        "МПа",
        ["Баланс до БГ", "Перепад насос–БГ"],
    ),
    ("q_fact", "Режимная подача", "м³/ч", ["Гидравлическая мощность", "Проверка рабочей точки"]),
    ("p_electric", "Режимная активная электрическая мощность", "кВт", ["Баланс машинного блока"]),
    ("rho", "Плотность жидкости", "кг/м³", ["Перевод давления в напор"]),
    ("t_year", "Годовая наработка для сценарной оценки", "ч", ["Годовая энергия и стоимость"]),
)
HALL_REQUIREMENT_KEYS = {
    "motor.p_nom",
    "motor.eta_nom",
    "transmission.efficiency",
    "vfd",
    "vfd.efficiency",
    "motor.synchronous",
    "regime.p_in",
    "regime.p_out",
    "regime.p_bg",
    "regime.q_fact",
    "regime.p_electric",
    "regime.t_year",
    "hall.geometry",
    "regime.consistency",
}


def _entry(key, label, value, unit, status, reason, affects, action):
    labels = {
        "equipment": "Открыть журнал оборудования",
        "network": "Проверить сведения о сети",
        "review": "Проверить первичные сведения",
    }
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "status": status,
        "reason": reason,
        "affects": affects,
        "action": action,
        "action_label": labels[action],
    }


def data_requirements(
    aggregate: AggregateSpec,
    *,
    audit: AuditResult | None = None,
    provenance: dict | None = None,
    scenario: bool = False,
    network: dict | None = None,
) -> list[dict]:
    """Same requirements power both a selected loss and readiness without telemetry."""
    confirmed = set((provenance or {}).get("confirmed_fields", []))
    field_sources = (provenance or {}).get("field_sources", {})
    estimated_fields = {
        key for key, origin in field_sources.items() if origin.get("evidence") == "estimate"
    }
    result = []
    for key, label, unit, affects in EQUIPMENT_REQUIREMENTS:
        value = aggregate
        for part in key.split("."):
            value = getattr(value, part, None)
        field_source = field_sources.get(key, {})
        if not scenario and field_source.get("reset"):
            value = None
        missing = value is None or isinstance(value, str) and not value.strip()
        is_confirmed = (
            key in confirmed and key not in estimated_fields and bool(field_source.get("source"))
        )
        status = (
            "missing"
            if missing
            else "assumed"
            if scenario or key in estimated_fields
            else "ready"
            if is_confirmed
            else "pending_confirmation"
        )
        reason = (
            "Значение не предоставлено."
            if missing
            else "Временное допущение сценария; паспорт не изменён."
            if scenario
            else f"Оценка специалиста; источник: {field_source.get('source', 'не указан')}."
            if key in estimated_fields
            else f"Подтверждено пользователем; источник: {field_source['source']}."
            if is_confirmed
            else "Значение есть, но подтверждение именно этого параметра "
            "по источнику не зафиксировано."
        )
        result.append(_entry(key, label, value, unit, status, reason, affects, "equipment"))
    pump = aggregate.pump
    source = pump.curve_source
    binding = bool(
        source
        and source.verified
        and source.model
        and source.model.replace(" ", "").casefold() == pump.model.replace(" ", "").casefold()
        and source.speed_rpm is not None
        and pump.n_rpm is not None
        and math.isclose(source.speed_rpm, pump.n_rpm, rel_tol=1e-6)
    )
    ch = audit.characteristic if audit else None
    for key, label, points, status_key in (
        (
            "pump.curve_qh",
            "Характеристика Q–H установленного исполнения",
            pump.curve_qh,
            "qh_status",
        ),
        (
            "pump.curve_qeta",
            "Характеристика Q–η установленного исполнения",
            pump.curve_qeta,
            "qeta_status",
        ),
    ):
        status = (
            "missing"
            if len(points) < 3
            else "assumed"
            if scenario or key in estimated_fields
            else "ready"
            if binding and (ch is None or getattr(ch, status_key) == "within_range")
            else "pending_confirmation"
        )
        reason = (
            "Нужно не менее трёх исходных точек в известных единицах."
            if len(points) < 3
            else "Точки временного сценария не подтверждают установленное оборудование."
            if scenario
            else "Оценочные точки, не подтверждённая характеристика установленного насоса."
            if key in estimated_fields
            else "Источник и привязка подтверждены; экстраполяция запрещена."
            if status == "ready"
            else "Точки есть, но исполнение, обороты либо охват текущей подачи не подтверждены."
        )
        result.append(
            _entry(
                key,
                label,
                points or None,
                "м³/ч; м" if key.endswith("qh") else "м³/ч; доля",
                status,
                reason,
                ["Проверка рабочей точки", "Уставки ПЧ"],
                "equipment",
            )
        )
    source_status = (
        "assumed"
        if scenario or "pump.curve_source" in estimated_fields
        else "ready"
        if binding
        else "missing"
        if source is None
        else "pending_confirmation"
    )
    result.append(
        _entry(
            "pump.curve_source",
            "Источник и применимость характеристик",
            source.model_dump(mode="json") if source else None,
            "",
            source_status,
            "Наличие кривой не подтверждает её применимость. "
            "Нужны источник, исполнение, обороты и явная проверка привязки.",
            ["Диагностика по характеристике", "Уставки ПЧ"],
            "equipment",
        )
    )
    if aggregate.vfd:
        frequency = source.frequency_hz if source else None
        result.append(
            _entry(
                "pump.curve_source.frequency_hz",
                "Частота питания исходной характеристики",
                frequency,
                "Гц",
                "ready"
                if frequency is not None and binding and not scenario
                else "missing"
                if frequency is None
                else "pending_confirmation",
                "Предельная частота ПЧ не заменяет частоту исходной характеристики.",
                ["Уставки ПЧ"],
                "equipment",
            )
        )
        result.append(
            _entry(
                "vfd.efficiency",
                "КПД ПЧ в расчётной модели",
                ETA_VFD_DEFAULT,
                "доля",
                "assumed",
                "Методика принимает 0,97; отдельного измерения потерь ПЧ нет. "
                "Это допущение, не паспортное подтверждение.",
                ["Потери ПЧ", "Потери ЭД", "Потери передачи", "Потери насоса"],
                "review",
            )
        )
    rm = aggregate.regime
    for key, label, unit, affects in REGIME_REQUIREMENTS:
        value = getattr(rm, key, None)
        status = "missing" if value is None else "ready"
        reason = (
            "Значение не предоставлено для выбранного режима."
            if value is None
            else "Значение выбранного режима; не переносится с другого времени или агрегата."
        )
        if key == "t_year" and value is None and audit is not None:
            value = audit.annual_runtime_hours
            status = "assumed" if audit.annual_runtime_is_assumed else "ready"
            reason = (
                "Приняты сценарные 8760 ч, не измеренная годовая наработка."
                if audit.annual_runtime_is_assumed
                else "Годовая база явно задана в исходных сведениях режима."
            )
        elif key == "q_fact" and value is None and audit is not None:
            reason += (
                " Для показанного расчёта Q получена из суточного объёма и наработки; "
                "это не мгновенная подача."
            )
        elif key == "p_electric" and value is None and audit is not None:
            reason += (
                " Для показанного расчёта использована средняя W/T; это не мгновенная мощность."
            )
        result.append(
            _entry("regime." + key, label, value, unit, status, reason, affects, "review")
        )
    conflict = None
    if audit is not None:
        r = audit.regime
        if r.p_hydraulic > r.p_electric + 1e-6:
            conflict = (
                "Гидравлическая мощность выше электрической: "
                "проверить единицы и одновременность измерений."
            )
        elif r.p_hydraulic < 0:
            conflict = (
                "Отрицательный прирост давления: насосный режим "
                "для принятой границы баланса не подтверждён."
            )
        elif r.p_bg is not None and r.p_bg > r.p_out:
            conflict = (
                "Давление БГ выше выкида; разложение на неотрицательные потери не подтверждено."
            )
        elif r.p_bg is not None and r.p_bg < r.p_in:
            conflict = (
                "БГ ниже давления приёма: нужен отдельный учёт входящей гидравлической "
                "энергии для этой границы баланса."
            )
    if conflict:
        result.append(
            _entry(
                "regime.consistency",
                "Согласованность режима",
                None,
                "",
                "conflict",
                conflict,
                ["Баланс машинного блока"],
                "measurement",
            )
        )
    if (
        audit is not None
        and audit.eta_motor_real is not None
        and aggregate.transmission.efficiency is not None
    ):
        eta = (
            audit.eta_motor_real
            * aggregate.transmission.efficiency
            * (ETA_VFD_DEFAULT if aggregate.vfd else 1.0)
        )
        if (
            not math.isfinite(eta)
            or not 0 < eta <= 1
            or audit.regime.p_hydraulic > audit.regime.p_electric * eta + 1e-6
        ):
            result.append(
                _entry(
                    "equipment.consistency",
                    "Согласованность КПД привода с режимом",
                    eta,
                    "доля",
                    "conflict",
                    "Модельная мощность вала ниже гидравлической либо КПД привода недопустим. "
                    "Распределение между ЭД, передачей и насосом не подтверждено; "
                    "общий перепад из измерений остаётся доступен.",
                    ["Распределение потерь по оборудованию"],
                    "equipment",
                )
            )
    result.append(
        _entry(
            "hall.geometry",
            "Высотные отметки и сечения насос–БГ",
            None,
            "",
            "missing",
            "Без отметок датчиков и сечений показан эквивалент перепада давления; "
            "высотная и скоростная составляющие не отделены от диссипативных потерь.",
            ["Физическая трактовка перепада насос–БГ"],
            "review",
        )
    )
    geometry = bool(network and network.get("segments"))
    wrong_group = bool(
        network
        and network.get("technical_place_code") not in (None, aggregate.technical_place_code)
    )
    result.append(
        _entry(
            "network.geometry",
            "Геометрия, арматура и расходы по ветвям сети",
            len(network["segments"]) if geometry else None,
            "участков",
            "conflict" if wrong_group else "pending_confirmation" if geometry else "missing",
            "Реестр сети относится к другой гидравлической группе агрегатов."
            if wrong_group
            else "Сетевой реестр ещё не означает одновременный измеренный баланс: "
            "нужны подтверждённые единицы, соединения, расходы и сопротивления.",
            ["Трение по отдельным трубам", "Местные сопротивления"],
            "network",
        )
    )
    return result
