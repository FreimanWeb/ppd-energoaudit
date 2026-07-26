import json

import pytest
from pydantic import ValidationError

from ppd_audit.telemetry import (
    TelemetrySubmission,
    export_telemetry_validation_summary,
    map_telemetry_to_calculation_input,
    telemetry_payload_from_excel_draft,
    validate_telemetry,
)


def test_telemetry_submission_normalizes_kgf_pressure():
    submission = TelemetrySubmission.model_validate({
        "object_id": "dns7s",
        "technical_place": "КНС-85",
        "injection_agent": "water",
        "aggregation_period": "day",
        "records": [
            {
                "timestamp": "2026-07-12T00:00:00",
                "aggregate_id": "Н-4",
                "metric": "p_in",
                "unit": "кгс/см²",
                "value": 12,
            }
        ],
    })

    payload = submission.to_payload()

    assert submission.object_id == "dns7s"
    assert payload.records[0].tag == "Н-4"
    assert payload.records[0].unit == "МПа"
    assert payload.records[0].value == pytest.approx(1.176)


def test_telemetry_payload_uses_default_schema():
    payload = TelemetrySubmission.model_validate({
        "object_id": "dns7s",
        "technical_place": "КНС-85",
        "aggregation_period": "day",
        "records": [
            {
                "timestamp": "2026-07-12T00:00:00",
                "aggregate_id": "Н-4",
                "metric": "p_in",
                "unit": "МПа",
                "value": 1.2,
            }
        ],
    }).to_payload()

    assert payload.model_dump(by_alias=True)["schema"] == "telemetry.v1"


def test_telemetry_submission_rejects_calculated_output_metric():
    with pytest.raises(ValidationError):
        TelemetrySubmission.model_validate({
            "object_id": "dns7s",
            "technical_place": "КНС-85",
            "aggregation_period": "day",
            "records": [
                {
                    "timestamp": "2026-07-12T00:00:00",
                    "aggregate_id": "Н-4",
                    "metric": "efficiency",
                    "unit": "%",
                    "value": 78,
                }
            ],
        })


def test_zero_measurement_is_marked_missing_for_calculation():
    payload = TelemetrySubmission.model_validate({
        "object_id": "dns7s",
        "technical_place": "КНС-85",
        "aggregation_period": "day",
        "records": [
            {
                "timestamp": "2026-07-12T00:00:00",
                "aggregate_id": "Н-4",
                "metric": "p_in",
                "unit": "МПа",
                "value": 0,
            }
        ],
    }).to_payload()

    report = validate_telemetry(payload)

    assert {issue.code for issue in report.issues} >= {"zero_is_missing", "missing_pressure_in"}


def test_telemetry_v1_reports_missing_calculation_fields():
    payload = telemetry_payload_from_excel_draft({
        "source": {"relative_path": "sample.xlsx"},
        "telemetry": [
            {
                "sheet": "Telemetry",
                "row": 2,
                "timestamp": "2026-01-02T03:04:00",
                "tag": "НА-1",
                "metric": "power_kw",
                "label": "Мощность, кВт",
                "unit": "кВт",
                "value": 12.5,
            }
        ],
    })

    report = validate_telemetry(payload)

    assert payload.schema == "telemetry.v1"
    assert report.total_records == 1
    assert report.by_metric == {"power_kw": 1}
    assert report.ok is False
    assert {issue.code for issue in report.issues} >= {
        "missing_pressure_in",
        "missing_pressure_out",
        "missing_flow",
        "missing_density",
    }


def test_maps_telemetry_v1_to_normalized_calculation_input():
    payload = telemetry_payload_from_excel_draft({
        "source": {"relative_path": "sample.xlsx"},
        "telemetry": [
            {
                "timestamp": "2026-01-02T00:00:00",
                "tag": "НА-1",
                "metric": "pressure",
                "label": "Давление на входе",
                "unit": "МПа",
                "value": 1.2,
            },
            {
                "timestamp": "2026-01-02T00:00:00",
                "tag": "НА-1",
                "metric": "pressure",
                "label": "Давление на выходе",
                "unit": "МПа",
                "value": 9.8,
            },
            {
                "timestamp": "2026-01-02T00:00:00",
                "tag": "НА-1",
                "metric": "flow",
                "label": "Суточная перекачка",
                "unit": "м³",
                "value": 2400,
            },
            {
                "timestamp": "2026-01-02T00:00:00",
                "tag": "НА-1",
                "metric": "energy_kwh",
                "label": "Суточный расход ЭЭ",
                "unit": "кВт·ч",
                "value": 4800,
            },
            {
                "timestamp": "2026-01-02T00:00:00",
                "tag": "НА-1",
                "metric": "runtime_h",
                "label": "Время работы",
                "unit": "ч",
                "value": 24,
            },
            {
                "timestamp": "2026-01-02T00:00:00",
                "tag": "НА-1",
                "metric": "density_kg_m3",
                "label": "Плотность",
                "unit": "кг/м³",
                "value": 1000,
            },
        ],
    })

    mapped = map_telemetry_to_calculation_input(payload, tag="НА-1")

    assert mapped.tag == "НА-1"
    assert mapped.p_in == 1.2
    assert mapped.p_out == 9.8
    assert mapped.q_day == 2400
    assert mapped.w == 4800
    assert mapped.t == 24
    assert mapped.rho == 1000
    assert mapped.to_regime().flow() == 100


def test_exports_validation_summary_for_draft_json_files(tmp_path):
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()
    (draft_root / "sample.xlsx.json").write_text(
        json.dumps({
            "source": {"relative_path": "sample.xlsx"},
            "telemetry": [
                {
                    "timestamp": "2026-01-02T00:00:00",
                    "tag": "НА-1",
                    "metric": "pressure",
                    "label": "Давление на входе",
                    "unit": "МПа",
                    "value": 1.2,
                },
                {
                    "timestamp": "2026-01-02T00:00:00",
                    "tag": "НА-1",
                    "metric": "power_kw",
                    "label": "Мощность, кВт",
                    "unit": "кВт",
                    "value": 12.5,
                },
            ],
        }),
        encoding="utf-8",
    )

    out_path = export_telemetry_validation_summary(draft_root, tmp_path / "summary.json")

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["summary"]["total_files"] == 1
    assert data["summary"]["total_records"] == 2
    assert data["files"][0]["path"] == "sample.xlsx.json"
    assert data["files"][0]["normalized_input"]["p_in"] == 1.2
    assert data["files"][0]["normalized_input"]["p_electric"] == 12.5
    assert data["files"][0]["validation"]["ok"] is False
