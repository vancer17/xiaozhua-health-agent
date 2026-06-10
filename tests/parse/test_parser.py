"""WP1 输入解析单元与集成测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.eval import load_health_triage_dataset, validate_input
from xiaozhua_health_agent.parse import (
    assert_all_parse_passed,
    get_fact_value,
    parse_all_case_inputs,
    parse_input,
)


@pytest.fixture
def dataset() -> object:
    """加载 V1 mock case 数据集。

    :returns: ``HealthTriageDataset`` 实例。
    :rtype: object
    """
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    return load_health_triage_dataset(cases_path)


def test_all_twenty_cases_parse_successfully(dataset: object) -> None:
    """20 case input 应全部解析成功并产出 FactSheet。"""
    inputs = [case.input for case in dataset.cases]  # type: ignore[attr-defined]
    records = parse_all_case_inputs(inputs)
    assert len(records) == 20
    assert_all_parse_passed(records)
    for record in records:
        assert record.result.fact_sheet is not None
        assert record.result.agent_input is not None
        assert record.result.fact_sheet.identity.case_id == record.case_id


def test_missing_vitals_preserves_null_vitals(dataset: object) -> None:
    """missing_vitals：核心体征应保持 null，不被补全。"""
    case = dataset.case_by_id("missing_vitals")  # type: ignore[attr-defined]
    result = parse_input(case.input)
    assert result.passed is True
    assert result.fact_sheet is not None
    vitals = result.fact_sheet.vitals
    assert vitals.temperature_c is None
    assert vitals.heart_rate_bpm is None
    assert vitals.respiratory_rate_bpm is None
    assert vitals.hrv_ms is None
    assert vitals.steps_today is None
    assert get_fact_value(result.fact_sheet, "vitals.temperatureC") is None


def test_stale_device_data_preserves_data_quality(dataset: object) -> None:
    """stale_device_data：dataQuality=stale 应原样保留。"""
    case = dataset.case_by_id("stale_device_data")  # type: ignore[attr-defined]
    result = parse_input(case.input)
    assert result.passed is True
    assert result.fact_sheet is not None
    assert result.fact_sheet.device.data_quality == "stale"
    assert result.fact_sheet.device.device_online is False


def test_parse_fails_when_required_field_missing(dataset: object) -> None:
    """故意缺必填字段时应明确失败，不 silent pass。"""
    case = dataset.case_by_id("normal_dog_daily_check")  # type: ignore[attr-defined]
    raw = case.input.model_dump(by_alias=True, mode="json")
    del raw["pet"]
    result = parse_input(raw)
    assert result.passed is False
    assert result.fact_sheet is None
    assert any(v.code == "FIELD_MISSING" for v in result.violations)


def test_parse_fails_on_invalid_scene(dataset: object) -> None:
    """scene 非 health_triage 时应契约校验失败。"""
    case = dataset.case_by_id("normal_dog_daily_check")  # type: ignore[attr-defined]
    raw = case.input.model_dump(by_alias=True, mode="json")
    raw["scene"] = "nutrition_advice"
    result = parse_input(raw)
    assert result.passed is False
    assert result.fact_sheet is None


def test_normalization_trims_user_report_text(dataset: object) -> None:
    """归一化应对用户文本执行 trim。"""
    case = dataset.case_by_id("normal_dog_daily_check")  # type: ignore[attr-defined]
    raw = case.input.model_dump(by_alias=True, mode="json")
    raw["userReport"]["text"] = "  今天看起来挺正常。  "
    result = parse_input(raw)
    assert result.passed is True
    assert result.fact_sheet is not None
    assert result.fact_sheet.user_report.text == "今天看起来挺正常。"


def test_fact_index_contains_upstream_risk(dataset: object) -> None:
    """fact_index 应包含上游 riskLevel 路径。"""
    case = dataset.case_by_id("emergency_breathing_difficulty")  # type: ignore[attr-defined]
    result = parse_input(case.input)
    assert result.passed is True
    assert result.fact_sheet is not None
    assert get_fact_value(result.fact_sheet, "healthEvidence.riskLevel") == "emergency"


def test_validate_input_and_parse_input_agree_on_valid_case(dataset: object) -> None:
    """契约校验与解析门面对合法 case 应一致通过。"""
    case = dataset.case_by_id("high_fever_resting")  # type: ignore[attr-defined]
    schema_result = validate_input(case.input)
    parse_result = parse_input(case.input)
    assert schema_result.passed is True
    assert parse_result.passed is True
