from __future__ import annotations

import math

import pytest

from ppd_audit import units
from ppd_audit.core import network
from ppd_audit.core.network import (
    FLAG_FRICTION_CAPPED,
    FLAG_HEAD_ABOVE_BG,
    FLAG_NO_PIPELINE,
    FLAG_NO_TRUNK,
    Fluid,
    WellMeasurement,
    analyze_network,
    pipe_flows,
    pipeline_friction_mpa,
    resolve_paths,
    section_roughness_m,
    water_viscosity_cst,
)
from ppd_audit.ingest.pipelines import Pipeline, PipeSection


WATER = Fluid(rho=1000.0, nu_cst=1.0)
STATION = ["КНС-1"]


def _section(
    length: float, outer: float = 114.0, wall: float = 9.0, coating: str = "ПЭ"
) -> PipeSection:
    return PipeSection(
        start_m=0.0,
        end_m=length,
        length_m=length,
        outer_mm=outer,
        wall_mm=wall,
        pipe_type="МПТ",
        material="Сталь 20",
        inner_coating=coating,
    )


def _pipe(name: str, start: str, end: str, length: float = 1000.0, **kwargs) -> Pipeline:
    return Pipeline(
        name=name,
        start=start,
        end=end,
        purpose="Разводящий",
        medium="Вода",
        length_m=length,
        temperature_c=10.0,
        work_pressure_atm=120.0,
        sections=[_section(length, **kwargs)],
    )


def _tree() -> list[Pipeline]:
    """КНС-1 → магистраль к скв 1 → отвод к скв 2; отдельная линия к скв 3."""
    return [
        _pipe("КНС-1 - Скв 1 - 1", "КНС-1", "Скв 1", 2000.0),
        _pipe(
            "(КНС-1 - Скв 1 - 1) - Скв 2 - 1",
            "КНС-1 - Скв 1 - 1",
            "Скв 2",
            500.0,
            outer=89.0,
            wall=7.0,
        ),
        _pipe("КНС-1 - Скв 3 - 1", "КНС-1", "Скв 3", 800.0),
    ]


def test_water_viscosity_matches_reference_points():
    assert water_viscosity_cst(20.0) == pytest.approx(1.0, abs=0.02)
    assert water_viscosity_cst(10.0) == pytest.approx(1.31, abs=0.02)
    assert water_viscosity_cst(5.0) > water_viscosity_cst(15.0)


def test_coated_pipe_is_smooth_and_bare_steel_is_rough():
    assert section_roughness_m(_section(10.0, coating="ПЭ")) == network.ROUGHNESS_SMOOTH_M
    assert section_roughness_m(_section(10.0, coating="нет")) == network.ROUGHNESS_STEEL_M


def test_branch_path_climbs_through_the_trunk_to_the_station():
    paths = resolve_paths(_tree(), STATION)

    assert [p.name for p in paths["2"].pipelines] == [
        "(КНС-1 - Скв 1 - 1) - Скв 2 - 1",
        "КНС-1 - Скв 1 - 1",
    ]
    assert paths["2"].complete
    assert paths["2"].length_m == pytest.approx(2500.0)


def test_continuation_from_a_node_at_the_end_of_another_pipeline():
    pipes = [
        _pipe("КНС-1 - ВРП-1 - 1", "КНС-1", "ВРП-1"),
        _pipe("ВРП-1 - Скв 5 - 1", "ВРП-1", "Скв 5"),
    ]
    path = resolve_paths(pipes, STATION)["5"]

    assert path.complete
    assert len(path.pipelines) == 2


def test_missing_trunk_gives_a_partial_path():
    pipes = [_pipe("(КНС-1 - Скв 9 - 1) - Скв 4 - 1", "КНС-1 - Скв 9 - 1", "Скв 4")]
    path = resolve_paths(pipes, STATION)["4"]

    assert not path.complete
    assert len(path.pipelines) == 1


def test_station_node_names_match_regardless_of_dashes_and_spaces():
    pipes = [_pipe("КНС 1 - Скв 7 - 1", "КНС 1", "Скв 7")]

    assert resolve_paths(pipes, STATION)["7"].complete


def test_supply_pipelines_are_not_part_of_the_distribution_tree():
    supply = _pipe("ДНС - КНС-1 - 1", "ДНС", "Скв 8")
    supply.purpose = "Подводящий"

    assert "8" not in resolve_paths([supply], STATION)


def test_shared_trunk_carries_the_sum_of_downstream_flows():
    paths = resolve_paths(_tree(), STATION)
    loads = pipe_flows(paths, {"1": 10.0, "2": 5.0, "3": 7.0})

    assert loads["КНС-1 - Скв 1 - 1"] == pytest.approx(15.0)
    assert loads["(КНС-1 - Скв 1 - 1) - Скв 2 - 1"] == pytest.approx(5.0)
    assert loads["КНС-1 - Скв 3 - 1"] == pytest.approx(7.0)


def test_friction_grows_with_flow_and_length():
    pipe = _tree()[0]

    low = pipeline_friction_mpa(pipe, 10.0, WATER)
    high = pipeline_friction_mpa(pipe, 20.0, WATER)
    assert 0 < low < high
    assert high / low == pytest.approx(4.0, rel=0.25)  # турбулентный режим: ~Q²


def test_network_power_splits_exactly_between_wells():
    """Σ q_i·Δp_пути,i равна Σ q_уч·Δp_уч — мощность не теряется и не дублируется."""
    pipes = _tree()
    flows = {"1": 10.0, "2": 5.0, "3": 7.0}
    wells = [WellMeasurement(well, q, 0.0, None, 8.0) for well, q in flows.items()]
    result = analyze_network(pipes, wells, STATION, 10.0, WATER)

    loads = pipe_flows(resolve_paths(pipes, STATION), flows)
    by_name = {p.name: p for p in pipes}
    per_pipe = sum(
        units.hydraulic_power_kw(pipeline_friction_mpa(by_name[name], q, WATER), q)
        for name, q in loads.items()
    )
    assert result.friction_kw == pytest.approx(per_pipe, rel=1e-9)


def test_measured_drops_are_split_into_friction_other_and_choke():
    wells = [WellMeasurement("3", 7.0, 50_000.0, 9.0, 7.5)]
    result = analyze_network(_tree(), wells, STATION, 10.0, WATER)
    well = result.wells[0]

    assert well.dp_network_mpa == pytest.approx(1.0)
    assert well.dp_choke_mpa == pytest.approx(1.5)
    assert well.dp_other_mpa == pytest.approx(1.0 - well.dp_friction_mpa)
    assert well.choke_kw == pytest.approx(1.5 * 7.0 / 3.6)


def test_without_choke_pressure_the_head_pressure_is_used():
    wells = [WellMeasurement("3", 7.0, 0.0, None, 9.2)]
    well = analyze_network(_tree(), wells, STATION, 10.0, WATER).wells[0]

    assert well.dp_choke_mpa == pytest.approx(0.0)
    assert well.dp_network_mpa == pytest.approx(0.8)


def test_flags_mark_missing_geometry_and_contradicting_pressures():
    wells = [
        WellMeasurement("99", 1.0, 0.0, None, 5.0),
        WellMeasurement("3", 1.0, 0.0, 11.0, 11.0),
    ]
    flags = {w.well: w.flags for w in analyze_network(_tree(), wells, STATION, 10.0, WATER).wells}

    assert FLAG_NO_PIPELINE in flags["99"]
    assert FLAG_HEAD_ABOVE_BG in flags["3"]


def test_partial_path_is_flagged():
    pipes = [_pipe("(КНС-1 - Скв 9 - 1) - Скв 4 - 1", "КНС-1 - Скв 9 - 1", "Скв 4")]
    wells = [WellMeasurement("4", 2.0, 0.0, None, 8.0)]

    assert FLAG_NO_TRUNK in analyze_network(pipes, wells, STATION, 10.0, WATER).wells[0].flags


def test_negative_drops_do_not_produce_power():
    wells = [WellMeasurement("3", 7.0, 0.0, 11.0, 12.0)]
    well = analyze_network(_tree(), wells, STATION, 10.0, WATER).wells[0]

    assert well.other_kw == 0.0
    assert well.choke_kw == 0.0


def test_required_pressure_is_set_by_the_most_demanding_well():
    wells = [
        WellMeasurement("1", 5.0, 0.0, 8.0, 6.0),
        WellMeasurement("3", 5.0, 0.0, 9.0, 8.5),
    ]
    result = analyze_network(_tree(), wells, STATION, 10.0, WATER)
    friction_3 = next(w for w in result.wells if w.well == "3").dp_friction_mpa

    assert result.required_pressure_mpa == pytest.approx(8.5 + friction_3)
    assert result.excess_pressure_mpa == pytest.approx(10.0 - 8.5 - friction_3)


def test_wells_with_contradicting_pressures_do_not_set_the_requirement():
    wells = [
        WellMeasurement("1", 5.0, 0.0, 8.0, 6.0),
        WellMeasurement("3", 5.0, 0.0, 12.0, 12.0),
    ]
    result = analyze_network(_tree(), wells, STATION, 10.0, WATER)

    assert result.required_pressure_mpa < 10.0


def test_annual_energy_follows_the_throttling_formula():
    """ΔW = Δp / (3,6·η) · V_год — так же, как годовые потери на дросселировании."""
    wells = [WellMeasurement("3", 7.0, 60_000.0, 9.0, 7.5)]
    result = analyze_network(_tree(), wells, STATION, 10.0, WATER)

    assert result.annual_energy_kwh("dp_choke_mpa", 0.5) == pytest.approx(
        1.5 / (3.6 * 0.5) * 60_000.0
    )


def test_empty_input_gives_empty_result():
    result = analyze_network([], [], STATION, 10.0, WATER)

    assert result.wells == []
    assert result.required_pressure_mpa is None
    assert math.isclose(result.friction_kw, 0.0)


def test_measured_drop_caps_the_friction_estimate():
    pipes = [_pipe("КНС-1 - Скв 5 - 1", "КНС-1", "Скв 5", 5000.0, outer=57.0, wall=5.0)]
    wells = [WellMeasurement("5", 20.0, 0.0, None, 9.8)]
    well = analyze_network(pipes, wells, STATION, 10.0, WATER).wells[0]

    assert well.dp_friction_calc_mpa > 0.2
    assert well.dp_friction_mpa == pytest.approx(0.2)
    assert well.dp_other_mpa == pytest.approx(0.0)
    assert FLAG_FRICTION_CAPPED in well.flags
