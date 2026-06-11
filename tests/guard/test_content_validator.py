"""WP5 ④-B ValidateContent（内容守卫）测试。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from xiaozhua_health_agent.copy import (
    DraftCopyJSON,
    clear_default_copy_knowledge_cache,
    generate_mechanical_draft_from_input,
    load_copy_knowledge_bundle,
    resolve_copy_template,
)
from xiaozhua_health_agent.eval import ViolationCode, load_health_triage_dataset
from xiaozhua_health_agent.guard import (
    ContentGuardInput,
    ContentGuardMode,
    load_synonym_map_async,
    validate_content,
    validate_content_async,
)
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.paths import default_synonym_map_path
from xiaozhua_health_agent.pipeline import (
    HealthTriagePipelineOptions,
    HealthTriagePipelineStage,
    run_health_triage,
)
from xiaozhua_health_agent.triage import run_triage_core


@pytest.fixture(autouse=True)
def _clear_copy_bundle_cache() -> None:
    """每个测试前清空默认知识包缓存。"""
    clear_default_copy_knowledge_cache()


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


def _build_guard_input_for_case(
    case_input: Mapping[str, Any],
    *,
    knowledge_bundle: object,
    draft_override: DraftCopyJSON | None = None,
) -> ContentGuardInput:
    """为单条 case 构造 ``ContentGuardInput``（测试辅助）。

    :param case_input: mock case 输入 JSON。
    :type case_input: collections.abc.Mapping[str, Any]
    :param knowledge_bundle: KB-TPL 知识包。
    :type knowledge_bundle: object
    :param draft_override: 可选替换草稿；省略时使用机械路径产出。
    :type draft_override: DraftCopyJSON | None
    :returns: 内容守卫输入上下文。
    :rtype: ContentGuardInput
    """
    parsed = parse_input(case_input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    if draft_override is not None:
        draft = draft_override
    else:
        mechanical = generate_mechanical_draft_from_input(
            case_input,
            bundle=knowledge_bundle,  # type: ignore[arg-type]
        )
        draft = mechanical.draft
    return ContentGuardInput(
        draft=draft,
        triage=triage,
        fact_sheet=parsed.fact_sheet,
        resolved=resolved,
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )


def test_validate_content_all_mechanical_cases_pass(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """20 case 机械文案在 strict 守卫下应全部通过（无 HIGH 违规）。"""
    for case in dataset.cases:  # type: ignore[attr-defined]
        guard_input = _build_guard_input_for_case(
            case.input,
            knowledge_bundle=knowledge_bundle,
        )
        result = validate_content(guard_input)
        assert result.hard_passed is True, (
            f"{case.case_id}: {[v.code for v in result.violations if v.severity == 'HIGH']}"
        )
        assert result.passed is True, case.case_id


@pytest.mark.asyncio
async def test_validate_content_async_matches_sync(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """异步守卫入口应与同步入口产出等价 ``passed`` 与违规码集合。"""
    case = dataset.case_by_id("emergency_seizure")  # type: ignore[attr-defined]
    guard_input = _build_guard_input_for_case(
        case.input,
        knowledge_bundle=knowledge_bundle,
    )
    sync_result = validate_content(guard_input)
    async_result = await validate_content_async(guard_input)

    assert sync_result.passed == async_result.passed
    assert sync_result.hard_passed == async_result.hard_passed
    assert {item.code for item in sync_result.violations} == {
        item.code for item in async_result.violations
    }


@pytest.mark.asyncio
async def test_load_synonym_map_async_returns_map() -> None:
    """``load_synonym_map_async`` 应异步加载 KB-SYN 同义词表。"""
    synonym_map = await load_synonym_map_async(default_synonym_map_path())
    assert len(synonym_map.global_synonyms) > 0


def test_forbidden_pattern_in_recommendation_fails(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """注入禁止词「保证」应触发 ``FORBIDDEN_PATTERN_HIT``。"""
    case = dataset.case_by_id("normal_dog_daily_check")  # type: ignore[attr-defined]
    guard_input = _build_guard_input_for_case(
        case.input,
        knowledge_bundle=knowledge_bundle,
    )
    poisoned = guard_input.draft.model_copy(
        update={"recommendation": "放心，一定没事，我保证治愈。"},
    )
    poisoned_input = ContentGuardInput(
        draft=poisoned,
        triage=guard_input.triage,
        fact_sheet=guard_input.fact_sheet,
        resolved=guard_input.resolved,
        copy_bundle=guard_input.copy_bundle,
    )
    result = validate_content(poisoned_input)
    assert result.hard_passed is False
    codes = {item.code for item in result.violations}
    assert ViolationCode.FORBIDDEN_PATTERN_HIT.value in codes


def test_evidence_hallucination_fails(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """篡改 ``evidence[]`` 为 ② 未提供内容应触发 ``EVIDENCE_HALLUCINATION``。"""
    case = dataset.case_by_id("normal_dog_daily_check")  # type: ignore[attr-defined]
    guard_input = _build_guard_input_for_case(
        case.input,
        knowledge_bundle=knowledge_bundle,
    )
    poisoned = guard_input.draft.model_copy(
        update={"evidence": ["体温 38.5°C，完全正常，趋势持续向好。"]},
    )
    poisoned_input = ContentGuardInput(
        draft=poisoned,
        triage=guard_input.triage,
        fact_sheet=guard_input.fact_sheet,
        resolved=guard_input.resolved,
        copy_bundle=guard_input.copy_bundle,
    )
    result = validate_content(poisoned_input)
    assert result.hard_passed is False
    codes = {item.code for item in result.violations}
    assert ViolationCode.EVIDENCE_HALLUCINATION.value in codes


def test_emergency_tone_downgrade_fails(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """紧急 case 注入弱化语气应触发 ``EMERGENCY_TONE_WEAK``。"""
    case = dataset.case_by_id("emergency_seizure")  # type: ignore[attr-defined]
    guard_input = _build_guard_input_for_case(
        case.input,
        knowledge_bundle=knowledge_bundle,
    )
    poisoned = guard_input.draft.model_copy(
        update={"recommendation": "先在家观察即可，不必着急联系兽医。"},
    )
    poisoned_input = ContentGuardInput(
        draft=poisoned,
        triage=guard_input.triage,
        fact_sheet=guard_input.fact_sheet,
        resolved=guard_input.resolved,
        copy_bundle=guard_input.copy_bundle,
    )
    result = validate_content(poisoned_input)
    assert result.hard_passed is False
    codes = {item.code for item in result.violations}
    assert ViolationCode.EMERGENCY_TONE_WEAK.value in codes


def test_pipeline_strict_mode_fails_when_guard_would_fail(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """strict 模式下 HIGH 违规应使 ``validate_content`` 阻断 ``passed``。"""
    case = dataset.case_by_id("normal_dog_daily_check")  # type: ignore[attr-defined]
    guard_input = _build_guard_input_for_case(
        case.input,
        knowledge_bundle=knowledge_bundle,
    )
    poisoned = guard_input.draft.model_copy(
        update={"recommendation": "我保证百分百治愈，不用担心。"},
    )
    poisoned_input = ContentGuardInput(
        draft=poisoned,
        triage=guard_input.triage,
        fact_sheet=guard_input.fact_sheet,
        resolved=guard_input.resolved,
        copy_bundle=guard_input.copy_bundle,
    )
    guard_result = validate_content(poisoned_input)
    assert guard_result.passed is False
    assert guard_result.hard_passed is False
    assert any(
        item.code == ViolationCode.FORBIDDEN_PATTERN_HIT.value
        for item in guard_result.violations
    )


def test_pipeline_report_only_continues_with_warnings(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """``report_only`` 模式下管道仍应完成并记录 ``guard_warnings``。"""
    case = dataset.case_by_id("normal_dog_daily_check")  # type: ignore[attr-defined]
    result = run_health_triage(
        case.input,
        options=HealthTriagePipelineOptions(
            load_default_copy_bundle=False,
            guard_mode=ContentGuardMode.REPORT_ONLY,
        ),
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    assert result.passed is True
    assert result.stage == HealthTriagePipelineStage.COMPLETED
    assert result.guard_result is not None


def test_pipeline_includes_guard_result_on_success(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """成功管道应携带 ``guard_result`` 且 ``hard_passed=True``。"""
    case = dataset.case_by_id("emergency_seizure")  # type: ignore[attr-defined]
    result = run_health_triage(
        case.input,
        options=HealthTriagePipelineOptions(load_default_copy_bundle=False),
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    assert result.passed is True
    assert result.guard_result is not None
    assert result.guard_result.hard_passed is True
