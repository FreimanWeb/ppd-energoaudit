from ppd_audit.services.telemetry_series import telemetry_series


def test_telemetry_series_groups_metrics_by_unit_and_keeps_zero_values():
    series = telemetry_series([
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "p_in",
            "value": 1.2,
            "unit": "МПа",
            "is_station": 0,
        },
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "p_bg",
            "value": 0.0,
            "unit": "МПа",
            "is_station": 1,
        },
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "power",
            "value": 250.0,
            "unit": "кВт",
            "is_station": 0,
        },
    ])

    pressure = series["МПа"]
    assert pressure.loc[0, "p_вх"] == 1.2
    assert pressure.loc[0, "p_БГ (станция)"] == 0.0
    assert series["кВт"].loc[0, "P_эл"] == 250.0


def test_telemetry_series_excludes_daily_totals_from_charts():
    series = telemetry_series([
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "q_day",
            "value": 2400.0,
            "unit": "м³/сут",
            "is_station": 0,
        },
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "runtime",
            "value": 24.0,
            "unit": "ч",
            "is_station": 0,
        },
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "energy",
            "value": 4800.0,
            "unit": "кВт·ч",
            "is_station": 0,
        },
    ])

    assert series == {}
