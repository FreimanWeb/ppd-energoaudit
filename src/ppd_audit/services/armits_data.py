"""Локальные снимки реестра сети и накопленной наработки; без записи в телеметрию."""

import json
from functools import cache

from ..config import project_root


@cache
def load_network(object_id: str) -> dict | None:
    """Пилотная сеть; идентификатор не используется как произвольный путь."""
    if object_id != "kns54an":
        return None
    path = project_root() / "data" / "armits" / "kns54an.json"
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def runtime_reading(object_id: str, aggregate_id: str) -> dict | None:
    """Показание с датой источника, независимо от даты выбранного режима."""
    path = project_root() / "data" / "aggregate_runtime.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    hours = payload["readings"].get(object_id, {}).get(aggregate_id)
    if hours is None:
        return None
    return {
        "hours": hours,
        "as_of": payload["as_of"],
        "basis": payload["basis"],
        "source": payload["source"],
    }
