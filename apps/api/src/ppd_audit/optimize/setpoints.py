"""Оптимизация уставок насосного агрегата с технологическими ограничениями.

ТЗ (разд. 5): уставки расхода/давления/частоты в рамках ограничений (предельные
давления, диапазон ПЧ, целевая зона КПД). Базовая постановка: устранить
дросселирование (целевое p_вых = p_БГ) и оценить требуемую частоту ПЧ.

Частота ПЧ ищется законом подобия H ∝ n² по характеристике насоса:
r²·H(Q/r) = H_цел, кандидат (Q/r) проверяется ``evaluate_pump_characteristic``.
Уставка «проверена» (status="validated") только по характеристике с явно
подтверждённой применимостью к установленным модели и оборотам; иначе —
«предложение» с ограничением, «недостижимо» или «недоступно».
Без ПЧ частота не выдаётся; невозможная частота не зажимается в диапазон.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from ..config import load_constraints
from ..core.audit import ETA_VFD_DEFAULT, AuditResult
from ..core.curves import evaluate_pump_characteristic, fit_parabola, poly2


if TYPE_CHECKING:
    from ..core.curves import PumpCharacteristic


class SetpointStatus(StrEnum):
    """Степень подтверждённости целевой уставки."""

    validated = "validated"  # точка проверена по подтверждённой характеристике
    proposal = "proposal"  # сценарное предложение, применимость не подтверждена
    infeasible = "infeasible"  # цель недостижима в заданных ограничениях
    unavailable = "unavailable"  # нет исходных данных для расчёта уставки
    no_change = "no_change"  # дросселирования нет — уставка не меняется


# Причины, по которым характеристика не принимается для проверки рабочей точки.
_QH_REASON = {
    "missing": "кривая Q-H отсутствует",
    "insufficient_points": "кривая Q-H содержит меньше 3 точек",
    "out_of_range": "рабочая подача вне диапазона кривой Q-H",
    "invalid_fit": "аппроксимация кривой Q-H даёт физически недопустимый напор",
    "model_mismatch": "кривая Q-H относится к другой модели насоса",
    "speed_mismatch": "кривая Q-H относится к другой частоте вращения",
    "not_applicable": "насос не центробежный — кривая Q-H неприменима",
}
_QETA_REASON = {
    "missing": "кривая Q-η отсутствует",
    "insufficient_points": "кривая Q-η содержит меньше 3 точек",
    "out_of_range": "рабочая подача вне диапазона кривой Q-η",
    "invalid_fit": "аппроксимация кривой Q-η даёт физически недопустимый КПД",
    "model_mismatch": "кривая Q-η относится к другой модели насоса",
    "speed_mismatch": "кривая Q-η относится к другой частоте вращения",
    "not_applicable": "кривая Q-η неприменима",
}


def characteristic_status_reason(ch: PumpCharacteristic) -> str:
    """Человекочитаемая причина недоступности проверки по характеристике."""
    reasons = [
        text
        for status, table in ((ch.qh_status, _QH_REASON), (ch.qeta_status, _QETA_REASON))
        if (text := table.get(status)) is not None
    ]
    if not reasons:
        return (
            f"источник характеристики ({ch.origin}) не подтверждён "
            "для установленных модели и оборотов"
        )
    return "; ".join(reasons)


def characteristic_limitation(audit: AuditResult, *, speed_path: bool = True) -> str | None:
    """Ограничение применимости рекомендации, зависящей от характеристики насоса.

    None — характеристика подтверждена (и есть ПЧ для скоростного пути), т.е.
    целевую точку можно проверить по закону подобия. Иначе — текст ограничения,
    который потребитель обязан показать вместо «проверенной» рекомендации.
    """
    ch = audit.characteristic
    notes: list[str] = []
    if ch is None or not ch.verified:
        detail = characteristic_status_reason(ch) if ch is not None else ""
        notes.append(
            "рабочая точка не проверена по подтверждённой характеристике насоса"
            + (f" ({detail})" if detail else "")
        )
    if speed_path and audit.spec is not None and not audit.spec.vfd:
        notes.append(
            "ПЧ отсутствует: сохранение подачи при снижении напора не проверено; "
            "нужна согласованная рабочая точка насоса и сети"
        )
    if not notes and speed_path:
        candidate = optimize_setpoint(audit, load_constraints())
        if candidate.status not in (SetpointStatus.validated.value, SetpointStatus.no_change.value):
            notes.extend(candidate.notes)
        elif candidate.saving_kwh_year is not None and candidate.saving_kwh_year <= 0:
            notes.append("модель новой точки не подтверждает экономию электроэнергии")
    return "; ".join(notes) if notes else None


@dataclass
class SetpointOptimization:
    current_p_out: float  # текущее давление выкида, МПа
    optimal_p_out: float | None  # проверяемая цель; None — давление БГ неизвестно
    sec_current: float  # текущий УРЭ
    sec_optimal: float | None  # модельный УРЭ только для проверенной целевой точки
    # Изменение годового потребления по модели новой рабочей точки, не ΔW_дрос.
    # None — целевая точка не проверена; отрицательное значение — рост потребления.
    saving_kwh_year: float | None
    vfd_freq_hz: float | None
    within_constraints: bool | None  # известные пределы давления; None — цель неизвестна
    status: str = SetpointStatus.proposal.value
    notes: list[str] = field(default_factory=list)


def _required_head_m(p_target: float, p_in: float, rho: float) -> float:
    """Требуемый напор при целевом давлении, м (формула 8)."""
    return (p_target - p_in) * 1.0e6 / (rho * 9.81)


def _current_curve_limitation(audit: AuditResult, ch: PumpCharacteristic) -> str | None:
    """Не переносить номинальную характеристику на несогласованный фактический режим.

    Учтён только остаток МНК на исходных точках и ошибка вычислений, не
    выдуманный эксплуатационный допуск. Иные допуски требуют подтверждения.
    """
    pump = audit.spec.pump
    for measured, reference, points, label in (
        (audit.regime.h_fact, ch.h_due_m, pump.curve_qh, "напор"),
        (audit.eta_pump, ch.eta_due, pump.curve_qeta, "КПД насоса"),
    ):
        if measured is None or reference is None:
            return f"фактический {label} не определён для сопоставления с характеристикой"
        coefficients = fit_parabola(points)
        fit_residual = max(abs(y - poly2(x, coefficients)) for x, y in points)
        delta = abs(measured - reference)
        if delta > fit_residual and not math.isclose(
            measured, reference, rel_tol=1e-7, abs_tol=1e-7
        ):
            return (
                f"измеренный {label} не согласуется с характеристикой "
                f"(расхождение {delta:.4g}, остаток МНК {fit_residual:.4g}); "
                "эксплуатационный допуск не подтверждён"
            )
    return None


def _vfd_frequency(
    audit: AuditResult,
    q: float,
    h_req: float,
    vfd_cfg: dict,
) -> tuple[float | None, PumpCharacteristic | None, str | None]:
    """Найти корень на пересечении известных диапазонов Q-H, Q-η и ПЧ."""
    pump = audit.spec.pump
    base = audit.characteristic or evaluate_pump_characteristic(pump, q)
    if base.h_due_m is None or base.eta_due is None:
        return None, base, characteristic_status_reason(base)
    source = pump.curve_source
    if source is None or source.frequency_hz is None:
        return None, base, "частота питания исходной характеристики не указана"
    f_nom = source.frequency_hz
    f_min = vfd_cfg.get("freq_min_hz", 35.0)
    f_max = vfd_cfg.get("freq_max_hz", 50.0)
    if not 0 < f_min <= f_max:
        return None, None, "некорректный диапазон частот ПЧ"
    lower_q = max(min(p[0] for p in pump.curve_qh), min(p[0] for p in pump.curve_qeta))
    upper_q = min(max(p[0] for p in pump.curve_qh), max(p[0] for p in pump.curve_qeta))
    lo = max(f_min / f_nom, q / upper_q)
    hi = min(f_max / f_nom, 1.0, q / lower_q if lower_q > 0 else math.inf)
    if lo > hi:
        return None, None, "диапазоны частоты ПЧ и подачи характеристики не пересекаются"
    coefficients = fit_parabola(pump.curve_qh)
    _, b, c = coefficients
    if min(b * q + 2 * c * lo, b * q + 2 * c * hi) <= 0:
        return None, base, "ветвь зависимости напора от частоты неоднозначна; нужна проверка"
    head_lo = lo * lo * poly2(q / lo, coefficients)
    head_hi = hi * hi * poly2(q / hi, coefficients)
    if not head_lo <= h_req <= head_hi:
        return None, None, "целевой напор недостижим в известных диапазонах частоты и подачи"
    for _ in range(40):
        mid = (lo + hi) / 2
        if mid * mid * poly2(q / mid, coefficients) < h_req:
            lo = mid
        else:
            hi = mid
    candidate = evaluate_pump_characteristic(pump, q / hi)
    if candidate.h_due_m is None or candidate.eta_due is None:
        return None, candidate, characteristic_status_reason(candidate)
    if not math.isclose(hi * hi * candidate.h_due_m, h_req, rel_tol=1e-8, abs_tol=1e-6):
        return None, None, "не найдено пересечение с целевым напором без экстраполяции"
    return hi * f_nom, candidate, None


def optimize_setpoint(
    audit: AuditResult,
    constraints,
) -> SetpointOptimization:
    """Проверить цель p_вых → p_БГ, не подменяя неизвестный эффект номинальным КПД.

    Частота, УРЭ и изменение потребления выдаются только для проверенной
    модели новой точки. Потенциал ΔW_дрос остаётся отдельной оценкой аудита.
    """
    reg = audit.regime
    if audit.spec is None or audit.spec.regime is None:
        raise ValueError("для оптимизации нужен измеренный режим агрегата")
    rm = audit.spec.regime
    notes: list[str] = []
    p_limits = constraints.pressure_limits
    ch = audit.characteristic or evaluate_pump_characteristic(audit.spec.pump, reg.q)
    sec_current = reg.p_electric / reg.q

    def result(
        status: SetpointStatus,
        optimal_p: float | None,
        freq: float | None = None,
        within: bool | None = True,
        eta_target: float | None = None,
    ) -> SetpointOptimization:
        if status == SetpointStatus.validated:
            sec_target = (optimal_p - rm.p_in) / (3.6 * eta_target)
            saving = (reg.p_electric - sec_target * reg.q) * audit.annual_runtime_hours
            if saving <= 0:
                notes.append("Модель новой точки не подтверждает снижение электропотребления.")
        elif status == SetpointStatus.no_change:
            sec_target, saving = sec_current, 0.0
        else:
            sec_target, saving = None, None
        return SetpointOptimization(
            current_p_out=reg.p_out,
            optimal_p_out=optimal_p,
            sec_current=sec_current,
            sec_optimal=sec_target,
            saving_kwh_year=saving,
            vfd_freq_hz=freq,
            within_constraints=within,
            status=status.value,
            notes=notes,
        )

    if rm.p_bg is None:
        notes.append("Давление на БГ не измерено: целевая уставка не определена.")
        return result(SetpointStatus.unavailable, None, within=None)
    optimal_p = min(rm.p_bg, reg.p_out)
    within = True
    for key, label in (
        ("pump_discharge_max", "выкид насоса"),
        ("manifold_max", "БГ"),
        ("waterline_max", "водовод"),
    ):
        if key in p_limits and optimal_p > p_limits[key]:
            within = False
            notes.append(
                f"целевое давление {optimal_p:.1f} МПа выше предела {label}: {p_limits[key]}"
            )
    if "pump_discharge_max" in p_limits and reg.p_out > p_limits["pump_discharge_max"]:
        notes.append(
            f"текущее p_вых {reg.p_out:.1f} МПа выше предела {p_limits['pump_discharge_max']} МПа"
        )
    if not within:
        return result(SetpointStatus.infeasible, optimal_p, within=False)
    if optimal_p >= reg.p_out:
        notes.append("дросселирование отсутствует — изменение уставки не требуется")
        return result(SetpointStatus.no_change, reg.p_out)
    if optimal_p <= rm.p_in:
        notes.append("целевое давление не выше давления приёма — уставка недостижима")
        return result(SetpointStatus.infeasible, optimal_p)
    if not audit.spec.vfd:
        notes.append(
            "ПЧ отсутствует: устранение дросселирования сдвинет рабочую точку по "
            "кривой насоса; подача и потребление в новой точке не подтверждены."
        )
        return result(SetpointStatus.proposal, optimal_p)
    if not ch.verified:
        notes.append(
            "Характеристика насоса не подтверждена: " + characteristic_status_reason(ch) + "."
        )
        return result(SetpointStatus.proposal, optimal_p)
    if limitation := _current_curve_limitation(audit, ch):
        notes.append("Уставка не проверена: " + limitation + ".")
        return result(SetpointStatus.proposal, optimal_p)
    freq, ch_star, reason = _vfd_frequency(
        audit, reg.q, _required_head_m(optimal_p, rm.p_in, rm.rho), constraints.vfd
    )
    if reason is not None:
        notes.append("Частота ПЧ не определена: " + reason + ".")
        status = SetpointStatus.proposal if ch_star is not None else SetpointStatus.infeasible
        return result(status, optimal_p)
    drive_eta = audit.eta_motor_real
    if drive_eta is None or ch_star.eta_due is None or audit.spec.transmission.efficiency is None:
        notes.append("КПД установки в целевой точке не определён.")
        return result(SetpointStatus.proposal, optimal_p)
    eta_unit = ch_star.eta_due * drive_eta * audit.spec.transmission.efficiency * ETA_VFD_DEFAULT
    zone = constraints.vfd.get("target_eff_zone")
    if not 0 < eta_unit <= 1 or zone and not zone[0] <= eta_unit <= zone[1]:
        notes.append(f"Модельный КПД установки {eta_unit:.3f} вне допустимой зоны {zone}.")
        return result(SetpointStatus.infeasible, optimal_p)
    notes.append(
        "Закон подобия и сохранение текущего КПД привода приняты модельно; "
        "это не команда управления и не подтверждённая экономия."
    )
    return result(SetpointStatus.validated, optimal_p, freq, eta_target=eta_unit)
