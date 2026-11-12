"""Локальные снимки реестра сети и накопленной наработки; без записи в телеметрию."""

import json
import re
from functools import cache

import yaml

from ..config import project_root


_OBJECT_ID = re.compile(r"[A-Za-z0-9_-]+")


@cache
def load_network(object_id: str) -> dict | None:
    """Снимок реестра сети объекта: data/armits/<object_id>.json, если подключён."""
    from .demo import DEMO_OBJECT_ID

    if object_id == DEMO_OBJECT_ID:
        from .demo import demo_network

        return demo_network()
    if _OBJECT_ID.fullmatch(object_id) is None:
        return None
    path = project_root() / "data" / "armits" / f"{object_id}.json"
    if not path.is_file():
        return None
    network = json.loads(path.read_text(encoding="utf-8"))
    config_path = project_root() / "config" / "network.yaml"
    if config_path.is_file():
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        binding = (config.get("plants") or {}).get(object_id, {})
        for key in ("station_nodes", "technical_place_code"):
            if key in binding:
                network[key] = binding[key]
    network.update(well_rates(object_id))
    return network


def well_rates(object_id: str) -> dict:
    """Фактическая закачка скважин по карточкам АРМИТС, м³/ч (среднекалендарная).

    Пустой словарь, если карточек объекта нет: тогда сценарий делит расход
    поровну, как раньше.
    """
    from . import catalog, network_view

    paths = catalog.source_paths(project_root())
    plant = network_view.plant_network(paths["network"], paths["network_config"], object_id)
    if plant is None:
        return {}
    cards = network_view.cards(plant)
    months = [card.last_month.month for card in cards if card.last_month]
    return {
        "well_rates": {
            card.well: card.last_month.mean_rate_m3h or 0.0 for card in cards if card.last_month
        },
        "well_rates_month": max(months).strftime("%m.%Y") if months else None,
    }


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
