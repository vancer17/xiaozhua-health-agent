"""WP5 MergeOutput 失败 violations 映射测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from xiaozhua_health_agent.copy import (
    generate_mechanical_draft_from_input,
    load_copy_knowledge_bundle,
)
from xiaozhua_health_agent.eval import (
    ViolationCode,
    ViolationDomain,
    load_health_triage_dataset,
    violations_from_pydantic_validation_error,
)
from xiaozhua_health_agent.output import (
    MergeOutputError,
    MergeOutputFailureKind,
    build_merge_output_error_for_safety_notice,
    build_merge_output_error_for_validation,
    make_merge_safety_notice_missing_violation,
    merge_agent_output,
    violations_from_merge_output_error,
    violations_from_merge_output_error_async,
)
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.pipeline import (
    HealthTriagePipelineStage,
    attempt_merge_and_validate_once,
)
from xiaozhua_health_agent.schemas import AgentOutput
from xiaozhua_health_agent.triage import run_triage_core


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


def test_make_merge_safety_notice_missing_violation_fields() -> None:
    """必填免责声明缺失违规应含 path 与 SAFETY_NOTICE_REQUIRED_MISSING 码。"""
    violation = make_merge_safety_notice_missing_violation()

    assert violation.code == ViolationCode.SAFETY_NOTICE_REQUIRED_MISSING.value
    assert violation.domain == ViolationDomain.SCHEMA.value
    assert violation.path == "safetyNotice"
    assert violation.field == "safetyNotice"


def test_build_merge_output_error_for_safety_notice_carries_violations() -> None:
    """``build_merge_output_error_for_safety_notice`` 应预填 violations。"""
    error = build_merge_output_error_for_safety_notice()

    assert error.failure_kind == MergeOutputFailureKind.SAFETY_NOTICE_REQUIRED_MISSING
    assert len(error.violations) == 1
    assert error.violations[0].path == "safetyNotice"


def test_merge_agent_output_safety_notice_error_has_violations(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """``merge_agent_output`` 在必填免责声明缺失时应抛出带 violations 的异常。"""
    case = dataset.case_by_id("emergency_seizure")  # type: ignore[attr-defined]
    mechanical = generate_mechanical_draft_from_input(
        case.input,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    draft = mechanical.draft.model_copy(update={"safety_notice": ""}, deep=True)
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    assert triage.safety_notice_required is True

    with pytest.raises(MergeOutputError) as exc_info:
        merge_agent_output(triage=triage, draft=draft)

    error = exc_info.value
    assert error.failure_kind == MergeOutputFailureKind.SAFETY_NOTICE_REQUIRED_MISSING
    assert len(error.violations) == 1
    mapped = violations_from_merge_output_error(error)
    assert mapped[0].code == ViolationCode.SAFETY_NOTICE_REQUIRED_MISSING.value


def test_build_merge_output_error_for_validation_maps_pydantic_errors() -> None:
    """``ValidationError`` 应映射为多条 schema 域违规。"""
    try:
        AgentOutput.model_validate(
            {
                "riskLevel": "not-a-risk",
                "scene": "health_triage",
                "title": "",
                "summary": "x",
                "evidence": [],
                "recommendation": "x",
                "whenToSeeVet": "x",
                "missingData": [],
                "confidence": "high",
                "safetyNotice": "x",
                "primaryAction": {"label": "x"},
            },
        )
    except ValidationError as exc:
        merge_error = build_merge_output_error_for_validation(exc)
    else:
        msg = "期望 AgentOutput.model_validate 抛出 ValidationError。"
        raise AssertionError(msg)

    assert merge_error.failure_kind == (
        MergeOutputFailureKind.AGENT_OUTPUT_VALIDATION_FAILED
    )
    assert len(merge_error.violations) >= 1
    assert all(
        item.domain == ViolationDomain.SCHEMA.value for item in merge_error.violations
    )


def test_violations_from_merge_output_error_fallback_from_cause() -> None:
    """无预填 violations 时应从 ``__cause__`` 推导 Pydantic 违规。"""
    try:
        AgentOutput.model_validate({"riskLevel": "watch"})
    except ValidationError as exc:
        bare_error = MergeOutputError(
            "合并失败",
            failure_kind=MergeOutputFailureKind.UNKNOWN,
        )
        bare_error.__cause__ = exc
    else:
        msg = "期望 ValidationError。"
        raise AssertionError(msg)

    mapped = violations_from_merge_output_error(bare_error)
    expected = violations_from_pydantic_validation_error(
        bare_error.__cause__,  # type: ignore[arg-type]
        domain=ViolationDomain.SCHEMA.value,
    )
    assert mapped == expected
    assert len(mapped) >= 1


@pytest.mark.asyncio
async def test_violations_from_merge_output_error_async_matches_sync() -> None:
    """异步映射应与同步结果一致。"""
    error = build_merge_output_error_for_safety_notice()
    sync_result = violations_from_merge_output_error(error)
    async_result = await violations_from_merge_output_error_async(error)
    assert async_result == sync_result


def test_attempt_merge_validate_once_merge_stage_violations(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """跳过 merge-ready 时 merge 失败应返回 ``stage=merge`` 且 violations 非空。"""
    case = dataset.case_by_id("emergency_seizure")  # type: ignore[attr-defined]
    mechanical = generate_mechanical_draft_from_input(
        case.input,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    bad_draft = mechanical.draft.model_copy(update={"safety_notice": ""}, deep=True)
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    if not triage.safety_notice_required:
        pytest.skip("该 case 未要求 safetyNotice。")

    attempt = attempt_merge_and_validate_once(
        triage=triage,
        draft=bad_draft,
        skip_final_schema_check=False,
        skip_merge_ready_check=True,
    )

    assert attempt.passed is False
    assert attempt.stage == HealthTriagePipelineStage.MERGE
    assert len(attempt.violations) >= 1
    assert attempt.violations[0].path == "safetyNotice"
