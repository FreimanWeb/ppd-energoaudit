"""Оркестратор расчётного ядра: энергоаудит агрегата по универсальному спецу.

audit_aggregate(AggregateSpec, branch) — единая точка входа: считает режим (7-16),
ЭД (24-27), декомпозицию (31-36 КНС / 37-43 перекачка), УРЭ (16-18) и годовые
потери (44-45) для ЛЮБОГО объекта. Не зависит от формата исходников.

run_pump_audit(plant_id) — обёртка для объекта из config/plants/<id>.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..spec import AggregateSpec, Branch, PumpKind
from . import curves, motor, specific_energy
from .pump import (RegimeResult, compute_regime, decompose_kns,
                   decompose_pumping, nominal_efficiency)

ETA_VFD_DEFAULT = 0.97  # η_пч по Методике («принимаем η_пч = 0,97»), формулы (15), (27)


@dataclass
class AuditResult:
    aggregate_id: str
    branch: str
    pump_kind: str
    regime: RegimeResult
    load_factor: float                # K_з (24)
    eta_motor_real: float             # η_эд.р (25-26)
    eta_pump: float                   # η_нас (27)
    sec_fact: float                   # УРЭ факт (16)
    sec_calc: float                   # УРЭ расч. (17)
    dw_efficiency: float              # ΔW_кпд (44), кВт·ч/год
    decomposition: object = None      # KnsDecomposition | PumpingDecomposition | None
    h_due: Optional[float] = None     # напор должный, м (центробежный)
    sec_optimal: Optional[float] = None
    dw_throttle: Optional[float] = None
    spec: Optional[AggregateSpec] = None
    trace: dict = field(default_factory=dict)   # формула → {expr, subst, value} для UI


def _trace(d: dict, fid: str, formula: str, subst: str, value) -> None:
    d[fid] = {"formula": formula, "subst": subst, "value": value}


def audit_aggregate(agg: AggregateSpec, branch: Branch = Branch.kns) -> AuditResult:
    """Полный расчёт агрегата по универсальному спецу."""
    if agg.regime is None:
        raise ValueError(f"у агрегата {agg.id} нет измеренного режима")
    rm = agg.regime
    tr: dict = {}

    # --- η_ном (14)/(15)
    eta_nom = agg.nominal_efficiency()
    if eta_nom is None and agg.reference and agg.reference.eta_nom:
        eta_nom = agg.reference.eta_nom
    if eta_nom is None:
        raise ValueError(f"нет данных для η_ном агрегата {agg.id}")
    _trace(tr, "14", "η_ном = η_ЭД.ном·η_нас.ном·η_тр",
           f"{agg.motor.eta_nom}·{agg.pump.eta_nom}·{agg.transmission_eff}", round(eta_nom, 4))

    # --- режим (7)-(16)
    flow = rm.flow()
    p_electric = rm.p_electric
    if p_electric is None and rm.w is not None and rm.t:
        p_electric = rm.w / rm.t                                  # (12)
    regime: RegimeResult = compute_regime(
        q=flow, rho=rm.rho, p_in=rm.p_in, p_out=rm.p_out, eta_nom=eta_nom,
        p_electric=p_electric, w=rm.w, t=rm.t, p_bg=rm.p_bg)
    _trace(tr, "8", "H_ф = (p_вых−p_вх)·1e6/(ρ·g)",
           f"({rm.p_out}−{rm.p_in})·1e6/({rm.rho}·9.81)", round(regime.h_fact, 2))
    _trace(tr, "11", "P_гидр = (p_вых−p_вх)·Q/3.6",
           f"({rm.p_out}−{rm.p_in})·{round(flow,2)}/3.6", round(regime.p_hydraulic, 3))
    _trace(tr, "13", "η_НА = P_гидр/P_эл",
           f"{round(regime.p_hydraulic,2)}/{round(regime.p_electric,2)}", round(regime.eta_unit, 4))

    # --- ЭД (24)-(27); η_пч/η_ред из спеца агрегата — формулы (15), (27)
    eta_vfd = ETA_VFD_DEFAULT if agg.vfd else 1.0
    eta_gear = agg.transmission_eff
    kz = motor.load_factor(regime.p_electric, agg.motor.p_nom, agg.motor.eta_nom)
    eta_mr = motor.motor_efficiency(kz, agg.motor.eta_nom, agg.motor.alpha)
    eta_pump = motor.pump_efficiency(regime.eta_unit, eta_mr, eta_vfd, eta_gear)
    _trace(tr, "24", "K_з = P_эл/(P_ном/η_ЭД.ном)",
           f"{round(regime.p_electric,2)}/({agg.motor.p_nom}/{agg.motor.eta_nom})", round(kz, 4))
    _trace(tr, "25-26", "η_эд.р (при K_з<0,7)", f"K_з={round(kz,3)}, α={agg.motor.alpha}",
           round(eta_mr, 4))
    _trace(tr, "27", "η_нас = η_НА/(η_эд.р·η_пч·η_ред)",
           f"{round(regime.eta_unit,4)}/({round(eta_mr,4)}·{eta_vfd}·{eta_gear})", round(eta_pump, 4))

    # --- УРЭ (16)-(17)
    if rm.w is not None and rm.q_day:
        sec_f = specific_energy.sec_fact(rm.w, rm.q_day)          # W/Q_сут
        sec_f_subst = f"{rm.w}/{rm.q_day}"
    else:
        sec_f = specific_energy.sec_fact(regime.p_electric, flow)  # P_эл/Q
        sec_f_subst = f"{round(regime.p_electric,2)}/{round(flow,2)}"
    sec_c = specific_energy.sec_calc(regime.p_out, regime.p_in, eta_nom)
    _trace(tr, "16", "УРЭ_ф = W/Q_сут", sec_f_subst, round(sec_f, 4))
    _trace(tr, "17", "УРЭ_р = (p_вых−p_вх)/(3.6·η_ном)",
           f"({rm.p_out}−{rm.p_in})/(3.6·{round(eta_nom,4)})", round(sec_c, 4))

    # --- должные напор (29) и КПД (30) по паспортным кривым (если заданы)
    h_due = None
    if len(agg.pump.curve_qh) >= 3:
        h_due = curves.head_due(flow, agg.pump.curve_qh)                 # (29)
        _trace(tr, "29", "H_д = aQ²+bQ+c (паспортная кривая Q-H)",
               f"Q={round(flow, 2)}", round(h_due, 1))
    elif agg.h_pump_due is not None:
        h_due = agg.h_pump_due       # снято с паспортной кривой вручную (паспорт/отчёт)
        _trace(tr, "29", "H_д (значение с паспортной кривой)", "ручной ввод", round(h_due, 1))

    # --- декомпозиция
    decomp = None
    if branch == Branch.transfer and agg.pump.kind == PumpKind.centrifugal:
        if len(agg.pump.curve_qeta) >= 3:
            eta_due = curves.eta_due(flow, agg.pump.curve_qeta)          # (30)
            eta_due_src = "кривая Q-η"
        elif agg.eta_pump_due is not None:
            eta_due = agg.eta_pump_due
            eta_due_src = "паспорт/отчёт (снято с кривой)"
        else:
            eta_due = agg.pump.eta_nom
            eta_due_src = "η_нас.ном (допущение: кривой нет)"
        _trace(tr, "30", "η_д = uQ²+vQ+w (должный КПД при подаче Q)",
               f"Q={round(flow, 2)}, источник: {eta_due_src}", round(eta_due, 4))
        decomp = decompose_pumping(regime, eta_motor_nom=agg.motor.eta_nom,
                                   eta_motor_real=eta_mr, eta_due=eta_due,
                                   eta_vfd=eta_vfd, eta_gear=eta_gear)
        eta_pump = decomp.eta_pump
    elif rm.p_bg is not None:
        decomp = decompose_kns(regime, eta_nom=eta_nom)

    # --- годовые потери (44)/(45), единая база Q_год = Q·T_год
    t_year = rm.t_year or (agg.reference.t_year if agg.reference else None) or 0.0
    q_year = flow * t_year
    dw_eff = specific_energy.annual_loss_efficiency_by_sec(q_year, sec_f, sec_c)
    _trace(tr, "44", "ΔW_кпд = Q_год·(УРЭ_ф−УРЭ_р)",
           f"{round(q_year,0)}·({round(sec_f,3)}−{round(sec_c,3)})", round(dw_eff, 1))
    dw_thr = None
    sec_opt = None
    if rm.p_bg is not None:
        dw_thr = specific_energy.annual_loss_throttle(regime.p_out, rm.p_bg, eta_nom, q_year)
        sec_opt = specific_energy.sec_optimal(rm.p_bg, rm.p_in, eta_nom)  # p_опт=p_БГ (КНС)

    return AuditResult(
        aggregate_id=agg.id, branch=branch.value, pump_kind=agg.pump.kind.value,
        regime=regime, load_factor=kz, eta_motor_real=eta_mr, eta_pump=eta_pump,
        sec_fact=sec_f, sec_calc=sec_c, dw_efficiency=dw_eff, decomposition=decomp,
        h_due=h_due, sec_optimal=sec_opt, dw_throttle=dw_thr, spec=agg, trace=tr)


def run_pump_audit(plant_id: str, aggregate_id: Optional[str] = None) -> AuditResult:
    """Аудит агрегата объекта из config/plants/<id>.yaml (через ObjectSpec)."""
    from ..spec_io import load_object_spec
    obj = load_object_spec(plant_id)
    agg = obj.aggregate(aggregate_id) if aggregate_id else obj.working_aggregates()[0]
    return audit_aggregate(agg, obj.branch)
