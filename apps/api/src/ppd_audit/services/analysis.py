"""Общие расчётные представления для API и frontend; без UI-зависимостей."""

from dataclasses import asdict

import numpy as np

from ..config import load_constraints
from ..measures import InjectionProfile, suggest_measures, suggest_measures_over_horizon
from ..optimize import optimize_setpoint


def efficiency_assessment(actual, nominal):
    """Прежние границы оценки КПД относительно паспортного значения."""
    if nominal is None:
        return {"name": "Паспортный КПД не подтверждён", "tone": "warn"}
    ratio = actual / nominal
    if ratio >= 0.9:
        return {"name": "норма", "tone": "ok"}
    if ratio >= 0.78:
        return {"name": "пониженный КПД", "tone": "warn"}
    return {"name": "низкий КПД", "tone": "bad"}


def pump_qh_curve(p):
    """Исходные точки либо явно оценочная парабола без паспортного статуса."""
    if p.curve_qh:
        points = sorted(p.curve_qh)
        return [c[0] for c in points], [c[1] for c in points], True
    if p.kind.value == "объёмный" or not (p.q_nom and p.h_nom):
        return None
    h0 = 1.22 * p.h_nom
    qs = np.linspace(0, 1.5 * p.q_nom, 41)
    return qs, h0 - (h0 - p.h_nom) / p.q_nom**2 * qs**2, False


def system_curve(q_work, h_fact, p_in, p_bg, rho, q_nom):
    """Оценочная характеристика трубопровода через рабочую точку."""
    if not q_work or h_fact is None:
        return None
    h_st = ((p_bg - p_in) * 1e6 / (rho * 9.81)) if (p_bg and p_bg > p_in) else 0.35 * h_fact
    h_st = max(0.0, min(h_st, 0.95 * h_fact))
    qs = np.linspace(0, 1.5 * (q_nom or q_work), 41)
    return qs, h_st + (h_fact - h_st) / q_work**2 * qs**2


def working_point(audit):
    p = audit.spec.pump
    rm = audit.spec.regime
    reg = audit.regime
    volumetric = p.kind.value == "объёмный"
    q = rm.flow()
    pc = pump_qh_curve(p)
    sc = None if volumetric else system_curve(q, reg.h_fact, rm.p_in, rm.p_bg, rm.rho, p.q_nom)
    qe = []
    source_origin = p.curve_source.kind if p.curve_source is not None else "unverified"
    origin = {
        "qh": source_origin if pc and pc[2] else "model" if pc else "unavailable",
        "qeta": "unavailable",
        "system": "model" if sc else "unavailable",
    }
    if p.curve_qeta:
        qe = [{"q": v[0], "eta": v[1]} for v in sorted(p.curve_qeta)]
        origin["qeta"] = source_origin
    elif p.q_nom and p.eta_nom and not volumetric:
        qe = [
            {"q": float(v), "eta": float(p.eta_nom * (1 - 0.9 * ((v - p.q_nom) / p.q_nom) ** 2))}
            for v in np.linspace(0.2 * p.q_nom, 1.4 * p.q_nom, 31)
        ]
        origin["qeta"] = "model"
    notes = []
    if audit.characteristic is not None:
        notes.extend(audit.characteristic.notes)
    if volumetric:
        notes.append(
            "Объёмный насос: модельные Q-H и характеристика трубопровода неприменимы; "
            "показаны фактические точки."
        )
    if "model" in origin.values():
        notes.append(
            "Модельные кривые — оценочные, не паспортные; "
            "не используются для диагностики должного напора."
        )
    return {
        "qh": [{"q": float(qv), "h": float(h)} for qv, h in zip(pc[0], pc[1], strict=True)]
        if pc
        else [],
        "qeta": qe,
        "system": [{"q": float(qv), "h": float(h)} for qv, h in zip(sc[0], sc[1], strict=True)]
        if sc
        else [],
        "point": {"q": q, "h": reg.h_fact, "eta": reg.eta_unit, "eta_pump": audit.eta_pump},
        "nominal": {
            "q": None if volumetric else p.q_nom,
            "h": None if volumetric else p.h_nom,
            "eta": None if volumetric else p.eta_nom,
        },
        "due": {
            "h": audit.h_due,
            "eta": audit.eta_pump_due,
        },
        "origin": origin,
        "notes": notes,
        "characteristic": asdict(audit.characteristic)
        if audit.characteristic is not None
        else None,
        "curve_source": p.curve_source.model_dump(mode="json") if p.curve_source else None,
        "ranges": {
            name: [min(point[0] for point in points), max(point[0] for point in points)]
            if points
            else None
            for name, points in (("qh", p.curve_qh), ("qeta", p.curve_qeta))
        },
        "pump_kind": p.kind.value,
    }


def base_annual_injection(audit, scope):
    return float(audit.regime.q) * float(scope.annual_runtime_hours)


def annual_summary(audit, tariff):
    """Годовые потери и стоимость по одному расчётному основанию."""
    return {
        "efficiency_energy_kwh": audit.dw_efficiency,
        "efficiency_money_krub": audit.dw_efficiency * tariff / 1000
        if audit.dw_efficiency is not None
        else None,
        "throttle_energy_kwh": audit.dw_throttle,
        "throttle_money_krub": audit.dw_throttle * tariff / 1000
        if audit.dw_throttle is not None
        else None,
    }


def measure_analysis(
    audit,
    scope,
    tariff,
    profile,
    *,
    horizon_years=3,
    discount_rate=0.15,
    basis="annual",
    quality=None,
    constraints=None,
):
    if quality is not None and not quality.allows_economic_conclusions:
        raise ValueError("Выбранный режим непригоден для экономических выводов.")
    notes = [
        "Сценарные оценки требуют диагностики; CAPEX типовой, результаты не являются проектным ТЭО."
    ]
    horizon = []
    optimized = None
    if basis == "forecast":
        if profile is None:
            profile = InjectionProfile.flat(base_annual_injection(audit, scope), horizon_years)
            notes.append(
                "Прогноз закачки не построен: мало данных. "
                "Экономика посчитана при постоянном объёме закачки."
            )
        horizon = suggest_measures_over_horizon(
            audit, profile, tariff=tariff, discount_rate=discount_rate
        )
    opt = optimize_setpoint(audit, constraints or load_constraints())
    if (
        basis == "forecast"
        and profile is not None
        and opt.status == "validated"
        and (opt.saving_kwh_year or 0) > 0
    ):
        total = opt.saving_kwh_year * sum(profile.ratios())
        optimized = {"energy_kwh": total, "money_krub": total * tariff / 1000.0}
    if scope.annual_runtime_is_assumed:
        notes.append(
            "Годовая наработка принята равной 8760 ч; фактическая наработка требует уточнения."
        )
    return {
        "annual": [asdict(v) for v in suggest_measures(audit, tariff)],
        "profile": asdict(profile) if basis == "forecast" else None,
        "horizon": [asdict(v) for v in horizon],
        "setpoint": asdict(opt),
        "optimized_horizon": optimized,
        "notes": notes,
        "scope": asdict(scope),
        "tariff": tariff,
    }


# Требуемая телеметрия (Методика энергоаудита, Таблица 8.2.1).
TELEMETRY_REQUIREMENTS = [
    ("Годовой объём перекачки", "Q_год", "м³", "обязательно", "УУЖ / расчёт"),
    ("Годовая наработка", "T_год", "ч", "обязательно", "журнал состояний"),
    ("Суточный расход жидкости", "Q_сут", "м³", "обязательно", "телеметрия (УУЖ)"),
    ("Время работы за сутки", "T", "ч", "обязательно", "журнал / телеметрия"),
    ("Подача мгновенная", "Q", "м³/ч", "желательно", "телеметрия"),
    ("Давление на приёме", "p_вх", "МПа", "обязательно", "датчик давления"),
    ("Давление на выкиде", "p_вых", "МПа", "обязательно", "датчик давления"),
    ("Плотность жидкости", "ρ", "кг/м³", "обязательно", "замер / тип воды"),
    ("Расход ЭЭ за сутки", "W", "кВт·ч", "обязательно", "счётчик ЭЭ"),
    ("Активная мощность", "P_эл", "кВт", "желательно", "счётчик ЭЭ"),
    ("Давление на БГ (для КНС)", "p_БГ", "МПа", "для КНС", "телеметрия гребёнки"),
    ("Вязкость (перекачка нефти)", "ν", "сСт", "для нефти", "лаборатория"),
    ("Диаметр выкидной трубы", "D", "мм", "для нефти/вязкости", "паспорт трубы"),
    ("Толщина стенки трубы", "d", "мм", "для нефти/вязкости", "паспорт трубы"),
]

YAML_TEMPLATE = """\
# config/plants/<id>.yaml — паспорт + режим объекта.
# Временный начальный ввод паспортов и выездных режимов вручную.
# Приложение регистрирует объект из файла; телеметрия и версии паспортов
# хранятся в БД. Выездной расчёт пока читает режим из этого YAML.
# `id` должен совпадать с именем файла.
id: kns_new
name: КНС-XXX
ngdu: НГДУ-XXX            # обязательно: без подтверждённого НГДУ объект не регистрируется
operator_visible: true    # false — исторический справочник, скрыт из каталога оператора
water_type: пресная        # пресная | агрессивная | пластовая
branch: кнс                # кнс | перекачка
# source необязателен: достаточно понятного происхождения, например:
# source: Паспорт изготовителя и контрольный замер
aggregates:
  - id: НА-1
    role: работа           # работа | резерв
    pump:
      model: ЦНС-180-1422
      kind: центробежный    # центробежный | объёмный
      q_nom: 180.0
      h_nom: 1422.0
      eta_nom: 0.72
      power_nom: 1250.0
      n_rpm: 3000.0
      curve_qh: []          # [[Q,H], ...] из паспорта (опц.) — включает диагностику (29)
      curve_qeta: []        # [[Q,eta], ...] (опц.) — уточняет η_д (30)
    motor:
      model: СТД-1250
      synchronous: true     # СТД/СДН — синхронные (α=2 в формуле 26)
      p_nom: 1250.0
      eta_nom: 0.95
      cos_phi: 0.9
      voltage_kv: 6.0
    transmission:
      efficiency: 1.0       # η_ред/ременная передача (у плунжерных СИН ~0,97)
    vfd: false              # при ПЧ: true → η_пч=0,97 в (15)/(27)
    regime:                 # отдельный контрольный замер
      measured_at: 2026-04-09
      rho: 1130.0
      p_in: 0.8
      p_out: 14.0
      p_bg: 13.5
      q_day: 4000.0
      t: 24.0
      w: 60000.0
      t_year: 8000.0
"""


MANUAL_REQUIREMENTS = [
    "Насос: модель, тип, Q_ном, H_ном, η_нас.ном, P_ном, n и кривые Q-H/Q-η из паспорта.",
    "Электродвигатель: модель, P_ном, η_ЭД.ном, cos φ, U, синхронный/асинхронный.",
    "ПЧ и трансмиссия: наличие ПЧ и КПД трансмиссии.",
    "Жидкость: ρ и ν по замеру; значения по умолчанию из config/fluids.yaml.",
    "Источник можно указать кратко в source: паспорт изготовителя, контрольный "
    "замер или ручной ввод. Ссылка на отчёт и адреса ячеек не обязательны.",
]


def onboarding(aggregate):
    rm = aggregate.regime
    p = aggregate.pump
    m = aggregate.motor
    checks = [
        (label, getattr(rm, key, None))
        for label, key in [
            ("Телеметрия: p_вх", "p_in"),
            ("Телеметрия: p_вых", "p_out"),
            ("Телеметрия: p_БГ (КНС)", "p_bg"),
            ("Телеметрия: Q_сут", "q_day"),
            ("Телеметрия: W (ЭЭ/сут)", "w"),
            ("Телеметрия: T (наработка)", "t"),
            ("Плотность ρ", "rho"),
        ]
    ]
    checks += [
        ("Паспорт насоса: H_ном", p.h_nom),
        ("Паспорт насоса: Q_ном", p.q_nom),
        ("Паспорт насоса: η_ном", p.eta_nom),
        ("Кривая Q-H", p.curve_qh or None),
        ("Паспорт ЭД: P_ном", m.p_nom),
        ("Паспорт ЭД: η_ном", m.eta_nom),
    ]
    return {
        "telemetry_requirements": [
            dict(zip(("parameter", "symbol", "unit", "requirement", "source"), row, strict=True))
            for row in TELEMETRY_REQUIREMENTS
        ],
        "manual_requirements": MANUAL_REQUIREMENTS,
        "checks": [{"field": k, "present": bool(v), "value": v} for k, v in checks],
        "yaml_template": YAML_TEMPLATE,
        "notes": [
            "Часть полей опциональна: объёмные насосы и объекты без Q-H "
            "считаются по своей ветке расчёта.",
            "Новый объект регистрируется из config/plants/<id>.yaml при запуске "
            "приложения: уже записанные в БД паспорта и правки оператора не "
            "перезаписываются.",
        ],
    }


def loss_components(audit) -> tuple[float, list[tuple[str, float]]]:
    """(полезная мощность, [(подпись потери, кВт)]). Сумма = P_эл."""
    d = audit.decomposition
    if d is None:
        return audit.regime.p_hydraulic, []
    if hasattr(d, "p_bg_useful"):  # КНС (31-36)
        return d.p_bg_useful, [
            ("Потери КПД", d.dp_efficiency),
            ("Номинальные", d.dp_nominal),
            ("Дросселирование", d.dp_na_throttle),
            ("Гидравл. насос→БГ", d.dp_hydraulic),
        ]
    # перекачка (37-42)
    return audit.regime.p_hydraulic, [
        ("Износ", d.dp_wear),
        ("Неоптим. подача", d.dp_suboptimal),
        ("Завыш. мощность ЭД", d.dp_motor),
        ("Вязкость", d.dp_viscosity),
        ("Номинальные", d.dp_nominal),
    ]
