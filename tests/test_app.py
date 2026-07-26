"""Smoke-тест Streamlit-дашборда: рендер без исключений.

Прогоняет app/main.py headless через AppTest для нескольких объектов
(включая КНС-ОПУ с расхождениями и ДНС-7с без эталона).
"""

from datetime import date
from pathlib import Path

import pytest


pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


APP = "app/main.py"


def test_default_render():
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception
    assert any(item.value == "Телеметрия за сутки" for item in at.subheader)
    assert at.dataframe


def test_data_editor_is_available():
    at = AppTest.from_file(APP, default_timeout=180).run()

    assert at.radio[0].label == "Режим"
    assert "Редактирование данных" in at.radio[0].options


def test_telemetry_viewer_uses_a_date_range():
    at = AppTest.from_file(APP, default_timeout=180).run()
    at.radio[0].set_value("Просмотр телеметрии").run()

    assert at.date_input[0].label == "Период телеметрии"
    assert any(item.value == "Телеметрия за период" for item in at.subheader)


def test_snapshot_is_not_a_sidebar_mode():
    at = AppTest.from_file(APP, default_timeout=180).run()

    assert "Режимный снимок" not in at.radio[0].options


def test_snapshot_is_single_page_without_telemetry_fallback():
    source = Path("app/tabs/snapshot.py").read_text(encoding="utf-8")

    assert "st.tabs(" not in source
    assert "telemetry.render_day" not in source


def test_analysis_and_snapshot_share_the_latest_pressure_snapshot():
    main = Path(APP).read_text(encoding="utf-8")
    snapshot = Path("app/tabs/snapshot.py").read_text(encoding="utf-8")

    assert "st.session_state.setdefault(snapshot_key, snapshots[-1].timestamp.isoformat())" in main
    assert "lib.get_snapshot_audit(" in main
    assert "snapshot_key = lib.snapshot_selection_key(" in snapshot


def test_fallback_scheme_draws_each_aggregate_as_a_parallel_branch():
    source = Path("app/tabs/scheme.py").read_text(encoding="utf-8")

    assert "aggregates = ctx.obj.aggregates" in source
    assert "параллельные ветви НА" in source


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


def test_snapshot_warning_explains_what_pressure_coverage_is_needed_for():
    source = Path(APP).read_text(encoding="utf-8")

    assert "Давления синхронны с работающим агрегатом менее чем для 80% точек" in source
    assert "показатели по давлению рассчитаны как режимный снимок, а не за сутки" in source


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
    """Объект с телеметрией показывает сырые точки и при непригодном режиме."""
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
    has_telemetry = any("metric" in list(getattr(df.value, "columns", [])) for df in at.dataframe)
    assert has_telemetry, "нет таблицы сырых точек телеметрии"


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
