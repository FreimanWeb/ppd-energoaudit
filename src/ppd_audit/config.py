"""Загрузка YAML-конфигов в типизированные модели.

Пути ищутся относительно корня проекта (каталог, содержащий config/ и data/).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml

from .models import Constraints, FluidProps
from .spec import ObjectSpec


def project_root() -> Path:
    """Корень проекта = два уровня вверх от src/ppd_audit/config.py."""
    return Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@cache
def load_constraints() -> Constraints:
    """config/constraints.yaml → Constraints."""
    return Constraints(**_load_yaml(project_root() / "config" / "constraints.yaml"))


@cache
def load_fluids() -> dict[str, FluidProps]:
    """config/fluids.yaml → {тип воды: FluidProps}."""
    raw = _load_yaml(project_root() / "config" / "fluids.yaml")
    return {name: FluidProps(**props) for name, props in raw["fluids"].items()}


@cache
def load_plant(plant_id: str) -> ObjectSpec:
    """Совместимый псевдоним нативного загрузчика паспорта объекта."""
    from .spec_io import load_object_spec

    return load_object_spec(plant_id)
