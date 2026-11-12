"""Гидравлика разводящей сети: от блок-гребёнки до устья нагнетательных скважин.

Подведённая к блок-гребёнке мощность расходуется в сети на три статьи:

- трение в водоводах — рассчитывается по геометрии участков (Дарси — Вейсбах);
- прочие потери в сети — разность измеренного перепада «БГ — устье до
  штуцера» и трения: задвижки и регуляторы на ВРП и БГ, перепад отметок,
  расхождение приборов;
- штуцеры на устье — разность давлений до и после штуцера.

Для дерева с одним источником сумма по скважинам q_i·Δp_i равна сумме по
участкам q_уч·Δp_уч, поэтому мощность сети раскладывается по скважинам без
потерь и двойного счёта.

Допущения расчёта трения:

- место врезки отвода по длине магистрали в реестре не указано, поэтому
  расход отвода проходит всю длину магистрали — оценка трения сверху;
- геодезических отметок в реестре нет, перепад высот относится к прочим
  потерям;
- шероховатость задана по типу трубы и внутреннему покрытию.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .. import units
from ..ingest.pipelines import Pipeline, PipeSection
from . import hydraulics
from .roughness import RoughnessRule, hydraulic_reference


DISTRIBUTION = "Разводящий"

FLAG_NO_PIPELINE = "водовода нет в реестре"
FLAG_NO_TRUNK = "магистрали нет в реестре"
FLAG_HEAD_ABOVE_BG = "давление на устье выше, чем на БГ"
FLAG_CHOKE_REVERSED = "давление после штуцера выше, чем до него"
FLAG_FRICTION_CAPPED = "расчётное трение больше замеренного перепада"
MEASUREMENT_FLAGS = (FLAG_HEAD_ABOVE_BG, FLAG_CHOKE_REVERSED)


def water_viscosity_cst(temperature_c: float) -> float:
    """Кинематическая вязкость воды, сСт, по формуле Пуазейля."""
    t = temperature_c
    return 1.78 / (1.0 + 0.0337 * t + 0.000221 * t * t)


def section_roughness_m(section: PipeSection) -> float:
    """Справочная эквивалентная шероховатость участка, м (см. ``core.roughness``)."""
    return section_roughness(section).value_m


def section_roughness(section: PipeSection) -> RoughnessRule:
    return hydraulic_reference().roughness(
        section.pipe_type, section.material, section.inner_coating
    )


@dataclass(frozen=True)
class Fluid:
    rho: float  # кг/м³
    nu_cst: float  # сСт


@dataclass(frozen=True)
class WellMeasurement:
    """Измеренный режим скважины для расчёта сети."""

    well: str
    q_m3h: float  # среднекалендарный расход, м³/ч
    annual_volume_m3: float
    p_before_choke_mpa: float | None
    p_after_choke_mpa: float | None


@dataclass
class WellPath:
    well: str
    pipelines: list[Pipeline]
    complete: bool

    @property
    def length_m(self) -> float:
        return sum(pipeline.active_length_m for pipeline in self.pipelines)


@dataclass
class WellHydraulics:
    """Перепады и мощности по одной скважине."""

    well: str
    q_m3h: float
    annual_volume_m3: float
    path_length_m: float
    path_complete: bool
    has_geometry: bool
    p_before_choke_mpa: float | None
    p_after_choke_mpa: float | None
    dp_friction_mpa: float
    dp_network_mpa: float | None
    dp_other_mpa: float | None
    dp_choke_mpa: float | None
    flags: list[str] = field(default_factory=list)
    dp_friction_calc_mpa: float | None = None  # трение по геометрии до ограничения замером

    @property
    def pressures_consistent(self) -> bool:
        """Замеры давления не противоречат направлению потока."""
        return not any(flag in MEASUREMENT_FLAGS for flag in self.flags)

    def power_kw(self, dp_mpa: float | None) -> float:
        if dp_mpa is None or dp_mpa <= 0:
            return 0.0
        return units.hydraulic_power_kw(dp_mpa, self.q_m3h)

    @property
    def friction_kw(self) -> float:
        return self.power_kw(self.dp_friction_mpa)

    @property
    def other_kw(self) -> float:
        return self.power_kw(self.dp_other_mpa)

    @property
    def choke_kw(self) -> float:
        return self.power_kw(self.dp_choke_mpa)


@dataclass(frozen=True)
class PipeLoad:
    """Расход, скорость и трение в одном трубопроводе сети."""

    pipeline: Pipeline
    q_m3h: float
    velocity_ms: float  # наибольшая по участкам — в самом узком сечении
    dp_friction_mpa: float


@dataclass
class NetworkResult:
    p_bg_mpa: float
    fluid: Fluid
    wells: list[WellHydraulics]
    loads: list[PipeLoad] = field(default_factory=list)

    @property
    def total_q_m3h(self) -> float:
        return sum(well.q_m3h for well in self.wells)

    @property
    def friction_kw(self) -> float:
        return sum(well.friction_kw for well in self.wells)

    @property
    def other_kw(self) -> float:
        return sum(well.other_kw for well in self.wells)

    @property
    def choke_kw(self) -> float:
        return sum(well.choke_kw for well in self.wells)

    @property
    def required_pressure_mpa(self) -> float | None:
        """Давление на БГ, достаточное для самой требовательной скважины.

        Сумма давления после штуцера и трения по пути до неё — то, что
        осталось бы при полностью открытых штуцерах и регулирующих задвижках.
        """
        needs = [
            well.p_after_choke_mpa + well.dp_friction_mpa
            for well in self.wells
            if well.p_after_choke_mpa is not None and well.pressures_consistent
        ]
        return max(needs) if needs else None

    @property
    def excess_pressure_mpa(self) -> float | None:
        required = self.required_pressure_mpa
        if required is None:
            return None
        return max(self.p_bg_mpa - required, 0.0)

    def annual_energy_kwh(self, dp_attr: str, eta: float) -> float:
        """Годовая электроэнергия на статью потерь: Δp / (3,6·η) · V_год."""
        total = 0.0
        for well in self.wells:
            dp = getattr(well, dp_attr)
            if dp is None or dp <= 0:
                continue
            total += dp / (units.HYDRAULIC_POWER_DIVISOR * eta) * well.annual_volume_m3
        return total

    def excess_energy_kwh(self, eta: float) -> float:
        excess = self.excess_pressure_mpa or 0.0
        volume = sum(well.annual_volume_m3 for well in self.wells)
        return excess / (units.HYDRAULIC_POWER_DIVISOR * eta) * volume


def _key(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def resolve_paths(
    pipelines: Iterable[Pipeline], station_nodes: Sequence[str]
) -> dict[str, WellPath]:
    """Путь от каждой скважины к станции по дереву водоводов.

    Путь полный, если цепочка дошла до узла станции. Если по дороге
    встретилась магистраль, которой нет в реестре, путь частичный: известна
    только его концевая часть.
    """
    network = [pipeline for pipeline in pipelines if pipeline.purpose == DISTRIBUTION]
    by_name = {pipeline.name: pipeline for pipeline in network}
    by_end: dict[str, Pipeline] = {}
    for pipeline in network:
        by_end.setdefault(_key(pipeline.end), pipeline)
    stations = {_key(node) for node in station_nodes}

    def parent(pipeline: Pipeline) -> tuple[Pipeline | None, bool]:
        start = pipeline.start
        if start in by_name and start != pipeline.name:
            return by_name[start], False
        tail = by_end.get(_key(start))
        if tail is not None and tail is not pipeline:
            return tail, False
        return None, _key(start) in stations

    paths: dict[str, WellPath] = {}
    for pipeline in sorted(network, key=lambda item: item.name):
        well = pipeline.well
        if well is None or well in paths:
            continue
        chain = [pipeline]
        complete = False
        while True:
            upper, reached = parent(chain[-1])
            if upper is None:
                complete = reached
                break
            if upper in chain:
                break
            chain.append(upper)
        paths[well] = WellPath(well=well, pipelines=chain, complete=complete)
    return paths


def pipe_flows(paths: dict[str, WellPath], flows: dict[str, float]) -> dict[str, float]:
    """Расход по каждому трубопроводу: сумма расходов скважин ниже по дереву."""
    totals: dict[str, float] = {}
    for well, path in paths.items():
        q = flows.get(well, 0.0)
        if q <= 0:
            continue
        for pipeline in path.pipelines:
            totals[pipeline.name] = totals.get(pipeline.name, 0.0) + q
    return totals


def pipeline_friction_mpa(pipeline: Pipeline, q_m3h: float, fluid: Fluid) -> float:
    """Потеря давления на трение по всем действующим участкам трубопровода."""
    return sum(
        hydraulics.darcy_weisbach_dp(
            q_m3h,
            section.length_m,
            section.inner_m,
            section_roughness_m(section),
            fluid.rho,
            fluid.nu_cst,
        )
        for section in pipeline.sections
    )


def analyze_network(
    pipelines: Iterable[Pipeline],
    wells: Sequence[WellMeasurement],
    station_nodes: Sequence[str],
    p_bg_mpa: float,
    fluid: Fluid,
) -> NetworkResult:
    """Раскладка потерь разводящей сети по скважинам."""
    paths = resolve_paths(pipelines, station_nodes)
    flows = {well.well: well.q_m3h for well in wells}
    loads = pipe_flows(paths, flows)
    by_name = {pipe.name: pipe for path in paths.values() for pipe in path.pipelines}
    pipe_loads = [
        PipeLoad(
            pipeline=by_name[name],
            q_m3h=q,
            velocity_ms=max(
                hydraulics.velocity(q, section.inner_m) for section in by_name[name].sections
            ),
            dp_friction_mpa=pipeline_friction_mpa(by_name[name], q, fluid),
        )
        for name, q in loads.items()
    ]
    friction = {load.pipeline.name: load.dp_friction_mpa for load in pipe_loads}

    results: list[WellHydraulics] = []
    for well in wells:
        path = paths.get(well.well)
        flags: list[str] = []
        dp_friction = sum(friction.get(p.name, 0.0) for p in path.pipelines) if path else 0.0
        if path is None:
            flags.append(FLAG_NO_PIPELINE)
        elif not path.complete:
            flags.append(FLAG_NO_TRUNK)

        p_before = well.p_before_choke_mpa
        p_after = well.p_after_choke_mpa
        if p_before is None:
            p_before = p_after  # штуцера нет или давление до него не замерено
        dp_network = p_bg_mpa - p_before if p_before is not None else None
        dp_choke = (p_before - p_after) if p_before is not None and p_after is not None else None
        dp_friction_calc = dp_friction
        if dp_network is not None and 0 <= dp_network < dp_friction:
            # Врезки отводов приняты в конце магистрали, поэтому расчёт трения —
            # оценка сверху; замеренный перепад до скважины её ограничивает.
            dp_friction = dp_network
            flags.append(FLAG_FRICTION_CAPPED)
        dp_other = dp_network - dp_friction if dp_network is not None else None

        if dp_network is not None and dp_network < 0:
            flags.append(FLAG_HEAD_ABOVE_BG)
        if dp_choke is not None and dp_choke < 0:
            flags.append(FLAG_CHOKE_REVERSED)

        results.append(
            WellHydraulics(
                well=well.well,
                q_m3h=well.q_m3h,
                annual_volume_m3=well.annual_volume_m3,
                path_length_m=path.length_m if path else 0.0,
                path_complete=bool(path and path.complete),
                has_geometry=path is not None,
                p_before_choke_mpa=p_before,
                p_after_choke_mpa=p_after,
                dp_friction_mpa=dp_friction,
                dp_network_mpa=dp_network,
                dp_other_mpa=dp_other,
                dp_choke_mpa=dp_choke,
                flags=flags,
                dp_friction_calc_mpa=dp_friction_calc,
            )
        )
    pipe_loads.sort(key=lambda load: load.dp_friction_mpa, reverse=True)
    return NetworkResult(p_bg_mpa=p_bg_mpa, fluid=fluid, wells=results, loads=pipe_loads)
