"""Сводка станции без подмены отсутствующих агрегатов частичной суммой."""

from dataclasses import asdict
from datetime import datetime, timedelta
from math import isfinite

from ..core.audit import audit_aggregate
from ..db import AuditDatabase
from ..measures.registry import suggest_measures
from ..spec import Branch, load_object_spec
from .analysis import annual_summary
from .armits_data import load_network
from .audit import run_energy_audit
from .catalog import tariff, with_confirmed_density
from .station_network import build_station_network
from .telemetry_audit import run_snapshot_audit


def station_summary(
    database: AuditDatabase,
    object_id: str,
    *,
    source: str,
    day: str | None = None,
    timestamp: str | None = None,
) -> dict:
    plant = database.plant(object_id)
    codes = [row["code"] for row in database.aggregates(object_id)]
    warnings = []
    stamp = None
    if source == "telemetry" and (day or timestamp):
        if not day or not timestamp:
            raise ValueError("для выбранного момента требуются day и timestamp")
        start = datetime.strptime(day, "%Y-%m-%d")
        if start.date().isoformat() != day:
            raise ValueError("дата должна иметь формат YYYY-MM-DD")
        stamp = datetime.fromisoformat(timestamp)
        if stamp.tzinfo is not None or not start <= stamp < start + timedelta(days=1):
            raise ValueError("момент должен принадлежать выбранным суткам без UTC offset")

    raw = {}
    if source == "telemetry":
        for code in codes:
            values = {}
            invalid_stamps = set()
            for row in database.measurements(object_id, code):
                if row["metric"] not in ("flow_rate", "power"):
                    continue
                value = float(row["value"])
                if row["quality"] not in (None, "", "good", "ready") or not isfinite(value):
                    invalid_stamps.add(row["timestamp"])
                    continue
                values.setdefault(row["timestamp"], {}).setdefault(row["metric"], set()).add(value)
            # Conflicting duplicates are not a valid basis for a station total.
            raw[code] = {
                key: {metric: next(iter(items)) for metric, items in value.items()}
                for key, value in values.items()
                if key not in invalid_stamps
                and all(len(items) == 1 for items in value.values())
                and set(value) == {"flow_rate", "power"}
            }
        if stamp is None and codes:
            common = set.intersection(*(set(raw[code]) for code in codes))
            if common:
                stamp = datetime.fromisoformat(max(common))
            else:
                warnings.append(
                    "Нет общего момента с измеренными подачей и мощностью всех агрегатов."
                )

    result = {
        "object_id": object_id,
        "object_name": plant["name"],
        "source": source,
        "timestamp": stamp.isoformat() if stamp else None,
        "aggregate_count": len(codes),
        "included_aggregates": [],
        "complete": False,
        "warnings": warnings,
        "pressures": {},
        "metrics": {"flow_m3h": None, "power_kw": None, "sec_kwh_m3": None},
        "annual": None,
        "annual_basis": None,
        "measures": [],
        "network": {
            "status": "unavailable",
            "warnings": ["Нет полного согласованного режима станции."],
        },
    }
    if not codes:
        warnings.append("Нет агрегатов для сводки станции.")
        return result
    if source == "telemetry" and stamp is None:
        return result
    obj = (
        with_confirmed_density(load_object_spec(object_id), database)
        if source == "field_trip"
        else None
    )
    audits, measure_audits, flows, powers = [], [], [], []
    annual_valid = True
    annual_runtimes = []
    for code in codes:
        try:
            if source == "field_trip":
                audit = run_energy_audit(obj, code)
                measure_audit = audit
                flow, power = audit.regime.q, audit.regime.p_electric
                known_runtime = audit.spec.regime.t_year is not None
                if not known_runtime:
                    regime = audit.spec.regime.model_copy(update={"t_year": 8760.0})
                    audit = audit_aggregate(
                        audit.spec.model_copy(update={"regime": regime}),
                        Branch(audit.branch),
                    )
                warnings.append(f"{code}: выездной замер; одновременность замеров не подтверждена.")
            else:
                point = raw[code].get(stamp.isoformat())
                if point is None:
                    raise ValueError("нет точных измерений подачи и мощности в выбранный момент")
                flow, power = point["flow_rate"], point["power"]
                if not isfinite(flow) or not isfinite(power) or flow <= 0 or power <= 0:
                    raise ValueError("недопустимая подача или мощность")
                start = stamp.replace(hour=0, minute=0, second=0, microsecond=0)
                snapshot = run_snapshot_audit(
                    database,
                    object_id,
                    code,
                    start,
                    start + timedelta(days=1),
                    stamp,
                    track_clarifications=False,
                )
                audit = snapshot.audit
                measure_audit = audit
                if not snapshot.quality.allows_economic_conclusions:
                    raise ValueError("измерения не пригодны для расчёта")
                regime = audit.spec.regime.model_copy(
                    update={
                        "q_fact": flow,
                        "p_electric": power,
                        "q_day": None,
                        "w": None,
                        "t": None,
                    }
                )
                audit = audit_aggregate(
                    audit.spec.model_copy(update={"regime": regime}),
                    Branch(audit.branch),
                )
                known_runtime = not snapshot.annual_runtime_is_assumed
                # Existing audit may use daily medians; never annualise them as a spot regime.
                annual_valid = (
                    annual_valid and not snapshot.uses_daily_flow and not snapshot.uses_daily_power
                )
            if not isfinite(flow) or not isfinite(power) or flow <= 0 or power <= 0:
                raise ValueError("недопустимая подача или мощность")
            if not 0 < audit.regime.eta_unit <= 1:
                raise ValueError("физически недопустимый КПД")
            result["pressures"][code] = {
                "p_in_mpa": audit.regime.p_in,
                "p_out_mpa": audit.regime.p_out,
            }
            audits.append(audit)
            # Match the detail page; station totals rebind raw Q/P separately.
            measure_audits.append(measure_audit)
            flows.append(flow)
            powers.append(power)
            result["included_aggregates"].append(code)
            annual_runtimes.append((known_runtime, audit.spec.regime.t_year))
        except (ArithmeticError, KeyError, ValueError, FileNotFoundError) as exc:
            warnings.append(f"{code}: {exc}")
    if len(audits) != len(codes):
        warnings.append("Неполный набор данных: суммы всей станции не рассчитаны.")
        return result
    result["complete"] = True
    result["metrics"] = {
        "flow_m3h": sum(flows),
        "power_kw": sum(powers),
        "sec_kwh_m3": sum(powers) / sum(flows),
    }
    warnings.append("УРЭ режима: сумма мощностей / сумма подач; это не суточная энергия / объём.")
    network = load_network(object_id)
    result["network"] = (
        build_station_network(audits, network)
        if network
        else {
            "status": "unavailable",
            "warnings": ["Сеть этого объекта не подключена."],
        }
    )
    if source == "field_trip":
        result["network"].setdefault("warnings", []).append(
            "Одновременность выездных замеров не подтверждена: баланс сети — сценарий."
        )
    assumed = [runtime for known, runtime in annual_runtimes if not known]
    if assumed:
        annual_valid = annual_valid and len(assumed) == len(codes) and len(set(assumed)) == 1
    if annual_valid:
        result["annual_basis"] = (
            f"Сценарий {assumed[0]:g} ч/год: наработка принята, это не фактические годовые потери."
            if assumed
            else "Сценарий текущих режимов с индивидуальной годовой наработкой агрегатов."
        )
        if assumed:
            warnings.append(result["annual_basis"])
        selected = tariff(stamp.date() if stamp else None, database=database)
        if selected["warning"]:
            warnings.append(selected["warning"])
        result["measures"] = [
            {"aggregate_id": audit.aggregate_id, **asdict(measure)}
            for audit in measure_audits
            for measure in suggest_measures(audit, selected["rub_per_kwh"])
        ]
        summaries = [annual_summary(audit, selected["rub_per_kwh"]) for audit in audits]
        result["annual"] = {
            key: sum(row[key] for row in summaries)
            if all(row[key] is not None and isfinite(row[key]) for row in summaries)
            else None
            for key in summaries[0]
        }
    else:
        warnings.append(
            "Годовая оценка станции недоступна: основания годовой наработки "
            "или режима агрегатов несопоставимы."
        )
    return result
