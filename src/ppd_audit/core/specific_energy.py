"""УРЭ, характеристика трубопровода и годовые потери.

Формулы Методики (разд. 8):
  УРЭ            (16)-(18)
  характеристика трубопровода и оптимальное давление (19)-(23)
  годовые потери энергии (44)-(47)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .. import units


# --- УРЭ (16)-(18) --------------------------------------------------------

def sec_fact(p_electric_avg: float, q_avg: float) -> float:
    """УРЭ факт (16): P_эл.ср/Q_ср = W/Q_сут, кВт·ч/м³."""
    return p_electric_avg / q_avg


def sec_calc(p_out: float, p_in: float, eta_nom: float) -> float:
    """УРЭ расчётный (17): (p_вых − p_вх)/(3.6·η_ном), кВт·ч/м³."""
    return (p_out - p_in) / (units.HYDRAULIC_POWER_DIVISOR * eta_nom)


def sec_optimal(p_opt: float, p_in: float, eta_ndt: float) -> float:
    """УРЭ оптимальный (18): (p_опт − p_вх)/(3.6·η_ндт), кВт·ч/м³.

    Для КНС p_опт = p_БГ; для перекачки — по характеристике трубопровода (23).
    """
    return (p_opt - p_in) / (units.HYDRAULIC_POWER_DIVISOR * eta_ndt)


# --- Характеристика трубопровода и оптимальное давление (19)-(23) ----------

@dataclass
class PipeCharacteristic:
    h_static: float   # H_с, м (20)
    k_t: float        # K_т, м/(м³/ч)² (21)

    def head(self, q: float) -> float:
        """H_т = H_с + K_т·Q² (19)."""
        return self.h_static + self.k_t * q * q


def pipe_characteristic(*, h_fact: float, q: float, rho: float,
                        p_pp: float, p_in: float, h_pp: float, h_geo: float) -> PipeCharacteristic:
    """Характеристика трубопровода (20)-(21).

    H_с ≈ (p_пп − p_вх)/(ρg)·1e6 + h_пп − h   (20)
    K_т = (H_ф − H_с)/Q²                       (21)
    """
    h_static = units.head_from_pressure(p_pp - p_in, rho) + h_pp - h_geo  # (20)
    k_t = (h_fact - h_static) / (q * q)                                   # (21)
    return PipeCharacteristic(h_static=h_static, k_t=k_t)


def optimal_pressure(*, q_day: float, rho: float, pipe: PipeCharacteristic) -> float:
    """Оптимальное давление при непрерывном равномерном режиме (22)-(23), МПа.

    Q_прит = Q_сут/24 (22);  p_опт = ρg·(H_с + K_т·Q_прит²)·1e-6 (23).
    """
    q_inflow = q_day / 24.0                              # (22)
    h_opt = pipe.head(q_inflow)
    return rho * units.G * h_opt * 1.0e-6                # (23)


# --- Годовые потери энергии (44)-(47) -------------------------------------

@dataclass
class AnnualLosses:
    dw_efficiency: float   # ΔW_кпд (44), кВт·ч/год
    dw_throttle: Optional[float] = None   # ΔW_др (45)
    dw_cyclic: Optional[float] = None     # ΔW_ц (46)
    dw_ndt: Optional[float] = None        # ΔW_ндт (47)


def annual_loss_efficiency_by_sec(q_year: float, sec_f: float, sec_c: float) -> float:
    """ΔW_кпд (44): Q_год·(УРЭ_ф − УРЭ_р), кВт·ч/год.

    ВНИМАНИЕ: корректно только если УРЭ_ф и Q_год на одной базе (годовое среднее).
    При разовом замере (Q_спот ≠ Q_год/T_год) используйте annual_loss_efficiency_by_power.
    """
    return q_year * (sec_f - sec_c)


def annual_loss_efficiency_by_power(dp_efficiency_kw: float, t_year: float) -> float:
    """ΔW_кпд через мощностную декомпозицию: ΔP_КПД(38)·T_год, кВт·ч/год.

    Этой формой считается ΔW_НА в аудите №31 (разовый замер): даёт 53 242,9 кВт·ч/год.
    """
    return dp_efficiency_kw * t_year


def annual_loss_throttle(p_out: float, p_bg: float, eta_nom: float, q_year: float) -> float:
    """ΔW_др (45): (p_вых − p_БГ)/(3.6·η_ном)·Q_год, кВт·ч/год."""
    return (p_out - p_bg) / (units.HYDRAULIC_POWER_DIVISOR * eta_nom) * q_year


def annual_loss_cyclic(p_out: float, p_opt: float, eta_nom: float, q_year: float) -> float:
    """ΔW_ц (46): (p_вых − p_опт)/(3.6·η_ном)·Q_год, кВт·ч/год."""
    return (p_out - p_opt) / (units.HYDRAULIC_POWER_DIVISOR * eta_nom) * q_year


def annual_loss_ndt(q_year: float, sec_f: float, sec_opt: float) -> float:
    """ΔW_ндт (47): Q_год·(УРЭ_ф − УРЭ_опт), кВт·ч/год."""
    return q_year * (sec_f - sec_opt)
