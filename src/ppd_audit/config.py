"""Загрузка YAML-конфигов в типизированные модели.

Пути ищутся относительно корня проекта (каталог, содержащий config/ и data/).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .models import Constraints, FluidProps, Plant


def project_root() -> Path:
    """Корень проекта = два уровня вверх от src/ppd_audit/config.py."""
    return Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=None)
def load_constraints() -> Constraints:
    """config/constraints.yaml → Constraints."""
    return Constraints(**_load_yaml(project_root() / "config" / "constraints.yaml"))


@lru_cache(maxsize=None)
def load_fluids() -> dict[str, FluidProps]:
    """config/fluids.yaml → {тип воды: FluidProps}."""
    raw = _load_yaml(project_root() / "config" / "fluids.yaml")
    return {name: FluidProps(**props) for name, props in raw["fluids"].items()}


@lru_cache(maxsize=None)
def load_plant(plant_id: str) -> Plant:
    """config/plants/<plant_id>.yaml → Plant."""
    path = project_root() / "config" / "plants" / f"{plant_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Паспорт объекта не найден: {path}")
    return Plant(**_load_yaml(path))


def resolve_fluid(plant: Plant) -> FluidProps:
    """Свойства жидкости объекта: типовые из fluids.yaml, переопределённые паспортом.

    Плотность по замеру в паспорте объекта (поле fluid.rho) имеет приоритет над
    типовым справочником (Методика: ρ задаётся по замеру, а не константой).
    """
    fluids = load_fluids()
    base = fluids.get(plant.fluid.get("type", "пресная"))
    rho = plant.fluid.get("rho", base.rho if base else 1000.0)
    nu = plant.fluid.get("nu", base.nu if base else 1.0)
    # если плотность взята из паспорта-замера — это уже не «оценка»
    estimate = "rho" not in plant.fluid
    return FluidProps(rho=rho, nu=nu, estimate=estimate,
                      note=plant.fluid.get("type", ""))
