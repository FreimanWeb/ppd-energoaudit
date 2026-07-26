from ppd_audit.ingest.calc_parameter_json import (
    build_parameter_json,
    export_calculation_parameter_jsons,
)
from ppd_audit.ingest.report_calc import CellBinding, ParsedCalc
from ppd_audit.spec import Branch, ObjectSpec, WaterType


def test_build_parameter_json_groups_values_for_manual_review():
    parsed = ParsedCalc(
        spec=ObjectSpec(
            id="kns-test",
            name="КНС test",
            water_type=WaterType.fresh,
            branch=Branch.kns,
            source="data/raw/ntu/test.xlsx",
            aggregates=[],
        ),
        cells=[
            CellBinding(
                object_id="kns-test",
                object_name="КНС test",
                water_type="пресная",
                aggregate_id="НА-1",
                role="input",
                field="p_in",
                label="pвх, давление на входе",
                method_ref="8/11/17",
                unit="МПа",
                sheet="Расчет",
                label_cell="A1",
                value_cell="B1",
                raw=1.2,
                value=1.2,
            ),
            CellBinding(
                object_id="kns-test",
                object_name="КНС test",
                water_type="пресная",
                aggregate_id="НА-1",
                role="passport",
                field="pump.model",
                label="Модель насоса",
                method_ref="паспорт",
                unit="",
                sheet="Расчет",
                label_cell="A2",
                value_cell="B2",
                raw="ЦНС 180",
                value=None,
            ),
        ],
    )

    payload = build_parameter_json(parsed, source_file="test.xlsx", source_kind="test")

    assert payload["schema"] == "ntu.calculation.parameters.v1"
    assert payload["object"]["id"] == "kns-test"
    assert payload["source"]["file"] == "test.xlsx"
    assert payload["aggregates"]["НА-1"]["input"]["p_in"]["value"] == 1.2
    assert payload["aggregates"]["НА-1"]["input"]["p_in"]["status"] == "parsed"
    assert payload["aggregates"]["НА-1"]["passport"]["pump.model"]["value"] == "ЦНС 180"
    assert payload["aggregates"]["НА-1"]["input"]["p_out"]["value"] is None
    assert payload["aggregates"]["НА-1"]["input"]["p_out"]["status"] == "needs_review"


def test_export_parameter_jsons_handles_extra_files(tmp_path):
    result = export_calculation_parameter_jsons(out_root=tmp_path)

    assert result["errors"] == []
