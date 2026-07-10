"""Электродвигатель: коэффициент загрузки и КПД — формулы (24)-(27) Методики.

Эталон ДНС-7с (Н-4): K_з≈0,6 (отчёт), η_эд.р≈0,931, η_нас≈0,558.
"""

from __future__ import annotations

LOAD_FACTOR_FULL = 0.7  # порог: при K_з ≥ 0,7 принимаем η_эд ≈ η_эд.ном


def electric_power_nominal(p_nom: float, eta_motor_nom: float) -> float:
    """Номинальная потребляемая мощность ЭД, кВт: P_эл.ном = P_ном / η_ЭД.ном (24)."""
    return p_nom / eta_motor_nom


def load_factor(p_electric: float, p_nom: float, eta_motor_nom: float) -> float:
    """Коэффициент загрузки ЭД (24): K_з = P_эл / P_эл.ном = P_эл / (P_ном/η_ЭД.ном).

    Примечание: отчёт №31 отображает K_з≈0,6 (= P_эл/P_ном); строгая формула (24)
    даёт K_з = P_эл·η_ЭД.ном/P_ном. На η_эд.р разница пренебрежимо мала.
    """
    return p_electric / electric_power_nominal(p_nom, eta_motor_nom)


def motor_efficiency(kz: float, eta_motor_nom: float, alpha: float = 1.0) -> float:
    """Расчётный КПД ЭД (24)-(26).

    При K_з ∈ [0,7; 1,0] → η_эд ≈ η_ЭД.ном.
    При K_з < 0,7:
        β = (α/K_з + K_з) / (1 + α)                         (26)
        η_эд.р = 1 / (1 + (1/η_ЭД.ном − 1)·β)               (25)
    α: 0,5..1 для асинхронных, до 2 для синхронных ЭД.
    """
    if kz >= LOAD_FACTOR_FULL:
        return eta_motor_nom
    beta = (alpha / kz + kz) / (1.0 + alpha)                # (26)
    return 1.0 / (1.0 + (1.0 / eta_motor_nom - 1.0) * beta)  # (25)


def pump_efficiency(eta_unit: float, eta_motor_real: float,
                    eta_vfd: float = 1.0, eta_gear: float = 1.0) -> float:
    """КПД насоса (27): η_нас = η_НА / (η_эд.р · η_пч · η_ред).

    η_НА = η_unit — фактический КПД насосной установки (13).
    """
    return eta_unit / (eta_motor_real * eta_vfd * eta_gear)
