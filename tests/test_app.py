"""Smoke-тест Streamlit-дашборда: рендер без исключений.

Прогоняет app/main.py headless через AppTest для нескольких объектов
(включая КНС-ОПУ с расхождениями и ДНС-7с без эталона).
"""

from datetime import date
from pathlib import Path

import pytest


pytest.importorskip("streamlit")
from app_fixture import app_database  # noqa: F401
from streamlit.testing.v1 import AppTest


APP = "app/main.py"


def _has_telemetry_chart(at: AppTest) -> bool:
    return any(getattr(element, "type", None) == "vega_lite_chart" for element in at.main)


def test_default_render():
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception
    assert any(item.value == "Телеметрия за сутки" for item in at.subheader)
    assert _has_telemetry_chart(at)


def test_sidebar_shows_only_supported_modes():
    at = AppTest.from_file(APP, default_timeout=180).run()

    assert at.radio[0].label == "Режим"
    assert at.radio[0].options == ["Анализ по телеметрии", "Выезд", "Просмотр телеметрии"]


def test_field_trip_mode_audits_yaml_object_without_telemetry():
    at = AppTest.from_file(APP, default_timeout=180).run()
    at.radio[0].set_value("Выезд").run()
    option = next(option for option in at.selectbox[0].options if "ДНС-7с" in option)
    at.selectbox[0].set_value(option).run()

    assert not at.exception
    assert any("Выездной аудит · YAML-паспорт" in item.value for item in at.markdown)
    assert not any("Телеметрия" in tab.label for tab in at.tabs)
    assert not any("Режимный расчёт" in tab.label for tab in at.tabs)


def test_field_trip_object_selector_omits_telemetry_markers():
    at = AppTest.from_file(APP, default_timeout=180).run()
    at.radio[0].set_value("Выезд").run()

    assert all(not option.startswith(("●", "○")) for option in at.selectbox[0].options)


def test_object_selector_marks_objects_without_telemetry():
    at = AppTest.from_file(APP, default_timeout=180).run()
    kns54 = next(option for option in at.selectbox[0].options if "КНС-54" in option)
    dns7 = next(option for option in at.selectbox[0].options if "ДНС-7с" in option)

    assert kns54.startswith("●")
    assert dns7.startswith("○")


def test_telemetry_viewer_uses_a_date_range():
    at = AppTest.from_file(APP, default_timeout=180).run()
    at.radio[0].set_value("Просмотр телеметрии").run()

    assert at.date_input[0].label == "Период телеметрии"
    assert any(item.value == "Телеметрия за период" for item in at.subheader)


def test_snapshot_is_not_a_sidebar_mode():
    at = AppTest.from_file(APP, default_timeout=180).run()

    assert "Режимный расчёт" not in at.radio[0].options


def test_snapshot_is_single_page_without_telemetry_fallback():
    source = Path("app/tabs/snapshot.py").read_text(encoding="utf-8")

    assert "st.tabs(" not in source
    assert "telemetry.render_day" not in source


def test_analysis_and_snapshot_share_the_latest_pressure_snapshot():
    at = _analysis_app()
    assert not at.exception
    selector = next(item for item in at.selectbox if item.label == "Показатель давления")
    assert selector.value == "2025-06-01T23:30:00"
    assert at.session_state["snapshot-kns54an-НА-2-2025-06-01"] == selector.value
    for index, pressure in ((len(selector.options) - 1, "10,500"), (0, "10,400")):
        selector.select_index(index).run()
        selector = next(item for item in at.selectbox if item.label == "Показатель давления")
        timestamp = selector.value
        pressure_metric = next(item for item in at.metric if item.label == "p_вых, МПа")
        assert pressure_metric.value == pressure
        overview_table = next(
            item.value
            for item in at.dataframe
            if "Параметр" in item.value.columns and "p_вых, МПа" in item.value["Параметр"].values
        )
        row = overview_table.loc[overview_table["Параметр"] == "p_вых, МПа"]
        assert row.iloc[0]["Значение"] == pressure
        assert at.session_state["snapshot-kns54an-НА-2-2025-06-01"] == timestamp


def _analysis_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=180).run()
    at.selectbox[1].set_value("НА-2").run()
    at.session_state["telemetry-date-kns54an-НА-2-picker"] = {
        "selected_date": "2025-06-01",
        "visible_month": "2025-06",
    }
    return at.run()


def test_fallback_scheme_draws_each_aggregate_as_a_parallel_branch():
    from xml.etree import ElementTree

    at = _analysis_app()
    assert not at.exception
    content = next(item.value for item in at.markdown if 'class="ppd-scheme"' in item.value)
    svg = ElementTree.fromstring(content[content.index("<svg ") : content.index("</svg>") + 6])
    nodes = [element for element in svg.iter() if element.get("data-node")]
    edges = {(element.get("data-from"), element.get("data-to")) for element in svg.iter()}
    for index, aggregate in enumerate(("НА-1", "НА-2")):
        pump = next(node for node in nodes if node.get("data-node") == f"pump-{index}")
        assert aggregate in "".join(pump.itertext())
        assert ("src", f"pump-{index}") in edges
        assert (f"pump-{index}", "man") in edges
    assert len([node for node in nodes if node.get("data-selected") == "true"]) == 1


def test_clarifications_have_human_readable_efficiency_labels():
    source = Path(APP).read_text(encoding="utf-8")

    assert '"pump_eta_nom": "КПД насоса"' in source
    assert '"motor_eta_nom": "КПД ЭД"' in source


def test_data_quality_is_not_an_analysis_tab():
    source = Path(APP).read_text(encoding="utf-8")

    assert '"✅ Качество данных"' not in source


def test_reconciliation_is_not_an_analysis_tab():
    source = Path(APP).read_text(encoding="utf-8")

    assert '"🔬 Модель vs Отчёт"' not in source


def test_pressure_coverage_notice_is_not_shown():
    """Плашка про 80% покрытия давлением убрана по решению заказчика.

    Сам отбор данных не изменился: при неполном покрытии показатели
    по-прежнему считаются как режимный снимок, статус суток в календаре
    остаётся «snapshot». Убрано только сообщение на экране.
    """
    source = Path(APP).read_text(encoding="utf-8")

    assert "Физически пригодное давление доступно менее чем" not in source


def test_manifold_pressure_rejection_notice_is_not_shown():
    """Плашка про исключённые снимки (p_вых ≤ p_БГ) убрана.

    Отбраковка таких снимков продолжает работать в ядре — снимок с давлением
    выкида ниже гребёнки в расчёт не попадает, о нём просто не сообщается.
    """
    source = Path(APP).read_text(encoding="utf-8")

    assert "Исключено снимков из расчёта НА" not in source


def test_analysis_warns_about_physically_impossible_efficiency():
    source = Path(APP).read_text(encoding="utf-8")

    assert "snapshot_audit.quality" in source
    assert "Режим непригоден для экономических выводов" in source


def test_unfit_regime_hides_loss_map_and_measures():
    losses = Path("app/tabs/losses.py").read_text(encoding="utf-8")
    measures = Path("app/tabs/measures.py").read_text(encoding="utf-8")

    assert "ctx.quality.allows_economic_conclusions" in losses
    assert "ctx.quality.allows_economic_conclusions" in measures


def test_overview_separates_snapshot_and_daily_regime_data():
    source = Path("app/tabs/overview.py").read_text(encoding="utf-8")

    assert '"Показатель давления"' in source
    assert '"Суточные данные"' in source
    assert '"Режим (замер)"' not in source


def test_clarifications_are_scoped_to_selected_aggregate(request):
    db = request.getfixturevalue("app_database")
    db.upsert_clarification(
        "kns54an",
        "НА-1",
        field="pump_eta_nom",
        provisional_value="0.55",
        reason="Только НА-1",
    )
    db.upsert_clarification(
        "kns54an",
        "НА-2",
        field="motor_eta_nom",
        provisional_value="0.96",
        reason="Только НА-2",
    )
    try:
        at = _analysis_app()
        assert not at.exception
        captions = " ".join(item.value for item in at.caption)
        assert "Только НА-2" in captions and "КПД ЭД = 0.96" in captions
        assert "Только НА-1" not in captions
    finally:
        for aggregate, field in (("НА-1", "pump_eta_nom"), ("НА-2", "motor_eta_nom")):
            db.resolve_clarification("kns54an", aggregate, field=field)


def test_missing_snapshot_still_renders_telemetry():
    source = Path(APP).read_text(encoding="utf-8")
    no_snapshot = source.split("if not snapshots:", maxsplit=1)[1]
    no_snapshot = no_snapshot.split("snapshot_key =", maxsplit=1)[0]

    assert "telemetry.render_day(object_id, agg_id, selected_date)" in no_snapshot


@pytest.mark.parametrize("label_part", ["КНС-129", "КНС-138", "КНС-175"])
def test_example_objects_are_hidden_from_selector(label_part):
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not any(label_part in option for option in at.selectbox[0].options)


@pytest.mark.parametrize("object_id", ["kns129ln", "kns138ln", "kns175"])
def test_example_objects_are_marked_in_specs(object_id):
    from ppd_audit.spec import load_object_spec

    assert load_object_spec(object_id).is_example


def test_object_selector_shows_ngdu():
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert any(
        "КНС-25" in option and "Джалильнефть" in option for option in at.selectbox[0].options
    )


def test_ngdu_filter_lists_known_ngdu():
    at = AppTest.from_file(APP, default_timeout=180).run()

    assert at.multiselect[1].label == "НГДУ"
    assert "Азнакаевскнефть" in at.multiselect[1].options


def test_regime_date_is_selected_with_calendar():
    at = AppTest.from_file(APP, default_timeout=180).run()

    assert not at.date_input
    assert not at.exception


def test_object_without_telemetry_shows_message():
    at = AppTest.from_file(APP, default_timeout=180).run()
    option = next(o for o in at.selectbox[0].options if "КНС-25" in o)
    at.selectbox[0].set_value(option).run()

    assert any("Нет телеметрии" in element.value for element in at.warning)


@pytest.mark.parametrize("label_part", ["КНС-ОПУ", "КНС-25", "ДНС-7с"])
def test_object_render(label_part):
    at = AppTest.from_file(APP, default_timeout=180).run()
    option = next(o for o in at.selectbox[0].options if label_part in o)
    at.selectbox[0].set_value(option).run()
    assert not at.exception, f"{label_part}: {at.exception}"


def test_telemetry_renders_for_object_with_measurements():
    """Объект с телеметрией показывает графики и при непригодном режиме."""
    at = AppTest.from_file(APP, default_timeout=180).run()
    option = next(o for o in at.selectbox[0].options if "КНС-54" in o)
    at.selectbox[0].set_value(option).run()
    at.selectbox[1].set_value("НА-2").run()
    at.session_state["telemetry-date-kns54an-НА-2-picker"] = {
        "selected_date": date(2025, 6, 5).isoformat(),
        "visible_month": "2025-06",
    }
    at.run()
    assert not at.exception
    assert _has_telemetry_chart(at), "нет графика телеметрии"


def test_topology_files_valid():
    """config/topology/*.yaml: у узлов есть x/y/label, рёбра ссылаются на существующие узлы."""
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[1]
    files = list((root / "config" / "topology").glob("*.yaml"))
    assert files, "нет файлов топологии"
    for f in files:
        t = yaml.safe_load(f.read_text(encoding="utf-8"))
        ids = {n["id"] for n in t["nodes"]}
        for n in t["nodes"]:
            assert {"x", "y", "label"} <= set(n), f"{f.name}: узел без x/y/label: {n}"
        for e in t.get("edges", []):
            assert e["from"] in ids and e["to"] in ids, f"{f.name}: битое ребро {e}"


def test_object_with_topology_and_no_telemetry_shows_message():
    """Топология не разрешает использовать legacy-режим без телеметрии."""
    at = AppTest.from_file(APP, default_timeout=180).run()
    option = next(o for o in at.selectbox[0].options if "КНС-25" in o)
    at.selectbox[0].set_value(option).run()
    assert not at.exception
    assert any("Нет телеметрии" in element.value for element in at.warning)


def test_object_with_unallocated_station_telemetry_shows_message():
    at = AppTest.from_file(APP, default_timeout=180).run()
    option = next(o for o in at.selectbox[0].options if "КНС-ОПУ" in o)
    at.selectbox[0].set_value(option).run()

    at.selectbox[1].set_value("НА-3").run()

    assert any("Нет пригодного режима" in element.value for element in at.warning)
    assert any(item.value == "Телеметрия за сутки" for item in at.subheader)


def test_unfit_regime_behavior_hides_loss_map_and_measures(request):
    from datetime import datetime

    db = request.getfixturevalue("app_database")
    db.add_measurement("kns54an", "НА-2", datetime(2025, 6, 1), "q_day", 96000, "м³/сут")
    try:
        at = _analysis_app()
        assert not at.exception
        assert any("Режим непригоден для экономических выводов" in item.value for item in at.error)
        for label in ("Карта потерь", "Мероприятия"):
            tab = next(item for item in at.tabs if item.label == label)
            assert tab.get("warning")
            assert not tab.get("dataframe")
            assert not tab.get("plotly_chart")
    finally:
        db.add_measurement("kns54an", "НА-2", datetime(2025, 6, 1), "q_day", 960, "м³/сут")


def test_incomplete_day_keeps_telemetry_without_yaml_fact_fallback():
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception
    assert any("Нет пригодного режима" in item.value for item in at.warning)
    assert _has_telemetry_chart(at)
    assert not at.metric
    assert not at.tabs
