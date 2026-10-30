from ppd_audit.services.telemetry_acceptance import acceptance_report


def row(metric, value, unit, timestamp="2026-10-01T12:00:00", **extra):
    return dict(
        metric=metric,
        value=value,
        unit=unit,
        timestamp=timestamp,
        is_station=False,
        quality="good",
        **extra,
    )


def test_daily_energy_and_volume_must_belong_to_same_day():
    report = acceptance_report([
        row("energy", 100, "кВт·ч"),
        row("q_day", 50, "м³", "2026-10-02T12:00:00"),
    ])
    assert report["calculations"][0]["status"] == "blocked"
    report = acceptance_report([row("energy", 100, "кВт·ч"), row("q_day", 50, "м³")])
    assert report["calculations"][0]["status"] == "available"


def test_wrong_units_and_station_totals_cannot_enable_aggregate_kpi():
    inputs = [row("energy", 100, "Вт·ч"), row("q_day", 50, "м³")]
    assert acceptance_report(inputs)["calculations"][0]["status"] == "blocked"
    inputs[0] = row("energy", 100, "кВт·ч")
    inputs[1]["is_station"] = True
    assert acceptance_report(inputs)["calculations"][0]["status"] == "blocked"


def test_missing_invalid_and_temporal_gaps_are_visible():
    report = acceptance_report([
        row("power", -1, "кВт"),
        row("power", 30, "кВт", "2026-10-02T12:00:00"),
        row("power", 40, "кВт", "2026-10-04T12:00:00"),
    ])
    signals = {s["metric"]: s for s in report["signals"]}
    assert signals["power"]["valid"] == 2
    assert signals["power"]["max_gap_hours"] == 48
    assert signals["p_in"]["records"] == 0
    assert signals["p_in"]["issues"]
    assert signals["power"]["issues"]


def test_zero_volume_and_duplicate_daily_totals_are_not_usable():
    assert (
        acceptance_report([row("energy", 100, "кВт·ч"), row("q_day", 0, "м³")])["calculations"][0][
            "status"
        ]
        == "blocked"
    )
    assert (
        acceptance_report([
            row("energy", 100, "кВт·ч"),
            row("q_day", 50, "м³"),
            row("q_day", 60, "м³", "2026-10-01T15:00:00"),
        ])["calculations"][0]["status"]
        == "blocked"
    )
