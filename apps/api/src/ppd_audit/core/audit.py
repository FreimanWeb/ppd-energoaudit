"""Оркестратор расчётного ядра: энергоаудит агрегата по универсальному спецу.

audit_aggregate(AggregateSpec, branch) — единая точка входа: считает режим (7-16),
ЭД (24-27), декомпозицию (31-36 КНС / 37-43 перекачка), УРЭ (16-18) и годовые
потери (44-45) для ЛЮБОГО объекта. Не зависит от формата исходников.

run_pump_audit(plant_id) — обёртка для объекта из config/plants/<id>.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..spec import AggregateSpec, Branch
from . import curves, motor, specific_energy
from .pump import (
    KnsDecomposition,
    PumpingDecomposition,
    RegimeResult,
    compute_regime,
    decompose_kns,
    decompose_pumping,
)
from .pump_profiles import profile_for


ETA_VFD_DEFAULT = 0.97  # η_пч по Методике («принимаем η_пч = 0,97»), формулы (15), (27)


@dataclass
class AuditResult:
    aggregate_id: str
    branch: str
    pump_kind: str
    audit_profile: str
    regime: RegimeResult
    load_factor: float | None  # K_з (24)
    eta_motor_real: float | None  # η_эд.р (25-26)
    eta_pump: float | None  # η_нас (27)
    sec_fact: float  # УРЭ факт (16)
    sec_calc: float | None  # УРЭ расч. (17)
    dw_efficiency: float | None  # ΔW_кпд (44), кВт·ч/год
    annual_runtime_hours: float
    annual_runtime_is_assumed: bool
    decomposition: KnsDecomposition | PumpingDecomposition | None = None
    h_due: float | None = None  # напор должный, м (центробежный)
    eta_pump_due: float | None = None
    characteristic: curves.PumpCharacteristic | None = None
    sec_optimal: float | None = None
    dw_throttle: float | None = None
    spec: AggregateSpec | None = None
    trace: dict = field(default_factory=dict)  # формула → {expr, subst, value} для UI


def _trace(d: dict, fid: str, formula: str, subst: str, value) -> None:
    d[fid] = {"formula": formula, "subst": subst, "value": value}


def audit_aggregate(agg: AggregateSpec, branch: Branch = Branch.kns) -> AuditResult:
    """Полный расчёт агрегата по универсальному спецу."""
    if agg.regime is None:
        raise ValueError(f"у агрегата {agg.id} нет измеренного режима")
    rm = agg.regime
    profile = profile_for(agg.pump.kind)
    tr: dict = {}

    # --- η_ном (14)/(15)
    eta_nom = agg.nominal_efficiency()
    motor_p_nom, motor_eta_nom = agg.motor.p_nom, agg.motor.eta_nom
    pump_eta_nom = agg.pump.eta_nom
    _trace(
        tr,
        "14",
        "η_ном = η_ЭД.ном·η_нас.ном·η_тр",
        f"{agg.motor.eta_nom}·{agg.pump.eta_nom}·{agg.transmission.efficiency}",
        round(eta_nom, 4) if eta_nom is not None else None,
    )

    # --- режим (7)-(16)
    flow = rm.flow()
    p_electric = rm.p_electric
    if p_electric is None and rm.w is not None and rm.t:
        p_electric = rm.w / rm.t  # (12)
    regime: RegimeResult = compute_regime(
        q=flow,
        rho=rm.rho,
        p_in=rm.p_in,
        p_out=rm.p_out,
        eta_nom=eta_nom,
        p_electric=p_electric,
        w=rm.w,
        t=rm.t,
        p_bg=rm.p_bg,
    )
    _trace(
        tr,
        "8",
        "H_ф = (p_вых−p_вх)·1e6/(ρ·g)",
        f"({rm.p_out}−{rm.p_in})·1e6/({rm.rho}·9.81)",
        round(regime.h_fact, 2),
    )
    _trace(
        tr,
        "11",
        "P_гидр = (p_вых−p_вх)·Q/3.6",
        f"({rm.p_out}−{rm.p_in})·{round(flow, 2)}/3.6",
        round(regime.p_hydraulic, 3),
    )
    _trace(
        tr,
        "13",
        "η_НА = P_гидр/P_эл",
        f"{round(regime.p_hydraulic, 2)}/{round(regime.p_electric, 2)}",
        round(regime.eta_unit, 4),
    )

    # --- ЭД (24)-(27); η_пч/η_ред из спеца агрегата — формулы (15), (27)
    eta_vfd = ETA_VFD_DEFAULT if agg.vfd else 1.0
    eta_gear = agg.transmission.efficiency
    kz = eta_mr = eta_pump = None
    if motor_p_nom is not None and motor_eta_nom is not None:
        kz = motor.load_factor(regime.p_electric, motor_p_nom, motor_eta_nom)
        eta_mr = motor.motor_efficiency(kz, motor_eta_nom, agg.motor.alpha)
        if eta_gear is not None:
            eta_pump = motor.pump_efficiency(regime.eta_unit, eta_mr, eta_vfd, eta_gear)
        _trace(
            tr,
            "24",
            "K_з = P_эл/(P_ном/η_ЭД.ном)",
            f"{round(regime.p_electric, 2)}/({motor_p_nom}/{motor_eta_nom})",
            round(kz, 4),
        )
        _trace(
            tr,
            "25-26",
            "η_эд.р (при K_з<0,7)",
            f"K_з={round(kz, 3)}, α={agg.motor.alpha}",
            round(eta_mr, 4),
        )
        _trace(
            tr,
            "27",
            "η_нас = η_НА/(η_эд.р·η_пч·η_ред)",
            f"{round(regime.eta_unit, 4)}/({round(eta_mr, 4)}·{eta_vfd}·{eta_gear})"
            if eta_gear is not None
            else "КПД передачи неизвестен",
            round(eta_pump, 4) if eta_pump is not None else None,
        )

    # --- УРЭ (16)-(17)
    sec_regime = specific_energy.sec_fact(regime.p_electric, flow)
    if rm.w is not None and rm.q_day:
        sec_f = specific_energy.sec_fact(rm.w, rm.q_day)  # W/Q_сут
        sec_f_subst = f"{rm.w}/{rm.q_day}"
        sec_f_formula = "УРЭ_ф = W/Q_сут"
    else:
        sec_f = sec_regime
        sec_f_subst = f"{round(regime.p_electric, 2)}/{round(flow, 2)}"
        sec_f_formula = "УРЭ_ф = P_эл/Q"
    sec_c = (
        specific_energy.sec_calc(regime.p_out, regime.p_in, eta_nom)
        if eta_nom is not None
        else None
    )
    _trace(tr, "16", sec_f_formula, sec_f_subst, round(sec_f, 4))
    _trace(
        tr,
        "17",
        "УРЭ_р = (p_вых−p_вх)/(3.6·η_ном)",
        f"({rm.p_out}−{rm.p_in})/(3.6·{eta_nom})"
        if eta_nom is not None
        else "Паспортный КПД не подтверждён",
        round(sec_c, 4) if sec_c is not None else None,
    )

    # --- опорные характеристики (29)/(30), в том числе для ветки КНС
    characteristic = curves.evaluate_pump_characteristic(agg.pump, flow)
    h_due = characteristic.h_due_m
    eta_reference = characteristic.eta_due
    if profile.uses_qh_curve and not agg.pump.curve_qh and agg.h_pump_due is not None:
        h_due = agg.h_pump_due
    if profile.uses_qeta_curve and not agg.pump.curve_qeta and agg.eta_pump_due is not None:
        eta_reference = agg.eta_pump_due
    source = agg.pump.curve_source
    source_reference = source.reference if source is not None else "источник не подтверждён"
    _trace(
        tr,
        "29",
        "H_д = aQ²+bQ+c (опорная характеристика Q-H)",
        f"Q={flow:g}; {characteristic.qh_status}; {source_reference}",
        round(h_due, 1) if h_due is not None else None,
    )
    _trace(
        tr,
        "30",
        "η_д = uQ²+vQ+w (опорная характеристика Q-η)",
        f"Q={flow:g}; {characteristic.qeta_status}; {source_reference}",
        round(eta_reference, 4) if eta_reference is not None else None,
    )

    # --- декомпозиция; справочная кривая не заменяет номинальный КПД КНС
    decomp: KnsDecomposition | PumpingDecomposition | None = None
    if (
        eta_nom is not None
        and eta_mr is not None
        and branch == Branch.transfer
        and profile.uses_qeta_curve
    ):
        eta_for_decomposition = eta_reference
        if eta_for_decomposition is None and not agg.pump.curve_qeta:
            eta_for_decomposition = pump_eta_nom
            _trace(
                tr,
                "30",
                "η_д (допущение: кривая Q-η отсутствует)",
                "Для декомпозиции принят номинальный КПД насоса",
                round(pump_eta_nom, 4),
            )
        if eta_for_decomposition is not None and eta_for_decomposition > 0:
            decomp = decompose_pumping(
                regime,
                eta_motor_nom=motor_eta_nom,
                eta_motor_real=eta_mr,
                eta_due=eta_for_decomposition,
                eta_vfd=eta_vfd,
                eta_gear=eta_gear,
            )
            eta_pump = decomp.eta_pump
    elif eta_nom is not None and rm.p_bg is not None:
        decomp = decompose_kns(regime, eta_nom=eta_nom)

    # --- годовые потери (44)/(45), единая база Q_год = Q·T_год
    annual_runtime = rm.t_year
    if annual_runtime is None and agg.reference is not None:
        annual_runtime = agg.reference.t_year
    annual_runtime_is_assumed = annual_runtime is None
    t_year = 8760.0 if annual_runtime is None else annual_runtime
    q_year = flow * t_year
    dw_eff = (
        specific_energy.annual_loss_efficiency_by_sec(q_year, sec_regime, sec_c)
        if sec_c is not None
        else None
    )
    _trace(
        tr,
        "44",
        "ΔW_кпд = Q_год·(УРЭ_реж−УРЭ_р)",
        f"Q_год = {flow:g}·{t_year:g} = {q_year:g} м³; "
        f"T_год: {'сценарий' if annual_runtime_is_assumed else 'заданная наработка'}; "
        f"УРЭ_реж = P_эл/Q = {sec_regime:g}; "
        f"{round(q_year, 0)}·({round(sec_regime, 3)}−{round(sec_c, 3)})"
        if sec_c is not None
        else "Паспортный КПД не подтверждён",
        round(dw_eff, 1) if dw_eff is not None else None,
    )
    dw_thr = None
    sec_opt = None
    if rm.p_bg is not None:
        dw_thr = specific_energy.annual_loss_throttle(
            regime.p_out,
            rm.p_bg,
            regime.eta_unit,
            q_year,
        )
        if eta_nom is not None:
            sec_opt = specific_energy.sec_optimal(rm.p_bg, rm.p_in, eta_nom)

    return AuditResult(
        aggregate_id=agg.id,
        branch=branch.value,
        pump_kind=agg.pump.kind.value,
        audit_profile=profile.name,
        regime=regime,
        load_factor=kz,
        eta_motor_real=eta_mr,
        eta_pump=eta_pump,
        sec_fact=sec_f,
        sec_calc=sec_c,
        dw_efficiency=dw_eff,
        annual_runtime_hours=t_year,
        annual_runtime_is_assumed=annual_runtime_is_assumed,
        decomposition=decomp,
        h_due=h_due,
        eta_pump_due=eta_reference,
        characteristic=characteristic,
        sec_optimal=sec_opt,
        dw_throttle=dw_thr,
        spec=agg,
        trace=tr,
    )


def run_pump_audit(plant_id: str, aggregate_id: str | None = None) -> AuditResult:
    """Аудит агрегата объекта из config/plants/<id>.yaml (через ObjectSpec)."""
    from ..spec import load_object_spec

    obj = load_object_spec(plant_id)
    agg = obj.aggregate(aggregate_id) if aggregate_id else obj.working_aggregates()[0]
    return audit_aggregate(agg, obj.branch)
