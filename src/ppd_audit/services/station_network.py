"""Единый баланс общей сети при совместной работе насосных агрегатов."""

from dataclasses import replace
from math import isclose, isfinite

from ..core.audit import ETA_VFD_DEFAULT, AuditResult
from ..core.pump import KnsDecomposition
from .network_losses import build_network_loss_map


def build_station_network(audits: list[AuditResult], network: dict) -> dict:
    """Суммировать upstream мощности, затем один раз рассчитать общую сеть.

    Только параллельные НА с общим коллектором и одинаковой схемой ПЧ.
    Совместность измерений и полноту списка работающих НА проверяет вызывающий код.
    """
    unavailable = {
        "status": "unavailable",
        "title": "Вся станция · цепочка потерь",
        "input_kw": None,
        "useful_kw": None,
        "total_loss_kw": None,
        "balance_error_kw": None,
        "items": [],
        "segments": [],
        "wells": [],
        "assumptions": [],
        "warnings": list(network.get("warnings", [])),
        "network": {},
        "measures": [],
        "comparison": None,
    }
    warnings = unavailable["warnings"]
    if not audits or len({audit.aggregate_id for audit in audits}) != len(audits):
        warnings.append("Нет полного списка уникальных работающих агрегатов станции.")
        return unavailable
    stages = []
    common = None
    for audit in audits:
        regime, spec = audit.regime, audit.spec
        if (
            spec is None
            or spec.regime is None
            or not isinstance(audit.decomposition, KnsDecomposition)
        ):
            warnings.append("Для всех работающих НА нужны режим, паспорт и декомпозиция до БГ.")
            return unavailable
        shared = (regime.p_in, regime.p_out, regime.p_bg, regime.rho, spec.regime.nu)
        efficiencies = (
            ETA_VFD_DEFAULT if spec.vfd else 1.0,
            audit.eta_motor_real,
            spec.transmission.efficiency,
            regime.eta_nom,
        )
        values = (
            *shared,
            regime.q,
            regime.p_electric,
            regime.p_hydraulic,
            audit.decomposition.p_bg_useful,
            *efficiencies,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value)
            for value in values
        ):
            warnings.append(
                "Неполные или некорректные давления, свойства жидкости, мощности или КПД НА."
            )
            return unavailable
        if (
            not regime.p_in < regime.p_bg <= regime.p_out
            or min(regime.rho, spec.regime.nu, regime.q, regime.p_electric) <= 0
            or any(not 0 < value <= 1 for value in efficiencies)
        ):
            warnings.append(
                "Для станционного баланса нужны положительные расходы и корректные КПД."
            )
            return unavailable
        if common is None:
            common = shared
        elif any(
            not isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)
            for a, b in zip(common, shared, strict=True)
        ):
            warnings.append(
                "Общие давления, плотность или вязкость НА различаются; сеть не объединена."
            )
            return unavailable
        if spec.vfd != audits[0].spec.vfd:
            warnings.append(
                "Разные схемы ПЧ НА: общий upstream без отдельных ветвей не поддерживается."
            )
            return unavailable
        electric = regime.p_electric
        after_vfd = electric * efficiencies[0]
        after_motor = after_vfd * efficiencies[1]
        shaft = after_motor * efficiencies[2]
        hydraulic, bg = regime.p_hydraulic, audit.decomposition.p_bg_useful
        if (
            not 0 < bg <= hydraulic <= shaft + 1e-8
            or not isclose(hydraulic, (regime.p_out - regime.p_in) * regime.q / 3.6)
            or not isclose(bg, (regime.p_bg - regime.p_in) * regime.q / 3.6)
        ):
            warnings.append(
                "Баланс отдельного НА противоречит расходу, давлениям или мощности ступеней."
            )
            return unavailable
        stages.append((electric, after_vfd, after_motor, shaft, hydraulic, bg))
    electric, after_vfd, after_motor, shaft, hydraulic, bg = (
        sum(values) for values in zip(*stages, strict=True)
    )
    first = audits[0]
    flow = sum(audit.regime.q for audit in audits)
    regime = replace(
        first.regime,
        q=flow,
        p_electric=electric,
        p_hydraulic=hydraulic,
        eta_unit=hydraulic / electric,
    )
    spec = first.spec.model_copy(
        update={
            "id": "station",
            "transmission": first.spec.transmission.model_copy(
                update={"efficiency": shaft / after_motor}
            ),
            "regime": first.spec.regime.model_copy(update={"q_fact": flow, "p_electric": electric}),
        }
    )
    decomposition = replace(
        first.decomposition,
        **{
            key: sum(getattr(audit.decomposition, key) for audit in audits)
            for key in (
                "dp_hydraulic",
                "dp_throttle",
                "dp_na_throttle",
                "p_bg_useful",
                "dp_nominal",
                "dp_efficiency",
            )
        },
        components={
            key: sum(audit.decomposition.components.get(key, 0) for audit in audits)
            for key in first.decomposition.components
        },
    )
    equivalent = replace(
        first,
        aggregate_id="station",
        regime=regime,
        spec=spec,
        eta_motor_real=after_motor / after_vfd,
        eta_pump=hydraulic / shaft,
        sec_fact=electric / flow,
        decomposition=decomposition,
        trace={},
    )
    result = build_network_loss_map(equivalent, network)
    result.update(title="Вся станция · цепочка потерь", measures=[], comparison=None)
    for assumption in result["assumptions"]:
        parameter = assumption["parameter"]
        if parameter == "source_flow_m3h":
            assumption.update(
                label="Суммарный расход работающих НА",
                basis="Сумма расходов совместно работающих НА на общем коллекторе",
            )
        elif parameter == "well_flow_m3h":
            assumption["basis"] = "Суммарный расход станции поровну между уникальными скважинами"
        elif parameter in {"motor_efficiency", "transmission_efficiency"}:
            assumption["basis"] = "Отношение суммарных выходной и входной мощностей ступени всех НА"
        elif parameter == "density_kgm3":
            assumption["basis"] = "Общая плотность жидкости всех работающих НА"
    result["warnings"] = [
        "Работают все учтённые НА; суммарный расход распределён поровну по уникальным скважинам."
        if warning.startswith("Работает только выбранный агрегат;")
        else warning
        for warning in result["warnings"]
    ]
    return result
