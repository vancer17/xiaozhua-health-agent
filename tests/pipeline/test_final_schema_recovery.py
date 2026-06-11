"""WP5 FinalSchemaCheck 失败 recovery 单元与集成测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from xiaozhua_health_agent.copy import (
    DraftCopyJSON,
    generate_mechanical_draft,
    load_copy_knowledge_bundle,
    resolve_copy_template,
)
from xiaozhua_health_agent.eval import (
    OutputValidationMode,
    ValidationResult,
    Violation,
    ViolationCode,
    load_health_triage_dataset,
    validate_output,
)
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.pipeline import (
    FINAL_SCHEMA_RECOVERY_ERROR_MESSAGE,
    HealthTriagePipelineOptions,
    HealthTriagePipelineStage,
    MergeValidateSingleAttemptResult,
    merge_and_validate_with_fallback_async,
    recover_from_final_schema_failure_async,
    should_attempt_final_schema_recovery,
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


def _build_recovery_context(
    dataset: object,
    case_id: str,
    knowledge_bundle: object,
) -> tuple[object, object, DraftCopyJSON]:
    """构建 FinalSchema recovery 测试用上下文（内部辅助）。

    :param dataset: mock case 数据集。
    :type dataset: object
    :param case_id: 用例 id。
    :type case_id: str
    :param knowledge_bundle: KB-TPL 知识包。
    :type knowledge_bundle: object
    :returns: ``(triage, resolved, good_draft)`` 三元组。
    :rtype: tuple[object, object, DraftCopyJSON]
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
    return triage, resolved, mechanical.draft


def _make_failed_schema_validation(
    *,
    mode: OutputValidationMode,
) -> ValidationResult[Any]:
    """构造模拟 FinalSchemaCheck 失败结果（内部辅助）。

    :param mode: 输出校验模式。
    :type mode: OutputValidationMode
    :returns: 未通过的校验结果。
    :rtype: ValidationResult[Any]
    """
    return ValidationResult(
        passed=False,
        schema_kind="output",
        schema_version="mock-v1",
        mode=mode,
        violations=[
            Violation(
                code=ViolationCode.FIELD_MISSING,
                path="title",
                message="模拟 FinalSchemaCheck 失败。",
            ),
        ],
        parsed=None,
    )


def test_should_attempt_final_schema_recovery() -> None:
    """``should_attempt_final_schema_recovery`` 仅在 final_schema 失败且启用时返回 True。"""
    failed = MergeValidateSingleAttemptResult(
        passed=False,
        stage=HealthTriagePipelineStage.FINAL_SCHEMA,
        output=None,
    )
    merge_failed = MergeValidateSingleAttemptResult(
        passed=False,
        stage=HealthTriagePipelineStage.MERGE,
        output=None,
    )

    assert should_attempt_final_schema_recovery(
        failed,
        enable_final_schema_recovery=True,
    )
    assert not should_attempt_final_schema_recovery(
        failed,
        enable_final_schema_recovery=False,
    )
    assert not should_attempt_final_schema_recovery(
        merge_failed,
        enable_final_schema_recovery=True,
    )


@pytest.mark.asyncio
async def test_final_schema_recovery_recovers_after_schema_failure(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """首次 FinalSchemaCheck 失败时，recovery 应以机械文案再合并并成功出站。"""
    triage, resolved, good_draft = _build_recovery_context(
        dataset,
        "normal_dog_daily_check",
        knowledge_bundle,
    )
    options = HealthTriagePipelineOptions(
        load_default_copy_bundle=False,
        enable_final_schema_recovery=True,
        enable_merge_fallback=False,
    )

    call_count = 0
    real_validate = validate_output

    def _validate_side_effect(
        output: object,
        *,
        mode: OutputValidationMode = OutputValidationMode.FULL,
    ) -> ValidationResult[Any]:
        """模拟首次 schema 失败、后续恢复成功（测试闭包）。

        :param output: 待校验输出对象。
        :type output: object
        :param mode: 输出校验模式。
        :type mode: OutputValidationMode
        :returns: 校验结果。
        :rtype: ValidationResult[Any]
        """
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_failed_schema_validation(mode=mode)
        return real_validate(output, mode=mode)

    with patch(
        "xiaozhua_health_agent.pipeline.merge_fallback.validate_output",
        side_effect=_validate_side_effect,
    ):
        result = await merge_and_validate_with_fallback_async(
            triage=triage,  # type: ignore[arg-type]
            draft=good_draft,
            resolved=resolved,  # type: ignore[arg-type]
            options=options,
        )

    assert result.passed is True
    assert result.used_final_schema_recovery is True
    assert result.final_schema_recovery_attempted is True
    assert result.used_merge_fallback is False
    assert result.merge_fallback_attempted is False
    assert result.stage == HealthTriagePipelineStage.COMPLETED
    assert result.output is not None
    assert result.pre_recovery_output is not None
    assert len(result.pre_recovery_violations) >= 1
    assert call_count == 2


@pytest.mark.asyncio
async def test_final_schema_recovery_disabled_stops_after_first_failure(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """``enable_final_schema_recovery=False`` 时首次 final_schema 失败即终止。"""
    triage, resolved, good_draft = _build_recovery_context(
        dataset,
        "normal_dog_daily_check",
        knowledge_bundle,
    )
    options = HealthTriagePipelineOptions(
        load_default_copy_bundle=False,
        enable_final_schema_recovery=False,
        enable_merge_fallback=False,
    )

    with patch(
        "xiaozhua_health_agent.pipeline.merge_fallback.validate_output",
        return_value=_make_failed_schema_validation(mode=OutputValidationMode.FULL),
    ):
        result = await merge_and_validate_with_fallback_async(
            triage=triage,  # type: ignore[arg-type]
            draft=good_draft,
            resolved=resolved,  # type: ignore[arg-type]
            options=options,
        )

    assert result.passed is False
    assert result.stage == HealthTriagePipelineStage.FINAL_SCHEMA
    assert result.used_final_schema_recovery is False
    assert result.final_schema_recovery_attempted is False
    assert result.pre_recovery_output is None
    assert len(result.violations) >= 1


@pytest.mark.asyncio
async def test_final_schema_recovery_still_fails_after_second_attempt(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """recovery 后仍 schema 失败时应保留 pre_recovery 快照并返回错误说明。"""
    triage, resolved, good_draft = _build_recovery_context(
        dataset,
        "normal_dog_daily_check",
        knowledge_bundle,
    )
    options = HealthTriagePipelineOptions(
        load_default_copy_bundle=False,
        enable_final_schema_recovery=True,
        enable_merge_fallback=False,
    )

    with patch(
        "xiaozhua_health_agent.pipeline.merge_fallback.validate_output",
        return_value=_make_failed_schema_validation(mode=OutputValidationMode.FULL),
    ):
        result = await merge_and_validate_with_fallback_async(
            triage=triage,  # type: ignore[arg-type]
            draft=good_draft,
            resolved=resolved,  # type: ignore[arg-type]
            options=options,
        )

    assert result.passed is False
    assert result.stage == HealthTriagePipelineStage.FINAL_SCHEMA
    assert result.used_final_schema_recovery is False
    assert result.final_schema_recovery_attempted is True
    assert result.pre_recovery_output is not None
    assert len(result.pre_recovery_violations) >= 1
    assert result.error_message is not None
    assert FINAL_SCHEMA_RECOVERY_ERROR_MESSAGE.split("。")[0] in result.error_message


@pytest.mark.asyncio
async def test_recover_from_final_schema_failure_async_rejects_wrong_stage(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """``recover_from_final_schema_failure_async`` 仅接受 ``stage=final_schema``。"""
    triage, resolved, good_draft = _build_recovery_context(
        dataset,
        "normal_dog_daily_check",
        knowledge_bundle,
    )
    wrong_attempt = MergeValidateSingleAttemptResult(
        passed=False,
        stage=HealthTriagePipelineStage.MERGE,
        output=None,
    )
    options = HealthTriagePipelineOptions(load_default_copy_bundle=False)

    with pytest.raises(ValueError, match="final_schema"):
        await recover_from_final_schema_failure_async(
            failed_attempt=wrong_attempt,
            triage=triage,  # type: ignore[arg-type]
            resolved=resolved,  # type: ignore[arg-type]
            original_draft=good_draft,
            options=options,
        )
