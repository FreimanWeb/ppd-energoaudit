"""Smoke-тест Streamlit-дашборда: рендер без исключений.

Прогоняет app/main.py headless через AppTest для нескольких объектов
(включая КНС-ОПУ с расхождениями и ДНС-7с без эталона).
"""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = "app/main.py"


def test_default_render():
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception
    assert len(at.tabs) == 9
    assert len(at.metric) >= 8


@pytest.mark.parametrize("label_part", ["КНС-ОПУ", "КНС-25", "ДНС-7с"])
def test_object_render(label_part):
    at = AppTest.from_file(APP, default_timeout=180).run()
    option = next(o for o in at.selectbox[0].options if label_part in o)
    at.selectbox[0].set_value(option).run()
    assert not at.exception, f"{label_part}: {at.exception}"


@pytest.mark.parametrize("label_part", ["КНС-25", "КНС-ОПУ", "ДНС-7с", "КНС-14"])
def test_new_tabs_render(label_part):
    """Вкладки «Схема ППД» и «Новый объект» рендерят свой контент для любого объекта."""
    at = AppTest.from_file(APP, default_timeout=180).run()
    option = next(o for o in at.selectbox[0].options if label_part in o)
    at.selectbox[0].set_value(option).run()
    assert not at.exception, f"{label_part}: {at.exception}"
    # «Новый объект»: таблица требований телеметрии (колонка «Обозн.»)
    has_telemetry = any("Обозн." in list(getattr(df.value, "columns", []))
                        for df in at.dataframe)
    assert has_telemetry, f"{label_part}: нет таблицы телеметрии (вкладка «Новый объект»)"
    # «Схема ППД»: блок потока мощности (Sankey)
    text = " ".join(m.value for m in at.markdown)
    assert "Поток мощности" in text, f"{label_part}: нет блока схемы ППД / Sankey"


def test_topology_files_valid():
    """config/topology/*.yaml: у узлов есть x/y/label, рёбра ссылаются на существующие узлы."""
    import yaml
    from pathlib import Path
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


def test_scheme_shows_asbuilt_when_topology_exists():
    """Объект с топологией (КНС-25) показывает as-built схему по техсхеме."""
    at = AppTest.from_file(APP, default_timeout=180).run()
    option = next(o for o in at.selectbox[0].options if "КНС-25" in o)
    at.selectbox[0].set_value(option).run()
    assert not at.exception
    assert "as-built" in " ".join(m.value for m in at.markdown)
