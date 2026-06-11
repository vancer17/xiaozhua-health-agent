"""WP5 ``classify_violations`` 路由测试。"""

from __future__ import annotations

import asyncio

import pytest

from xiaozhua_health_agent.eval import (
    Violation,
    ViolationCode,
    ViolationDomain,
    ViolationSeverity,
)
from xiaozhua_health_agent.pipeline import (
    ClassifyViolationsResult,
    DraftRetryOptions,
    RetryAction,
    classify_violations,
    classify_violations_async,
    classify_violations_detailed,
    filter_retryable_violations,
    max_retry_action,
)


def _violation(
    *,
    code: str,
    domain: str = ViolationDomain.GUARD.value,
    severity: str = ViolationSeverity.HIGH.value,
    path: str = "summary",
) -> Violation:
    """构造测试用 ``Violation``（内部辅助）。

    :param code: 违规码。
    :type code: str
    :param domain: 违规域。
    :type domain: str
    :param severity: 严重度。
    :type severity: str
    :param path: JSON 路径。
    :type path: str
    :returns: 违规记录。
    :rtype: Violation
    """
    return Violation(
        code=code,  # type: ignore[arg-type]
        domain=domain,  # type: ignore[arg-type]
        path=path,
        field=path.split(".", maxsplit=1)[0],
        message="测试违规",
        severity=severity,  # type: ignore[arg-type]
    )


def test_classify_empty_violations_returns_accept() -> None:
    """无违规时应返回 ``ACCEPT``。"""
    assert classify_violations(()) == RetryAction.ACCEPT


def test_filter_retryable_violations_ignores_semantic_eval() -> None:
    """``semantic_eval`` 域违规不应进入路由。"""
    violations = (
        _violation(
            code=ViolationCode.MUST_MENTION_MISSING.value,
            domain=ViolationDomain.SEMANTIC_EVAL.value,
        ),
        _violation(code=ViolationCode.FORBIDDEN_PATTERN_HIT.value),
    )
    filtered = filter_retryable_violations(violations)
    assert len(filtered) == 1
    assert filtered[0].code == ViolationCode.FORBIDDEN_PATTERN_HIT.value


def test_classify_ignores_semantic_eval_only() -> None:
    """仅含评测域违规时应等价于 ``ACCEPT``。"""
    violations = (
        _violation(
            code=ViolationCode.RISK_MISMATCH.value,
            domain=ViolationDomain.RISK_EVAL.value,
        ),
    )
    assert classify_violations(violations) == RetryAction.ACCEPT


def test_classify_forbidden_mechanical_path_uses_fallback() -> None:
    """机械路径下禁止词应路由为 ``MECHANICAL_FALLBACK``。"""
    action = classify_violations(
        (_violation(code=ViolationCode.FORBIDDEN_PATTERN_HIT.value),),
        options=DraftRetryOptions(llm_enabled=False),
    )
    assert action == RetryAction.MECHANICAL_FALLBACK


def test_classify_forbidden_llm_path_uses_retry_llm() -> None:
    """LLM 路径下禁止词应路由为 ``RETRY_LLM``。"""
    action = classify_violations(
        (_violation(code=ViolationCode.FORBIDDEN_PATTERN_HIT.value),),
        options=DraftRetryOptions(llm_enabled=True),
        attempt_index=1,
    )
    assert action == RetryAction.RETRY_LLM


def test_classify_schema_error_llm_enabled() -> None:
    """结构错误在 LLM 启用时应 ``RETRY_LLM``。"""
    action = classify_violations(
        (
            _violation(
                code=ViolationCode.FIELD_MISSING.value,
                domain=ViolationDomain.SCHEMA.value,
                path="title",
            ),
        ),
        options=DraftRetryOptions(llm_enabled=True),
    )
    assert action == RetryAction.RETRY_LLM


def test_classify_action_lock_prefers_deterministic_repair() -> None:
    """行动锁定不一致应优先 ``DETERMINISTIC_REPAIR``。"""
    action = classify_violations(
        (_violation(code=ViolationCode.ACTION_ROUTE_MISMATCH.value),),
        options=DraftRetryOptions(enable_deterministic_repair=True),
    )
    assert action == RetryAction.DETERMINISTIC_REPAIR


def test_classify_safety_notice_missing_uses_repair() -> None:
    """免责声明缺失应走确定性修补。"""
    action = classify_violations(
        (
            _violation(
                code=ViolationCode.SAFETY_NOTICE_REQUIRED_MISSING.value,
                severity=ViolationSeverity.MEDIUM.value,
            ),
        ),
    )
    assert action == RetryAction.DETERMINISTIC_REPAIR


def test_classify_forced_mention_med_default_deterministic_repair() -> None:
    """默认配置下 MED forcedMention 应优先尝试机械补 mention。"""
    action = classify_violations(
        (
            _violation(
                code=ViolationCode.FORCED_MENTION_MISSING.value,
                severity=ViolationSeverity.MEDIUM.value,
            ),
        ),
    )
    assert action == RetryAction.DETERMINISTIC_REPAIR


def test_classify_forced_mention_med_accept_when_repair_disabled() -> None:
    """关闭确定性修补且允许 MED 警告时应 ``ACCEPT``。"""
    action = classify_violations(
        (
            _violation(
                code=ViolationCode.FORCED_MENTION_MISSING.value,
                severity=ViolationSeverity.MEDIUM.value,
            ),
        ),
        options=DraftRetryOptions(
            enable_deterministic_repair=False,
            allow_accept_with_med_warnings=True,
        ),
    )
    assert action == RetryAction.ACCEPT


def test_classify_forced_mention_enforced_triggers_llm_retry() -> None:
    """``enforce_forced_mentions_on_retry`` 且 LLM 启用时应 ``RETRY_LLM``。"""
    action = classify_violations(
        (
            _violation(
                code=ViolationCode.FORCED_MENTION_MISSING.value,
                severity=ViolationSeverity.MEDIUM.value,
            ),
        ),
        options=DraftRetryOptions(
            llm_enabled=True,
            enforce_forced_mentions_on_retry=True,
        ),
    )
    assert action == RetryAction.RETRY_LLM


def test_classify_risk_text_inconsistent_med_accept() -> None:
    """``RISK_TEXT_INCONSISTENT``（MED）默认 ``ACCEPT``。"""
    action = classify_violations(
        (
            _violation(
                code=ViolationCode.RISK_TEXT_INCONSISTENT.value,
                severity=ViolationSeverity.MEDIUM.value,
            ),
        ),
    )
    assert action == RetryAction.ACCEPT


def test_classify_multiple_violations_takes_strongest() -> None:
    """多条违规应取最强动作。"""
    violations = (
        _violation(
            code=ViolationCode.FORCED_MENTION_MISSING.value,
            severity=ViolationSeverity.MEDIUM.value,
        ),
        _violation(code=ViolationCode.EVIDENCE_HALLUCINATION.value),
    )
    action = classify_violations(
        violations,
        options=DraftRetryOptions(llm_enabled=False),
    )
    assert action == RetryAction.MECHANICAL_FALLBACK


def test_max_retry_action_empty_is_accept() -> None:
    """空动作序列聚合为 ``ACCEPT``。"""
    assert max_retry_action(()) == RetryAction.ACCEPT


def test_attempt_budget_escalates_retry_llm_to_fallback() -> None:
    """达到 ``max_attempts`` 时应将 ``RETRY_LLM`` 升级为机械兜底。"""
    action = classify_violations(
        (_violation(code=ViolationCode.FORBIDDEN_PATTERN_HIT.value),),
        options=DraftRetryOptions(llm_enabled=True, max_attempts=3),
        attempt_index=3,
    )
    assert action == RetryAction.MECHANICAL_FALLBACK


def test_attempt_budget_escalates_deterministic_repair_to_fallback() -> None:
    """末次尝试时 ``DETERMINISTIC_REPAIR`` 应升级为机械兜底。"""
    action = classify_violations(
        (_violation(code=ViolationCode.ACTION_ROUTE_MISMATCH.value),),
        options=DraftRetryOptions(max_attempts=2),
        attempt_index=2,
    )
    assert action == RetryAction.MECHANICAL_FALLBACK


def test_fallback_disabled_yields_abort() -> None:
    """关闭机械兜底时 HIGH 违规在机械路径应 ``ABORT``。"""
    action = classify_violations(
        (_violation(code=ViolationCode.EVIDENCE_HALLUCINATION.value),),
        options=DraftRetryOptions(
            llm_enabled=False,
            fallback_to_mechanical=False,
        ),
    )
    assert action == RetryAction.ABORT


def test_emergency_tone_mechanical_uses_deterministic_repair() -> None:
    """机械路径下紧急语气弱化可先尝试确定性修补。"""
    action = classify_violations(
        (_violation(code=ViolationCode.EMERGENCY_TONE_WEAK.value),),
        options=DraftRetryOptions(
            llm_enabled=False,
            enable_deterministic_repair=True,
        ),
        attempt_index=1,
    )
    assert action == RetryAction.DETERMINISTIC_REPAIR


def test_classify_violations_detailed_metadata() -> None:
    """详细分类应暴露过滤计数与 raw/final 动作。"""
    violations = (
        _violation(
            code=ViolationCode.MUST_MENTION_MISSING.value,
            domain=ViolationDomain.SEMANTIC_EVAL.value,
        ),
        _violation(code=ViolationCode.FORBIDDEN_PATTERN_HIT.value),
    )
    result = classify_violations_detailed(
        violations,
        options=DraftRetryOptions(llm_enabled=True),
    )
    assert isinstance(result, ClassifyViolationsResult)
    assert result.ignored_violation_count == 1
    assert len(result.considered_violations) == 1
    assert result.raw_action == RetryAction.RETRY_LLM
    assert result.action == RetryAction.RETRY_LLM


def test_classify_violations_rejects_invalid_attempt_index() -> None:
    """``attempt_index`` 非法时应抛出 ``ValueError``。"""
    with pytest.raises(ValueError, match="attempt_index"):
        classify_violations((), attempt_index=0)


def test_classify_violations_async_matches_sync() -> None:
    """异步入口应与同步分类结果一致。"""

    async def _run() -> RetryAction:
        """执行异步分类（闭包）。

        :returns: 协调动作。
        :rtype: RetryAction
        """
        return await classify_violations_async(
            (_violation(code=ViolationCode.FORBIDDEN_PATTERN_HIT.value),),
            options=DraftRetryOptions(llm_enabled=True),
        )

    assert asyncio.run(_run()) == RetryAction.RETRY_LLM
