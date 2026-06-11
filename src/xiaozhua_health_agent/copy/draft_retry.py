"""WP4/WP5 ③-2 文案 LLM 重试协调器。

在通义千问生成失败、JSON 解析失败或主/次行动 ``route``/``label`` 与 ③-1 draft
不一致时，按 ``pipeline-design.md`` §6.2 有限重试；耗尽后可回退机械文案。

默认生产配置 ``enforce_locked_actions=True``：解析阶段强制回写 route，不消耗重试次数。
``retry_on_action_mismatch=True`` 且 ``enforce_locked_actions=False`` 时，对
``LockedActionMismatch`` 触发带 repair 提示的重试。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

from xiaozhua_health_agent.copy.action_lock_enforcer import (
    LockedActionMismatch,
    collect_locked_action_mismatches,
    is_retryable_locked_action_mismatch,
)
from xiaozhua_health_agent.copy.copy_types import CopyTemplateResolved
from xiaozhua_health_agent.copy.draft_parser import (
    DraftParseError,
    DraftParseResult,
    DraftParseWarning,
    parse_draft_copy_from_model_text,
)
from xiaozhua_health_agent.copy.draft_prompt import build_draft_chat_completion_request
from xiaozhua_health_agent.copy.draft_types import DraftCopyJSON
from xiaozhua_health_agent.copy.mechanical_draft import (
    MechanicalDraftOptions,
    MechanicalDraftResult,
    generate_mechanical_draft,
)
from xiaozhua_health_agent.copy.qwen_client import (
    AsyncQwenClient,
    QwenChatCompletionRequest,
    QwenChatCompletionResponse,
    QwenChatMessage,
)

__all__ = [
    "DraftGenerationRetryOptions",
    "DraftGenerationRetryResult",
    "DraftRetryFailureKind",
    "DraftRetryFailureKindLiteral",
    "append_draft_repair_user_message",
    "build_draft_repair_user_content",
    "run_draft_llm_with_retry_async",
]

DraftRetryFailureKindLiteral: TypeAlias = Literal[
    "parse_error",
    "action_mismatch",
    "qwen_error",
    "exhausted",
]

_DEFAULT_MAX_ATTEMPTS: Final[int] = 3


class DraftRetryFailureKind:
    """文案 LLM 重试失败原因常量（便于批跑报告）。"""

    PARSE_ERROR: DraftRetryFailureKindLiteral = "parse_error"
    ACTION_MISMATCH: DraftRetryFailureKindLiteral = "action_mismatch"
    QWEN_ERROR: DraftRetryFailureKindLiteral = "qwen_error"
    EXHAUSTED: DraftRetryFailureKindLiteral = "exhausted"


@dataclass(frozen=True, slots=True)
class DraftGenerationRetryOptions:
    """③-2 LLM 文案生成重试与行动锁定选项。

    :ivar max_attempts: 总尝试次数（含首次），默认 3。
    :vartype max_attempts: int
    :ivar enforce_locked_actions: 解析时是否强制回写 draft（默认 ``True``）。
    :vartype enforce_locked_actions: bool
    :ivar lock_action_label: 是否同时锁定 ``label``。
    :vartype lock_action_label: bool
    :ivar retry_on_parse_error: JSON/字段解析失败时是否重试。
    :vartype retry_on_parse_error: bool
    :ivar retry_on_action_mismatch: 行动与 draft 不一致时是否重试（需 ``enforce_locked_actions=False`` 才有意义）。
    :vartype retry_on_action_mismatch: bool
    :ivar fallback_to_mechanical: 全部尝试失败后是否回退机械文案。
    :vartype fallback_to_mechanical: bool
    """

    max_attempts: int = _DEFAULT_MAX_ATTEMPTS
    enforce_locked_actions: bool = True
    lock_action_label: bool = True
    retry_on_parse_error: bool = True
    retry_on_action_mismatch: bool = False
    fallback_to_mechanical: bool = True


@dataclass(frozen=True, slots=True)
class DraftGenerationRetryResult:
    """带重试的 ③-2 文案生成结果。

    :ivar passed: 是否成功产出 ``DraftCopyJSON``。
    :vartype passed: bool
    :ivar draft: 成功时的文案草稿。
    :vartype draft: DraftCopyJSON | None
    :ivar parse_warnings: 解析/回填警告。
    :vartype parse_warnings: tuple[DraftParseWarning, ...]
    :ivar attempt_count: 实际 LLM 调用次数。
    :vartype attempt_count: int
    :ivar used_mechanical_fallback: 是否最终使用机械兜底。
    :vartype used_mechanical_fallback: bool
    :ivar last_model: 最后一次通义模型 id；机械兜底时为 ``mechanical``。
    :vartype last_model: str
    :ivar last_raw_excerpt: 最后一次 LLM 原文摘要（调试）。
    :vartype last_raw_excerpt: str | None
    :ivar failure_kind: 失败原因；成功时为 ``None``。
    :vartype failure_kind: DraftRetryFailureKindLiteral | None
    :ivar failure_message: 失败说明。
    :vartype failure_message: str | None
    :ivar last_action_mismatches: 最后一次检测到的行动不一致（重试路径）。
    :vartype last_action_mismatches: tuple[LockedActionMismatch, ...]
    :ivar mechanical_result: 机械兜底完整结果（若使用）。
    :vartype mechanical_result: MechanicalDraftResult | None
    """

    passed: bool
    draft: DraftCopyJSON | None
    parse_warnings: tuple[DraftParseWarning, ...] = ()
    attempt_count: int = 0
    used_mechanical_fallback: bool = False
    last_model: str = "unknown"
    last_raw_excerpt: str | None = None
    failure_kind: DraftRetryFailureKindLiteral | None = None
    failure_message: str | None = None
    last_action_mismatches: tuple[LockedActionMismatch, ...] = ()
    mechanical_result: MechanicalDraftResult | None = None


@dataclass(frozen=True, slots=True)
class _AttemptState:
    """单次 LLM 尝试的中间状态（内部）。"""

    parse_result: DraftParseResult | None = None
    mismatches: tuple[LockedActionMismatch, ...] = ()
    raw_excerpt: str | None = None
    model: str = "unknown"
    parse_error_message: str | None = None


async def run_draft_llm_with_retry_async(
    *,
    resolved: CopyTemplateResolved,
    qwen_client: AsyncQwenClient,
    options: DraftGenerationRetryOptions | None = None,
    mechanical_options: MechanicalDraftOptions | None = None,
    completion_factory: Callable[
        [QwenChatCompletionRequest],
        Awaitable[QwenChatCompletionResponse],
    ]
    | None = None,
) -> DraftGenerationRetryResult:
    """执行带有限重试的 ③-2 通义千问文案生成。

    :param resolved: 步骤 ③-1 模板解析包（锁定行动 draft 真源）。
    :type resolved: CopyTemplateResolved
    :param qwen_client: 通义异步客户端。
    :type qwen_client: AsyncQwenClient
    :param options: 重试与行动锁定选项；省略时使用生产默认（强制回写 route）。
    :type options: DraftGenerationRetryOptions | None
    :param mechanical_options: 机械兜底选项。
    :type mechanical_options: MechanicalDraftOptions | None
    :param completion_factory: 可选注入补全调用（单测用）；默认 ``qwen_client.create_chat_completion``。
    :type completion_factory: collections.abc.Callable | None
    :returns: 重试协调结果。
    :rtype: DraftGenerationRetryResult
    """
    effective = options if options is not None else DraftGenerationRetryOptions()
    max_attempts = max(1, effective.max_attempts)
    invoke_completion = (
        completion_factory
        if completion_factory is not None
        else qwen_client.create_chat_completion
    )

    base_request = build_draft_chat_completion_request(resolved)
    messages: list[QwenChatMessage] = list(base_request.messages)

    last_state = _AttemptState()
    all_warnings: list[DraftParseWarning] = []

    for attempt_index in range(max_attempts):
        attempt_number = attempt_index + 1
        request = QwenChatCompletionRequest(
            messages=tuple(messages),
            model=base_request.model,
            temperature=base_request.temperature,
            max_tokens=base_request.max_tokens,
            response_format=base_request.response_format,
        )

        try:
            completion = await invoke_completion(request)
        except Exception as exc:
            last_state = _AttemptState(
                model=getattr(qwen_client, "default_model", "unknown"),
                parse_error_message=str(exc),
            )
            if attempt_number >= max_attempts:
                return _build_failure_or_mechanical(
                    resolved=resolved,
                    effective=effective,
                    mechanical_options=mechanical_options,
                    attempt_count=attempt_number,
                    last_state=last_state,
                    all_warnings=tuple(all_warnings),
                    failure_kind=DraftRetryFailureKind.QWEN_ERROR,
                    failure_message=str(exc),
                )
            continue

        attempt_state = _process_llm_completion(
            completion=completion,
            resolved=resolved,
            enforce_locked_actions=effective.enforce_locked_actions,
            lock_action_label=effective.lock_action_label,
        )
        last_state = attempt_state
        if attempt_state.parse_result is not None:
            all_warnings.extend(attempt_state.parse_result.warnings)

        if attempt_state.parse_result is not None and not attempt_state.mismatches:
            return DraftGenerationRetryResult(
                passed=True,
                draft=attempt_state.parse_result.draft,
                parse_warnings=tuple(all_warnings),
                attempt_count=attempt_number,
                used_mechanical_fallback=False,
                last_model=completion.model,
                last_raw_excerpt=attempt_state.raw_excerpt,
            )

        should_retry = _should_retry_attempt(
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            state=attempt_state,
            options=effective,
        )
        if not should_retry:
            if (
                effective.enforce_locked_actions
                and attempt_state.parse_result is not None
            ):
                return DraftGenerationRetryResult(
                    passed=True,
                    draft=attempt_state.parse_result.draft,
                    parse_warnings=tuple(all_warnings),
                    attempt_count=attempt_number,
                    used_mechanical_fallback=False,
                    last_model=completion.model,
                    last_raw_excerpt=attempt_state.raw_excerpt,
                )
            break

        repair_content = build_draft_repair_user_content(
            violations=attempt_state.mismatches,
            parse_error_message=attempt_state.parse_error_message,
        )
        messages = append_draft_repair_user_message(
            messages,
            assistant_content=completion.content,
            repair_user_content=repair_content,
        )

    return _build_failure_or_mechanical(
        resolved=resolved,
        effective=effective,
        mechanical_options=mechanical_options,
        attempt_count=max_attempts,
        last_state=last_state,
        all_warnings=tuple(all_warnings),
        failure_kind=_resolve_terminal_failure_kind(last_state),
        failure_message=_resolve_terminal_failure_message(last_state),
    )


def build_draft_repair_user_content(
    *,
    violations: tuple[LockedActionMismatch, ...] = (),
    parse_error_message: str | None = None,
) -> str:
    """构建重试轮次的 user repair 消息正文。

    :param violations: 行动锁定不一致列表。
    :type violations: tuple[LockedActionMismatch, ...]
    :param parse_error_message: 解析错误说明（若有）。
    :type parse_error_message: str | None
    :returns: repair 提示文本。
    :rtype: str
    """
    lines: list[str] = [
        "上次输出的 DraftCopyJSON 未通过校验，请仅修正违规字段并重新输出完整 JSON 对象。",
        "",
    ]

    if parse_error_message:
        lines.append(f"解析错误：{parse_error_message}")
        lines.append("")

    if violations:
        lines.append(
            "行动字段违规（必须与 templatePack 中 primaryActionDraft / secondaryActionDraft 完全一致）："
        )
        for item in violations:
            lines.append(f"- {item.json_path}: {item.message}")
        lines.append("")
        lines.append(
            "primaryAction.route 与 secondaryAction.route 不得修改；"
            "label 须与 draft 一致（除非 templatePack 另有说明）。",
        )
        lines.append("")

    lines.append("只输出一个 JSON 对象，不要 Markdown 围栏或解释文字。")
    return "\n".join(lines)


def append_draft_repair_user_message(
    messages: list[QwenChatMessage],
    *,
    assistant_content: str,
    repair_user_content: str,
) -> list[QwenChatMessage]:
    """在消息列表末尾追加 assistant 输出与 repair user 消息。

    :param messages: 现有消息列表（会被复制扩展）。
    :type messages: list[QwenChatMessage]
    :param assistant_content: 上一轮模型 JSON 正文。
    :type assistant_content: str
    :param repair_user_content: repair user 提示。
    :type repair_user_content: str
    :returns: 扩展后的新消息列表。
    :rtype: list[QwenChatMessage]
    """
    extended = list(messages)
    extended.append(QwenChatMessage(role="assistant", content=assistant_content))
    extended.append(QwenChatMessage(role="user", content=repair_user_content))
    return extended


def _process_llm_completion(
    *,
    completion: QwenChatCompletionResponse,
    resolved: CopyTemplateResolved,
    enforce_locked_actions: bool,
    lock_action_label: bool,
) -> _AttemptState:
    """处理单次 LLM 补全：解析 JSON 并可选检测行动不一致（内部辅助）。

    :param completion: 通义补全响应。
    :type completion: QwenChatCompletionResponse
    :param resolved: ③-1 解析包。
    :type resolved: CopyTemplateResolved
    :param enforce_locked_actions: 是否在解析时强制回写行动。
    :type enforce_locked_actions: bool
    :param lock_action_label: 是否锁定 label。
    :type lock_action_label: bool
    :returns: 单次尝试状态。
    :rtype: _AttemptState
    """
    raw_excerpt = _truncate_text(completion.content)

    try:
        parse_result = parse_draft_copy_from_model_text(
            completion.content,
            resolved=resolved,
            enforce_locked_actions=enforce_locked_actions,
            lock_action_label=lock_action_label,
        )
    except DraftParseError as exc:
        return _AttemptState(
            raw_excerpt=exc.raw_excerpt or raw_excerpt,
            model=completion.model,
            parse_error_message=str(exc),
        )

    mismatches: tuple[LockedActionMismatch, ...] = ()
    if not enforce_locked_actions and parse_result is not None:
        mismatches = collect_locked_action_mismatches(
            parse_result.draft.to_alias_dict(),
            resolved,
            lock_label=lock_action_label,
        )

    return _AttemptState(
        parse_result=parse_result,
        mismatches=mismatches,
        raw_excerpt=raw_excerpt,
        model=completion.model,
    )


def _should_retry_attempt(
    *,
    attempt_number: int,
    max_attempts: int,
    state: _AttemptState,
    options: DraftGenerationRetryOptions,
) -> bool:
    """判断是否继续 LLM 重试（内部辅助）。

    :param attempt_number: 当前尝试序号（1-based）。
    :type attempt_number: int
    :param max_attempts: 最大尝试次数。
    :type max_attempts: int
    :param state: 当前尝试状态。
    :type state: _AttemptState
    :param options: 重试选项。
    :type options: DraftGenerationRetryOptions
    :returns: 应重试时返回 ``True``。
    :rtype: bool
    """
    if attempt_number >= max_attempts:
        return False

    if state.parse_result is None and options.retry_on_parse_error:
        return True

    if (
        not options.enforce_locked_actions
        and options.retry_on_action_mismatch
        and state.mismatches
        and any(is_retryable_locked_action_mismatch(item) for item in state.mismatches)
    ):
        return True

    return False


def _build_failure_or_mechanical(
    *,
    resolved: CopyTemplateResolved,
    effective: DraftGenerationRetryOptions,
    mechanical_options: MechanicalDraftOptions | None,
    attempt_count: int,
    last_state: _AttemptState,
    all_warnings: tuple[DraftParseWarning, ...],
    failure_kind: DraftRetryFailureKindLiteral,
    failure_message: str | None,
) -> DraftGenerationRetryResult:
    """构建失败结果或机械兜底结果（内部辅助）。

    :param resolved: ③-1 解析包。
    :type resolved: CopyTemplateResolved
    :param effective: 重试选项。
    :type effective: DraftGenerationRetryOptions
    :param mechanical_options: 机械兜底选项。
    :type mechanical_options: MechanicalDraftOptions | None
    :param attempt_count: 已尝试次数。
    :type attempt_count: int
    :param last_state: 最后一次尝试状态。
    :type last_state: _AttemptState
    :param all_warnings: 累计解析警告。
    :type all_warnings: tuple[DraftParseWarning, ...]
    :param failure_kind: 失败类型。
    :type failure_kind: DraftRetryFailureKindLiteral
    :param failure_message: 失败说明。
    :type failure_message: str | None
    :returns: 重试协调结果。
    :rtype: DraftGenerationRetryResult
    """
    if effective.fallback_to_mechanical:
        mechanical = generate_mechanical_draft(resolved, options=mechanical_options)
        return DraftGenerationRetryResult(
            passed=True,
            draft=mechanical.draft,
            parse_warnings=all_warnings,
            attempt_count=attempt_count,
            used_mechanical_fallback=True,
            last_model="mechanical",
            last_raw_excerpt=last_state.raw_excerpt,
            failure_kind=failure_kind,
            failure_message=failure_message,
            last_action_mismatches=last_state.mismatches,
            mechanical_result=mechanical,
        )

    return DraftGenerationRetryResult(
        passed=False,
        draft=None,
        parse_warnings=all_warnings,
        attempt_count=attempt_count,
        used_mechanical_fallback=False,
        last_model=last_state.model,
        last_raw_excerpt=last_state.raw_excerpt,
        failure_kind=failure_kind,
        failure_message=failure_message,
        last_action_mismatches=last_state.mismatches,
    )


def _resolve_terminal_failure_kind(
    state: _AttemptState,
) -> DraftRetryFailureKindLiteral:
    """推断终端失败类型（内部辅助）。

    :param state: 最后尝试状态。
    :type state: _AttemptState
    :returns: 失败类型。
    :rtype: DraftRetryFailureKindLiteral
    """
    if state.parse_result is None:
        return DraftRetryFailureKind.PARSE_ERROR
    if state.mismatches:
        return DraftRetryFailureKind.ACTION_MISMATCH
    return DraftRetryFailureKind.EXHAUSTED


def _resolve_terminal_failure_message(state: _AttemptState) -> str | None:
    """推断终端失败说明（内部辅助）。

    :param state: 最后尝试状态。
    :type state: _AttemptState
    :returns: 说明文本。
    :rtype: str | None
    """
    if state.parse_error_message:
        return state.parse_error_message
    if state.mismatches:
        return state.mismatches[0].message
    return "LLM 文案生成重试次数已耗尽。"


def _truncate_text(text: str, *, max_length: int = 240) -> str:
    """截断文本用于日志摘要（内部辅助）。

    :param text: 原文。
    :type text: str
    :param max_length: 最大长度。
    :type max_length: int
    :returns: 截断摘要。
    :rtype: str
    """
    stripped = text.strip()
    if len(stripped) <= max_length:
        return stripped
    return stripped[:max_length] + "…"
