"""WP5 Merge 阶段兜底单元与集成测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.copy import (
    DraftCopyJSON,
    generate_mechanical_draft,
    load_copy_knowledge_bundle,
    resolve_copy_template,
)
from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.pipeline import (
    HealthTriagePipelineOptions,
    HealthTriagePipelineStage,
    attempt_merge_and_validate_once,
    merge_and_validate_with_fallback_async,
    run_health_triage,
)
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


def _build_merge_context(
    dataset: object,
    case_id: str,
    knowledge_bundle: object,
) -> tuple[object, object, DraftCopyJSON, DraftCopyJSON]:
    """构建 Merge 兜底测试用上下文（内部辅助）。

    :param dataset: mock case 数据集。
    :type dataset: object
    :param case_id: 用例 id。
    :type case_id: str
    :param knowledge_bundle: KB-TPL 知识包。
    :type knowledge_bundle: object
    :returns: ``(triage, resolved, mechanical_draft, bad_draft)`` 四元组。
    :rtype: tuple[object, object, DraftCopyJSON, DraftCopyJSON]
    """
    case = dataset.case_by_id(case_id)  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    mechanical = generate_mechanical_draft(resolved)
    bad_draft = mechanical.draft.model_copy(
        update={"safety_notice": ""},
        deep=True,
    )
    return triage, resolved, mechanical.draft, bad_draft


@pytest.mark.asyncio
async def test_merge_fallback_recovers_from_merge_error(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """首次合并失败时，Merge 阶段机械兜底应恢复并成功出站。"""
    triage, resolved, good_draft, bad_draft = _build_merge_context(
        dataset,
        "emergency_seizure",
        knowledge_bundle,
    )
    if not triage.safety_notice_required:  # type: ignore[attr-defined]
        pytest.skip("该 case 未要求 safetyNotice，跳过 MergeOutputError 场景。")

    options = HealthTriagePipelineOptions(
        load_default_copy_bundle=False,
        enable_merge_fallback=True,
    )

    result = await merge_and_validate_with_fallback_async(
        triage=triage,  # type: ignore[arg-type]
        draft=bad_draft,
        resolved=resolved,  # type: ignore[arg-type]
        options=options,
    )

    assert result.passed is True
    assert result.used_merge_fallback is True
    assert result.merge_fallback_attempted is True
    assert result.stage == HealthTriagePipelineStage.COMPLETED
    assert result.output is not None
    assert result.draft != bad_draft
    assert result.draft.title == good_draft.title


@pytest.mark.asyncio
async def test_merge_fallback_disabled_stops_after_first_failure(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """``enable_merge_fallback=False`` 时首次失败即终止，不尝试兜底。"""
    triage, resolved, _good_draft, bad_draft = _build_merge_context(
        dataset,
        "emergency_seizure",
        knowledge_bundle,
    )
    if not triage.safety_notice_required:  # type: ignore[attr-defined]
        pytest.skip("该 case 未要求 safetyNotice，跳过 MergeOutputError 场景。")

    options = HealthTriagePipelineOptions(
        load_default_copy_bundle=False,
        enable_merge_fallback=False,
    )

    result = await merge_and_validate_with_fallback_async(
        triage=triage,  # type: ignore[arg-type]
        draft=bad_draft,
        resolved=resolved,  # type: ignore[arg-type]
        options=options,
    )

    assert result.passed is False
    assert result.stage == HealthTriagePipelineStage.MERGE_READY
    assert result.used_merge_fallback is False
    assert result.merge_fallback_attempted is False
    assert len(result.violations) >= 1


def test_merge_fallback_disabled_with_skip_merge_ready_returns_merge_violations(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """跳过 merge-ready 且禁用兜底时，应在 ``stage=merge`` 返回结构化 violations。"""
    triage, resolved, _good_draft, bad_draft = _build_merge_context(
        dataset,
        "emergency_seizure",
        knowledge_bundle,
    )
    if not triage.safety_notice_required:  # type: ignore[attr-defined]
        pytest.skip("该 case 未要求 safetyNotice，跳过 MergeOutputError 场景。")

    options = HealthTriagePipelineOptions(
        load_default_copy_bundle=False,
        enable_merge_fallback=False,
        skip_merge_ready_check=True,
    )

    attempt = attempt_merge_and_validate_once(
        triage=triage,  # type: ignore[arg-type]
        draft=bad_draft,
        skip_final_schema_check=False,
        skip_merge_ready_check=options.skip_merge_ready_check,
    )

    assert attempt.passed is False
    assert attempt.stage == HealthTriagePipelineStage.MERGE
    assert len(attempt.violations) >= 1
    assert attempt.violations[0].path == "safetyNotice"


def test_attempt_merge_and_validate_once_success(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """合法 mechanical draft 应单次通过 merge 与 FULL schema。"""
    triage, _resolved, good_draft, _bad = _build_merge_context(
        dataset,
        "normal_dog_daily_check",
        knowledge_bundle,
    )

    attempt = attempt_merge_and_validate_once(
        triage=triage,  # type: ignore[arg-type]
        draft=good_draft,
        skip_final_schema_check=False,
    )

    assert attempt.passed is True
    assert attempt.stage == HealthTriagePipelineStage.COMPLETED
    assert attempt.output is not None


def test_normal_pipeline_does_not_use_merge_fallback(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """正常 case 路径不应触发 Merge 阶段兜底。"""
    case = dataset.case_by_id("normal_dog_daily_check")  # type: ignore[attr-defined]
    result = run_health_triage(
        case.input,
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    assert result.passed is True
    assert result.used_merge_fallback is False
    assert result.merge_fallback_attempted is False
    assert result.used_final_schema_recovery is False
    assert result.final_schema_recovery_attempted is False
