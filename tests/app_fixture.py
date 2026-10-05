"""Изолированная SQLite-телеметрия для регрессии Streamlit без внешних выгрузок."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
import streamlit as st

from ppd_audit.db_seed import bootstrap_database


@pytest.fixture(scope="module", autouse=True)
def app_database(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        path = tmp_path_factory.mktemp("streamlit") / "telemetry.sqlite"
        db = bootstrap_database(path, Path(__file__).resolve().parents[1] / "config" / "plants")
        # НА-1 открывается по умолчанию: телеметрия есть, расчёт невозможен.
        # НА-2 имеет полный пригодный день и более свежий неполный день.
        for aggregate in ("НА-1", "НА-2"):
            db.add_measurement("kns54an", aggregate, datetime(2025, 6, 5), "power", 210, "кВт")
        start = datetime(2025, 6, 1)
        for metric, value, unit in (
            ("p_in", 1.2, "МПа"),
            ("p_out", 10.4, "МПа"),
            ("p_bg", 8, "МПа"),
            ("power", 210, "кВт"),
            ("density", 1000, "кг/м³"),
            ("q_day", 960, "м³/сут"),
            ("runtime", 24, "ч"),
            ("energy", 5040, "кВт·ч"),
        ):
            db.add_measurement(
                "kns54an",
                "НА-2",
                start,
                metric,
                value,
                unit,
                source_kind="scada",
                source_file="fixture.csv",
            )
        # Вторая устойчивая пара нужна для проверки общего выбора снимка.
        for metric, value, unit in (
            ("p_in", 1.3, "МПа"),
            ("p_out", 10.5, "МПа"),
            ("power", 211, "кВт"),
        ):
            db.add_measurement("kns54an", "НА-2", start + timedelta(hours=12), metric, value, unit)
        db.add_measurement("kns54an", "НА-2", start + timedelta(hours=23), "power", 211, "кВт")
        # Станционный ряд ОПУ не заменяет отсутствующие давления НА-3.
        db.add_measurement("knsopu", None, start, "power", 400, "кВт")
        db.add_measurement("knsopu", "НА-3", start, "power", 210, "кВт")
        patch.setenv("PPD_DATABASE_PATH", str(path))
        st.cache_resource.clear()
        st.cache_data.clear()
        yield db
        st.cache_resource.clear()
        st.cache_data.clear()
