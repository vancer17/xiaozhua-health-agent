"""WP5 文案重试协调器类型定义测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.copy import resolve_copy_template
from xiaozhua_health_agent.eval import (
    Violation,
    ViolationCode,
    ViolationDomain,
    load_health_triage_dataset,
)
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.pipeline.retry_types import (
    DEFAULT_DRAFT_RETRY_OPTIONS,
    DraftRetryAttemptRecord,
    DraftRetryContext,
    DraftRetryGeneratorKind,
    DraftRetryOptions,
    DraftRetryOutcome,
    RetryAction,
    build_draft_retry_context,
    compare_retry_action_strength,
)
from xiaozhua_health_agent.triage import run_triage_core


@pytest.fixture
def retry_context() -> DraftRetryContext:
    """构造 emergency_seizure case 的重试上下文。

    :returns: ``DraftRetryContext`` 实例。
    :rtype: DraftRetryContext
    """
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    dataset = load_health_triage_dataset(cases_path)
    case = dataset.case_by_id("emergency_seizure")
    parsed = parse_input(case.input)
    assert parsed.passed and parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(parsed.fact_sheet, triage)
    return build_draft_retry_context(
        parsed=parsed,
        triage=triage,
        resolved=resolved,
    )


def test_default_draft_retry_options_mechanical_path() -> None:
    """默认配置应对机械路径关闭 LLM 并启用机械兜底。"""
    opts = DEFAULT_DRAFT_RETRY_OPTIONS
    assert opts.llm_enabled is False
    assert opts.fallback_to_mechanical is True
    assert opts.max_attempts == 3
    assert opts.guard_mode == "strict"


def test_resolved_mechanical_fallback_options_stronger_than_first_pass() -> None:
    """终端兜底选项应比首次机械选项更保守（关闭编号前缀）。"""
    opts = DraftRetryOptions()
    first = opts.resolved_mechanical_options()
    fallback = opts.resolved_mechanical_fallback_options()
    assert first.append_missing_mentions is True
    assert fallback.append_missing_mentions is True
    assert fallback.summary_use_numbered_prefix is False


def test_resolved_llm_retry_options_disables_inner_mechanical_fallback() -> None:
    """内层 LLM 选项不应自行机械兜底，由外层协调器负责。"""
    opts = DraftRetryOptions(llm_enabled=True)
    inner = opts.resolved_llm_retry_options()
    assert inner.fallback_to_mechanical is False


def test_can_invoke_llm_respects_max_llm_retries() -> None:
    """``can_invoke_llm`` 应在达到 ``max_llm_retries`` 后返回 ``False``。"""
    opts = DraftRetryOptions(llm_enabled=True, max_llm_retries=2)
    assert opts.can_invoke_llm(0) is True
    assert opts.can_invoke_llm(1) is True
    assert opts.can_invoke_llm(2) is False
    assert opts.remaining_llm_slots(1) == 1
    assert opts.remaining_llm_slots(2) == 0


def test_build_draft_retry_context_success(retry_context: DraftRetryContext) -> None:
    """成功路径应保留 caseId 与 triage 锁定字段。"""
    assert retry_context.case_id == "emergency_seizure"
    assert retry_context.parsed.fact_sheet is not None
    assert retry_context.triage.final_risk_level == "emergency"


def test_build_draft_retry_context_rejects_failed_parse(
    retry_context: DraftRetryContext,
) -> None:
    """解析失败时不应构造协调器上下文。"""
    parsed = parse_input({})
    assert not parsed.passed
    with pytest.raises(ValueError, match="fact_sheet"):
        build_draft_retry_context(
            parsed=parsed,
            triage=retry_context.triage,
            resolved=retry_context.resolved,
        )


def test_compare_retry_action_strength_ordering() -> None:
    """动作强度序应与设计一致（兜底强于 LLM 重试）。"""
    assert (
        compare_retry_action_strength(
            RetryAction.MECHANICAL_FALLBACK.value,
            RetryAction.RETRY_LLM.value,
        )
        > 0
    )
    assert (
        compare_retry_action_strength(
            RetryAction.ACCEPT.value,
            RetryAction.ABORT.value,
        )
        < 0
    )


def test_draft_retry_outcome_last_violations() -> None:
    """``last_violations`` 应返回最后一轮记录。"""
    violation = Violation(
        code=ViolationCode.FORBIDDEN_PATTERN_HIT.value,
        domain=ViolationDomain.GUARD.value,
        path="summary",
        field="summary",
        message="测试",
    )
    history = (
        DraftRetryAttemptRecord(
            attempt_index=1,
            action_before_validate=RetryAction.DETERMINISTIC_REPAIR.value,
            generator=DraftRetryGeneratorKind.MECHANICAL,
            passed=False,
            violations=(),
        ),
        DraftRetryAttemptRecord(
            attempt_index=2,
            action_before_validate=RetryAction.MECHANICAL_FALLBACK.value,
            generator=DraftRetryGeneratorKind.MECHANICAL_FALLBACK,
            passed=True,
            violations=(violation,),
        ),
    )
    outcome = DraftRetryOutcome(
        passed=True,
        draft=None,
        attempt_count=2,
        used_mechanical_fallback=True,
        generator=DraftRetryGeneratorKind.MECHANICAL_FALLBACK,
        violations_history=history,
        terminal_action=RetryAction.ACCEPT.value,
    )
    assert outcome.last_violations == (violation,)
