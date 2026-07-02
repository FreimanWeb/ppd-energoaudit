"""ЗРА / штуцеры: потери на дросселирование (формулы 31-33, 45 Методики).

Дросселирование — намеренное снижение давления задвижкой/штуцером, прямая потеря
энергии. Здесь — для отдельного элемента (ЗРА/штуцер), вне декомпозиции агрегата.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import units


@dataclass
class ThrottleLoss:
    dp_throttle: float       # перепад на ЗРА/штуцере, МПа
    power_hydraulic: float   # гидравлич. мощность дросселирования, кВт (31)
    power_electric: float    # эквивалентная электрическая, кВт (32)
    annual_kwh: float        # годовые потери, кВт·ч/год (45)
    annual_rub: float


def throttle_loss(*, p_before: float, p_after: float, q: float, eta_nom: float,
                  t_year: float, tariff: float = 4.68) -> ThrottleLoss:
    """Потери на дросселировании ЗРА/штуцера.

    ΔP_гидр = Δp_задв·Q/3.6 (31);  ΔP_др = ΔP_гидр/η_ном (32);
    ΔW_др = (Δp_задв)/(3.6·η_ном)·Q_год (45).
    """
    dp = p_before - p_after
    p_hyd = units.hydraulic_power_kw(dp, q)          # (31)
    p_el = p_hyd / eta_nom                            # (32)
    q_year = q * t_year
    annual = dp / (units.HYDRAULIC_POWER_DIVISOR * eta_nom) * q_year   # (45)
    return ThrottleLoss(dp_throttle=dp, power_hydraulic=p_hyd, power_electric=p_el,
                        annual_kwh=annual, annual_rub=annual * tariff)
