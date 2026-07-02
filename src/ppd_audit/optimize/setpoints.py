"""Оптимизация уставок насосного агрегата с технологическими ограничениями.

ТЗ (разд. 5): уставки расхода/давления/частоты в рамках ограничений (предельные
давления, диапазон ПЧ, целевая зона КПД). Базовая постановка: устранить
дросселирование (целевое p_вых = p_БГ) и оценить требуемую частоту ПЧ.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..core.audit import AuditResult


@dataclass
class SetpointOptimization:
    current_p_out: float            # текущее давление выкида, МПа
    optimal_p_out: float            # целевое давление выкида, МПа
    sec_current: float              # текущий УРЭ
    sec_optimal: float              # УРЭ при оптимальной уставке
    saving_kwh_year: float          # экономия, кВт·ч/год
    vfd_freq_hz: Optional[float]    # требуемая частота ПЧ (если применимо)
    within_constraints: bool
    notes: list[str]


def optimize_setpoint(audit: AuditResult, constraints, t_year: Optional[float] = None
                      ) -> SetpointOptimization:
    """Оптимизация уставки давления: устранить дросселирование (p_вых → p_БГ).

    Экономия ≈ ΔW_дрос (45). Проверяет предельные давления и диапазон ПЧ.
    """
    reg = audit.regime
    rm = audit.spec.regime
    notes: list[str] = []
    t_year = t_year or (rm.t_year or 8760.0)

    p_limits = constraints.pressure_limits
    vfd_cfg = constraints.vfd

    # целевое давление: при наличии p_БГ убираем дросселирование
    optimal_p = rm.p_bg if rm.p_bg is not None else reg.p_out
    saving = audit.dw_throttle or 0.0

    sec_optimal = audit.sec_optimal if audit.sec_optimal is not None else audit.sec_calc

    # частота ПЧ для снижения напора пропорционально давлению (закон подобия H~n²)
    freq = None
    if optimal_p < reg.p_out and reg.h_fact > 0:
        ratio = max(0.0, (optimal_p - rm.p_in) / (reg.p_out - rm.p_in))
        f_max = vfd_cfg.get("freq_max_hz", 50.0)
        f_min = vfd_cfg.get("freq_min_hz", 35.0)
        freq = round(f_max * ratio ** 0.5, 1)
        if freq < f_min:
            notes.append(f"требуемая частота {freq} Гц ниже минимума {f_min} Гц")
            freq = f_min

    within = True
    if "pump_discharge_max" in p_limits and reg.p_out > p_limits["pump_discharge_max"]:
        within = False
        notes.append(f"p_вых {reg.p_out:.1f} МПа выше предела {p_limits['pump_discharge_max']} МПа")
    if not notes:
        notes.append("уставка в пределах ограничений")

    return SetpointOptimization(
        current_p_out=reg.p_out, optimal_p_out=round(optimal_p, 3),
        sec_current=audit.sec_fact, sec_optimal=round(sec_optimal, 3),
        saving_kwh_year=round(saving, 1), vfd_freq_hz=freq,
        within_constraints=within, notes=notes)
