"""WP5 LLM 文案生成 — 外层协调器与 ``draft_retry`` 内层桥接（异步 IO）。

将 **首轮 LLM 生成** 与 **guard 违规后的 repair 重写** 统一委托
``xiaozhua_health_agent.copy.run_draft_llm_with_retry_async``，内层固定
``max_attempts=1``、``fallback_to_mechanical=False``；**attempt 预算**由外层
``DraftRetryOptions.max_llm_retries`` 与 ``llm_generation_count`` 计数。

包外请通过 ``xiaozhua_health_agent.pipeline`` 门面导入公开符号。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final

from xiaozhua_health_agent.copy import (
    AsyncQwenClient,
    DraftCopyJSON,
    DraftGenerationRetryOptions,
    DraftGenerationRetryResult,
    append_draft_repair_user_message,
    build_draft_chat_completion_request,
    create_default_qwen_client,
    run_draft_llm_with_retry_async,
)
from xiaozhua_health_agent.eval import Violation
from xiaozhua_health_agent.pipeline.retry_types import (
    DraftRetryContext,
    DraftRetryOptions,
)

__all__ = [
    "GuardRepairLlmResult",
    "InitialLlmDraftResult",
    "LlmDraftGenerationError",
    "build_guard_repair_user_content",
    "generate_guard_repair_llm_draft_async",
    "generate_initial_llm_draft_async",
    "resolve_qwen_client",
]

_INNER_LLM_MAX_ATTEMPTS: Final[int] = 1
"""外层协调器调用内层 ``draft_retry`` 时，单次仅允许 1 次 LLM 补全。"""


class LlmDraftGenerationError(RuntimeError):
    """LLM 文案生成失败且外层未启用机械兜底时抛出。

    :ivar message: 人类可读错误说明。
    :vartype message: str
    :ivar inner_result: 内层 ``draft_retry`` 结果（若有）。
    :vartype inner_result: DraftGenerationRetryResult | None
    """

    def __init__(
        self,
        message: str,
        *,
        inner_result: DraftGenerationRetryResult | None = None,
    ) -> None:
        """构造 LLM 生成错误。

        :param message: 错误说明。
        :type message: str
        :param inner_result: 可选内层重试结果，便于批跑诊断。
        :type inner_result: DraftGenerationRetryResult | None
        """
        super().__init__(message)
        self.inner_result = inner_result


@dataclass(frozen=True, slots=True)
class InitialLlmDraftResult:
    """首轮 LLM 文案生成结果（外层协调器消费）。

    :ivar draft: 成功产出的文案草稿。
    :vartype draft: DraftCopyJSON
    :ivar llm_call_count: 本次内层 ``draft_retry`` 实际 LLM 调用次数。
    :vartype llm_call_count: int
    :ivar inner_result: 内层完整结果（含 parse_warnings 等）。
    :vartype inner_result: DraftGenerationRetryResult
    """

    draft: DraftCopyJSON
    llm_call_count: int
    inner_result: DraftGenerationRetryResult


@dataclass(frozen=True, slots=True)
class GuardRepairLlmResult:
    """guard 违规后 LLM repair 重写结果（外层协调器消费）。

    :ivar draft: repair 后的文案草稿。
    :vartype draft: DraftCopyJSON
    :ivar llm_call_count: 本次内层 LLM 调用次数。
    :vartype llm_call_count: int
    :ivar inner_result: 内层完整结果。
    :vartype inner_result: DraftGenerationRetryResult
    """

    draft: DraftCopyJSON
    llm_call_count: int
    inner_result: DraftGenerationRetryResult


def resolve_qwen_client(qwen_client: AsyncQwenClient | None) -> AsyncQwenClient:
    """解析通义客户端：显式注入或默认构造。

    :param qwen_client: 调用方注入的客户端；为 ``None`` 时使用环境配置构造。
    :type qwen_client: AsyncQwenClient | None
    :returns: 可用的异步通义客户端。
    :rtype: AsyncQwenClient
    """
    if qwen_client is not None:
        return qwen_client
    return create_default_qwen_client()


def build_guard_repair_user_content(violations: tuple[Violation, ...]) -> str:
    """将 ``schema`` / ``guard`` 违规格式化为 LLM repair user 消息正文。

    与 ``copy.build_draft_repair_user_content``（行动锁定专用）互补；
    本函数面向 WP5 ValidateContent 全量违规列表。

    :param violations: 参与路由的违规列表（通常来自 ``ClassifyViolationsResult``）。
    :type violations: tuple[Violation, ...]
    :returns: repair 提示正文。
    :rtype: str
    """
    lines: list[str] = [
        (
            "上次输出的 DraftCopyJSON 未通过 ValidateContent 内容守卫，"
            "请仅修正违规字段并重新输出完整 JSON 对象。"
        ),
        "",
        "违规列表：",
    ]
    for item in violations:
        lines.append(
            f"- [{item.severity}] {item.code} @ {item.path}: {item.message}",
        )
    lines.extend(
        [
            "",
            "不得修改 primaryAction/secondaryAction 的 route；不得输出 riskLevel/confidence。",
            "evidence 不得包含 templatePack 与 factSheet 中不存在的新事实或数字。",
            "只输出一个 JSON 对象，不要 Markdown 围栏或解释文字。",
        ],
    )
    return "\n".join(lines)


async def generate_initial_llm_draft_async(
    context: DraftRetryContext,
    *,
    options: DraftRetryOptions,
    qwen_client: AsyncQwenClient | None = None,
) -> InitialLlmDraftResult:
    """调用内层 ``draft_retry`` 产出首轮 LLM 文案（单次 LLM，无内层机械兜底）。

    内层 ``max_attempts`` 固定为 1；JSON 解析与行动锁定由 ``draft_retry`` 处理。
    若失败，由外层协调器决定是否降级机械兜底（``fallback_to_mechanical``）。

    :param context: 协调器只读上下文（须含 ``resolved``）。
    :type context: DraftRetryContext
    :param options: 外层协调器配置。
    :type options: DraftRetryOptions
    :param qwen_client: 可选通义客户端。
    :type qwen_client: AsyncQwenClient | None
    :returns: 首轮 LLM 文案与调用计数。
    :rtype: InitialLlmDraftResult
    :raises LlmDraftGenerationError: 内层失败时抛出；``inner_result`` 可供外层诊断。
    """
    client = resolve_qwen_client(qwen_client)
    inner_result = await run_draft_llm_with_retry_async(
        resolved=context.resolved,
        qwen_client=client,
        options=_resolve_inner_llm_options(options),
        mechanical_options=options.resolved_mechanical_fallback_options(),
    )

    if inner_result.passed and inner_result.draft is not None:
        return InitialLlmDraftResult(
            draft=inner_result.draft,
            llm_call_count=max(1, inner_result.attempt_count),
            inner_result=inner_result,
        )

    msg = inner_result.failure_message or "首轮 LLM 文案生成失败。"
    raise LlmDraftGenerationError(msg, inner_result=inner_result)


async def generate_guard_repair_llm_draft_async(
    context: DraftRetryContext,
    *,
    current_draft: DraftCopyJSON,
    violations: tuple[Violation, ...],
    options: DraftRetryOptions,
    qwen_client: AsyncQwenClient | None = None,
) -> GuardRepairLlmResult:
    """在 guard 违规后，带 repair 对话上下文调用内层 ``draft_retry``（单次 LLM）。

    消息链：原 system/user prompt → assistant(当前 draft JSON) → user(repair 提示)。
    内层仍负责 JSON 解析与行动锁定回写。

    :param context: 协调器只读上下文。
    :type context: DraftRetryContext
    :param current_draft: 未通过 guard 的当前草稿。
    :type current_draft: DraftCopyJSON
    :param violations: 触发 ``RETRY_LLM`` 的违规列表。
    :type violations: tuple[Violation, ...]
    :param options: 外层协调器配置。
    :type options: DraftRetryOptions
    :param qwen_client: 可选通义客户端。
    :type qwen_client: AsyncQwenClient | None
    :returns: repair 后的文案与 LLM 调用计数。
    :rtype: GuardRepairLlmResult
    :raises LlmDraftGenerationError: 内层 LLM repair 失败时抛出。
    """
    client = resolve_qwen_client(qwen_client)
    base_request = build_draft_chat_completion_request(context.resolved)
    assistant_payload = json.dumps(
        current_draft.to_alias_dict(),
        ensure_ascii=False,
    )
    repair_content = build_guard_repair_user_content(violations)
    initial_messages = append_draft_repair_user_message(
        list(base_request.messages),
        assistant_content=assistant_payload,
        repair_user_content=repair_content,
    )

    inner_result = await run_draft_llm_with_retry_async(
        resolved=context.resolved,
        qwen_client=client,
        options=_resolve_inner_llm_options(options),
        mechanical_options=options.resolved_mechanical_fallback_options(),
        initial_messages=tuple(initial_messages),
    )

    if inner_result.passed and inner_result.draft is not None:
        return GuardRepairLlmResult(
            draft=inner_result.draft,
            llm_call_count=max(1, inner_result.attempt_count),
            inner_result=inner_result,
        )

    msg = inner_result.failure_message or "guard repair LLM 重写失败。"
    raise LlmDraftGenerationError(msg, inner_result=inner_result)


def _resolve_inner_llm_options(
    options: DraftRetryOptions,
) -> DraftGenerationRetryOptions:
    """解析外层协调器委托内层 ``draft_retry`` 时使用的选项（内部辅助）。

    统一策略：内层 **仅 1 次** LLM 补全、**不** 在内层做机械兜底（由外层负责）。

    :param options: 外层 ``DraftRetryOptions``。
    :type options: DraftRetryOptions
    :returns: 内层 ``DraftGenerationRetryOptions``。
    :rtype: DraftGenerationRetryOptions
    """
    configured = options.resolved_llm_retry_options()
    return DraftGenerationRetryOptions(
        max_attempts=_INNER_LLM_MAX_ATTEMPTS,
        enforce_locked_actions=configured.enforce_locked_actions,
        lock_action_label=configured.lock_action_label,
        retry_on_parse_error=configured.retry_on_parse_error,
        retry_on_action_mismatch=configured.retry_on_action_mismatch,
        fallback_to_mechanical=False,
    )
