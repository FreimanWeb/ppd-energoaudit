"""Справочные сведения к диагностике насосного агрегата.

Правила отклонений из «Таблиц по КНС» считает ``services.diagnostics``
(адресная диагностика с привязкой к модели и источнику). Здесь — то, что
помогает разобрать её результат:
- сравнение УРЭ и КПД с бенчмарками насосов и электродвигателей
  (``data/reference/reference.json``);
- рабочие характеристики ЦНСн из приложения к «Алгоритму определения
  критичных параметров НА»;
- журнал дефектов 1С ТОИР и вероятные причины по тому же алгоритму.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict
from functools import cache
from pathlib import Path

import yaml

from ..config import project_root
from ..core.audit import AuditResult
from ..ingest.toir import read_defects, toir_files
from .diagnostics import DiagnosticReport


def _root() -> Path:
    return project_root()


@cache
def _yaml(path: Path, stamp: int) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@cache
def _json(path: Path, stamp: int) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def toir_config() -> dict:
    path = _root() / "config" / "toir.yaml"
    return _yaml(path, path.stat().st_mtime_ns)


def reference_data() -> dict:
    path = _root() / "data" / "reference" / "reference.json"
    return _json(path, path.stat().st_mtime_ns) if path.is_file() else {}


def _flow_class(label: str, daily: float) -> bool:
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", label.replace(",", "."))]
    if label.startswith("до"):
        return daily <= numbers[0]
    if label.startswith("свыше"):
        return daily > numbers[0]
    return len(numbers) == 2 and numbers[0] < daily <= numbers[1]


def pump_benchmark(audit: AuditResult) -> dict | None:
    """Класс подачи КНС и средневзвешенный УРЭ применяемых и энергоэффективных насосов."""
    block = next(
        (item for item in reference_data().get("pump_benchmark", []) if item["system"] == "ППД"),
        None,
    )
    if block is None:
        return None
    daily = audit.regime.q * 24
    row = next((item for item in block["rows"] if _flow_class(item["class"], daily)), None)
    if row is None:
        return None
    return {
        "daily_flow_m3": daily,
        "class": row["class"],
        "flow_unit": block["flow_unit"],
        "current_pumps": row["current_pumps"],
        "current_sec": row["current_sec"],
        "current_efficiency": row["current_efficiency"]["text"],
        "efficient_pumps": row["efficient_pumps"],
        "efficient_sec": row["efficient_sec"],
        "efficient_efficiency": row["efficient_efficiency"]["text"],
        "sec_fact": audit.sec_fact,
        "gap_to_efficient": audit.sec_fact - row["efficient_sec"],
    }


def _model_key(text: str) -> str:
    return re.sub(r"[^0-9A-ZА-Я]", "", text.upper().replace("Ё", "Е"))


def motor_benchmark(audit: AuditResult) -> dict | None:
    """Строка бенчмарка ЭД той же серии и мощности: применяемый КПД и НДТ."""
    motor = audit.spec.motor if audit.spec else None
    if motor is None or not motor.p_nom:
        return None
    model = _model_key(motor.model or "")
    # Серия: СТДМ и СТД — одно семейство синхронных ЭД, АРМ — асинхронные.
    family = next((name for name in ("СТД", "АРМ", "ВАО", "АП") if name in model), None)
    candidates = [
        (group, item)
        for group in reference_data().get("motor_benchmark", [])
        for item in group["items"]
        if item.get("power_kw") == motor.p_nom
        and (
            family is None or any(family in _model_key(brand) for brand in item["brands"].values())
        )
    ]
    if not candidates:
        return None
    current = [pair for pair in candidates if _model_key(pair[1]["brands"]["current"]) == model]
    exact = [
        pair
        for pair in candidates
        if any(_model_key(brand) == model for brand in pair[1]["brands"].values())
    ]
    group, item = (current or exact or candidates)[0]
    best = item["efficiency"]["best"]
    return {
        "group": group["type"],
        "item": item["id"],
        "power_kw": item["power_kw"],
        "current_brand": item["brands"]["current"],
        "best_brand": item["brands"]["best"],
        "alternatives": [item["brands"]["alternative_1"], item["brands"]["alternative_2"]],
        "current_efficiency_pct": item["efficiency"]["current"]["text"],
        "best_efficiency_pct": best["text"],
        "passport_efficiency_pct": motor.eta_nom * 100 if motor.eta_nom else None,
        "gain_pct": (best["max"] - motor.eta_nom * 100)
        if best.get("max") is not None and motor.eta_nom
        else None,
    }


def pump_range(audit: AuditResult) -> dict:
    """Рабочие характеристики ЦНСн из приложения к алгоритму, если типоразмер есть."""
    pump = audit.spec.pump if audit.spec else None
    rows = reference_data().get("critical_parameters", {}).get("pump_ranges", [])
    if pump is None or not pump.q_nom:
        return {"found": False, "note": "Нет номинальной подачи насоса."}
    sizes = sorted({row["size"] for row in rows})
    match = re.search(r"ЦНС\s*(\d+)", pump.model or "")
    size = f"ЦНС {match.group(1)}" if match else None
    candidates = [row for row in rows if row["size"] == size]
    near = [row for row in candidates if pump.h_nom and abs(row["head_m"] - pump.h_nom) <= 1]
    if near:
        row = near[0]
        return {
            "found": True,
            **row,
            "q_in_range": row["q_min_m3h"] <= audit.regime.q <= row["q_max_m3h"],
        }
    return {
        "found": False,
        "note": (
            f"Типоразмера {pump.model} в приложении нет: оно охватывает "
            f"{', '.join(sizes)} с напором до 600 м. Рабочая область оценена как "
            "0,7–1,2·Q_ном по «Таблицам по КНС»; границы требуют сверки с паспортом."
        ),
        "q_min_m3h": 0.7 * pump.q_nom,
        "q_max_m3h": 1.2 * pump.q_nom,
        "q_in_range": 0.7 * pump.q_nom <= audit.regime.q <= 1.2 * pump.q_nom,
    }


def defect_history(plant_code: str, aggregate_code: str, limit: int = 12) -> dict | None:
    """Журнал дефектов 1С ТОИР с вероятными причинами по алгоритму."""
    root = _root()
    path = toir_files(root / "data" / "toir", root / "config" / "toir.yaml").get((
        plant_code,
        aggregate_code,
    ))
    if path is None:
        return None
    defects = read_defects(path)
    mapping = toir_config().get("defect_algorithm") or {}
    algorithm = {
        row["id"]: row for row in reference_data().get("critical_parameters", {}).get("rows", [])
    }
    kinds = Counter(item.kind or "не указан" for item in defects)
    last = {}
    for item in defects:
        if item.kind not in last and item.detected_at:
            last[item.kind] = item.detected_at
    by_kind = []
    for kind, count in kinds.most_common():
        rows = [algorithm[number] for number in mapping.get(kind, []) if number in algorithm]
        by_kind.append({
            "kind": kind,
            "count": count,
            "last": last[kind].date().isoformat() if kind in last else None,
            "algorithm": rows,
        })
    return {
        "source": path.name,
        "element": next((item.element for item in defects if item.element), ""),
        "total": len(defects),
        "first": min((d.detected_at for d in defects if d.detected_at), default=None),
        "last": max((d.detected_at for d in defects if d.detected_at), default=None),
        "high": sum(item.criticality == "Высокая" for item in defects),
        "by_kind": by_kind,
        "recent": [
            {
                "number": item.number,
                "date": item.detected_at.date().isoformat() if item.detected_at else None,
                "defect": item.defect,
                "kind": item.kind,
                "cause": item.cause,
                "criticality": item.criticality,
                "status": item.status,
            }
            for item in defects[:limit]
        ],
    }


def recommendations(
    audit: AuditResult, plant_code: str, aggregate_code: str, diagnostics: DiagnosticReport
) -> dict:
    history = defect_history(plant_code, aggregate_code)
    if history:
        for key in ("first", "last"):
            history[key] = history[key].date().isoformat() if history[key] else None
    pump = audit.spec.pump if audit.spec else None
    motor = audit.spec.motor if audit.spec else None
    regime = audit.regime
    return {
        "object_id": plant_code,
        "aggregate_id": aggregate_code,
        "pump_model": pump.model if pump else None,
        "motor_model": motor.model if motor else None,
        "values": {
            "q_m3h": regime.q,
            "q_nom_m3h": pump.q_nom if pump else None,
            "eta_unit": regime.eta_unit,
            "eta_nom": regime.eta_nom,
            "p_out_mpa": regime.p_out,
            "p_bg_mpa": regime.p_bg,
        },
        "diagnostics": asdict(diagnostics),
        "pump_benchmark": pump_benchmark(audit),
        "motor_benchmark": motor_benchmark(audit),
        "pump_range": pump_range(audit),
        "defects": history,
        "sources": [
            "Бенчмаркинпо насосам.xlsx, бенчмаркет электродвигателей.xlsx",
            "Алгоритм определения критичных параметров НА с приложением по НРХ (2023)",
            "1С ТОИР: журналы выявленных дефектов",
        ],
    }
