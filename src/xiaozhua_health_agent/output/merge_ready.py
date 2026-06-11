"""WP5 merge-ready draft 契约 — 合并前不变量校验。

在 ``merge_agent_output`` 之前验证 ``DraftCopyJSON`` 是否满足结构与合并语义约束，
避免在 merge 层才发现 ``safetyNoticeRequired`` 等条件不满足。

包外请通过 ``xiaozhua_health_agent.output`` 门面导入公开符号。
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, Final

from xiaozhua_health_agent.copy import DraftCopyJSON
from xiaozhua_health_agent.eval import (
    Violation,
    ViolationCode,
    ViolationCodeLiteral,
    ViolationDomain,
    ViolationSeverity,
    normalize_text,
    validate_draft_structure,
)
from xiaozhua_health_agent.output.merge_ready_types import (
    DEFAULT_MERGE_READY_OPTIONS,
    MERGE_READY_ERROR_MESSAGE,
    MERGE_READY_SCHEMA_VERSION,
    MergeReadyError,
    MergeReadyOptions,
    MergeReadyResult,
)
from xiaozhua_health_agent.triage import TriageCoreResult

__all__ = [
    "assert_merge_ready",
    "assert_merge_ready_async",
    "check_merge_ready",
    "check_merge_ready_async",
]

_TEXT_FIELD_CHECKS: Final[tuple[tuple[tuple[str, str], str], ...]] = (
    (("title", "title"), "卡片标题"),
    (("summary", "summary"), "风险摘要"),
    (("recommendation", "recommendation"), "行动建议"),
    (("when_to_see_vet", "whenToSeeVet"), "就医升级条件"),
)
"""文案必填字段：(模型属性名, JSON path) 与中文说明。"""


def check_merge_ready(
    draft: DraftCopyJSON | Mapping[str, Any],
    triage: TriageCoreResult,
    *,
    options: MergeReadyOptions | None = None,
) -> MergeReadyResult:
    """校验 ``DraftCopyJSON`` 是否满足 merge-ready 契约（同步）。

    校验顺序：

    1. ``validate_draft_structure``（④-A 结构子集）；
    2. 文案字段去空白后非空；
    3. ``primaryAction.label`` / 可选 ``secondaryAction.label``；
    4. 可选 ``evidence`` 非空列表；
    5. ``safetyNoticeRequired=true`` 时 ``safetyNotice`` 长度门禁。

    :param draft: 步骤 ③ 文案草稿或等价 JSON 对象。
    :type draft: DraftCopyJSON | collections.abc.Mapping[str, Any]
    :param triage: 步骤 ② 锁定分诊结论（只读；本函数不修改）。
    :type triage: TriageCoreResult
    :param options: 校验配置；省略时使用 ``DEFAULT_MERGE_READY_OPTIONS``。
    :type options: MergeReadyOptions | None
    :returns: merge-ready 校验结果。
    :rtype: MergeReadyResult
    :raises ValueError: ``min_safety_notice_length`` 小于 1 时抛出。
    """
    effective_options = options if options is not None else DEFAULT_MERGE_READY_OPTIONS
    if effective_options.min_safety_notice_length < 1:
        msg = "MergeReadyOptions.min_safety_notice_length 必须 >= 1。"
        raise ValueError(msg)

    structure = validate_draft_structure(draft)
    if not structure.passed or structure.parsed is None:
        return MergeReadyResult(
            passed=False,
            violations=tuple(structure.violations),
            draft=None,
            schema_version=MERGE_READY_SCHEMA_VERSION,
        )

    parsed_draft = structure.parsed
    semantic_violations = _collect_semantic_merge_ready_violations(
        parsed_draft,
        triage=triage,
        options=effective_options,
    )
    if semantic_violations:
        return MergeReadyResult(
            passed=False,
            violations=semantic_violations,
            draft=parsed_draft,
            schema_version=MERGE_READY_SCHEMA_VERSION,
        )

    return MergeReadyResult(
        passed=True,
        violations=(),
        draft=parsed_draft,
        schema_version=MERGE_READY_SCHEMA_VERSION,
    )


async def check_merge_ready_async(
    draft: DraftCopyJSON | Mapping[str, Any],
    triage: TriageCoreResult,
    *,
    options: MergeReadyOptions | None = None,
) -> MergeReadyResult:
    """校验 merge-ready 契约（异步；CPU 路径委托线程池）。

    :param draft: 步骤 ③ 文案草稿或等价 JSON 对象。
    :type draft: DraftCopyJSON | collections.abc.Mapping[str, Any]
    :param triage: 步骤 ② 锁定分诊结论。
    :type triage: TriageCoreResult
    :param options: 校验配置。
    :type options: MergeReadyOptions | None
    :returns: merge-ready 校验结果。
    :rtype: MergeReadyResult
    """

    def _run_check_in_thread() -> MergeReadyResult:
        """在线程池执行 merge-ready 校验（闭包）。

        :returns: merge-ready 校验结果。
        :rtype: MergeReadyResult
        """
        return check_merge_ready(
            draft,
            triage,
            options=options,
        )

    return await asyncio.to_thread(_run_check_in_thread)


def assert_merge_ready(
    draft: DraftCopyJSON | Mapping[str, Any],
    triage: TriageCoreResult,
    *,
    options: MergeReadyOptions | None = None,
) -> DraftCopyJSON:
    """断言 draft 满足 merge-ready 契约；不满足时抛出 ``MergeReadyError``。

    :param draft: 待校验文案草稿。
    :type draft: DraftCopyJSON | collections.abc.Mapping[str, Any]
    :param triage: 步骤 ② 锁定分诊结论。
    :type triage: TriageCoreResult
    :param options: 校验配置。
    :type options: MergeReadyOptions | None
    :returns: 校验通过后的强类型 ``DraftCopyJSON``。
    :rtype: DraftCopyJSON
    :raises MergeReadyError: 未满足 merge-ready 契约时抛出。
    """
    result = check_merge_ready(draft, triage, options=options)
    if result.passed and result.draft is not None:
        return result.draft

    detail = _format_violation_summary(result.violations)
    message = MERGE_READY_ERROR_MESSAGE
    if detail:
        message = f"{MERGE_READY_ERROR_MESSAGE} {detail}"
    raise MergeReadyError(message, violations=result.violations)


async def assert_merge_ready_async(
    draft: DraftCopyJSON | Mapping[str, Any],
    triage: TriageCoreResult,
    *,
    options: MergeReadyOptions | None = None,
) -> DraftCopyJSON:
    """异步断言 merge-ready 契约。

    :param draft: 待校验文案草稿。
    :type draft: DraftCopyJSON | collections.abc.Mapping[str, Any]
    :param triage: 步骤 ② 锁定分诊结论。
    :type triage: TriageCoreResult
    :param options: 校验配置。
    :type options: MergeReadyOptions | None
    :returns: 校验通过后的强类型 ``DraftCopyJSON``。
    :rtype: DraftCopyJSON
    :raises MergeReadyError: 未满足 merge-ready 契约时抛出。
    """
    result = await check_merge_ready_async(draft, triage, options=options)
    if result.passed and result.draft is not None:
        return result.draft

    detail = _format_violation_summary(result.violations)
    message = MERGE_READY_ERROR_MESSAGE
    if detail:
        message = f"{MERGE_READY_ERROR_MESSAGE} {detail}"
    raise MergeReadyError(message, violations=result.violations)


def _collect_semantic_merge_ready_violations(
    draft: DraftCopyJSON,
    *,
    triage: TriageCoreResult,
    options: MergeReadyOptions,
) -> tuple[Violation, ...]:
    """收集 merge-ready 语义层违规（结构已通过后调用，内部辅助）。

    :param draft: 已通过结构校验的文案草稿。
    :type draft: DraftCopyJSON
    :param triage: 锁定分诊结论。
    :type triage: TriageCoreResult
    :param options: merge-ready 配置。
    :type options: MergeReadyOptions
    :returns: 违规元组；无问题时为空。
    :rtype: tuple[Violation, ...]
    """
    violations: list[Violation] = []

    for (attr_name, json_path), label in _TEXT_FIELD_CHECKS:
        raw_value = getattr(draft, attr_name)
        if not isinstance(raw_value, str):
            violations.append(
                _make_merge_ready_violation(
                    code=ViolationCode.TYPE_ERROR.value,
                    path=json_path,
                    field=_top_level_field(json_path),
                    message=f"{label}（{json_path}）必须为字符串。",
                ),
            )
            continue
        if not raw_value.strip():
            violations.append(
                _make_merge_ready_violation(
                    code=ViolationCode.FIELD_MISSING.value,
                    path=json_path,
                    field=_top_level_field(json_path),
                    message=f"{label}（{json_path}）去空白后不得为空。",
                ),
            )

    violations.extend(_check_primary_action_label(draft))
    violations.extend(_check_secondary_action_label(draft))
    violations.extend(_check_evidence_requirement(draft, options=options))
    violations.extend(
        _check_required_safety_notice(
            draft,
            triage=triage,
            min_length=options.min_safety_notice_length,
        ),
    )

    return tuple(violations)


def _check_primary_action_label(draft: DraftCopyJSON) -> tuple[Violation, ...]:
    """校验 ``primaryAction.label`` 去空白后非空（内部辅助）。

    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :returns: 违规列表；满足时为空。
    :rtype: tuple[Violation, ...]
    """
    label = draft.primary_action.label
    if isinstance(label, str) and label.strip():
        return ()
    return (
        _make_merge_ready_violation(
            code=ViolationCode.ACTION_INVALID.value,
            path="primaryAction.label",
            field="primaryAction",
            message="primaryAction.label 去空白后不得为空。",
        ),
    )


def _check_secondary_action_label(draft: DraftCopyJSON) -> tuple[Violation, ...]:
    """校验可选 ``secondaryAction.label``（内部辅助）。

    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :returns: 违规列表；无次行动或 label 合法时为空。
    :rtype: tuple[Violation, ...]
    """
    if draft.secondary_action is None:
        return ()
    label = draft.secondary_action.label
    if isinstance(label, str) and label.strip():
        return ()
    return (
        _make_merge_ready_violation(
            code=ViolationCode.ACTION_INVALID.value,
            path="secondaryAction.label",
            field="secondaryAction",
            message="secondaryAction 存在时，label 去空白后不得为空。",
        ),
    )


def _check_evidence_requirement(
    draft: DraftCopyJSON,
    *,
    options: MergeReadyOptions,
) -> tuple[Violation, ...]:
    """按配置校验 ``evidence`` 列表（内部辅助）。

    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :param options: merge-ready 配置。
    :type options: MergeReadyOptions
    :returns: 违规列表。
    :rtype: tuple[Violation, ...]
    """
    if not options.require_non_empty_evidence:
        return ()
    if len(draft.evidence) > 0:
        return ()
    return (
        _make_merge_ready_violation(
            code=ViolationCode.FIELD_MISSING.value,
            path="evidence",
            field="evidence",
            message="merge-ready 要求 evidence 至少包含一条非空事实句。",
        ),
    )


def _check_required_safety_notice(
    draft: DraftCopyJSON,
    *,
    triage: TriageCoreResult,
    min_length: int,
) -> tuple[Violation, ...]:
    """当 ② 要求免责声明时校验 ``safetyNotice``（内部辅助）。

    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :param triage: 锁定分诊结论。
    :type triage: TriageCoreResult
    :param min_length: 归一化后最小有效长度。
    :type min_length: int
    :returns: 违规列表。
    :rtype: tuple[Violation, ...]
    """
    if not triage.safety_notice_required:
        return ()

    normalized = normalize_text(draft.safety_notice)
    if len(normalized) >= min_length:
        return ()

    return (
        _make_merge_ready_violation(
            code=ViolationCode.SAFETY_NOTICE_REQUIRED_MISSING.value,
            path="safetyNotice",
            field="safetyNotice",
            message=(
                "safetyNoticeRequired 为 true，但 safetyNotice 过短或为空"
                f"（merge-ready 要求至少 {min_length} 个有效字符）。"
            ),
        ),
    )


def _make_merge_ready_violation(
    *,
    code: ViolationCodeLiteral,
    path: str,
    field: str | None,
    message: str,
) -> Violation:
    """构造 ``domain=schema`` 的 merge-ready 违规项（内部辅助）。

    :param code: 违规码。
    :type code: ViolationCodeLiteral
    :param path: JSON 字段路径。
    :type path: str
    :param field: 顶层字段名。
    :type field: str | None
    :param message: 人类可读说明。
    :type message: str
    :returns: 结构化违规记录。
    :rtype: Violation
    """
    return Violation(
        code=code,
        domain=ViolationDomain.SCHEMA.value,
        path=path,
        field=field,
        message=message,
        severity=ViolationSeverity.HIGH.value,
    )


def _top_level_field(json_path: str) -> str | None:
    """从 JSON 路径提取顶层字段名（内部辅助）。

    :param json_path: 点分路径，如 ``primaryAction.label``。
    :type json_path: str
    :returns: 顶层字段；无法解析时为 ``None``。
    :rtype: str | None
    """
    if not json_path:
        return None
    return json_path.split(".", maxsplit=1)[0]


def _format_violation_summary(violations: tuple[Violation, ...]) -> str:
    """将违规列表格式化为单行摘要（内部辅助）。

    :param violations: 违规元组。
    :type violations: tuple[Violation, ...]
    :returns: 摘要文本；无违规时为空串。
    :rtype: str
    """
    if not violations:
        return ""
    codes = ", ".join(f"{item.code}@{item.path}" for item in violations[:3])
    suffix = "" if len(violations) <= 3 else f" 等共 {len(violations)} 项"
    return f"({codes}{suffix})"
