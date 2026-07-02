"""Насосная установка/агрегат: режим и декомпозиция потерь.

Формулы Методики (разд. 8):
  режим           (7)-(16)
  декомпозиция КНС (31)-(36)
  декомпозиция перекачки (37)-(42), контроль баланса (43)

Все мощности в кВт, давления в МПа, подача в м³/ч.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .. import units
from . import motor

BALANCE_TOL = 1.0e-6  # допуск контроля баланса мощностей (43), кВт


# --- Номинальный КПД установки (14)/(15) ----------------------------------

def nominal_efficiency(eta_motor_nom: float, eta_pump_nom: float,
                       eta_vfd: float = 1.0, eta_gear: float = 1.0) -> float:
    """η_ном = η_пч · η_ЭД.ном · η_тр · η_нас.ном (15); без ПЧ/редуктора → (14)."""
    return eta_vfd * eta_motor_nom * eta_gear * eta_pump_nom


# --- Режим (7)-(16) -------------------------------------------------------

@dataclass
class RegimeResult:
    q: float                  # подача, м³/ч
    rho: float                # плотность, кг/м³
    p_in: float               # давление приём, МПа
    p_out: float              # давление выкид, МПа
    eta_nom: float            # номинальный КПД установки (14)/(15)
    h_fact: float             # напор фактический, м (8)
    p_hydraulic: float        # гидравлическая мощность, кВт (11)
    p_electric: float         # электрическая мощность, кВт (12)
    eta_unit: float           # КПД установки факт η_НУ/η_НА (13)
    # доп. для КНС
    p_bg: Optional[float] = None      # давление на БГ, МПа
    dp_valve: Optional[float] = None  # Δp на задвижке, МПа (9)
    h_bg: Optional[float] = None      # напор до БГ, м (10)


def compute_regime(*, q: float, rho: float, p_in: float, p_out: float,
                   eta_nom: float,
                   p_electric: Optional[float] = None,
                   w: Optional[float] = None, t: Optional[float] = None,
                   p_bg: Optional[float] = None) -> RegimeResult:
    """Расчёт параметров режима (7)-(16).

    P_эл берётся напрямую (измеренная активная мощность) либо как W/T (12).
    """
    dp = p_out - p_in
    h_fact = units.head_from_pressure(dp, rho)        # (8)
    p_hyd = units.hydraulic_power_kw(dp, q)           # (11)

    if p_electric is None:
        if w is None or not t:
            raise ValueError("нужна P_эл или пара (W, T) для (12)")
        p_electric = w / t                            # (12)

    eta_unit = p_hyd / p_electric                     # (13)

    res = RegimeResult(q=q, rho=rho, p_in=p_in, p_out=p_out, eta_nom=eta_nom,
                       h_fact=h_fact, p_hydraulic=p_hyd, p_electric=p_electric,
                       eta_unit=eta_unit)
    if p_bg is not None:
        res.p_bg = p_bg
        res.dp_valve = p_out - p_bg                                   # (9)
        res.h_bg = units.head_from_pressure(p_bg - p_in, rho)         # (10)
    return res


# --- Декомпозиция перекачки нефти (37)-(43) --------------------------------

@dataclass
class PumpingDecomposition:
    dp_nominal: float        # ΔP_ном (37)
    dp_efficiency: float     # ΔP_КПД (38)
    dp_suboptimal: float     # ΔP_неопт (39)
    dp_viscosity: float      # ΔP_вязк (40)
    dp_motor: float          # ΔP_ЭД (41)
    dp_wear: float           # ΔP_изн (42)
    eta_pump: float          # η_нас (27)
    balance_residual: float  # ΔP_КПД − Σ(40,39,41,42)  (43)
    balance_ok: bool


def decompose_pumping(regime: RegimeResult, *, eta_motor_nom: float,
                      eta_motor_real: float, eta_due: float,
                      eta_due_visc: Optional[float] = None,
                      eta_vfd: float = 1.0, eta_gear: float = 1.0,
                      tol: float = BALANCE_TOL) -> PumpingDecomposition:
    """Декомпозиция потерь насосного агрегата перекачки (37)-(42) + баланс (43).

    eta_due      — должный КПД насоса при рабочей подаче (29)-(30);
    eta_due_visc — должный КПД с учётом вязкости (если нет — равен eta_due, K_η≈1).
    """
    P = regime.p_hydraulic
    Pe = regime.p_electric
    eta_NA = regime.eta_unit
    eta_nom = regime.eta_nom
    ed = eta_due_visc if eta_due_visc is not None else eta_due

    eta_pump = motor.pump_efficiency(eta_NA, eta_motor_real, eta_vfd, eta_gear)  # (27)

    dp_nominal = P * (1.0 / eta_nom - 1.0)                                # (37)
    dp_kpd = P * (1.0 / eta_NA - 1.0 / eta_nom)                           # (38)
    dp_suboptimal = P * (1.0 / (eta_due * eta_motor_nom) - 1.0 / eta_nom)  # (39)
    dp_visc = (P / eta_motor_nom) * (1.0 / ed - 1.0 / eta_due)            # (40)
    dp_motor = Pe - P / (eta_pump * eta_motor_nom)                        # (41)
    dp_wear = (P / eta_motor_nom) * (1.0 / eta_pump - 1.0 / ed)           # (42)

    comp_sum = dp_visc + dp_suboptimal + dp_motor + dp_wear
    residual = dp_kpd - comp_sum                                          # (43)

    return PumpingDecomposition(
        dp_nominal=dp_nominal, dp_efficiency=dp_kpd, dp_suboptimal=dp_suboptimal,
        dp_viscosity=dp_visc, dp_motor=dp_motor, dp_wear=dp_wear,
        eta_pump=eta_pump, balance_residual=residual, balance_ok=abs(residual) < tol)


# --- Декомпозиция КНС (31)-(36) -------------------------------------------

@dataclass
class KnsDecomposition:
    dp_hydraulic: float      # ΔP_гидр на задвижке (31)
    dp_throttle: float       # ΔP_др (32)
    dp_na_throttle: float    # ΔP_НАдр (33)
    p_bg_useful: float       # P_БГ полезная на гребёнке (34)
    dp_nominal: float        # ΔP_ном (35)
    dp_efficiency: float     # ΔP_КПД (36)
    components: dict = field(default_factory=dict)


def decompose_kns(regime: RegimeResult, *, eta_nom: Optional[float] = None) -> KnsDecomposition:
    """Декомпозиция потерь насосной установки КНС (31)-(36).

    Требует p_bg в режиме (давление на БГ). Δp_задв = p_вых − p_БГ.
    """
    if regime.dp_valve is None:
        raise ValueError("для КНС-декомпозиции нужен p_bg (Δp_задв)")
    eta_nom = eta_nom if eta_nom is not None else regime.eta_nom
    P = regime.p_hydraulic
    Pe = regime.p_electric

    dp_hyd = units.hydraulic_power_kw(regime.dp_valve, regime.q)  # (31)
    dp_throttle = dp_hyd / eta_nom                                # (32)
    dp_na_throttle = dp_hyd / eta_nom - dp_hyd                    # (33)
    p_bg = P - dp_hyd                                             # (34)
    dp_nominal = p_bg / eta_nom - p_bg                            # (35)
    dp_eff = Pe - dp_nominal - dp_throttle - p_bg                 # (36)

    # 5-частная энергодиаграмма КНС, сумма = P_эл:
    # P_БГ + ΔP_гидр + ΔP_НАдр + ΔP_ном + ΔP_КПД (т.к. ΔP_гидр+ΔP_НАдр = ΔP_др).
    return KnsDecomposition(
        dp_hydraulic=dp_hyd, dp_throttle=dp_throttle, dp_na_throttle=dp_na_throttle,
        p_bg_useful=p_bg, dp_nominal=dp_nominal, dp_efficiency=dp_eff,
        components={
            "полезная_БГ": p_bg,              # P_БГ (34)
            "гидр_насос_БГ": dp_hyd,          # ΔP_гидр (31)
            "дросселирование": dp_na_throttle,  # ΔP_НАдр (33)
            "номинальные": dp_nominal,        # ΔP_ном (35)
            "КПД": dp_eff,                    # ΔP_КПД (36)
        })
