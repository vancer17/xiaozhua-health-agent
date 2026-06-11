"""WP5 文案重试协调器 — 上下文、配置、结果与动作枚举（类型定义）。

对应 ``pipeline-design.md`` §6.2 重试协调器；协调器状态机实现见后续
``retry_coordinator`` 模块。本模块仅定义 DTO，不含编排逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeAlias

from xiaozhua_health_agent.copy import (
    CopyKnowledgeBundle,
    CopyTemplateResolved,
    DraftCopyJSON,
    DraftGenerationRetryOptions,
    MechanicalDraftOptions,
)
from xiaozhua_health_agent.eval import SynonymMap, Violation
from xiaozhua_health_agent.guard import (
    ContentGuardMode,
    ContentGuardModeLiteral,
    ContentGuardOptions,
    ContentGuardResult,
    DEFAULT_CONTENT_GUARD_OPTIONS,
)
from xiaozhua_health_agent.parse import ParseResult
from xiaozhua_health_agent.triage import TriageCoreResult

__all__ = [
    "DRAFT_RETRY_SCHEMA_VERSION",
    "DEFAULT_DRAFT_RETRY_OPTIONS",
    "DraftRetryAttemptRecord",
    "DraftRetryContext",
    "DraftRetryGeneratorKind",
    "DraftRetryGeneratorKindLiteral",
    "DraftRetryOptions",
    "DraftRetryOutcome",
    "RetryAction",
    "RetryActionLiteral",
    "RETRY_ACTION_STRENGTH",
    "build_draft_retry_context",
    "compare_retry_action_strength",
]

DRAFT_RETRY_SCHEMA_VERSION: str = "xiaozhua.health_agent.draft_retry.v1"
"""文案重试协调器逻辑 schema 版本（写入批跑报告元数据）。"""

RetryActionLiteral: TypeAlias = Literal[
    "accept",
    "deterministic_repair",
    "retry_llm",
    "mechanical_fallback",
    "abort",
]
"""协调器在单轮校验后选择的下一步动作。"""

DraftRetryGeneratorKindLiteral: TypeAlias = Literal[
    "mechanical",
    "qwen",
    "mechanical_fallback",
    "skipped",
]
"""文案草稿实际生成器种类（与 ``CopyLlmGeneratorKind`` 对齐并扩展 skipped）。"""


class RetryAction(StrEnum):
    """WP5 重试协调器路由动作。

    数值越大表示动作越强（越接近终止/兜底）；``compare_retry_action_strength``
    用于同一轮多条违规时取最强动作。
    """

    ACCEPT = "accept"
    DETERMINISTIC_REPAIR = "deterministic_repair"
    RETRY_LLM = "retry_llm"
    MECHANICAL_FALLBACK = "mechanical_fallback"
    ABORT = "abort"


class DraftRetryGeneratorKind:
    """文案生成器种类常量。"""

    MECHANICAL: DraftRetryGeneratorKindLiteral = "mechanical"
    QWEN: DraftRetryGeneratorKindLiteral = "qwen"
    MECHANICAL_FALLBACK: DraftRetryGeneratorKindLiteral = "mechanical_fallback"
    SKIPPED: DraftRetryGeneratorKindLiteral = "skipped"


RETRY_ACTION_STRENGTH: dict[RetryActionLiteral, int] = {
    RetryAction.ACCEPT.value: 0,
    RetryAction.DETERMINISTIC_REPAIR.value: 1,
    RetryAction.RETRY_LLM.value: 2,
    RetryAction.MECHANICAL_FALLBACK.value: 3,
    RetryAction.ABORT.value: 4,
}
"""动作强度序（供多违规聚合时取 max）。"""


def compare_retry_action_strength(
    left: RetryActionLiteral,
    right: RetryActionLiteral,
) -> int:
    """比较两个 ``RetryAction`` 强度。

    :param left: 左侧动作。
    :type left: RetryActionLiteral
    :param right: 右侧动作。
    :type right: RetryActionLiteral
    :returns: ``left`` 更强时为正数，相等为 0，更弱为负数。
    :rtype: int
    """
    return RETRY_ACTION_STRENGTH[left] - RETRY_ACTION_STRENGTH[right]


@dataclass(frozen=True, slots=True)
class DraftRetryOptions:
    """WP5 文案重试协调器运行配置。

    :ivar max_attempts: 协调器总尝试上限（含首次生成），默认 3。
    :vartype max_attempts: int
    :ivar max_llm_retries: LLM 路径下外层允许的 LLM 重试次数上限（不含内层
        ``DraftGenerationRetryOptions``）；``llm_enabled=False`` 时忽略。
    :vartype max_llm_retries: int
    :ivar llm_enabled: 是否启用 LLM 文案生成；阶段 1 机械管道为 ``False``。
    :vartype llm_enabled: bool
    :ivar fallback_to_mechanical: 耗尽或不可修复 HIGH 违规时是否终端机械兜底。
    :vartype fallback_to_mechanical: bool
    :ivar enable_deterministic_repair: 是否允许 sanitize / 机械补 mention 等确定性修补。
    :vartype enable_deterministic_repair: bool
    :ivar count_repair_as_attempt: 确定性修补是否计入 ``attempt_count``。
    :vartype count_repair_as_attempt: bool
    :ivar allow_accept_with_med_warnings: ``hard_passed`` 且仅 MED 违规时是否视为通过。
    :vartype allow_accept_with_med_warnings: bool
    :ivar enforce_forced_mentions_on_retry: MED ``FORCED_MENTION_MISSING`` 是否触发 LLM 重试。
    :vartype enforce_forced_mentions_on_retry: bool
    :ivar guard_mode: 管道级守卫失败处理模式（与 ``HealthTriagePipelineOptions`` 对齐）。
    :vartype guard_mode: ContentGuardModeLiteral
    :ivar guard_options: ValidateContent 运行配置。
    :vartype guard_options: ContentGuardOptions
    :ivar mechanical_options: 首次机械生成选项；省略时使用 ``append_missing_mentions=True``。
    :vartype mechanical_options: MechanicalDraftOptions | None
    :ivar mechanical_fallback_options: 终端机械兜底选项；省略时使用强兜底默认。
    :vartype mechanical_fallback_options: MechanicalDraftOptions | None
    :ivar llm_retry_options: 内层 LLM 重试选项；省略时由协调器构造（``fallback_to_mechanical=False``）。
    :vartype llm_retry_options: DraftGenerationRetryOptions | None
    """

    max_attempts: int = 3
    max_llm_retries: int = 2
    llm_enabled: bool = False
    fallback_to_mechanical: bool = True
    enable_deterministic_repair: bool = True
    count_repair_as_attempt: bool = False
    allow_accept_with_med_warnings: bool = True
    enforce_forced_mentions_on_retry: bool = False
    guard_mode: ContentGuardModeLiteral = ContentGuardMode.STRICT
    guard_options: ContentGuardOptions = DEFAULT_CONTENT_GUARD_OPTIONS
    mechanical_options: MechanicalDraftOptions | None = None
    mechanical_fallback_options: MechanicalDraftOptions | None = None
    llm_retry_options: DraftGenerationRetryOptions | None = None

    def resolved_mechanical_options(self) -> MechanicalDraftOptions:
        """解析首次机械文案选项。

        :returns: 显式配置或默认机械选项。
        :rtype: MechanicalDraftOptions
        """
        if self.mechanical_options is not None:
            return self.mechanical_options
        return MechanicalDraftOptions(append_missing_mentions=True)

    def resolved_mechanical_fallback_options(self) -> MechanicalDraftOptions:
        """解析终端机械兜底选项（补全 forced mentions，保守句式）。

        :returns: 显式配置或强兜底默认。
        :rtype: MechanicalDraftOptions
        """
        if self.mechanical_fallback_options is not None:
            return self.mechanical_fallback_options
        return MechanicalDraftOptions(
            append_missing_mentions=True,
            summary_use_numbered_prefix=False,
        )

    def resolved_llm_retry_options(self) -> DraftGenerationRetryOptions:
        """解析内层 LLM 重试选项（不在内层做机械兜底，由外层协调器负责）。

        外层统一 attempt 策略：内层 ``max_attempts`` 恒为 1（见
        ``llm_draft_generation._resolve_inner_llm_options``）；外层用
        ``max_llm_retries`` 与 ``llm_generation_count`` 限制 LLM 总调用次数。

        :returns: 合并后的 LLM 重试配置（可被内层 resolver 再收紧）。
        :rtype: DraftGenerationRetryOptions
        """
        if self.llm_retry_options is not None:
            return self.llm_retry_options
        return DraftGenerationRetryOptions(
            max_attempts=1,
            fallback_to_mechanical=False,
        )

    def can_invoke_llm(self, llm_generation_count: int) -> bool:
        """判断是否仍可发起一次外层 LLM 调用（含首轮与 guard repair）。

        :param llm_generation_count: 已累计的 LLM 调用次数。
        :type llm_generation_count: int
        :returns: 未达 ``max_llm_retries`` 上限时为 ``True``。
        :rtype: bool
        """
        return llm_generation_count < self.max_llm_retries

    def remaining_llm_slots(self, llm_generation_count: int) -> int:
        """返回剩余可发起的 LLM 调用次数。

        :param llm_generation_count: 已累计的 LLM 调用次数。
        :type llm_generation_count: int
        :returns: 非负剩余次数。
        :rtype: int
        """
        return max(0, self.max_llm_retries - llm_generation_count)


DEFAULT_DRAFT_RETRY_OPTIONS: DraftRetryOptions = DraftRetryOptions()
"""机械路径默认重试配置（无 LLM、启用终端机械兜底）。"""


@dataclass(frozen=True, slots=True)
class DraftRetryContext:
    """单次请求的重试协调器只读上下文。

    持有 ①–③-1 产物与知识包引用；**不包含**可变的 ``DraftCopyJSON``。
    ``triage`` 在协调器全程只读，不得被修改。

    :ivar case_id: 用例标识。
    :vartype case_id: str
    :ivar parsed: 步骤 ① 解析结果（须 ``passed=True`` 且含 ``fact_sheet``）。
    :vartype parsed: ParseResult
    :ivar triage: 步骤 ② 锁定分诊结论。
    :vartype triage: TriageCoreResult
    :ivar resolved: 步骤 ③-1 模板解析包。
    :vartype resolved: CopyTemplateResolved
    :ivar copy_bundle: 可选 KB-TPL / KB-FORBID 等知识包。
    :vartype copy_bundle: CopyKnowledgeBundle | None
    :ivar synonym_map: 可选预加载 KB-SYN；省略时由 guard 异步入口加载。
    :vartype synonym_map: SynonymMap | None
    """

    case_id: str
    parsed: ParseResult
    triage: TriageCoreResult
    resolved: CopyTemplateResolved
    copy_bundle: CopyKnowledgeBundle | None = None
    synonym_map: SynonymMap | None = None


def build_draft_retry_context(
    *,
    parsed: ParseResult,
    triage: TriageCoreResult,
    resolved: CopyTemplateResolved,
    copy_bundle: CopyKnowledgeBundle | None = None,
    synonym_map: SynonymMap | None = None,
    case_id: str | None = None,
) -> DraftRetryContext:
    """从管道中间产物构造 ``DraftRetryContext``。

    :param parsed: 步骤 ① 解析结果。
    :type parsed: ParseResult
    :param triage: 步骤 ② 分诊结论。
    :type triage: TriageCoreResult
    :param resolved: 步骤 ③-1 模板解析包。
    :type resolved: CopyTemplateResolved
    :param copy_bundle: 可选知识包。
    :type copy_bundle: CopyKnowledgeBundle | None
    :param synonym_map: 可选同义词表。
    :type synonym_map: SynonymMap | None
    :param case_id: 可选 caseId；省略时从 ``parsed.fact_sheet`` 读取。
    :type case_id: str | None
    :returns: 协调器上下文。
    :rtype: DraftRetryContext
    :raises ValueError: 解析未通过或缺少 ``fact_sheet`` 时抛出。
    """
    if not parsed.passed or parsed.fact_sheet is None:
        msg = "DraftRetryContext 要求 ParseResult.passed=True 且 fact_sheet 非空。"
        raise ValueError(msg)

    resolved_case_id = case_id
    if resolved_case_id is None:
        resolved_case_id = parsed.fact_sheet.identity.case_id

    return DraftRetryContext(
        case_id=resolved_case_id,
        parsed=parsed,
        triage=triage,
        resolved=resolved,
        copy_bundle=copy_bundle,
        synonym_map=synonym_map,
    )


@dataclass(frozen=True, slots=True)
class DraftRetryAttemptRecord:
    """单轮校验尝试记录（供 ``violations_history`` 与 L7 审计）。

    :ivar attempt_index: 尝试序号（1-based）。
    :vartype attempt_index: int
    :ivar action_before_validate: 本轮校验前协调器采取的动作。
    :vartype action_before_validate: RetryActionLiteral
    :ivar generator: 本轮使用的文案生成器。
    :vartype generator: DraftRetryGeneratorKindLiteral
    :ivar passed: 本轮 ValidateContent 是否通过（按 ``guard_mode`` 语义）。
    :vartype passed: bool
    :ivar violations: 本轮全部 ``schema`` / ``guard`` 违规。
    :vartype violations: tuple[Violation, ...]
    :ivar sanitized: 本轮 draft 是否经确定性修补。
    :vartype sanitized: bool
    """

    attempt_index: int
    action_before_validate: RetryActionLiteral
    generator: DraftRetryGeneratorKindLiteral
    passed: bool
    violations: tuple[Violation, ...] = ()
    sanitized: bool = False


@dataclass(frozen=True, slots=True)
class DraftRetryOutcome:
    """WP5 文案重试协调器执行结果。

    :ivar passed: 是否产出可进入 ⑤ merge 的 ``DraftCopyJSON``。
    :vartype passed: bool
    :ivar draft: 最终文案草稿；失败时为 ``None``。
    :vartype draft: DraftCopyJSON | None
    :ivar attempt_count: 有效尝试次数（生成 + 可选 LLM 重试；修补是否计入由配置决定）。
    :vartype attempt_count: int
    :ivar used_mechanical_fallback: 是否使用过终端机械兜底。
    :vartype used_mechanical_fallback: bool
    :ivar generator: 最终文案生成器种类。
    :vartype generator: DraftRetryGeneratorKindLiteral
    :ivar violations_history: 各轮校验记录（按时间序）。
    :vartype violations_history: tuple[DraftRetryAttemptRecord, ...]
    :ivar last_guard_result: 最后一轮 ``ContentGuardResult``；未跑 guard 时为 ``None``。
    :vartype last_guard_result: ContentGuardResult | None
    :ivar terminal_action: 终止时的协调动作；成功 ``accept``，失败可能为 ``abort`` 等。
    :vartype terminal_action: RetryActionLiteral | None
    :ivar error_message: 协调器级失败说明（``passed=False`` 时）。
    :vartype error_message: str | None
    :ivar llm_generation_count: 累计 LLM API 调用次数（机械路径为 0）。
    :vartype llm_generation_count: int
    """

    passed: bool
    draft: DraftCopyJSON | None
    attempt_count: int
    used_mechanical_fallback: bool
    generator: DraftRetryGeneratorKindLiteral
    violations_history: tuple[DraftRetryAttemptRecord, ...] = ()
    last_guard_result: ContentGuardResult | None = None
    terminal_action: RetryActionLiteral | None = None
    error_message: str | None = None
    llm_generation_count: int = 0

    @property
    def last_violations(self) -> tuple[Violation, ...]:
        """最后一轮校验违规（便于批跑报告）。

        :returns: 违规元组；无历史时为空。
        :rtype: tuple[Violation, ...]
        """
        if len(self.violations_history) == 0:
            return ()
        return self.violations_history[-1].violations
