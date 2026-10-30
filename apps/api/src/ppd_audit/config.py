"""Загрузка YAML-конфигов в типизированные модели.

Пути ищутся относительно корня проекта (каталог, содержащий config/ и data/).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .spec import ObjectSpec


class FluidProps(BaseModel):
    """Свойства жидкости из config/fluids.yaml."""

    rho: float = Field(..., description="плотность, кг/м³")
    nu: float = Field(..., description="кинематическая вязкость, сСт")
    estimate: bool = False
    note: str = ""


class Constraints(BaseModel):
    """Технологические ограничения из config/constraints.yaml."""

    pressure_limits: dict = Field(default_factory=dict)
    vfd: dict = Field(default_factory=dict)
    operation: dict = Field(default_factory=dict)
    wells: dict = Field(default_factory=dict)
    kpi: dict = Field(default_factory=dict)
    economics: dict = Field(default_factory=dict)


@cache
def project_root() -> Path:
    """Корень репозитория: ближайший предок с config/, data/ и pyproject.toml.

    Не зависит от cwd и от глубины установки пакета (src-layout, editable).
    """
    for ancestor in Path(__file__).resolve().parents:
        if (
            (ancestor / "config").is_dir()
            and (ancestor / "data").is_dir()
            and (ancestor / "pyproject.toml").is_file()
        ):
            return ancestor
    raise RuntimeError(
        "корень репозитория (config/ + data/ + pyproject.toml) не найден "
        f"выше {Path(__file__).resolve()}"
    )


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
    from .spec import load_object_spec

    return load_object_spec(plant_id)
