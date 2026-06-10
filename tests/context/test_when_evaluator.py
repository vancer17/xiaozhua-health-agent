"""WP2 evalWhen 通用求值器测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.context import (
    EvalContext,
    WhenEvaluationError,
    build_eval_context,
    compute_derived_facts,
    eval_when,
    eval_when_traced,
)
from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.parse import parse_input

# EMG-04 概念结构（见 triage-core-spec.md §5.3）
EMG_04_WHEN: dict[str, object] = {
    "all": [
        {"field": "userReport.breathingDifficulty", "eq": True},
        {
            "any": [
                {"fact": "severeRestingResp"},
                {"fact": "openMouthBreathingReported"},
                {
                    "all": [
                        {"fact": "isBrachycephalic"},
                        {"field": "vitals.respiratoryRateBpm", "gte": 55},
                    ],
                },
            ],
        },
    ],
}


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


def _eval_context_for_case(dataset: object, case_id: str) -> EvalContext:
    """为指定 case 构建 EvalContext。

    :param dataset: case 数据集。
    :type dataset: object
    :param case_id: case 标识。
    :type case_id: str
    :returns: 求值上下文。
    :rtype: EvalContext
    """
    case = dataset.case_by_id(case_id)  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.passed is True
    assert parsed.fact_sheet is not None
    derived = compute_derived_facts(parsed.fact_sheet)
    return build_eval_context(parsed.fact_sheet, derived)


def test_eval_all_empty_is_true(dataset: object) -> None:
    """空 all 组合应为真。"""
    ctx = _eval_context_for_case(dataset, "normal_dog_daily_check")
    assert eval_when({"all": []}, ctx) is True


def test_eval_any_empty_is_false(dataset: object) -> None:
    """空 any 组合应为假。"""
    ctx = _eval_context_for_case(dataset, "normal_dog_daily_check")
    assert eval_when({"any": []}, ctx) is False


def test_eval_not_negates(dataset: object) -> None:
    """not 应对子块取反。"""
    ctx = _eval_context_for_case(dataset, "mild_fever_after_exercise")
    assert eval_when({"not": {"fact": "hasExerciseContext"}}, ctx) is False
    assert eval_when({"not": {"fact": "isResting"}}, ctx) is True


def test_eval_field_null_is_false(dataset: object) -> None:
    """field 在 null 时应为假。"""
    ctx = _eval_context_for_case(dataset, "missing_vitals")
    assert eval_when({"field": "vitals.temperatureC", "gte": 39.0}, ctx) is False


def test_eval_derived_max_signal_risk(dataset: object) -> None:
    """derived 原子应比较 maxSignalRisk。"""
    ctx = _eval_context_for_case(dataset, "emergency_breathing_difficulty")
    assert eval_when({"derived": "maxSignalRisk", "eq": "emergency"}, ctx) is True


def test_emg_04_case_four_does_not_match(dataset: object) -> None:
    """#4：breathingDifficulty  alone 不触发 EMG-04。"""
    ctx = _eval_context_for_case(dataset, "respiratory_rate_high_resting")
    assert eval_when(EMG_04_WHEN, ctx) is False


def test_emg_04_case_twelve_matches(dataset: object) -> None:
    """#12：应命中 EMG-04 when。"""
    ctx = _eval_context_for_case(dataset, "emergency_breathing_difficulty")
    assert eval_when(EMG_04_WHEN, ctx) is True


def test_eval_signal_risk_gte(dataset: object) -> None:
    """signal 原子应按 riskGte 匹配。"""
    ctx = _eval_context_for_case(dataset, "respiratory_rate_high_resting")
    when = {
        "signal": {"id": "respiratory", "riskGte": "warning"},
    }
    assert eval_when(when, ctx) is True


def test_unknown_fact_raises(dataset: object) -> None:
    """未知 fact 符号应 fail-fast。"""
    ctx = _eval_context_for_case(dataset, "normal_dog_daily_check")
    with pytest.raises(WhenEvaluationError):
        eval_when({"fact": "notARealFact"}, ctx)


def test_eval_when_traced_returns_trace(dataset: object) -> None:
    """带轨迹求值应记录子条件。"""
    ctx = _eval_context_for_case(dataset, "emergency_breathing_difficulty")
    result = eval_when_traced(EMG_04_WHEN, ctx)
    assert result.matched is True
    assert len(result.trace) > 0
    assert any(entry.block_type == "fact" for entry in result.trace)
