"""Ввод/вывод универсального спеца: yaml ↔ ObjectSpec, конвертер легаси-паспорта.

Источники спеца:
  * нативный yaml ObjectSpec (config/plants/<id>.yaml, сгенерированный парсером);
  * легаси-паспорт dns7s.yaml (reference_regime/aggregates) — конвертируется;
  * парсер «… расчет.xlsx» (ingest/report_calc.py);
  * ручной ввод (передать готовый ObjectSpec).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .config import project_root
from .spec import ObjectSpec


def _plants_dir() -> Path:
    return project_root() / "config" / "plants"


def save_object_spec(spec: ObjectSpec, path: Path | None = None) -> Path:
    """Сохранить спец в нативный yaml (формат ручной правки)."""
    path = path or (_plants_dir() / f"{spec.id}.yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = spec.model_dump(mode="json", exclude_none=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return path


def load_object_spec(plant_id: str) -> ObjectSpec:
    """Загрузить спец объекта: нативный ObjectSpec или конвертация легаси-паспорта."""
    path = _plants_dir() / f"{plant_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Паспорт объекта не найден: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return ObjectSpec(**raw)
