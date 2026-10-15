"""Сценарный баланс КНС → сеть → скважины без подмены измеренных данных."""

from __future__ import annotations

import math
import re
from collections import defaultdict

from ..core.audit import AuditResult
from ..core.hydraulics import darcy_weisbach_dp, velocity
from ..core.pump import KnsDecomposition


_OPTIONS = {
    "roughness_mm": (0.1, 0.0, 5.0, "Шероховатость", "мм"),
    "well_depth_m": (1800.0, 1.0, 10000.0, "Длина ствола скважины", "м"),
    "well_diameter_mm": (62.0, 10.0, 500.0, "Внутренний диаметр НКТ", "мм"),
    "local_resistance_k": (2.0, 0.0, 1000.0, "Суммарное местное сопротивление", ""),
    "useful_pressure_mpa": (3.0, 0.0, 100.0, "Требуемое давление без геодезии", "МПа"),
    "elevation_change_m": (0.0, -1000.0, 1000.0, "Превышение скважин над БГ", "м"),
}


def _name(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip()).upper()
    return re.sub(r"КНС\s+54\b", "КНС-54", normalized)


def _well(value: str) -> str | None:
    match = re.fullmatch(r"СКВ\.?\s*(\S+)", _name(value))
    return match.group(1).split("/")[0] if match else None


def _parameters(options: dict | None) -> dict:
    supplied = options or {}
    unknown = supplied.keys() - _OPTIONS.keys()
    if unknown:
        raise ValueError(f"Неизвестные параметры сети: {', '.join(sorted(unknown))}")
    values = {}
    for key, (default, minimum, maximum, _, _) in _OPTIONS.items():
        raw = supplied.get(key, default)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"{key}: требуется число")
        value = float(raw)
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f"{key}: допустимый диапазон {minimum}…{maximum}")
        values[key] = value
    return values


def _paths(network: dict, warnings: list[str]) -> tuple[dict, dict, set[str]]:
    """Один путь на скважину; интервалы трубы остаются последовательными."""
    groups = defaultdict(list)
    for segment in network["segments"]:
        if (
            segment["purpose"] not in {"Внутриплощадочный", "Подводящий"}
            and not _name(segment["to_node"]).startswith("БГ-")
            and not _name(segment["from_node"]).startswith(("КНС-53", "КНС 53"))
        ):
            groups[str(segment["pipeline_id"])].append(segment)
    by_name = defaultdict(list)
    by_end = defaultdict(list)
    for pid, sections in groups.items():
        by_name[_name(sections[0]["pipeline_name"])].append(pid)
        by_end[_name(sections[0]["to_node"])].append(pid)
    parents = {}
    synthetic_roots = set()
    for pid, sections in groups.items():
        origin = _name(sections[0]["from_node"])
        candidates = by_name.get(origin) or by_end.get(origin, [])
        candidates = [candidate for candidate in candidates if candidate != pid]
        if len(candidates) > 1:
            raise ValueError(f"Неоднозначное соединение трубопровода {pid}: {candidates}")
        parents[pid] = candidates[0] if candidates else None
        if not candidates and origin != "КНС-54":
            synthetic_roots.add(pid)

    def path(pid: str) -> list[str]:
        result = []
        while pid is not None:
            if pid in result:
                raise ValueError(f"Цикл в сети: {' → '.join([*result, pid])}")
            result.append(pid)
            pid = parents[pid]
        return list(reversed(result))

    # Check even unused branches: a cycle must not disappear with zero assigned demand.
    all_paths = {pid: path(pid) for pid in groups}
    terminal = defaultdict(list)
    for pid, sections in groups.items():
        well = _well(sections[0]["to_node"])
        if well:
            terminal[well].append(pid)
    wells = sorted({_name(str(well["id"])).split("/")[0] for well in network["wells"]})
    paths = {}
    for well in wells:
        candidates = terminal.get(well, [])
        if len(candidates) > 1:
            raise ValueError(f"Несколько входящих трубопроводов у скважины {well}")
        paths[well] = all_paths[candidates[0]] if candidates else []
    unmatched = [well for well, ids in paths.items() if not ids]
    if unmatched:
        warnings.append(
            "Синтетическое подключение без известной длины водовода: " + ", ".join(unmatched)
        )
    used = {pid for ids in paths.values() for pid in ids}
    disconnected = sorted(used & synthetic_roots)
    if disconnected:
        warnings.append(
            "Входы ветвей синтетически подключены к БГ без добавочной длины: "
            + ", ".join(disconnected)
        )
    excluded = sorted(groups.keys() - used)
    if excluded:
        warnings.append(
            "Без подтверждённого спроса скважин, исключены из downstream: " + ", ".join(excluded)
        )
    return dict(groups), paths, synthetic_roots


def build_network_loss_map(audit: AuditResult, network: dict, options: dict | None = None) -> dict:
    """Разложить мощность на БГ, сохранив upstream баланс выбранного агрегата.

    Все расходы ветвей синтетические: один работающий агрегат питает поровну
    уникальные скважины; реестровые Q/P с неизвестными единицами не используются.
    """
    values = _parameters(options)
    warnings = list(network.get("warnings", []))
    result = {
        "status": "unavailable",
        "title": "Полная цепочка КНС-54 · сценарий",
        "input_kw": None,
        "useful_kw": None,
        "total_loss_kw": None,
        "balance_error_kw": None,
        "items": [],
        "segments": [],
        "wells": [],
        "assumptions": [
            {
                "parameter": key,
                "label": definition[3],
                "value": values[key],
                "unit": definition[4],
                "provenance": "synthetic",
                "basis": "Сценарное допущение; требуется подтверждение измерениями/паспортом",
            }
            for key, definition in _OPTIONS.items()
        ],
        "warnings": warnings,
        "network": {
            "pipeline_count": 0,
            "segment_count": 0,
            "total_length_m": 0.0,
            "well_count": 0,
            "excluded_pipeline_count": 0,
            "synthetic_connection_count": 0,
            "source_file": network.get("source_file"),
            "exported_at": network.get("exported_at"),
        },
        "options": values,
    }
    regime = audit.regime
    if network.get("object_id") != "kns54an":
        warnings.append("Сценарий поддерживает только сеть КНС-54.")
        return result
    observed = [regime.q, regime.rho, regime.p_electric, regime.p_hydraulic]
    if not all(math.isfinite(value) and value > 0 for value in observed):
        warnings.append("Нет положительного конечного расхода, плотности или мощности агрегата.")
        return result
    if not isinstance(audit.decomposition, KnsDecomposition):
        warnings.append("Для полного баланса нужна декомпозиция КНС с давлением на БГ.")
        return result
    available_kw = audit.decomposition.p_bg_useful
    efficiencies = [
        0.97 if audit.spec and audit.spec.vfd else 1.0,
        audit.eta_motor_real,
        audit.spec.transmission.efficiency if audit.spec else None,
    ]
    if any(
        not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 1
        for value in efficiencies
    ):
        warnings.append("Нет корректных КПД ПЧ, ЭД или передачи для физической цепочки.")
        return result
    after_vfd = regime.p_electric * efficiencies[0]
    after_motor = after_vfd * efficiencies[1]
    shaft = after_motor * efficiencies[2]
    for parameter, label, value, unit, provenance, basis in [
        ("density_kgm3", "Плотность", regime.rho, "кг/м³", "calculated", "Выбранный режим"),
        (
            "source_flow_m3h",
            "Расход выбранного агрегата",
            regime.q,
            "м³/ч",
            "calculated",
            "Выбранный режим; другие агрегаты в сценарии выключены",
        ),
        (
            "vfd_efficiency",
            "КПД ПЧ",
            efficiencies[0],
            "",
            "synthetic",
            "Принято 0,97 при наличии ПЧ, иначе 1",
        ),
        (
            "motor_efficiency",
            "КПД ЭД",
            efficiencies[1],
            "",
            "calculated",
            "Расчётный КПД ЭД из выбранного аудита",
        ),
        (
            "transmission_efficiency",
            "КПД передачи",
            efficiencies[2],
            "",
            "calculated",
            "Паспорт выбранного агрегата",
        ),
    ]:
        result["assumptions"].append({
            "parameter": parameter,
            "label": label,
            "value": value,
            "unit": unit,
            "provenance": provenance,
            "basis": basis,
        })
    upstream_losses = [
        ("Потери ПЧ", regime.p_electric - after_vfd),
        ("Потери ЭД", after_vfd - after_motor),
        ("Потери передачи", after_motor - shaft),
        ("Потери насоса", shaft - regime.p_hydraulic),
        ("Гидравлика насос→БГ", regime.p_hydraulic - available_kw),
    ]
    if (
        not math.isfinite(available_kw)
        or available_kw <= 0
        or any(power < -1e-8 for _, power in upstream_losses)
    ):
        warnings.append("Физическая цепочка агрегата содержит отрицательные потери/мощность БГ.")
        return result
    try:
        groups, paths, synthetic_roots = _paths(network, warnings)
    except (KeyError, ValueError) as exc:
        warnings.append(str(exc))
        return result
    if not paths:
        warnings.append("Нет скважин для распределения расхода.")
        return result

    warnings.extend([
        "Работает только выбранный агрегат; расход распределён поровну по уникальным скважинам.",
        "Точки врезок неизвестны: учтена вся длина родительской трубы; потери могут быть завышены.",
        "Внутриплощадочные, подводящие и участок до БГ исключены: насос→БГ уже учтён.",
        "Для соединений названия «КНС 54» и «КНС-54» приняты эквивалентными.",
        "Реестровые Q/P не использованы: единицы и дата измерений не подтверждены.",
        "Требуемое давление и геодезический перепад определяют полезную работу; "
        "геодезия добавлена отдельно как ρgΔz, а не потеря.",
        "Штуцирование — остаток баланса сценария, а не измеренная потеря на штуцере.",
        "Накопленная наработка не используется; годовые энергия и экономия здесь не оцениваются.",
    ])
    result["input_kw"] = regime.p_electric
    q_well = regime.q / len(paths)
    result["assumptions"].append({
        "parameter": "well_flow_m3h",
        "label": "Расход каждой скважины",
        "value": q_well,
        "unit": "м³/ч",
        "provenance": "synthetic",
        "basis": "Расход одного агрегата поровну между уникальными скважинами, без учёта пластов",
    })
    available_dp = available_kw * 3.6 / regime.q
    demands = defaultdict(int)
    for ids in paths.values():
        for pid in ids:
            demands[pid] += 1
    pipe_dp = defaultdict(float)
    pipe_kw = 0.0
    nu = audit.spec.regime.nu if audit.spec and audit.spec.regime else None
    if nu is None:
        nu = 1.0
        result["assumptions"].append({
            "parameter": "viscosity_cst",
            "label": "Кинематическая вязкость",
            "value": nu,
            "unit": "сСт",
            "provenance": "synthetic",
            "basis": "Вязкость отсутствует в исходном режиме; принято 1 сСт",
        })
    if not isinstance(nu, (int, float)) or not math.isfinite(nu) or nu <= 0:
        warnings.append("Нет положительной кинематической вязкости.")
        return result
    for pid, count in demands.items():
        sections = sorted(groups[pid], key=lambda section: section["start_m"])
        previous_end = None
        for section in sections:
            length = section["length_m"]
            diameter = section["outer_diameter_mm"] - 2 * section["wall_thickness_mm"]
            start, end = section["start_m"], section["end_m"]
            geometry = [length, diameter, start, end]
            if not all(math.isfinite(value) for value in geometry) or length <= 0 or diameter <= 0:
                warnings.append(f"Некорректная геометрия участка {section['id']}.")
                return result
            if end <= start or abs(end - start - length) > 0.01:
                warnings.append(f"Длина не совпадает с интервалом участка {section['id']}.")
                return result
            if previous_end is not None and abs(start - previous_end) > 0.01:
                warnings.append(f"Разрыв или перекрытие интервалов трубопровода {pid}.")
                return result
            previous_end = end
            q = q_well * count
            dp = darcy_weisbach_dp(
                q, length, diameter / 1000, values["roughness_mm"] / 1000, regime.rho, nu
            )
            power = dp * q / 3.6
            pipe_dp[pid] += dp
            pipe_kw += power
            result["segments"].append({
                "id": section["id"],
                "pipeline_id": pid,
                "name": section["pipeline_name"],
                "length_m": length,
                "inner_diameter_mm": diameter,
                "flow_m3h": q,
                "pressure_loss_mpa": dp,
                "power_kw": power,
                "provenance": "synthetic",
                "basis": "Darcy–Weisbach; геометрия реестра, допущение мм/м и Dнар−2s "
                "без покрытия; синтетический расход/шероховатость",
                "source_sheet": section["source_sheet"],
                "source_row": section["source_row"],
            })

    well_d = values["well_diameter_mm"] / 1000
    well_dp = darcy_weisbach_dp(
        q_well,
        values["well_depth_m"],
        well_d,
        values["roughness_mm"] / 1000,
        regime.rho,
        nu,
    )
    local_dp = values["local_resistance_k"] * regime.rho * velocity(q_well, well_d) ** 2 / 2e6
    useful_dp = (
        values["useful_pressure_mpa"] + regime.rho * 9.81 * values["elevation_change_m"] / 1e6
    )
    if useful_dp < 0:
        warnings.append(
            "Суммарное требуемое давление отрицательно; внешняя энергия гравитации не моделируется."
        )
        return result
    feasible = True
    choke_kw = 0.0
    for well, ids in paths.items():
        branch_dp = sum(pipe_dp[pid] for pid in ids)
        required_dp = branch_dp + well_dp + local_dp + useful_dp
        deficit = max(required_dp - available_dp, 0.0)
        choke = None if deficit > 1e-9 else (available_dp - required_dp) * q_well / 3.6
        if choke is None:
            feasible = False
        else:
            choke_kw += choke
        result["wells"].append({
            "id": well,
            "flow_m3h": q_well,
            "pipe_loss_kw": branch_dp * q_well / 3.6,
            "well_loss_kw": well_dp * q_well / 3.6,
            "armature_loss_kw": local_dp * q_well / 3.6,
            "choke_loss_kw": choke,
            "useful_kw": useful_dp * q_well / 3.6,
            "required_pressure_mpa": required_dp,
            "available_pressure_mpa": available_dp,
            "deficit_mpa": deficit,
            "deficit_kw": deficit * q_well / 3.6,
            "path_pipeline_ids": ids,
            "synthetic_connection": not ids or bool(set(ids) & synthetic_roots),
            "provenance": "synthetic",
        })

    def item(name: str, power: float, category: str, provenance: str, basis: str) -> dict:
        return {
            "name": name,
            "power_kw": power,
            "share": power / regime.p_electric,
            "category": category,
            "provenance": provenance,
            "basis": basis,
        }

    result["items"] = [
        item(
            name,
            power,
            "потеря",
            "calculated",
            "Баланс ступеней; КПД ЭД расчётный, передачи паспортный, ПЧ 0,97 при наличии",
        )
        for name, power in upstream_losses
    ] + [
        item(
            "Трение в трубопроводах",
            pipe_kw,
            "потеря",
            "synthetic",
            "Darcy–Weisbach по участкам; общий участок учтён один раз",
        ),
        item(
            "Арматура сети и скважин",
            local_dp * regime.q / 3.6,
            "потеря",
            "synthetic",
            "K·ρ·v²/2; K задан на путь каждой скважины",
        ),
        item(
            "Трение в стволах скважин",
            well_dp * regime.q / 3.6,
            "потеря",
            "synthetic",
            "Darcy–Weisbach; синтетические длина и внутренний диаметр НКТ",
        ),
    ]
    result["network"].update(
        pipeline_count=len(demands),
        segment_count=len(result["segments"]),
        total_length_m=sum(section["length_m"] for section in result["segments"]),
        well_count=len(paths),
        excluded_pipeline_count=len({str(row["pipeline_id"]) for row in network["segments"]})
        - len(demands),
        synthetic_connection_count=len(set(demands) & synthetic_roots)
        + sum(not ids for ids in paths.values()),
    )
    if not feasible:
        result["status"] = "infeasible"
        warnings.append(
            "Распределение расходов невыполнимо: части скважин не хватает напора. "
            "Потери не масштабировались; итоговый баланс не заявлен."
        )
        return result
    useful_kw = useful_dp * regime.q / 3.6
    result["items"].extend([
        item(
            "Штуцирование скважин",
            choke_kw,
            "потеря",
            "synthetic",
            "Остаточный избыток напора после сопротивлений и полезного эквивалента",
        ),
        item(
            "Полезная закачка",
            useful_kw,
            "полезная",
            "synthetic",
            "Расход × поверхностный эквивалент требуемого давления; не потеря",
        ),
    ])
    total_loss_kw = sum(
        part["power_kw"] for part in result["items"] if part["category"] == "потеря"
    )
    result.update(
        status="scenario",
        useful_kw=useful_kw,
        total_loss_kw=total_loss_kw,
        balance_error_kw=regime.p_electric - useful_kw - total_loss_kw,
    )
    return result


def build_network_analysis(
    audit: AuditResult,
    network: dict,
    options: dict | None = None,
    intervention: str | None = None,
) -> dict:
    """Сравнить модельные мероприятия при неизменной полезной подаче.

    Снижение сопротивления само по себе не экономит входную мощность: для
    каждого мероприятия предполагается перенастройка насоса/регулирования.
    """
    definitions = {
        "reduce_head": (
            "Снизить избыточный напор",
            "Штуцирование скважин",
            "Настроить подачу напора по наиболее требовательной ветви.",
            None,
        ),
        "clean_pipes": (
            "Очистить трубы и НКТ с настройкой напора",
            "Трение в трубопроводах",
            "Вдвое снизить сценарную шероховатость труб и НКТ, затем настроить напор.",
            "roughness_mm",
        ),
        "reduce_local_resistance": (
            "Снизить местные сопротивления с настройкой напора",
            "Арматура сети и скважин",
            "Вдвое снизить сценарный K арматуры, затем настроить напор.",
            "local_resistance_k",
        ),
    }
    if intervention is not None and (
        not isinstance(intervention, str) or intervention not in definitions
    ):
        raise ValueError("Неизвестное мероприятие сети")
    baseline = build_network_loss_map(audit, network, options)
    baseline.update(measures=[], comparison=None)
    if baseline["status"] != "scenario":
        if intervention is not None:
            raise ValueError("Мероприятие неприменимо: нет выполнимого исходного баланса")
        return baseline

    assumptions = [
        "Прогноз модели на синтетических параметрах, а не достигнутая экономия.",
        "Мероприятия — альтернативы одному исходному режиму; экономия не суммируется.",
        "Расход выбранного агрегата и полезное требуемое давление сохранены.",
        "Насос/регулирование перенастроены на максимальное требуемое давление ветвей.",
        "КПД ПЧ, ЭД, передачи, насоса и доля потерь насос→БГ приняты постоянными.",
        "Применимость настройки и сохранение КПД требуют проверки характеристик оборудования.",
        "Без настройки напора снижение сопротивлений перейдёт в штуцирование без экономии.",
    ]
    before = {key: baseline[key] for key in ("input_kw", "total_loss_kw", "useful_kw")}
    available_dp = baseline["wells"][0]["available_pressure_mpa"]
    for measure_id, (name, loss_name, description, parameter) in definitions.items():
        candidate_options = dict(baseline["options"])
        if parameter:
            if candidate_options[parameter] == 0:
                continue
            candidate_options[parameter] *= 0.5
        candidate = build_network_loss_map(audit, network, candidate_options)
        if candidate["status"] != "scenario":
            continue
        required_dp = max(well["required_pressure_mpa"] for well in candidate["wells"])
        ratio = required_dp / available_dp
        input_kw = baseline["input_kw"] * ratio
        saving_kw = baseline["input_kw"] - input_kw
        if saving_kw <= 1e-8:
            continue

        # Fixed efficiencies scale upstream power; downstream delivery stays unchanged.
        items = [dict(part) for part in candidate["items"]]
        for part in items[:5]:
            part["power_kw"] *= ratio
            part["provenance"] = "synthetic"
            part["basis"] = "Прогноз при перенастройке напора и постоянных КПД upstream"
        choke_kw = sum(
            max(required_dp - well["required_pressure_mpa"], 0.0) * well["flow_m3h"] / 3.6
            for well in candidate["wells"]
        )
        for part in items:
            if part["name"] == "Штуцирование скважин":
                part["power_kw"] = choke_kw
            part["share"] = part["power_kw"] / input_kw if input_kw else 0.0
        total_loss_kw = sum(part["power_kw"] for part in items if part["category"] == "потеря")
        after = {
            "input_kw": input_kw,
            "total_loss_kw": total_loss_kw,
            "useful_kw": candidate["useful_kw"],
            "balance_error_kw": input_kw - total_loss_kw - candidate["useful_kw"],
            "items": items,
        }
        saving_pct = saving_kw / baseline["input_kw"] * 100
        measure = {
            "id": measure_id,
            "name": name,
            "loss_name": loss_name,
            "description": description,
            "saving_kw": saving_kw,
            "saving_pct": saving_pct,
            "baseline_input_kw": baseline["input_kw"],
            "after_input_kw": input_kw,
            "required_pressure_mpa": required_dp,
            "options": candidate_options,
            "assumptions": list(assumptions),
        }
        baseline["measures"].append(measure)
        if intervention == measure_id:
            baseline["comparison"] = {
                "measure_id": measure_id,
                "name": name,
                "saving_kw": saving_kw,
                "saving_pct": saving_pct,
                "before": before,
                "after": after,
                "assumptions": list(assumptions),
            }
    baseline["measures"].sort(key=lambda measure: measure["saving_kw"], reverse=True)
    if intervention is not None and baseline["comparison"] is None:
        raise ValueError("Мероприятие неприменимо: нет положительного модельного эффекта")
    return baseline
