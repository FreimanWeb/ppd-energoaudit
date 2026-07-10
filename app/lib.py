"""Data-слой Streamlit-приложения: кешируемые обёртки над расчётным ядром.

Отделяет UI от ядра: страницы вызывают только функции отсюда.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Пакет лежит в src/ — добавляем в путь при запуске `streamlit run app/main.py`
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from ppd_audit.config import load_constraints           # noqa: E402
from ppd_audit.core.audit import AuditResult, audit_aggregate  # noqa: E402
from ppd_audit.spec import ObjectSpec                    # noqa: E402
from ppd_audit.spec_io import load_object_spec           # noqa: E402
from ppd_audit.verify.runner import run_verification     # noqa: E402

WATER_ORDER = ["пресная", "агрессивная", "пластовая"]


@st.cache_data(show_spinner=False)
def list_object_ids() -> list[str]:
    """Все объекты из config/plants/*.yaml, для которых грузится спец."""
    ids = []
    for p in sorted((_ROOT / "config" / "plants").glob("*.yaml")):
        try:
            load_object_spec(p.stem)
            ids.append(p.stem)
        except Exception:
            continue
    return ids


@st.cache_data(show_spinner=False)
def get_object(object_id: str) -> ObjectSpec:
    return load_object_spec(object_id)


@st.cache_data(show_spinner=False)
def object_index() -> list[dict]:
    """Список объектов с метаданными для выбора/фильтра."""
    out = []
    for oid in list_object_ids():
        o = get_object(oid)
        out.append({"id": oid, "name": o.name, "water": o.water_type.value,
                    "branch": o.branch.value, "n_agg": len(o.working_aggregates())})
    return out


@st.cache_data(show_spinner=False)
def get_audit(object_id: str, aggregate_id: str) -> AuditResult:
    obj = get_object(object_id)
    return audit_aggregate(obj.aggregate(aggregate_id), obj.branch)


@st.cache_data(show_spinner=True)
def get_verification() -> dict:
    """Двусторонняя сверка модель↔xlsx. Возвращает строки как dict."""
    res = run_verification(save_specs=False)
    from ppd_audit.verify.compare import row_to_dict
    return {"rows": [row_to_dict(r) for r in res["rows"]],
            "summary": res["summary"], "errors": res["errors"]}


@st.cache_data(show_spinner=False)
def tariff() -> float:
    return load_constraints().economics.get("tariff_rub_kwh", 4.68)


@st.cache_data(show_spinner=False)
def get_topology(object_id: str) -> dict | None:
    """As-built технологическая схема объекта (config/topology/<id>.yaml), если задана.

    Отдельный конфиг (узлы/трубопроводы) — не часть core-спеки, поэтому добавление
    топологии не влияет на расчётное ядро и его тесты.
    """
    import yaml
    p = _ROOT / "config" / "topology" / f"{object_id}.yaml"
    if not p.exists():
        return None
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def constraints():
    return load_constraints()
