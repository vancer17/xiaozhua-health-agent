"""WP5 LLM 文案生成桥接层单元测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from xiaozhua_health_agent.copy import (
    DraftGenerationRetryResult,
    DraftRetryFailureKind,
    QwenChatCompletionRequest,
    QwenChatCompletionResponse,
    load_copy_knowledge_bundle,
    resolve_copy_template,
)
from xiaozhua_health_agent.eval import (
    Violation,
    ViolationCode,
    ViolationDomain,
    load_health_triage_dataset,
)
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.pipeline import (
    DraftRetryContext,
    DraftRetryOptions,
    LlmDraftGenerationError,
    build_draft_retry_context,
    build_guard_repair_user_content,
    generate_guard_repair_llm_draft_async,
    generate_initial_llm_draft_async,
)
from xiaozhua_health_agent.triage import run_triage_core


@pytest.fixture
def retry_context() -> DraftRetryContext:
    """构造 mild_fever case 的重试上下文。

    :returns: ``DraftRetryContext`` 实例。
    :rtype: DraftRetryContext
    """
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    dataset = load_health_triage_dataset(cases_path)
    case = dataset.case_by_id("mild_fever_after_exercise")
    parsed = parse_input(case.input)
    assert parsed.passed and parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    bundle = load_copy_knowledge_bundle()
    resolved = resolve_copy_template(parsed.fact_sheet, triage, bundle=bundle)
    return build_draft_retry_context(
        parsed=parsed,
        triage=triage,
        resolved=resolved,
        copy_bundle=bundle,
    )


def _minimal_draft_payload(resolved: object) -> dict[str, Any]:
    """构造最小合法 DraftCopyJSON 载荷。

    :param resolved: ``CopyTemplateResolved`` 实例。
    :type resolved: object
    :returns: JSON 可序列化载荷。
    :rtype: dict[str, Any]
    """
    primary = resolved.primary_action_draft.model_dump(by_alias=True, mode="json")  # type: ignore[attr-defined]
    return {
        "title": "活动后指标偏高",
        "summary": "刚运动后体温略高，建议休息补水后复查。",
        "evidence": list(resolved.evidence_bullets),  # type: ignore[attr-defined]
        "recommendation": "请先休息并补充饮水。",
        "whenToSeeVet": "若休息后仍偏高，请联系兽医。",
        "safetyNotice": "",
        "primaryAction": primary,
        "secondaryAction": None,
    }


def _make_completion(content: str) -> QwenChatCompletionResponse:
    """构造测试用通义补全响应。

    :param content: 模型输出正文。
    :type content: str
    :returns: 补全响应 DTO。
    :rtype: QwenChatCompletionResponse
    """
    return QwenChatCompletionResponse(
        content=content,
        model="qwen-test",
        usage=None,
        finish_reason="stop",
        raw=cast(Any, None),
    )


class _StubQwenClient:
    """满足 ``llm_draft_generation`` 对 client 的最小依赖。"""

    default_model: str = "qwen-test"


def test_build_guard_repair_user_content_includes_violation_fields() -> None:
    """guard repair 提示应列出违规码、路径与说明。"""
    violation = Violation(
        code=ViolationCode.FORBIDDEN_PATTERN_HIT.value,
        domain=ViolationDomain.GUARD.value,
        path="summary",
        field="summary",
        message="含禁止词",
    )
    content = build_guard_repair_user_content((violation,))

    assert "FORBIDDEN_PATTERN_HIT" in content
    assert "summary" in content
    assert "含禁止词" in content


@pytest.mark.asyncio
async def test_generate_initial_llm_draft_async_success(
    retry_context: DraftRetryContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首轮 LLM 生成成功时应返回 draft 与调用计数。"""
    payload = _minimal_draft_payload(retry_context.resolved)
    call_count = 0

    async def completion_factory(
        request: QwenChatCompletionRequest,
    ) -> QwenChatCompletionResponse:
        nonlocal call_count
        call_count += 1
        return _make_completion(json.dumps(payload, ensure_ascii=False))

    from xiaozhua_health_agent.copy import run_draft_llm_with_retry_async

    async def _patched_run(*args: object, **kwargs: object) -> object:
        """注入 ``completion_factory`` 的单测补丁（闭包）。

        :returns: ``DraftGenerationRetryResult``。
        :rtype: object
        """
        kwargs["completion_factory"] = completion_factory
        kwargs["qwen_client"] = _StubQwenClient()
        return await run_draft_llm_with_retry_async(*args, **kwargs)  # type: ignore[misc]

    monkeypatch.setattr(
        "xiaozhua_health_agent.pipeline.llm_draft_generation.run_draft_llm_with_retry_async",
        _patched_run,
    )

    result = await generate_initial_llm_draft_async(
        retry_context,
        options=DraftRetryOptions(llm_enabled=True),
        qwen_client=_StubQwenClient(),  # type: ignore[arg-type]
    )

    assert result.draft.title == payload["title"]
    assert result.llm_call_count == 1
    assert call_count == 1


@pytest.mark.asyncio
async def test_generate_initial_llm_draft_async_raises_on_failure(
    retry_context: DraftRetryContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """内层 ``draft_retry`` 失败时应抛出 ``LlmDraftGenerationError``。"""
    inner_failure = DraftGenerationRetryResult(
        passed=False,
        draft=None,
        attempt_count=1,
        failure_kind=DraftRetryFailureKind.QWEN_ERROR,
        failure_message="模拟 LLM 失败",
    )

    async def _stub_run(*args: object, **kwargs: object) -> DraftGenerationRetryResult:
        """返回失败的内层结果（闭包）。

        :returns: 失败 ``DraftGenerationRetryResult``。
        :rtype: DraftGenerationRetryResult
        """
        _ = args, kwargs
        return inner_failure

    monkeypatch.setattr(
        "xiaozhua_health_agent.pipeline.llm_draft_generation.run_draft_llm_with_retry_async",
        _stub_run,
    )

    with pytest.raises(LlmDraftGenerationError, match="模拟 LLM 失败"):
        await generate_initial_llm_draft_async(
            retry_context,
            options=DraftRetryOptions(llm_enabled=True),
            qwen_client=_StubQwenClient(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_generate_guard_repair_llm_draft_async_uses_repair_messages(
    retry_context: DraftRetryContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """guard repair 应通过 ``initial_messages`` 传入 repair 对话链。"""
    from xiaozhua_health_agent.copy import DraftCopyJSON

    current_draft = DraftCopyJSON.model_validate(
        _minimal_draft_payload(retry_context.resolved),
    )
    fixed_payload = dict(_minimal_draft_payload(retry_context.resolved))
    fixed_payload["summary"] = "修正后的摘要，不含禁止词。"
    captured_messages: list[object] = []

    async def _stub_run(
        *args: object,
        **kwargs: object,
    ) -> DraftGenerationRetryResult:
        """捕获 ``initial_messages`` 并返回成功结果（闭包）。

        :returns: 成功 ``DraftGenerationRetryResult``。
        :rtype: DraftGenerationRetryResult
        """
        _ = args
        initial_messages = kwargs.get("initial_messages")
        if initial_messages is not None:
            captured_messages.extend(initial_messages)
        draft = DraftCopyJSON.model_validate(fixed_payload)
        return DraftGenerationRetryResult(
            passed=True,
            draft=draft,
            attempt_count=1,
        )

    monkeypatch.setattr(
        "xiaozhua_health_agent.pipeline.llm_draft_generation.run_draft_llm_with_retry_async",
        _stub_run,
    )

    violation = Violation(
        code=ViolationCode.FORBIDDEN_PATTERN_HIT.value,
        domain=ViolationDomain.GUARD.value,
        path="summary",
        field="summary",
        message="含禁止词",
    )
    result = await generate_guard_repair_llm_draft_async(
        retry_context,
        current_draft=current_draft,
        violations=(violation,),
        options=DraftRetryOptions(llm_enabled=True),
        qwen_client=_StubQwenClient(),  # type: ignore[arg-type]
    )

    assert result.draft.summary == fixed_payload["summary"]
    assert result.llm_call_count == 1
    assert len(captured_messages) >= 3
    roles = [getattr(message, "role", None) for message in captured_messages]
    assert "assistant" in roles
    assert roles[-1] == "user"
