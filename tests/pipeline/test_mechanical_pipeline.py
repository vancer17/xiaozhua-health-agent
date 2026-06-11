"""WP5 阶段 1 — 机械健康分诊管道门面测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from xiaozhua_health_agent.copy import load_copy_knowledge_bundle
from xiaozhua_health_agent.eval import (
    OutputValidationMode,
    load_health_triage_dataset,
    run_full_output_evaluation_with_provider,
    validate_output,
)
from xiaozhua_health_agent.pipeline import (
    HealthTriagePipelineStage,
    assert_milestone_b_hard_gate,
    make_health_triage_output_provider,
    run_health_triage,
    run_health_triage_async,
    run_mechanical_health_triage_full_output_batch,
    run_milestone_b_batch,
)
from xiaozhua_health_agent.pipeline.pipeline_types import HealthTriagePipelineOptions


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


@pytest.fixture
def knowledge_bundle() -> object:
    """加载 copy 知识资产聚合包。

    :returns: ``CopyKnowledgeBundle`` 实例。
    :rtype: object
    """
    return load_copy_knowledge_bundle()


def test_mechanical_pipeline_single_case_output_schema(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """单 case 机械管道应产出通过 FULL schema 的 ``AgentOutput``。"""
    case = dataset.case_by_id("emergency_seizure")  # type: ignore[attr-defined]
    result = run_health_triage(
        case.input,
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )

    assert result.passed is True
    assert result.stage == HealthTriagePipelineStage.COMPLETED
    assert result.output is not None
    assert result.triage is not None
    assert result.output.risk_level == result.triage.final_risk_level
    assert result.output.confidence == result.triage.confidence

    schema_check = validate_output(
        result.output,
        mode=OutputValidationMode.FULL,
    )
    assert schema_check.passed is True


def test_mechanical_pipeline_all_cases_risk_locked(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """20 case 机械管道 risk/confidence 应与 ② 锁定值一致。"""
    for case in dataset.cases:  # type: ignore[attr-defined]
        result = run_health_triage(
            case.input,
            copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
        )
        assert result.passed is True, case.case_id
        assert result.output is not None
        assert result.triage is not None
        assert result.output.risk_level == case.expected.risk_level, case.case_id
        assert result.output.confidence == case.expected.confidence, case.case_id


@pytest.mark.asyncio
async def test_async_pipeline_matches_sync(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """异步入口应与同步入口产出等价 risk/confidence。"""
    case = dataset.case_by_id("mild_fever_after_exercise")  # type: ignore[attr-defined]
    options = HealthTriagePipelineOptions(load_default_copy_bundle=False)

    sync_result = run_health_triage(
        case.input,
        options=options,
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    async_result = await run_health_triage_async(
        case.input,
        options=options,
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )

    assert sync_result.passed is True
    assert async_result.passed is True
    assert sync_result.output is not None
    assert async_result.output is not None
    assert sync_result.output.risk_level == async_result.output.risk_level
    assert sync_result.output.title == async_result.output.title


def test_parse_failure_returns_stage_parse() -> None:
    """缺必填字段时应停在 parse 阶段。"""
    result = run_health_triage({"caseId": "bad-input-only"})

    assert result.passed is False
    assert result.stage == HealthTriagePipelineStage.PARSE
    assert result.output is None
    assert len(result.violations) > 0


def test_provider_for_full_output_evaluation(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """``make_health_triage_output_provider`` 应支撑 full-output 硬门槛（risk 维度）。"""
    provider = make_health_triage_output_provider(
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    report = run_full_output_evaluation_with_provider(
        dataset,  # type: ignore[arg-type]
        provider,
    )
    assert report.risk_passed == report.total
    assert report.total == 20


def test_full_output_batch_helper(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """批跑辅助函数应产出 full-output 报告且 risk 维全绿。"""
    report = run_mechanical_health_triage_full_output_batch(
        dataset,  # type: ignore[arg-type]
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    assert report.total == 20
    assert report.risk_passed == 20


def test_milestone_b_closed_loop_acceptance(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """里程碑 B 闭环：20/20 管道成功 + full-output 硬门槛全绿。"""
    milestone_report = run_milestone_b_batch(
        dataset,  # type: ignore[arg-type]
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    assert_milestone_b_hard_gate(milestone_report)


def test_async_loads_default_bundle_when_not_injected() -> None:
    """未注入 bundle 时异步路径应能加载默认知识包并完成单 case。"""

    async def _run() -> bool:
        """执行冒烟用例（闭包）。

        :returns: 管道是否通过。
        :rtype: bool
        """
        cases_path = (
            Path(__file__).resolve().parents[2]
            / "docs/cases/health_triage_cases.v1.json"
        )
        ds = load_health_triage_dataset(cases_path)
        case = ds.case_by_id("normal_dog_daily_check")
        result = await run_health_triage_async(case.input)
        return result.passed

    assert asyncio.run(_run()) is True
