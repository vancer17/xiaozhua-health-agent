"""WP5 文案重试协调器 — 确定性文案修补（``DETERMINISTIC_REPAIR`` 动作）。

在 ``validate_structure`` / ``validate_content`` 产出违规后，对 ``DraftCopyJSON`` 做
**不调 LLM、不改 ``TriageCoreResult``** 的确定性修正；供外层协调器在
``classify_violations`` 返回 ``deterministic_repair`` 时调用。

包外请通过 ``xiaozhua_health_agent.pipeline`` 门面导入
``apply_deterministic_repair`` / ``apply_deterministic_repair_async``。
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final, Literal, TypeAlias

from xiaozhua_health_agent.copy import (
    ActionLockOptions,
    DraftCopyJSON,
    MechanicalDraftOptions,
    MechanicalDraftResult,
    build_locked_draft_fields,
    enforce_locked_actions,
    generate_mechanical_draft,
    resolve_safety_notice_snippet,
)
from xiaozhua_health_agent.eval import Violation, ViolationCode, normalize_text
from xiaozhua_health_agent.guard import sanitize_draft_for_guard
from xiaozhua_health_agent.pipeline.retry_types import (
    DEFAULT_DRAFT_RETRY_OPTIONS,
    DraftRetryContext,
    DraftRetryOptions,
)
from xiaozhua_health_agent.pipeline.violation_classifier import (
    filter_retryable_violations,
)

__all__ = [
    "DeterministicRepairKind",
    "DeterministicRepairKindLiteral",
    "DeterministicRepairResult",
    "apply_deterministic_repair",
    "apply_deterministic_repair_async",
    "collect_repair_kinds_from_violations",
]

DeterministicRepairKindLiteral: TypeAlias = Literal[
    "action_lock",
    "safety_notice",
    "evidence_reset",
    "field_from_mechanical",
    "forced_mentions",
    "full_mechanical_regen",
]


class DeterministicRepairKind(StrEnum):
    """确定性修补步骤种类（写入 ``DeterministicRepairResult.applied_repairs``）。"""

    ACTION_LOCK = "action_lock"
    SAFETY_NOTICE = "safety_notice"
    EVIDENCE_RESET = "evidence_reset"
    FIELD_FROM_MECHANICAL = "field_from_mechanical"
    FORCED_MENTIONS = "forced_mentions"
    FULL_MECHANICAL_REGEN = "full_mechanical_regen"


_ACTION_LOCK_CODES: Final[frozenset[str]] = frozenset(
    {
        ViolationCode.ACTION_ROUTE_MISMATCH.value,
        ViolationCode.ACTION_LABEL_MISMATCH.value,
        ViolationCode.ACTION_INVALID.value,
    },
)

_SCHEMA_STRUCTURE_CODES: Final[frozenset[str]] = frozenset(
    {
        ViolationCode.PARSE_ERROR.value,
        ViolationCode.FIELD_MISSING.value,
        ViolationCode.TYPE_ERROR.value,
        ViolationCode.ENUM_INVALID.value,
        ViolationCode.EXTRA_FIELD.value,
        ViolationCode.VALUE_ERROR.value,
    },
)

_FIELD_REPAIR_CODES: Final[frozenset[str]] = frozenset(
    {
        ViolationCode.FORBIDDEN_PATTERN_HIT.value,
        ViolationCode.EMERGENCY_TONE_WEAK.value,
        ViolationCode.RISK_TEXT_INCONSISTENT.value,
    },
)

_DRAFT_FIELD_ATTRS: Final[dict[str, str]] = {
    "title": "title",
    "summary": "summary",
    "recommendation": "recommendation",
    "whenToSeeVet": "when_to_see_vet",
    "when_to_see_vet": "when_to_see_vet",
    "safetyNotice": "safety_notice",
    "safety_notice": "safety_notice",
    "evidence": "evidence",
    "primaryAction": "primary_action",
    "primary_action": "primary_action",
    "secondaryAction": "secondary_action",
    "secondary_action": "secondary_action",
}


@dataclass(frozen=True, slots=True)
class DeterministicRepairResult:
    """``apply_deterministic_repair`` 执行结果。

    :ivar draft: 修补后的文案草稿（未修补时与输入语义相同，可能为同一对象）。
    :vartype draft: DraftCopyJSON
    :ivar changed: 是否对 ``draft`` 做了至少一项确定性修改。
    :vartype changed: bool
    :ivar applied_repairs: 已执行的修补步骤（按执行顺序）。
    :vartype applied_repairs: tuple[DeterministicRepairKindLiteral, ...]
    :ivar repair_notes: 人类可读修补说明（调试 / 批跑报告）。
    :vartype repair_notes: tuple[str, ...]
    :ivar considered_violations: 参与修补决策的可路由违规（``schema`` / ``guard``）。
    :vartype considered_violations: tuple[Violation, ...]
    :ivar ignored_violation_count: 被忽略的评测域违规数量。
    :vartype ignored_violation_count: int
    """

    draft: DraftCopyJSON
    changed: bool
    applied_repairs: tuple[DeterministicRepairKindLiteral, ...] = ()
    repair_notes: tuple[str, ...] = ()
    considered_violations: tuple[Violation, ...] = ()
    ignored_violation_count: int = 0


@dataclass
class _RepairState:
    """可变修补状态（内部 DTO，单次 ``apply`` 调用内使用）。

    :ivar draft: 当前文案草稿。
    :vartype draft: DraftCopyJSON
    :ivar changed: 是否发生过修改。
    :vartype changed: bool
    :ivar applied: 已记录修补种类。
    :vartype applied: list[DeterministicRepairKindLiteral]
    :ivar notes: 修补说明。
    :vartype notes: list[str]
    :ivar mechanical_cache: 惰性机械参考稿。
    :vartype mechanical_cache: _MechanicalReferenceCache | None
    """

    draft: DraftCopyJSON
    changed: bool = False
    applied: list[DeterministicRepairKindLiteral] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    mechanical_cache: _MechanicalReferenceCache | None = None


@dataclass
class _MechanicalReferenceCache:
    """惰性缓存 ``generate_mechanical_draft`` 结果（内部辅助）。

    :ivar resolved_options: 机械文案选项。
    :vartype resolved_options: MechanicalDraftOptions
    :ivar result: 已生成的机械稿；首次访问时填充。
    :vartype result: MechanicalDraftResult | None
    """

    resolved_options: MechanicalDraftOptions
    result: MechanicalDraftResult | None = None

    def get_mechanical(
        self,
        context: DraftRetryContext,
    ) -> MechanicalDraftResult:
        """返回机械参考稿，必要时首次生成。

        :param context: 重试协调器上下文。
        :type context: DraftRetryContext
        :returns: 机械文案生成结果。
        :rtype: MechanicalDraftResult
        """
        if self.result is None:
            self.result = generate_mechanical_draft(
                context.resolved,
                options=self.resolved_options,
            )
        return self.result


def collect_repair_kinds_from_violations(
    violations: Sequence[Violation],
) -> tuple[DeterministicRepairKindLiteral, ...]:
    """根据违规码推断应执行的确定性修补种类（不含执行顺序）。

    :param violations: 单轮 ``schema`` / ``guard`` 违规列表。
    :type violations: collections.abc.Sequence[Violation]
    :returns: 去重后的修补种类元组（顺序为声明顺序，非执行顺序）。
    :rtype: tuple[DeterministicRepairKindLiteral, ...]
    """
    considered = filter_retryable_violations(violations)
    kinds: list[DeterministicRepairKindLiteral] = []
    codes = {item.code for item in considered}

    if codes & _SCHEMA_STRUCTURE_CODES:
        _append_kind(kinds, DeterministicRepairKind.FULL_MECHANICAL_REGEN.value)
    if codes & _ACTION_LOCK_CODES:
        _append_kind(kinds, DeterministicRepairKind.ACTION_LOCK.value)
    if ViolationCode.SAFETY_NOTICE_REQUIRED_MISSING.value in codes:
        _append_kind(kinds, DeterministicRepairKind.SAFETY_NOTICE.value)
    if ViolationCode.EVIDENCE_HALLUCINATION.value in codes:
        _append_kind(kinds, DeterministicRepairKind.EVIDENCE_RESET.value)
    if codes & _FIELD_REPAIR_CODES:
        _append_kind(kinds, DeterministicRepairKind.FIELD_FROM_MECHANICAL.value)
    if ViolationCode.FORCED_MENTION_MISSING.value in codes:
        _append_kind(kinds, DeterministicRepairKind.FORCED_MENTIONS.value)

    return tuple(kinds)


def apply_deterministic_repair(
    draft: DraftCopyJSON,
    violations: Sequence[Violation],
    context: DraftRetryContext,
    *,
    options: DraftRetryOptions | None = None,
) -> DeterministicRepairResult:
    """对文案草稿执行确定性修补（同步）。

    仅消费 ``schema`` / ``guard`` 域违规；``semantic_eval`` / ``risk_eval`` 忽略。
    当 ``enable_deterministic_repair=False`` 或无有效违规时原样返回。

    固定执行顺序（与 ``pipeline-design.md`` §6.2 一致）：

    1. 结构类违规 → 整稿机械重生（极端兜底）
    2. 行动锁定回写
    3. ``safetyNotice`` sanitize
    4. ``evidence`` 重置为 ``evidenceBullets``
    5. 禁止词 / 紧急语气 / 风险一致性 → 按字段用机械参考稿覆盖
    6. ``forcedMentions`` 追加至 summary

    :param draft: 当前文案草稿。
    :type draft: DraftCopyJSON
    :param violations: 触发 ``DETERMINISTIC_REPAIR`` 的违规列表。
    :type violations: collections.abc.Sequence[Violation]
    :param context: 协调器只读上下文（含 ``triage`` / ``resolved`` / ``copy_bundle``）。
    :type context: DraftRetryContext
    :param options: 协调器配置；省略时使用 ``DEFAULT_DRAFT_RETRY_OPTIONS``。
    :type options: DraftRetryOptions | None
    :returns: 修补结果（含 ``changed`` 与 ``applied_repairs``）。
    :rtype: DeterministicRepairResult
    """
    effective_options = options if options is not None else DEFAULT_DRAFT_RETRY_OPTIONS
    considered = filter_retryable_violations(violations)
    ignored_count = len(violations) - len(considered)

    if not effective_options.enable_deterministic_repair or len(considered) == 0:
        return DeterministicRepairResult(
            draft=draft,
            changed=False,
            considered_violations=considered,
            ignored_violation_count=ignored_count,
        )

    state = _RepairState(draft=draft)
    codes: set[str] = {str(item.code) for item in considered}

    if codes & _SCHEMA_STRUCTURE_CODES:
        _apply_full_mechanical_regen(state, context, effective_options)

    if codes & _ACTION_LOCK_CODES:
        _apply_action_lock_repair(state, context, effective_options)

    if (
        ViolationCode.SAFETY_NOTICE_REQUIRED_MISSING.value in codes
        or context.triage.safety_notice_required
    ):
        _apply_safety_notice_repair(state, context)

    if ViolationCode.EVIDENCE_HALLUCINATION.value in codes:
        _apply_evidence_reset_repair(state, context)

    field_paths = _collect_field_paths_for_repair(considered, codes)
    if len(field_paths) > 0:
        _apply_field_from_mechanical_repair(
            state,
            context,
            effective_options,
            field_paths=field_paths,
        )

    if ViolationCode.FORCED_MENTION_MISSING.value in codes:
        _apply_forced_mentions_repair(state, context)

    return DeterministicRepairResult(
        draft=state.draft,
        changed=state.changed,
        applied_repairs=tuple(state.applied),
        repair_notes=tuple(state.notes),
        considered_violations=considered,
        ignored_violation_count=ignored_count,
    )


async def apply_deterministic_repair_async(
    draft: DraftCopyJSON,
    violations: Sequence[Violation],
    context: DraftRetryContext,
    *,
    options: DraftRetryOptions | None = None,
) -> DeterministicRepairResult:
    """``apply_deterministic_repair`` 的异步版本（CPU 修补在线程池执行）。

    :param draft: 当前文案草稿。
    :type draft: DraftCopyJSON
    :param violations: 触发修补的违规列表。
    :type violations: collections.abc.Sequence[Violation]
    :param context: 协调器只读上下文。
    :type context: DraftRetryContext
    :param options: 协调器配置。
    :type options: DraftRetryOptions | None
    :returns: 修补结果。
    :rtype: DeterministicRepairResult
    """

    def _run_repair() -> DeterministicRepairResult:
        """在线程池中执行同步确定性修补（闭包）。

        :returns: 修补结果。
        :rtype: DeterministicRepairResult
        """
        return apply_deterministic_repair(
            draft,
            violations,
            context,
            options=options,
        )

    return await asyncio.to_thread(_run_repair)


def _append_kind(
    kinds: list[DeterministicRepairKindLiteral],
    kind: DeterministicRepairKindLiteral,
) -> None:
    """向种类列表追加唯一项（内部辅助）。

    :param kinds: 可变种类列表。
    :type kinds: list[DeterministicRepairKindLiteral]
    :param kind: 待追加种类。
    :type kind: DeterministicRepairKindLiteral
    :returns: ``None``
    :rtype: None
    """
    if kind not in kinds:
        kinds.append(kind)


def _collect_field_paths_for_repair(
    considered: Sequence[Violation],
    codes: set[str],
) -> frozenset[str]:
    """收集需从机械参考稿覆盖的顶层字段名（内部辅助）。

    :param considered: 可路由违规列表。
    :type considered: collections.abc.Sequence[Violation]
    :param codes: 违规码集合。
    :type codes: set[str]
    :returns: 顶层字段名集合（如 ``summary``、``recommendation``）。
    :rtype: frozenset[str]
    """
    if not (codes & _FIELD_REPAIR_CODES):
        return frozenset()

    paths: set[str] = set()
    for item in considered:
        if item.code not in _FIELD_REPAIR_CODES:
            continue
        top = _resolve_draft_attr(item.path, item.field)
        if top is not None:
            paths.add(top)
    return frozenset(paths)


def _resolve_draft_attr(path: str, field: str | None) -> str | None:
    """将违规 path 映射为 ``DraftCopyJSON`` 属性名（内部辅助）。

    :param path: JSON 路径。
    :type path: str
    :param field: 可选顶层字段名。
    :type field: str | None
    :returns: snake_case 属性名；无法解析时为 ``None``。
    :rtype: str | None
    """
    if field is not None and field in _DRAFT_FIELD_ATTRS:
        return _DRAFT_FIELD_ATTRS[field]

    head = path.split(".", maxsplit=1)[0]
    bracket = head.find("[")
    if bracket >= 0:
        head = head[:bracket]
    return _DRAFT_FIELD_ATTRS.get(head)


def _ensure_mechanical_cache(
    state: _RepairState,
    options: DraftRetryOptions,
) -> _MechanicalReferenceCache:
    """确保 ``state`` 上存在机械参考稿缓存（内部辅助）。

    :param state: 可变修补状态。
    :type state: _RepairState
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: 机械参考稿缓存。
    :rtype: _MechanicalReferenceCache
    """
    if state.mechanical_cache is None:
        state.mechanical_cache = _MechanicalReferenceCache(
            resolved_options=options.resolved_mechanical_options(),
        )
    return state.mechanical_cache


def _apply_full_mechanical_regen(
    state: _RepairState,
    context: DraftRetryContext,
    options: DraftRetryOptions,
) -> None:
    """用机械路径整稿替换当前 draft（内部辅助）。

    :param state: 可变修补状态。
    :type state: _RepairState
    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: ``None``
    :rtype: None
    """
    cache = _ensure_mechanical_cache(state, options)
    mechanical = cache.get_mechanical(context)
    if state.draft.model_dump() == mechanical.draft.model_dump():
        return

    state.draft = mechanical.draft
    state.changed = True
    _record_repair(
        state,
        DeterministicRepairKind.FULL_MECHANICAL_REGEN.value,
        "结构类违规触发整稿机械重生。",
    )


def _apply_action_lock_repair(
    state: _RepairState,
    context: DraftRetryContext,
    options: DraftRetryOptions,
) -> None:
    """强制回写主/次行动与 ③-1 draft 一致（内部辅助）。

    :param state: 可变修补状态。
    :type state: _RepairState
    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: ``None``
    :rtype: None
    """
    lock_options = ActionLockOptions(
        enforce=True,
        lock_label=options.guard_options.lock_action_label,
    )
    payload = state.draft.to_alias_dict()
    patched_payload, _warnings = enforce_locked_actions(
        payload,
        context.resolved,
        options=lock_options,
    )
    patched = DraftCopyJSON.from_alias_dict(patched_payload)
    if patched.model_dump() == state.draft.model_dump():
        return

    state.draft = patched
    state.changed = True
    _record_repair(
        state,
        DeterministicRepairKind.ACTION_LOCK.value,
        "已强制回写 primaryAction / secondaryAction 与模板 draft 一致。",
    )


def _apply_safety_notice_repair(
    state: _RepairState,
    context: DraftRetryContext,
) -> None:
    """补全 ``safetyNotice`` 免责声明片段（内部辅助）。

    :param state: 可变修补状态。
    :type state: _RepairState
    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :returns: ``None``
    :rtype: None
    """
    if state.draft.safety_notice.strip():
        return

    if not context.triage.safety_notice_required:
        return

    patched, did_patch = sanitize_draft_for_guard(
        state.draft,
        triage=context.triage,
        copy_bundle=context.copy_bundle,
    )
    if not did_patch:
        snippet = _resolve_safety_snippet_fallback(context)
        if not snippet:
            return
        patched = state.draft.model_copy(
            update={"safety_notice": snippet},
            deep=True,
        )
        did_patch = True

    if not did_patch or patched.model_dump() == state.draft.model_dump():
        return

    state.draft = patched
    state.changed = True
    _record_repair(
        state,
        DeterministicRepairKind.SAFETY_NOTICE.value,
        "已补全 safetyNotice 免责声明片段。",
    )


def _resolve_safety_snippet_fallback(context: DraftRetryContext) -> str:
    """在 sanitize 失败时尝试直接解析 snippet（内部辅助）。

    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :returns: snippet 文本；不可用时为空串。
    :rtype: str
    """
    if context.copy_bundle is None:
        return ""
    return resolve_safety_notice_snippet(
        kb_tpl=context.copy_bundle.kb_tpl,
        triage=context.triage,
    ).strip()


def _apply_evidence_reset_repair(
    state: _RepairState,
    context: DraftRetryContext,
) -> None:
    """将 ``evidence`` 重置为 ② ``evidenceBullets`` 原文（内部辅助）。

    :param state: 可变修补状态。
    :type state: _RepairState
    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :returns: ``None``
    :rtype: None
    """
    locked = build_locked_draft_fields(context.resolved)
    new_evidence = list(locked.evidence)
    if state.draft.evidence == new_evidence:
        return

    state.draft = state.draft.model_copy(
        update={"evidence": new_evidence},
        deep=True,
    )
    state.changed = True
    _record_repair(
        state,
        DeterministicRepairKind.EVIDENCE_RESET.value,
        "已将 evidence 重置为 evidenceBullets 原文。",
    )


def _apply_field_from_mechanical_repair(
    state: _RepairState,
    context: DraftRetryContext,
    options: DraftRetryOptions,
    *,
    field_paths: frozenset[str],
) -> None:
    """用机械参考稿覆盖指定字段（内部辅助）。

    :param state: 可变修补状态。
    :type state: _RepairState
    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :param field_paths: 待覆盖的 ``DraftCopyJSON`` 属性名集合。
    :type field_paths: frozenset[str]
    :returns: ``None``
    :rtype: None
    """
    cache = _ensure_mechanical_cache(state, options)
    reference = cache.get_mechanical(context).draft
    updates: dict[str, Any] = {}

    for attr in field_paths:
        if attr == "evidence":
            continue
        reference_value = getattr(reference, attr)
        if getattr(state.draft, attr) != reference_value:
            updates[attr] = reference_value

    if len(updates) == 0:
        return

    state.draft = state.draft.model_copy(update=updates, deep=True)
    state.changed = True
    fields_text = ", ".join(sorted(updates.keys()))
    _record_repair(
        state,
        DeterministicRepairKind.FIELD_FROM_MECHANICAL.value,
        f"已用机械参考稿覆盖字段：{fields_text}。",
    )


def _apply_forced_mentions_repair(
    state: _RepairState,
    context: DraftRetryContext,
) -> None:
    """向 summary 追加缺失的 ``forcedMentions`` 主题（内部辅助）。

    :param state: 可变修补状态。
    :type state: _RepairState
    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :returns: ``None``
    :rtype: None
    """
    required = context.triage.forced_mentions
    if len(required) == 0:
        return

    new_summary, appended = _append_missing_mentions_to_summary(
        state.draft.summary,
        required,
    )
    if len(appended) == 0:
        return

    state.draft = state.draft.model_copy(
        update={"summary": new_summary},
        deep=True,
    )
    state.changed = True
    _record_repair(
        state,
        DeterministicRepairKind.FORCED_MENTIONS.value,
        f"已向 summary 追加 forcedMentions：{', '.join(appended)}。",
    )


def _append_missing_mentions_to_summary(
    summary: str,
    required_mentions: Sequence[str],
) -> tuple[str, tuple[str, ...]]:
    """向 summary 追加尚未出现的强制提及主题（内部辅助）。

    逻辑与 ``copy.mechanical_draft._append_missing_mentions`` 对齐。

    :param summary: 当前 summary 正文。
    :type summary: str
    :param required_mentions: ② ``forcedMentions`` 列表。
    :type required_mentions: collections.abc.Sequence[str]
    :returns: ``(新 summary, 已追加主题)`` 元组。
    :rtype: tuple[str, tuple[str, ...]]
    """
    corpus = normalize_text(summary)
    missing: list[str] = []
    for mention in required_mentions:
        stripped = mention.strip()
        if not stripped:
            continue
        normalized_mention = normalize_text(stripped)
        if normalized_mention and normalized_mention not in corpus:
            missing.append(stripped)

    if len(missing) == 0:
        return summary, ()

    appendix = "请同时留意：" + "、".join(missing) + "。"
    return f"{summary}\n{appendix}", tuple(missing)


def _record_repair(
    state: _RepairState,
    kind: DeterministicRepairKindLiteral,
    note: str,
) -> None:
    """记录单次修补步骤（内部辅助）。

    :param state: 可变修补状态。
    :type state: _RepairState
    :param kind: 修补种类。
    :type kind: DeterministicRepairKindLiteral
    :param note: 人类可读说明。
    :type note: str
    :returns: ``None``
    :rtype: None
    """
    _append_kind(state.applied, kind)
    state.notes.append(note)
