"""Addressed review rules from A-2026-023, not autonomous operating instructions.

Bindings require object + aggregate + exact pump model. Unconfirmed working zones,
curves and ambiguous source units are visible but cannot generate recommendations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import yaml

from ..config import project_root
from ..core.audit import AuditResult
from .result_scope import ResultScope
from .telemetry_quality import TelemetryQuality


RuleStatus = Literal[
    "triggered", "clear", "insufficient_data", "pending_confirmation", "not_applicable"
]
Category = Literal["data_check", "operating_deviation", "inspection"]


@dataclass(frozen=True)
class RuleSource:
    artifact_id: str
    file: str
    sha256: str
    sheet: str
    cells: str


@dataclass(frozen=True)
class Evidence:
    key: str
    label: str
    value: float | None
    unit: str
    basis: str


@dataclass(frozen=True)
class DiagnosticRule:
    id: str
    title: str
    category: Category
    status: RuleStatus
    condition: str
    evidence: tuple[Evidence, ...]
    reason: str
    action: str
    source: RuleSource


@dataclass(frozen=True)
class DiagnosticReport:
    object_id: str
    aggregate_id: str
    pump_model: str
    binding_status: Literal["matched", "pending_confirmation", "model_mismatch", "not_applicable"]
    note: str
    rules: tuple[DiagnosticRule, ...]


@dataclass(frozen=True)
class _Rule:
    id: str
    title: str
    category: Category
    condition: str
    action: str = ""
    confirmation: str = ""


@lru_cache(maxsize=1)
def _catalog() -> dict:
    return yaml.safe_load((project_root() / "config" / "diagnostics.yaml").read_text())


def _model_key(model: str) -> str:
    return model.replace(" ", "").replace("(", "").replace(")", "").casefold()


def _definitions(profile: dict) -> tuple[_Rule, ...]:
    zone = (
        "Рабочая область из таблицы требует сверки с паспортом; "
        "область аппроксимации её не заменяет."
    )
    curve = "Нет подтверждённой характеристики для установленного исполнения, частоты и диапазона."
    return (
        _Rule(
            "flow_low",
            "Подача ниже рабочей области",
            "operating_deviation",
            f"Q < {profile['flow_min']:g} м³/ч",
            confirmation=zone,
        ),
        _Rule(
            "flow_high",
            "Подача выше рабочей области",
            "operating_deviation",
            f"Q > {profile['flow_max']:g} м³/ч",
            confirmation=zone,
        ),
        _Rule(
            "head_low", "Напор ниже должного", "inspection", "Hф < 0,9 × Hдолжн", confirmation=curve
        ),
        _Rule(
            "head_high",
            "Напор выше должного",
            "data_check",
            "Hф > 1,05 × Hдолжн",
            confirmation=curve,
        ),
        _Rule(
            "pressure_drop_high",
            "Перепад насос–БГ",
            "operating_deviation",
            "pвых − pБГ > 20 атм",
            confirmation=(
                "В источнике не уточнён вид атмосферы; перевод порога в МПа не подтверждён."
            ),
        ),
        _Rule(
            "pressure_order",
            "Согласованность давлений БГ и насоса",
            "data_check",
            "pБГ > pвых",
            "Проверьте датчики, единицы и синхронность давлений. "
            "Не меняйте положение арматуры по этому признаку.",
        ),
        _Rule(
            "daily_efficiency_high",
            "Среднесуточный КПД выше номинального",
            "data_check",
            "ηНА среднесуточный > ηном",
            "Проверьте суточные гидравлические и электрические измерения и паспортные КПД.",
        ),
        _Rule(
            "specific_energy_low",
            "Фактический УРЭ ниже расчётного",
            "data_check",
            "УРЭф < УРЭр",
            "Проверьте основание УРЭ, давления, расход, энергию и паспортные значения. "
            "Это не диагноз неисправности.",
        ),
        _Rule(
            "motor_underload",
            "Низкая загрузка электродвигателя",
            "operating_deviation",
            "Kз < 0,5",
            "Проверьте загрузку на сопоставимых режимах и соответствие мощности ЭД. "
            "Замена требует технического обследования и расчёта.",
        ),
        _Rule(
            "motor_overload",
            "Перегрузка электродвигателя",
            "operating_deviation",
            "Kз > 1",
            "Проверьте измеренную мощность и паспорт ЭД; оцените режим "
            "с ответственным специалистом. Автоматический подбор замены не выполняется.",
        ),
        _Rule(
            "pump_efficiency_low",
            "КПД насоса ниже должного",
            "inspection",
            "ηнас ниже ηдолжн более чем на 5%",
            confirmation=(
                f"{curve} Нужно уточнить: 5% относительного отклонения или процентных пунктов."
            ),
        ),
        _Rule(
            "annual_throttle_loss",
            "Годовые потери на дросселирование",
            "inspection",
            "ΔWдр > 0 кВт·ч/год",
            "Проверьте причины перепада насос–БГ и возможность изменения режима. "
            "Не открывайте задвижку без проверки технологических ограничений.",
        ),
        _Rule(
            "annual_efficiency_loss",
            "Годовые потери по КПД",
            "inspection",
            "ΔWкпд > 0 кВт·ч/год",
            "Проверьте достоверность режима и причины отклонения КПД. "
            "Положительные потери сами по себе не доказывают износ "
            "или необходимость капремонта.",
        ),
        _Rule(
            "suboptimal_flow_loss",
            "Потери из-за неоптимальной подачи",
            "inspection",
            "ΔPнеопт > 0 кВт",
            confirmation=curve,
        ),
    )


def diagnose_aggregate(
    object_id: str,
    audit: AuditResult,
    scope: ResultScope,
    quality: TelemetryQuality | None,
) -> DiagnosticReport:
    aggregate = audit.spec
    model = aggregate.pump.model if aggregate else ""
    catalog = _catalog()
    profile = catalog["profiles"].get(object_id, {}).get(audit.aggregate_id)
    if profile is None or aggregate is None:
        return DiagnosticReport(
            object_id,
            audit.aggregate_id,
            model,
            "not_applicable",
            "В источнике нет привязки правил к этому объекту и агрегату; "
            "это не оценка исправности.",
            (),
        )
    binding_status: Literal["matched", "pending_confirmation", "model_mismatch"] = "matched"
    binding_note = profile.get("binding_note", "")
    if _model_key(model) != _model_key(profile["model"]) or audit.pump_kind != "центробежный":
        binding_status = "model_mismatch"
        binding_note = (
            f"Источник относится к {profile['model']}; текущая модель {model}. "
            "Правила не переносятся на другое оборудование."
        )
    elif binding_note:
        binding_status = "pending_confirmation"
    rm = aggregate.regime
    pressure_basis = (
        quality.basis.get("pressure", "Измеренный режим") if quality else "Измеренный режим"
    )
    power_basis = quality.basis.get("power", "Измеренный режим") if quality else "Измеренный режим"

    def evidence(key: str, label: str, value: float | None, unit: str, basis: str) -> Evidence:
        return Evidence(
            key, label, value if value is not None and math.isfinite(value) else None, unit, basis
        )

    q = evidence("q", "Подача", audit.regime.q, "м³/ч", "Подача выбранного режима")
    head = evidence("head", "Фактический напор", audit.regime.h_fact, "м", pressure_basis)
    due_head = evidence(
        "head_due",
        "Должный напор",
        audit.h_due,
        "м",
        "Расчётная характеристика; применимость не подтверждена",
    )
    p_bg = evidence("p_bg", "Давление БГ", rm.p_bg if rm else None, "МПа", pressure_basis)
    p_out = evidence("p_out", "Давление на выкиде", rm.p_out if rm else None, "МПа", pressure_basis)
    load = evidence(
        "load",
        "Коэффициент загрузки ЭД",
        audit.load_factor,
        "о.е.",
        f"{power_basis}; Kз = Pэл × ηЭД.ном / Pном",
    )
    power = evidence("power", "Мощность", audit.regime.p_electric, "кВт", power_basis)
    nominal_power = evidence(
        "motor_power_nom",
        "Номинальная мощность ЭД",
        aggregate.motor.p_nom,
        "кВт",
        "Паспорт выбранного агрегата",
    )
    nominal_eta = evidence(
        "motor_eta_nom",
        "Номинальный КПД ЭД",
        aggregate.motor.eta_nom,
        "о.е.",
        "Паспорт выбранного агрегата",
    )
    values = {
        "flow_low": (q,),
        "flow_high": (q,),
        "head_low": (head, due_head),
        "head_high": (head, due_head),
        "pressure_drop_high": (p_out, p_bg),
        "pressure_order": (p_bg, p_out),
        # The selected pressure snapshot does not determine a daily mean efficiency.
        "daily_efficiency_high": (
            evidence(
                "daily_eta", "Среднесуточный КПД", None, "о.е.", "Среднесуточный КПД не рассчитан"
            ),
            evidence(
                "eta_nom",
                "Номинальный КПД НА",
                audit.regime.eta_nom,
                "о.е.",
                "Паспорт выбранного агрегата",
            ),
        ),
        "specific_energy_low": (
            evidence(
                "sec_fact",
                "Фактический УРЭ",
                audit.sec_fact,
                "кВт·ч/м³",
                "Суточные W/Q" if scope.daily_kpi_is_fact else "Выбранный режим P/Q",
            ),
            evidence("sec_calc", "Расчётный УРЭ", audit.sec_calc, "кВт·ч/м³", pressure_basis),
        ),
        "motor_underload": (load, power, nominal_power, nominal_eta),
        "motor_overload": (load, power, nominal_power, nominal_eta),
        "pump_efficiency_low": (
            evidence(
                "eta_pump", "КПД насоса", audit.eta_pump, "о.е.", "Расчёт по выбранному режиму"
            ),
            evidence(
                "eta_due",
                "Подтверждённый должный КПД",
                None,
                "о.е.",
                "Нет подтверждённой характеристики",
            ),
        ),
        "annual_throttle_loss": (
            evidence(
                "dw_throttle",
                "Годовые потери",
                audit.dw_throttle,
                "кВт·ч/год",
                "Сценарная годовая оценка",
            ),
        ),
        "annual_efficiency_loss": (
            evidence(
                "dw_efficiency",
                "Годовые потери",
                audit.dw_efficiency,
                "кВт·ч/год",
                "Сценарная годовая оценка",
            ),
        ),
        "suboptimal_flow_loss": (
            evidence(
                "dp_suboptimal",
                "Потери неоптимальной подачи",
                None,
                "кВт",
                "Отдельная статья не рассчитана в ветке КНС",
            ),
        ),
    }
    bad_pressure = p_bg.value is not None and p_out.value is not None and p_bg.value > p_out.value
    blocked_quality = quality is not None and not quality.allows_economic_conclusions
    matches = {
        "pressure_order": bad_pressure,
        "specific_energy_low": audit.sec_calc is not None and audit.sec_fact < audit.sec_calc,
        "motor_underload": audit.load_factor is not None and audit.load_factor < 0.5,
        "motor_overload": audit.load_factor is not None and audit.load_factor > 1,
        "annual_throttle_loss": (audit.dw_throttle or 0) > 0,
        "annual_efficiency_loss": audit.dw_efficiency is not None and audit.dw_efficiency > 0,
    }
    results = []
    for number, rule in enumerate(_definitions(profile)):
        row = profile["first_row"] + number
        source = RuleSource(**catalog["source"], sheet=profile["sheet"], cells=f"A{row}:F{row}")
        inputs = values[rule.id]
        status: RuleStatus = "clear"
        reason = (
            "Условие этого правила не обнаружено; это не заключение об исправности оборудования."
        )
        action = ""
        if binding_status != "matched":
            status, reason = "pending_confirmation", binding_note
        elif rule.confirmation:
            status, reason = "pending_confirmation", rule.confirmation
        elif any(item.value is None for item in inputs):
            status, reason = (
                "insufficient_data",
                "Нет всех необходимых данных на сопоставимом основании.",
            )
        elif rule.category != "data_check" and (blocked_quality or bad_pressure):
            status, reason = (
                "insufficient_data",
                "Сначала проверьте противоречия и качество исходных данных; "
                "режимные рекомендации заблокированы.",
            )
        elif rule.id == "specific_energy_low" and scope.daily_kpi_is_fact:
            status, reason = (
                "insufficient_data",
                "Суточный W/Q нельзя сопоставлять с расчётным УРЭ по одному снимку давления.",
            )
        elif rule.id.startswith("annual_") and scope.annual_runtime_is_assumed:
            status, reason = (
                "insufficient_data",
                "Годовая наработка принята как допущение; годовой эффект не подтверждён.",
            )
        else:
            triggered = matches[rule.id]
            if triggered:
                status = "triggered"
                reason = "Обнаружен признак для проверки, а не установленная причина неисправности."
                action = rule.action
        results.append(
            DiagnosticRule(
                rule.id,
                rule.title,
                rule.category,
                status,
                rule.condition,
                inputs,
                reason,
                action,
                source,
            )
        )
    return DiagnosticReport(
        object_id,
        audit.aggregate_id,
        model,
        binding_status,
        binding_note
        or (
            "Правила относятся только к выбранному агрегату и режиму. "
            "Не являются командами управления или автоматическим решением о замене."
        ),
        tuple(results),
    )


def rule_catalog() -> dict:
    """Правила и привязки к агрегатам для справочника — без расчёта режима."""
    catalog = _catalog()
    flow = {"flow_low": "Q < Q_мин рабочей области", "flow_high": "Q > Q_макс рабочей области"}
    rules = [
        {
            "id": rule.id,
            "title": rule.title,
            "category": rule.category,
            "condition": flow.get(rule.id, rule.condition),
            "action": rule.action,
            "confirmation": rule.confirmation,
        }
        for rule in _definitions({"flow_min": 0.0, "flow_max": 0.0})
    ]
    bindings = [
        {
            "object_id": object_id,
            "aggregate_id": aggregate_id,
            "model": profile["model"],
            "sheet": profile["sheet"],
            "flow_min": profile["flow_min"],
            "flow_max": profile["flow_max"],
            "note": profile.get("binding_note", ""),
        }
        for object_id, aggregates in catalog["profiles"].items()
        for aggregate_id, profile in aggregates.items()
    ]
    return {"source": catalog["source"], "rules": rules, "bindings": bindings}
