"""WP4 ③-2 文案 LLM 重试协调器单元测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from xiaozhua_health_agent.copy import (
    DraftGenerationRetryOptions,
    DraftRetryFailureKind,
    QwenChatCompletionRequest,
    QwenChatCompletionResponse,
    load_copy_knowledge_bundle,
    resolve_copy_template,
    run_draft_llm_with_retry_async,
)
from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.triage import run_triage_core


@pytest.fixture
def mild_fever_resolved() -> object:
    """case #2 的 CopyTemplateResolved。"""
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    dataset = load_health_triage_dataset(cases_path)
    case = dataset.case_by_id("mild_fever_after_exercise")
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    bundle = load_copy_knowledge_bundle()
    return resolve_copy_template(parsed.fact_sheet, triage, bundle=bundle)


def _minimal_draft_payload(
    resolved: object,
    *,
    route_override: str | None = None,
) -> dict[str, Any]:
    """构造最小合法 DraftCopyJSON 载荷。"""
    primary = resolved.primary_action_draft.model_dump(by_alias=True, mode="json")  # type: ignore[attr-defined]
    if route_override is not None:
        primary["route"] = route_override
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
    """构造测试用通义补全响应。"""
    return QwenChatCompletionResponse(
        content=content,
        model="qwen-test",
        usage=None,
        finish_reason="stop",
        raw=cast(Any, None),
    )


class _StubQwenClient:
    """仅满足 ``run_draft_llm_with_retry_async`` 对 client 的最小依赖。"""

    default_model: str = "qwen-test"


@pytest.mark.asyncio
async def test_run_draft_llm_enforce_corrects_route_in_one_attempt(
    mild_fever_resolved: object,
) -> None:
    """默认 enforce 模式下错误 route 应在首次尝试内回写，不触发重试。"""
    resolved = mild_fever_resolved
    wrong_route_payload = _minimal_draft_payload(resolved, route_override="emergency")
    call_count = 0

    async def completion_factory(
        request: QwenChatCompletionRequest,
    ) -> QwenChatCompletionResponse:
        nonlocal call_count
        call_count += 1
        return _make_completion(json.dumps(wrong_route_payload, ensure_ascii=False))

    client = _StubQwenClient()
    result = await run_draft_llm_with_retry_async(
        resolved=resolved,  # type: ignore[arg-type]
        qwen_client=client,
        options=DraftGenerationRetryOptions(enforce_locked_actions=True),
        completion_factory=completion_factory,
    )

    assert result.passed is True
    assert result.attempt_count == 1
    assert call_count == 1
    assert result.draft is not None
    assert (
        result.draft.primary_action.route == resolved.primary_action_draft.route  # type: ignore[attr-defined]
    )
    assert result.used_mechanical_fallback is False


@pytest.mark.asyncio
async def test_run_draft_llm_strict_mode_retries_on_action_mismatch(
    mild_fever_resolved: object,
) -> None:
    """strict 模式（不 enforce + retry_on_action_mismatch）应在 mismatch 后重试。"""
    resolved = mild_fever_resolved
    wrong_payload = _minimal_draft_payload(resolved, route_override="emergency")
    correct_payload = _minimal_draft_payload(resolved)
    responses = [
        json.dumps(wrong_payload, ensure_ascii=False),
        json.dumps(correct_payload, ensure_ascii=False),
    ]
    call_index = 0

    async def completion_factory(
        request: QwenChatCompletionRequest,
    ) -> QwenChatCompletionResponse:
        nonlocal call_index
        content = responses[min(call_index, len(responses) - 1)]
        call_index += 1
        return _make_completion(content)

    client = _StubQwenClient()
    result = await run_draft_llm_with_retry_async(
        resolved=resolved,  # type: ignore[arg-type]
        qwen_client=client,
        options=DraftGenerationRetryOptions(
            max_attempts=3,
            enforce_locked_actions=False,
            retry_on_action_mismatch=True,
            fallback_to_mechanical=False,
        ),
        completion_factory=completion_factory,
    )

    assert result.passed is True
    assert result.attempt_count == 2
    assert result.draft is not None
    assert (
        result.draft.primary_action.route == resolved.primary_action_draft.route  # type: ignore[attr-defined]
    )


@pytest.mark.asyncio
async def test_run_draft_llm_exhausted_falls_back_to_mechanical(
    mild_fever_resolved: object,
) -> None:
    """重试耗尽且 fallback_to_mechanical 时应产出机械文案。"""
    resolved = mild_fever_resolved
    wrong_payload = _minimal_draft_payload(resolved, route_override="emergency")

    async def completion_factory(
        request: QwenChatCompletionRequest,
    ) -> QwenChatCompletionResponse:
        return _make_completion(json.dumps(wrong_payload, ensure_ascii=False))

    client = _StubQwenClient()
    result = await run_draft_llm_with_retry_async(
        resolved=resolved,  # type: ignore[arg-type]
        qwen_client=client,
        options=DraftGenerationRetryOptions(
            max_attempts=2,
            enforce_locked_actions=False,
            retry_on_action_mismatch=True,
            fallback_to_mechanical=True,
        ),
        completion_factory=completion_factory,
    )

    assert result.passed is True
    assert result.used_mechanical_fallback is True
    assert result.attempt_count == 2
    assert result.failure_kind == DraftRetryFailureKind.ACTION_MISMATCH
    assert result.mechanical_result is not None
