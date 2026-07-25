"""Ручное изменение паспортов и отдельных точек телеметрии в SQLite."""

from __future__ import annotations

import json
from datetime import datetime, time
from typing import Any

import lib
import streamlit as st

from ppd_audit.db import telemetry_units


def _number(value: Any) -> str:
    return "" if value is None else str(value)


def _parse_number(label: str, value: str) -> float | None:
    if not value.strip():
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{label}: нужно число") from exc


def _curve(value: str, label: str) -> str:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}: нужен JSON-массив пар [Q, значение]") from exc
    if not isinstance(parsed, list) or any(
        not isinstance(point, list) or len(point) != 2 for point in parsed
    ):
        raise ValueError(f"{label}: нужны пары [Q, значение]")
    return json.dumps(parsed)


def _curve_text(passport: dict[str, Any], field: str) -> str:
    try:
        return json.dumps(json.loads(passport[field]), ensure_ascii=False)
    except (KeyError, TypeError, json.JSONDecodeError):
        return "[]"


def render(object_id: str, aggregate_id: str) -> None:
    database = lib.database()
    now = datetime.now()
    try:
        passport = database.active_passport(object_id, aggregate_id, now)
    except KeyError as exc:
        st.error(str(exc))
        return

    st.subheader(f"Редактирование данных: {object_id} / {aggregate_id}")
    st.caption("Изменения сохраняются в SQLite. YAML остаётся только начальным импортом.")

    st.markdown("### Паспорт агрегата")
    with st.form("passport"):
        valid_from = st.date_input(
            "Паспорт действует с",
            value=datetime.fromisoformat(passport["valid_from"]).date(),
        )
        pump_col, motor_col = st.columns(2)
        with pump_col:
            pump_model = st.text_input("Насос: модель", value=passport["pump_model"])
            pump_kind = st.selectbox(
                "Насос: тип",
                ("центробежный", "объёмный"),
                index=("центробежный", "объёмный").index(passport["pump_kind"]),
            )
            pump_q_nom = st.text_input("Насос: Q ном, м³/ч", _number(passport["pump_q_nom"]))
            pump_h_nom = st.text_input("Насос: H ном, м", _number(passport["pump_h_nom"]))
            pump_eta_nom = st.text_input("Насос: η ном", _number(passport["pump_eta_nom"]))
            pump_power_nom = st.text_input(
                "Насос: мощность ном, кВт", _number(passport["pump_power_nom"])
            )
            pump_n_rpm = st.text_input("Насос: n, об/мин", _number(passport["pump_n_rpm"]))
        with motor_col:
            motor_model = st.text_input("Двигатель: модель", value=passport["motor_model"])
            motor_p_nom = st.text_input("Двигатель: P ном, кВт", _number(passport["motor_p_nom"]))
            motor_eta_nom = st.text_input("Двигатель: η ном", _number(passport["motor_eta_nom"]))
            motor_cos_phi = st.text_input("Двигатель: cos φ", _number(passport["motor_cos_phi"]))
            motor_voltage_kv = st.text_input(
                "Двигатель: U, кВ", _number(passport["motor_voltage_kv"])
            )
            motor_i_nom = st.text_input("Двигатель: I ном, А", _number(passport["motor_i_nom"]))
            motor_n_rpm = st.text_input("Двигатель: n, об/мин", _number(passport["motor_n_rpm"]))
            motor_synchronous = st.checkbox(
                "Синхронный двигатель", value=bool(passport["motor_synchronous"])
            )
        transmission_model = st.text_input(
            "Трансмиссия: модель", value=passport["transmission_model"] or ""
        )
        transmission_ratio = st.text_input(
            "Трансмиссия: передаточное число", _number(passport["transmission_ratio"])
        )
        transmission_eff = st.text_input(
            "Трансмиссия: КПД", _number(passport["transmission_eff"])
        )
        vfd = st.checkbox("ПЧ установлен", value=bool(passport["vfd"]))
        curve_qh = st.text_area("Кривая Q-H, JSON", _curve_text(passport, "pump_curve_qh_json"))
        curve_qeta = st.text_area("Кривая Q-η, JSON", _curve_text(passport, "pump_curve_qeta_json"))
        save_passport = st.form_submit_button("Сохранить паспорт")

    if save_passport:
        try:
            if not pump_model.strip() or not motor_model.strip():
                raise ValueError("Для насоса и двигателя нужны модели")
            database.add_passport(
                object_id,
                aggregate_id,
                valid_from=datetime.combine(valid_from, time.min),
                pump_model=pump_model.strip(),
                pump_kind=pump_kind,
                pump_q_nom=_parse_number("Насос: Q ном", pump_q_nom),
                pump_h_nom=_parse_number("Насос: H ном", pump_h_nom),
                pump_eta_nom=_parse_number("Насос: η ном", pump_eta_nom),
                motor_model=motor_model.strip(),
                motor_p_nom=_parse_number("Двигатель: P ном", motor_p_nom),
                motor_eta_nom=_parse_number("Двигатель: η ном", motor_eta_nom),
                pump_power_nom=_parse_number("Насос: мощность ном", pump_power_nom),
                pump_n_rpm=_parse_number("Насос: n", pump_n_rpm),
                pump_curve_qh_json=_curve(curve_qh, "Кривая Q-H"),
                pump_curve_qeta_json=_curve(curve_qeta, "Кривая Q-η"),
                motor_synchronous=motor_synchronous,
                motor_cos_phi=_parse_number("Двигатель: cos φ", motor_cos_phi),
                motor_voltage_kv=_parse_number("Двигатель: U", motor_voltage_kv),
                motor_i_nom=_parse_number("Двигатель: I ном", motor_i_nom),
                motor_n_rpm=_parse_number("Двигатель: n", motor_n_rpm),
                transmission_model=transmission_model.strip() or None,
                transmission_ratio=_parse_number(
                    "Трансмиссия: передаточное число", transmission_ratio
                ),
                transmission_eff=_parse_number("Трансмиссия: КПД", transmission_eff) or 1.0,
                vfd=vfd,
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.success("Паспорт сохранён.")

    st.markdown("### Точка телеметрии")
    st.caption("Точка с теми же датой, временем и metric будет заменена.")
    units = telemetry_units()
    metrics = list(units)
    with st.form("telemetry"):
        measured_date = st.date_input("Дата измерения", value=now.date())
        measured_time = st.time_input("Время измерения", value=now.time().replace(microsecond=0))
        metric = st.selectbox(
            "Параметр", metrics, format_func=lambda item: f"{item} ({units[item]})"
        )
        value = st.number_input("Значение", value=0.0, format="%.6f")
        quality = st.text_input("Качество / примечание")
        save_measurement = st.form_submit_button("Сохранить точку")

    if save_measurement:
        database.add_measurement(
            object_id,
            aggregate_id,
            datetime.combine(measured_date, measured_time),
            metric,
            value,
            units[metric],
            quality=quality.strip() or None,
        )
        st.success("Точка телеметрии сохранена.")
