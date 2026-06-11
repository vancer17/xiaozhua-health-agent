"""WP4 ③-2 单次 case 通义千问文案生成管道（异步 IO）。

编排 ① 解析 → ② 分诊 → ③-1 模板解析 → 通义千问 → ``draft_parser``，
产出 ``DraftCopyJSON`` 或结构化错误。

包外请通过 ``xiaozhua_health_agent.copy`` 门面导入 ``generate_draft_copy_async``。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from xiaozhua_health_agent.copy.copy_types import CopyKnowledgeBundle
from xiaozhua_health_agent.copy.draft_parser import DraftParseWarning
from xiaozhua_health_agent.copy.draft_retry import (
    DraftGenerationRetryOptions,
    run_draft_llm_with_retry_async,
)
from xiaozhua_health_agent.copy.draft_types import DraftCopyJSON
from xiaozhua_health_agent.copy.mechanical_draft import (
    MechanicalDraftOptions,
    MechanicalDraftWarning,
    generate_mechanical_draft,
)
from xiaozhua_health_agent.copy.qwen_client import (
    AsyncQwenClient,
    QwenApiError,
    QwenChatCompletionRequest,
    QwenChatCompletionResponse,
    QwenClientError,
    QwenConfigurationError,
    QwenTimeoutError,
    create_default_qwen_client,
)
from xiaozhua_health_agent.copy.template_resolver import resolve_copy_template
from xiaozhua_health_agent.parse import ParseResult, parse_input
from xiaozhua_health_agent.triage import TriageCoreResult, run_triage_core

__all__ = [
    "CopyLlmCaseResult",
    "CopyLlmGeneratorKind",
    "CopyLlmGeneratorKindLiteral",
    "CopyLlmPipelineError",
    "DraftGenerationRetryOptions",
    "generate_draft_copy_async",
    "generate_draft_copy_for_parsed_async",
]

CopyLlmGeneratorKindLiteral: TypeAlias = Literal["qwen", "mechanical", "skipped"]

CopyLlmGeneratorKind = CopyLlmGeneratorKindLiteral
"""文案生成器种类（qwen / mechanical / skipped）。"""


class CopyLlmPipelineError(Exception):
    """③-2 管道在 ①/②/③-1 阶段的失败（非 LLM 解析错误）。

    :ivar message: 错误说明。
    :vartype message: str
    :ivar stage: 失败阶段标识。
    :vartype stage: str
    """

    def __init__(self, message: str, *, stage: str) -> None:
        """构造管道错误。

        :param message: 人类可读说明。
        :type message: str
        :param stage: 阶段名（``parse`` / ``triage`` / ``resolve``）。
        :type stage: str
        """
        super().__init__(message)
        self.stage = stage


@dataclass(frozen=True, slots=True)
class CopyLlmCaseResult:
    """单 case ③-2 通义千问文案生成结果。

    :ivar case_id: 用例标识。
    :vartype case_id: str
    :ivar template_id: ③-1 查表主键。
    :vartype template_id: str
    :ivar passed: 是否成功产出可校验 ``DraftCopyJSON``。
    :vartype passed: bool
    :ivar draft: 成功时的文案草稿。
    :vartype draft: DraftCopyJSON | None
    :ivar parse_warnings: LLM 解析/回填警告（``generator=qwen`` 时）。
    :vartype parse_warnings: tuple[DraftParseWarning, ...]
    :ivar mechanical_warnings: 机械文案组装警告（``generator=mechanical`` 时）。
    :vartype mechanical_warnings: tuple[MechanicalDraftWarning, ...]
    :ivar generator: 实际使用的生成器。
    :vartype generator: CopyLlmGeneratorKindLiteral
    :ivar model: 通义模型 id；跳过时为 ``skipped``。
    :vartype model: str
    :ivar error_code: 失败时的错误码。
    :vartype error_code: str | None
    :ivar error_message: 失败时的错误说明。
    :vartype error_message: str | None
    :ivar raw_model_excerpt: LLM 原始正文摘要（调试）。
    :vartype raw_model_excerpt: str | None
    :ivar triage: 步骤 ② 结果（成功路径保留，便于批跑报告 ruleHits）。
    :vartype triage: TriageCoreResult | None
    :ivar attempt_count: LLM 调用次数（含重试）。
    :vartype attempt_count: int
    :ivar used_mechanical_fallback: 是否在重试耗尽后使用机械兜底。
    :vartype used_mechanical_fallback: bool
    """

    case_id: str
    template_id: str
    passed: bool
    draft: DraftCopyJSON | None
    parse_warnings: tuple[DraftParseWarning, ...]
    generator: CopyLlmGeneratorKindLiteral
    model: str
    error_code: str | None = None
    error_message: str | None = None
    raw_model_excerpt: str | None = None
    triage: TriageCoreResult | None = None
    mechanical_warnings: tuple[MechanicalDraftWarning, ...] = ()
    attempt_count: int = 0
    used_mechanical_fallback: bool = False


async def generate_draft_copy_async(
    agent_input: Mapping[str, Any],
    *,
    qwen_client: AsyncQwenClient | None = None,
    bundle: CopyKnowledgeBundle | None = None,
    skip_llm: bool = False,
    use_mechanical: bool = False,
    mechanical_options: MechanicalDraftOptions | None = None,
    retry_options: DraftGenerationRetryOptions | None = None,
) -> CopyLlmCaseResult:
    """对单次 Agent 输入执行 ①→②→③-1→文案生成，产出文案草稿。

    :param agent_input: 符合 input_schema 的 case / App 输入 JSON。
    :type agent_input: collections.abc.Mapping[str, Any]
    :param qwen_client: 可选注入客户端；省略时在 qwen 路径使用默认配置构造。
    :type qwen_client: AsyncQwenClient | None
    :param bundle: 可选 KB-TPL 知识包；传给 ③-1。
    :type bundle: CopyKnowledgeBundle | None
    :param skip_llm: 为 ``True`` 时仅执行至 ③-1 并返回 ``passed=False``（用于无 Key 冒烟结构）。
    :type skip_llm: bool
    :param use_mechanical: 为 ``True`` 时使用机械文案路径（不调用通义千问）。
    :type use_mechanical: bool
    :param mechanical_options: 机械文案可选行为；仅 ``use_mechanical=True`` 时生效。
    :type mechanical_options: MechanicalDraftOptions | None
    :param retry_options: ③-2 LLM 重试与行动锁定选项；省略时使用默认（强制回写 route）。
    :type retry_options: DraftGenerationRetryOptions | None
    :returns: 单 case 生成结果。
    :rtype: CopyLlmCaseResult
    """
    parsed = parse_input(agent_input)
    return await generate_draft_copy_for_parsed_async(
        parsed,
        qwen_client=qwen_client,
        bundle=bundle,
        skip_llm=skip_llm,
        use_mechanical=use_mechanical,
        mechanical_options=mechanical_options,
        retry_options=retry_options,
    )


async def generate_draft_copy_for_parsed_async(
    parsed: ParseResult,
    *,
    qwen_client: AsyncQwenClient | None = None,
    bundle: CopyKnowledgeBundle | None = None,
    skip_llm: bool = False,
    use_mechanical: bool = False,
    mechanical_options: MechanicalDraftOptions | None = None,
    retry_options: DraftGenerationRetryOptions | None = None,
) -> CopyLlmCaseResult:
    """对已解析输入执行 ②→③-1→文案生成。

    :param parsed: 步骤 ① ``parse_input`` 结果。
    :type parsed: ParseResult
    :param qwen_client: 可选通义客户端。
    :type qwen_client: AsyncQwenClient | None
    :param bundle: 可选知识资产包。
    :type bundle: CopyKnowledgeBundle | None
    :param skip_llm: 是否跳过文案生成（仅 ③-1）。
    :type skip_llm: bool
    :param use_mechanical: 是否使用机械文案路径。
    :type use_mechanical: bool
    :param mechanical_options: 机械文案选项。
    :type mechanical_options: MechanicalDraftOptions | None
    :param retry_options: LLM 重试与行动锁定选项。
    :type retry_options: DraftGenerationRetryOptions | None
    :returns: 单 case 生成结果。
    :rtype: CopyLlmCaseResult
    :raises CopyLlmPipelineError: ① 解析失败时抛出（``parse_input`` 已内嵌校验）。
    :raises ValueError: ``parsed.fact_sheet`` 为空时抛出。
    """
    if parsed.fact_sheet is None:
        msg = "ParseResult.fact_sheet 为空，无法执行文案生成管道。"
        raise ValueError(msg)

    case_id = parsed.fact_sheet.identity.case_id
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=bundle,
    )

    if use_mechanical:
        mechanical_result = generate_mechanical_draft(
            resolved,
            options=mechanical_options,
        )
        return CopyLlmCaseResult(
            case_id=case_id,
            template_id=mechanical_result.template_id,
            passed=True,
            draft=mechanical_result.draft,
            parse_warnings=(),
            mechanical_warnings=mechanical_result.warnings,
            generator="mechanical",
            model="mechanical",
            triage=triage,
        )

    if skip_llm:
        return CopyLlmCaseResult(
            case_id=case_id,
            template_id=resolved.template_id,
            passed=False,
            draft=None,
            parse_warnings=(),
            generator="skipped",
            model="skipped",
            error_code="LLM_SKIPPED",
            error_message="skip_llm=True，未调用通义千问。",
            triage=triage,
        )

    client = qwen_client if qwen_client is not None else create_default_qwen_client()

    async def _invoke(
        request: QwenChatCompletionRequest,
    ) -> QwenChatCompletionResponse:
        return await client.create_chat_completion(request)

    try:
        retry_result = await run_draft_llm_with_retry_async(
            resolved=resolved,
            qwen_client=client,
            options=retry_options,
            mechanical_options=mechanical_options,
            completion_factory=_invoke,
        )
    except QwenConfigurationError as exc:
        return _failure_result(
            case_id=case_id,
            template_id=resolved.template_id,
            triage=triage,
            error_code="QWEN_CONFIG",
            error_message=str(exc),
        )
    except QwenTimeoutError as exc:
        return _failure_result(
            case_id=case_id,
            template_id=resolved.template_id,
            triage=triage,
            error_code="QWEN_TIMEOUT",
            error_message=str(exc),
        )
    except QwenApiError as exc:
        return _failure_result(
            case_id=case_id,
            template_id=resolved.template_id,
            triage=triage,
            error_code="QWEN_API",
            error_message=str(exc),
        )
    except QwenClientError as exc:
        return _failure_result(
            case_id=case_id,
            template_id=resolved.template_id,
            triage=triage,
            error_code="QWEN_CLIENT",
            error_message=str(exc),
        )

    if retry_result.passed and retry_result.draft is not None:
        generator: CopyLlmGeneratorKindLiteral = (
            "mechanical" if retry_result.used_mechanical_fallback else "qwen"
        )
        mechanical_warnings: tuple[MechanicalDraftWarning, ...] = ()
        if retry_result.mechanical_result is not None:
            mechanical_warnings = retry_result.mechanical_result.warnings
        return CopyLlmCaseResult(
            case_id=case_id,
            template_id=resolved.template_id,
            passed=True,
            draft=retry_result.draft,
            parse_warnings=retry_result.parse_warnings,
            mechanical_warnings=mechanical_warnings,
            generator=generator,
            model=retry_result.last_model,
            raw_model_excerpt=retry_result.last_raw_excerpt,
            triage=triage,
            attempt_count=retry_result.attempt_count,
            used_mechanical_fallback=retry_result.used_mechanical_fallback,
        )

    error_code = retry_result.failure_kind or "EXHAUSTED"
    return CopyLlmCaseResult(
        case_id=case_id,
        template_id=resolved.template_id,
        passed=False,
        draft=None,
        parse_warnings=retry_result.parse_warnings,
        generator="qwen",
        model=retry_result.last_model,
        error_code=error_code.upper() if error_code else "EXHAUSTED",
        error_message=retry_result.failure_message,
        raw_model_excerpt=retry_result.last_raw_excerpt,
        triage=triage,
        attempt_count=retry_result.attempt_count,
        used_mechanical_fallback=retry_result.used_mechanical_fallback,
    )


def _failure_result(
    *,
    case_id: str,
    template_id: str,
    triage: TriageCoreResult,
    error_code: str,
    error_message: str,
) -> CopyLlmCaseResult:
    """构造通义调用失败结果（内部辅助）。

    :param case_id: 用例 id。
    :type case_id: str
    :param template_id: 模板 id。
    :type template_id: str
    :param triage: 分诊结果。
    :type triage: TriageCoreResult
    :param error_code: 错误码。
    :type error_code: str
    :param error_message: 错误说明。
    :type error_message: str
    :returns: 失败结果对象。
    :rtype: CopyLlmCaseResult
    """
    return CopyLlmCaseResult(
        case_id=case_id,
        template_id=template_id,
        passed=False,
        draft=None,
        parse_warnings=(),
        generator="qwen",
        model="unknown",
        error_code=error_code,
        error_message=error_message,
        triage=triage,
    )
