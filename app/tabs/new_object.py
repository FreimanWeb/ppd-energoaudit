"""Новый объект — требуемая телеметрия, ручной ввод, чек готовности, YAML-шаблоны."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ppd_audit.services.analysis import (
    TELEMETRY_REQUIREMENTS,
    VERIFICATION_TEMPLATE,
    YAML_TEMPLATE,
    onboarding,
)
from tabs.common import Ctx, fmt


def render(ctx: Ctx) -> None:
    st.subheader("Подключение нового объекта: что нужно для расчёта")
    st.caption("Требования к данным и готовность текущего объекта.")

    st.markdown("### 1. Требуемая телеметрия (Методика, табл. 8.2.1)")
    st.dataframe(
        pd.DataFrame(
            TELEMETRY_REQUIREMENTS,
            columns=["Параметр", "Обозн.", "Ед.", "Обязательность", "Источник"],
        ),
        width="stretch",
        hide_index=True,
    )

    st.markdown("### 2. Что вводится вручную (паспорта и конфиг)")
    st.markdown(
        "- **Насос:** модель, тип (центробежный/объёмный), Q_ном, H_ном, η_нас.ном, P_ном, "
        "n об/мин, кривые Q-H и Q-η (координаты) — из паспорта/каталога.\n"
        "- **Электродвигатель:** модель, P_ном, η_ЭД.ном, cos φ, U, синхронный/асинхронный.\n"
        "- **ПЧ / трансмиссия:** наличие ПЧ (η_пч=0,97), КПД трансмиссии (если есть).\n"
        "- **Жидкость:** ρ и ν — по замеру; по умолчанию по типу воды из `config/fluids.yaml`.\n"
        "- **Эталоны для сверки** (опц.): инженерный `… расчет.xlsx` и текстовый отчёт `.doc`."
    )

    st.markdown("### 3. Готовность текущего объекта")
    readiness = onboarding(ctx.agg)
    checks = [(item["field"], item["value"]) for item in readiness["checks"]]

    def _val(v):
        if isinstance(v, (int, float)):
            return fmt(v, 3)
        return "список координат" if v else "—"

    st.dataframe(
        pd.DataFrame([
            {"Поле": k, "Статус": "есть" if v else "нет", "Значение": _val(v)} for k, v in checks
        ]),
        width="stretch",
        hide_index=True,
    )
    missing = [k for k, v in checks if not v]
    if missing:
        st.warning(
            "Не заполнено: " + ", ".join(missing) + ". Часть полей опциональна "
            "(объёмные насосы и объекты без паспортной кривой Q-H считаются корректно "
            "по своей ветке расчёта)."
        )
    else:
        st.success("Все ключевые поля заполнены.")

    st.markdown("### 4. Шаблон конфигурации")
    st.caption("Положить файлы в «НТУ цифровая платформа/<вид воды>/…», затем создать паспорт:")
    st.code(YAML_TEMPLATE, language="yaml")
    st.markdown("Чтобы объект попал в сверку — добавить запись в `config/verification.yaml`:")
    st.code(VERIFICATION_TEMPLATE, language="yaml")
    st.markdown(
        "Затем выполнить (сконвертирует `.doc`, создаст `plants/<id>.yaml`, "
        "добавит объект в обе сверки и в дашборд):"
    )
    st.code("python -m ppd_audit.verify", language="bash")
