"""UI-тесты telemetry-only дашборда.

Расчётные файлы и текстовые отчёты сверяются отдельными тестами. Дашборд показывает
KPI только для пригодного суточного режима из SQLite-телеметрии.
"""

import pytest


pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


APP = "app/main.py"
REPORT_OBJECTS = ["КНС-25", "КНС-155", "КНС-ОПУ", "КНС-10", "КНС-154", "КНС-14"]


def _select_object(at, label_part):
    option = next(o for o in at.selectbox[0].options if label_part in o)
    return at.selectbox[0].set_value(option).run()


def test_smoke_starts():
    at = AppTest.from_file(APP, default_timeout=240).run()
    assert not at.exception
    assert any(item.value == "Телеметрия за сутки" for item in at.subheader)


@pytest.mark.parametrize("label_part", REPORT_OBJECTS)
def test_legacy_object_is_not_calculated_without_telemetry(label_part):
    """Отчётный объект без рядов не получает KPI из legacy-расчёта."""
    at = AppTest.from_file(APP, default_timeout=240).run()
    at = _select_object(at, label_part)
    assert not at.exception, f"{label_part}: {at.exception}"
    assert any(
        "Нет телеметрии" in element.value or "Нет пригодного режима" in element.value
        for element in at.warning
    )
