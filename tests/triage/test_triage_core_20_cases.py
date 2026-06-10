"""WP3 Triage Core 20 case risk-only 回归测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.eval import (
    assert_risk_only_hard_gate,
    load_health_triage_dataset,
)
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.triage import run_triage_core, run_triage_risk_batch


@pytest.fixture
def dataset() -> object:
    """加载 V1 mock case 数据集。"""
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    return load_health_triage_dataset(cases_path)


def test_triage_risk_batch_hard_gate(dataset: object) -> None:
    """20/20 riskLevel 硬门槛全绿。"""
    report = run_triage_risk_batch(dataset)  # type: ignore[arg-type]
    assert_risk_only_hard_gate(report)


@pytest.mark.parametrize(
    ("case_id", "expected_risk", "expected_confidence"),
    [
        ("normal_dog_daily_check", "normal", "high"),
        ("mild_fever_after_exercise", "watch", "medium"),
        ("high_fever_resting", "warning", "high"),
        ("respiratory_rate_high_resting", "warning", "high"),
        ("heart_rate_high_after_play", "watch", "medium"),
        ("heart_rate_high_resting_warning", "warning", "high"),
        ("hrv_stress_watch", "watch", "medium"),
        ("limping_pain_watch", "watch", "medium"),
        ("recovery_slow_watch", "watch", "medium"),
        ("missing_vitals", "watch", "low"),
        ("conflict_user_normal_sensor_fever", "warning", "medium"),
        ("emergency_breathing_difficulty", "emergency", "high"),
        ("emergency_seizure", "emergency", "high"),
        ("persistent_vomiting_warning", "warning", "medium"),
        ("mild_diarrhea_watch", "watch", "medium"),
        ("senior_cat_low_energy", "warning", "medium"),
        ("puppy_fever_high_risk", "warning", "high"),
        ("post_vaccine_tired_watch", "watch", "medium"),
        ("stale_device_data", "watch", "low"),
        ("chronic_heart_resp_warning", "warning", "high"),
    ],
)
def test_triage_core_per_case(
    dataset: object,
    case_id: str,
    expected_risk: str,
    expected_confidence: str,
) -> None:
    """逐 case 校验 risk 与 confidence。"""
    case = dataset.case_by_id(case_id)  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.passed and parsed.fact_sheet is not None
    result = run_triage_core(parsed.fact_sheet)
    assert result.final_risk_level == expected_risk
    assert result.confidence == expected_confidence
