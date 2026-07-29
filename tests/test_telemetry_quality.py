from ppd_audit.services.telemetry_quality import assess_telemetry_quality


def test_quality_marks_impossible_efficiency_unfit():
    quality = assess_telemetry_quality(
        eta_unit=1.11,
        uses_daily_flow=True,
        uses_daily_power=True,
    )

    assert quality.status == "unfit"
    assert "efficiency_above_one" in quality.codes
    assert quality.allows_economic_conclusions is False


def test_quality_marks_daily_basis_as_assumption():
    quality = assess_telemetry_quality(
        eta_unit=0.71,
        uses_daily_flow=True,
        uses_daily_power=False,
    )

    assert quality.status == "assumptions"
    assert quality.basis["flow"] == "Q_сут / T_сут"
    assert quality.basis["power"] == "P_эл в момент снимка"
    assert quality.allows_economic_conclusions is True


def test_quality_rejects_inconsistent_daily_totals():
    quality = assess_telemetry_quality(
        eta_unit=0.71,
        uses_daily_flow=False,
        uses_daily_power=False,
        energy_kwh=100.0,
        integrated_energy_kwh=120.0,
        runtime_hours=5.0,
        powered_hours=7.0,
        q_day_m3=1000.0,
        integrated_flow_m3=800.0,
    )

    assert quality.status == "unfit"
    assert {
        "energy_mismatch",
        "runtime_mismatch",
        "daily_flow_mismatch",
    } <= set(quality.codes)
