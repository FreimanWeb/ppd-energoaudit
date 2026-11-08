"""Справочная шероховатость труб по типу, материалу и покрытию.

В реестре трубопроводов шероховатости нет, поэтому она берётся из
``config/hydraulic_reference.yaml``: правила сверху вниз, первое подходящее.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml


NO_COATING = {"", "нет", "-", "—", "отсутствует"}


@dataclass(frozen=True)
class RoughnessRule:
    id: str
    label: str
    value_mm: float
    range_mm: tuple[float, float]
    sources: tuple[str, ...]
    pipe_types: tuple[str, ...] = ()
    materials: tuple[str, ...] = ()
    coatings: tuple[str, ...] = ()
    any_coating: bool = False

    @property
    def value_m(self) -> float:
        return self.value_mm / 1000.0

    def matches(self, pipe_type: str, material: str, coating: str) -> bool:
        conditions = []
        if self.pipe_types or self.materials:
            conditions.append(
                pipe_type.strip().upper() in {item.upper() for item in self.pipe_types}
                or any(item.lower() in material.lower() for item in self.materials)
            )
        if self.coatings:
            conditions.append(any(item.lower() in coating.lower() for item in self.coatings))
        if self.any_coating:
            conditions.append(coating.strip().lower() not in NO_COATING)
        return all(conditions)


@dataclass(frozen=True)
class HydraulicReference:
    rules: tuple[RoughnessRule, ...]
    tubing: RoughnessRule
    sources: dict[str, str]

    def roughness(
        self, pipe_type: str = "", material: str = "", coating: str = ""
    ) -> RoughnessRule:
        for rule in self.rules:
            if rule.matches(pipe_type or "", material or "", coating or ""):
                return rule
        return self.rules[-1]

    def as_dict(self) -> dict:
        def rule(item: RoughnessRule) -> dict:
            return {
                "id": item.id,
                "label": item.label,
                "value_mm": item.value_mm,
                "range_mm": list(item.range_mm),
                "sources": [self.sources.get(key, key) for key in item.sources],
            }

        return {
            "roughness": [rule(item) for item in self.rules],
            "tubing": rule(self.tubing),
        }


def _rule(raw: dict) -> RoughnessRule:
    return RoughnessRule(
        id=str(raw["id"]),
        label=str(raw["label"]),
        value_mm=float(raw["value_mm"]),
        range_mm=tuple(float(value) for value in raw.get("range_mm") or [raw["value_mm"]] * 2),
        sources=tuple(raw.get("sources") or ()),
        pipe_types=tuple(raw.get("pipe_types") or ()),
        materials=tuple(raw.get("materials") or ()),
        coatings=tuple(raw.get("coatings") or ()),
        any_coating=bool(raw.get("any_coating")),
    )


def default_reference_path() -> Path:
    from ..config import project_root

    return project_root() / "config" / "hydraulic_reference.yaml"


@cache
def _load(path: Path, stamp: int) -> HydraulicReference:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = tuple(_rule(item) for item in raw.get("roughness") or [])
    if not rules:
        raise ValueError(f"{path.name}: нет правил шероховатости")
    return HydraulicReference(
        rules=rules,
        tubing=_rule(raw["tubing"]),
        sources={
            key: " ".join(str(value).split()) for key, value in (raw.get("sources") or {}).items()
        },
    )


def hydraulic_reference(path: Path | None = None) -> HydraulicReference:
    path = path or default_reference_path()
    return _load(path, path.stat().st_mtime_ns)
