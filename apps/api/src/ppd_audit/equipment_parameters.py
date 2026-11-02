"""Stable equipment keys with human-readable names, symbols, units and input domains."""


def _parameter(key, name, symbol="", unit="", kind="number", **details):
    return {
        "key": key,
        "component": key.split(".")[0],
        "name": name,
        "symbol": symbol,
        "unit": unit,
        "kind": kind,
        **details,
    }


_POSITIVE = {"minimum": 0, "exclusive_minimum": True}
_EFFICIENCY = {**_POSITIVE, "maximum": 1}
EQUIPMENT_PARAMETERS = [
    _parameter("pump.model", "Модель и исполнение насоса", kind="text"),
    _parameter(
        "pump.kind",
        "Тип насоса",
        kind="select",
        options=[
            {"value": "центробежный", "label": "Центробежный"},
            {"value": "объёмный", "label": "Объёмный"},
        ],
    ),
    _parameter("pump.q_nom", "Номинальная подача насоса", "Q_ном", "м³/ч", **_POSITIVE),
    _parameter("pump.h_nom", "Номинальный напор насоса", "H_ном", "м", **_POSITIVE),
    _parameter("pump.eta_nom", "Номинальный КПД насоса", "η_ном", "доля", **_EFFICIENCY),
    _parameter("pump.power_nom", "Потребляемая мощность насоса", "P_ном", "кВт", **_POSITIVE),
    _parameter("pump.n_rpm", "Частота вращения насоса", "n", "об/мин", **_POSITIVE),
    _parameter("pump.curve_qh", "Напорная характеристика насоса", "Q–H", "м³/ч; м", "curve_qh"),
    _parameter("pump.curve_qeta", "Характеристика КПД насоса", "Q–η", "м³/ч; доля", "curve_qeta"),
    _parameter(
        "pump.curve_source", "Источник и применимость характеристик насоса", kind="curve_source"
    ),
    _parameter("motor.model", "Модель двигателя", kind="text"),
    _parameter("motor.synchronous", "Синхронный тип двигателя", kind="bool"),
    _parameter(
        "motor.p_nom", "Номинальная мощность двигателя на валу", "P_ном", "кВт", **_POSITIVE
    ),
    _parameter("motor.eta_nom", "Номинальный КПД двигателя", "η_ном", "доля", **_EFFICIENCY),
    _parameter(
        "motor.cos_phi",
        "Номинальный коэффициент мощности двигателя",
        "cos φ",
        "доля",
        minimum=-1,
        maximum=1,
    ),
    _parameter("motor.voltage_kv", "Номинальное напряжение двигателя", "U_ном", "кВ", **_POSITIVE),
    _parameter("motor.i_nom", "Номинальный ток двигателя", "I_ном", "А", **_POSITIVE),
    _parameter(
        "motor.n_rpm", "Номинальная частота вращения двигателя", "n_ном", "об/мин", **_POSITIVE
    ),
    _parameter("transmission.model", "Модель механической передачи", kind="text"),
    _parameter("transmission.ratio", "Передаточное число", "i", **_POSITIVE),
    _parameter(
        "transmission.efficiency", "КПД механической передачи", "η_передачи", "доля", **_EFFICIENCY
    ),
    _parameter("vfd", "Наличие преобразователя частоты", kind="bool"),
]
