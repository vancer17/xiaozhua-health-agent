"""WP2 DerivedFacts 单元与 case 驱动测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.context import DerivedFacts, compute_derived_facts
from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.parse import parse_input


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


def _derived_for_case_id(dataset: object, case_id: str) -> DerivedFacts:
    """解析指定 case 并计算 DerivedFacts。

    :param dataset: case 数据集。
    :type dataset: object
    :param case_id: case 标识。
    :type case_id: str
    :returns: 派生事实。
    :rtype: DerivedFacts
    """
    case = dataset.case_by_id(case_id)  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.passed is True
    assert parsed.fact_sheet is not None
    return compute_derived_facts(parsed.fact_sheet)


def test_mild_fever_after_exercise_exercise_context(dataset: object) -> None:
    """#2：运动后应有宽口径运动情境，非安静。"""
    derived = _derived_for_case_id(dataset, "mild_fever_after_exercise")
    assert derived.has_exercise_context is True
    assert derived.is_resting is False


def test_high_fever_resting_not_exercise_context(dataset: object) -> None:
    """#3：安静高热不应有运动情境。"""
    derived = _derived_for_case_id(dataset, "high_fever_resting")
    assert derived.has_exercise_context is False
    assert derived.is_resting is True


def test_respiratory_case_four_not_severe_emergency(dataset: object) -> None:
    """#4：呼吸困难 alone 不触发 severeRestingResp / 张口呼吸。"""
    derived = _derived_for_case_id(dataset, "respiratory_rate_high_resting")
    assert derived.severe_resting_resp is False
    assert derived.open_mouth_breathing_reported is False


def test_emergency_breathing_case_twelve_severe(dataset: object) -> None:
    """#12：安静极高呼吸 + 张口呼吸 + 短鼻。"""
    derived = _derived_for_case_id(dataset, "emergency_breathing_difficulty")
    assert derived.severe_resting_resp is True
    assert derived.open_mouth_breathing_reported is True
    assert derived.is_brachycephalic is True


def test_missing_vitals_core_missing(dataset: object) -> None:
    """#10：核心体征三项全缺。"""
    derived = _derived_for_case_id(dataset, "missing_vitals")
    assert derived.vitals_core_missing is True


def test_emergency_seizure_not_vitals_core_missing(dataset: object) -> None:
    """#13：体温缺失但 HR/RR 存在，不算 vitalsCoreMissing。"""
    derived = _derived_for_case_id(dataset, "emergency_seizure")
    assert derived.vitals_core_missing is False


def test_conflict_user_device_normal_and_fever(dataset: object) -> None:
    """#11：用户说正常 + 设备安静发热。"""
    derived = _derived_for_case_id(dataset, "conflict_user_normal_sensor_fever")
    assert derived.user_says_normal is True
    assert derived.device_shows_resting_fever is True


def test_heart_rate_resting_chronic_tachycardia_split(dataset: object) -> None:
    """#6 vs #20：心率 vs 呼吸维度分流（#6 RR=40 可同时满足 tachypnea 阈值）。"""
    case_six = _derived_for_case_id(dataset, "heart_rate_high_resting_warning")
    case_twenty = _derived_for_case_id(dataset, "chronic_heart_resp_warning")
    assert case_six.has_resting_tachycardia is True
    assert case_twenty.has_resting_tachycardia is False
    assert case_twenty.has_resting_tachypnea is True


def test_heart_rate_after_play_exercise_context(dataset: object) -> None:
    """#5：运动后心率不应算安静心动过速。"""
    derived = _derived_for_case_id(dataset, "heart_rate_high_after_play")
    assert derived.has_exercise_context is True
    assert derived.has_resting_tachycardia is False


def test_puppy_fever_is_puppy_kitten(dataset: object) -> None:
    """#17：幼犬标记。"""
    derived = _derived_for_case_id(dataset, "puppy_fever_high_risk")
    assert derived.is_puppy_kitten is True


def test_stale_device_data_not_vitals_core_missing(dataset: object) -> None:
    """#19：数据过期但 vitals 有值。"""
    derived = _derived_for_case_id(dataset, "stale_device_data")
    assert derived.vitals_core_missing is False


def test_all_twenty_cases_compute_derived_facts(dataset: object) -> None:
    """20 case 均应能成功计算 DerivedFacts。"""
    for case in dataset.cases:  # type: ignore[attr-defined]
        parsed = parse_input(case.input)
        assert parsed.passed is True
        assert parsed.fact_sheet is not None
        derived = compute_derived_facts(parsed.fact_sheet)
        assert isinstance(derived, DerivedFacts)
