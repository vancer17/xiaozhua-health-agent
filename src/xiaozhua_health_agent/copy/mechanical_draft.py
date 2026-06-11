"""WP4 ③ 无 LLM 机械文案路径（Template Fallback 共用实现）。

在 ``CopyTemplateResolved`` 上执行占位符替换与字段组装，产出 ``DraftCopyJSON``。
对应 ``pipeline-design.md`` §7.2 与 ``kb-tpl-template-spec.md`` §14.3。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, TypeAlias

from pydantic import ValidationError

from xiaozhua_health_agent.copy.copy_types import (
    CopyKnowledgeBundle,
    CopyTemplateResolved,
)
from xiaozhua_health_agent.copy.draft_locked_fields import (
    LockedDraftFields,
    build_locked_draft_fields,
)
from xiaozhua_health_agent.copy.draft_types import DraftCopyJSON
from xiaozhua_health_agent.copy.template_resolver import resolve_copy_template
from xiaozhua_health_agent.copy.template_substitution import (
    filter_outline_lines,
    has_unresolved_placeholders,
    substitute_template_text,
)
from xiaozhua_health_agent.parse import ParseResult, parse_input
from xiaozhua_health_agent.triage import run_triage_core

__all__ = [
    "MechanicalDraftOptions",
    "MechanicalDraftResult",
    "MechanicalDraftWarning",
    "MechanicalDraftWarningCode",
    "MechanicalDraftWarningCodeLiteral",
    "generate_mechanical_draft",
    "generate_mechanical_draft_for_parsed",
    "generate_mechanical_draft_from_input",
    "join_summary_outline",
]

MechanicalDraftWarningCodeLiteral: TypeAlias = str

_SUMMARY_MARKERS: Final[tuple[str, ...]] = (
    "①",
    "②",
    "③",
    "④",
    "⑤",
    "⑥",
    "⑦",
    "⑧",
    "⑨",
    "⑩",
)
"""summary 提纲行前缀序号。"""

_SUMMARY_DEGRADED_FALLBACK: Final[str] = "请结合当前监测数据与宠物状态继续观察。"
"""提纲全部无效时的极简 summary 兜底句。"""

_TITLE_DEGRADED_FALLBACK: Final[str] = "健康分诊提示"
"""title 组装失败时的极简标题。"""


class MechanicalDraftWarningCode(StrEnum):
    """机械文案组装阶段的非致命警告码。"""

    UNRESOLVED_PLACEHOLDER_IN_TITLE = "UNRESOLVED_PLACEHOLDER_IN_TITLE"
    SUMMARY_LINE_DROPPED = "SUMMARY_LINE_DROPPED"
    SUMMARY_DEGRADED = "SUMMARY_DEGRADED"
    MISSING_MENTIONS_APPENDED = "MISSING_MENTIONS_APPENDED"
    RECOMMENDATION_EMPTY_DEGRADED = "RECOMMENDATION_EMPTY_DEGRADED"
    WHEN_TO_SEE_VET_EMPTY_DEGRADED = "WHEN_TO_SEE_VET_EMPTY_DEGRADED"


@dataclass(frozen=True, slots=True)
class MechanicalDraftOptions:
    """机械文案生成可选行为。

    :ivar append_missing_mentions: 为 ``True`` 时在 summary 末尾追加未覆盖的
        ``forcedMentions`` 主题句（仅 mechanical / fallback 路径，提高 mustMention 命中率）。
    :vartype append_missing_mentions: bool
    :ivar summary_use_numbered_prefix: 为 ``True`` 时用 ①②③ 前缀拼接 summary 行。
    :vartype summary_use_numbered_prefix: bool
    :ivar on_missing_slot_in_title: title 槽位缺失策略，传给 ``substitute_template_text``。
    :vartype on_missing_slot_in_title: str
    """

    append_missing_mentions: bool = True
    summary_use_numbered_prefix: bool = True
    on_missing_slot_in_title: str = "omit"


@dataclass(frozen=True, slots=True)
class MechanicalDraftWarning:
    """单条机械文案组装警告。

    :ivar code: 警告码。
    :vartype code: MechanicalDraftWarningCode
    :ivar message: 人类可读说明。
    :vartype message: str
    :ivar field: 关联输出字段名（若有）。
    :vartype field: str | None
    """

    code: MechanicalDraftWarningCode
    message: str
    field: str | None = None


@dataclass(frozen=True, slots=True)
class MechanicalDraftResult:
    """机械文案生成结果。

    :ivar draft: 校验通过的文案草稿。
    :vartype draft: DraftCopyJSON
    :ivar warnings: 组装过程产生的警告列表。
    :vartype warnings: tuple[MechanicalDraftWarning, ...]
    :ivar template_id: 使用的模板主键（便于批跑报告）。
    :vartype template_id: str
    """

    draft: DraftCopyJSON
    warnings: tuple[MechanicalDraftWarning, ...]
    template_id: str


def generate_mechanical_draft(
    resolved: CopyTemplateResolved,
    *,
    options: MechanicalDraftOptions | None = None,
) -> MechanicalDraftResult:
    """从 ``CopyTemplateResolved`` 机械组装 ``DraftCopyJSON``（不调用 LLM）。

    :param resolved: 步骤 ③-1 产出的模板解析包。
    :type resolved: CopyTemplateResolved
    :param options: 可选行为配置；省略时使用默认选项。
    :type options: MechanicalDraftOptions | None
    :returns: 文案草稿与组装警告。
    :rtype: MechanicalDraftResult
    :raises ValueError: 组装后仍无法满足 ``DraftCopyJSON`` 必填约束时抛出。
    """
    opts = options if options is not None else MechanicalDraftOptions()
    warnings: list[MechanicalDraftWarning] = []
    filled_slots = resolved.filled_slots
    locked = build_locked_draft_fields(resolved)

    title = _build_title(
        resolved.title_pattern,
        filled_slots,
        on_missing=opts.on_missing_slot_in_title,
        warnings=warnings,
    )
    summary = _build_summary(
        resolved.summary_outline,
        filled_slots,
        required_mentions=resolved.required_mentions,
        options=opts,
        warnings=warnings,
    )
    recommendation = _build_single_field(
        resolved.recommendation_template,
        filled_slots,
        field_name="recommendation",
        fallback="请根据当前状态采取适当措施。",
        warnings=warnings,
    )
    when_to_see_vet = _build_single_field(
        resolved.when_to_see_vet_template,
        filled_slots,
        field_name="whenToSeeVet",
        fallback="如有疑虑或症状加重，请联系兽医。",
        warnings=warnings,
    )

    draft = _assemble_draft_copy_json(
        title=title,
        summary=summary,
        recommendation=recommendation,
        when_to_see_vet=when_to_see_vet,
        locked=locked,
    )

    return MechanicalDraftResult(
        draft=draft,
        warnings=tuple(warnings),
        template_id=resolved.template_id,
    )


def generate_mechanical_draft_from_input(
    agent_input: Mapping[str, Any],
    *,
    bundle: CopyKnowledgeBundle | None = None,
    options: MechanicalDraftOptions | None = None,
) -> MechanicalDraftResult:
    """对单次 Agent 输入执行 ①→②→③-1→机械文案组装。

    :param agent_input: 符合 input_schema 的 case / App 输入 JSON。
    :type agent_input: collections.abc.Mapping[str, Any]
    :param bundle: 可选 KB-TPL 知识包；传给 ③-1。
    :type bundle: CopyKnowledgeBundle | None
    :param options: 机械文案选项。
    :type options: MechanicalDraftOptions | None
    :returns: 机械文案结果。
    :rtype: MechanicalDraftResult
    :raises xiaozhua_health_agent.parse.ParseError: 输入契约校验失败时由 ``parse_input`` 抛出。
    """
    parsed = parse_input(agent_input)
    return generate_mechanical_draft_for_parsed(
        parsed,
        bundle=bundle,
        options=options,
    )


def generate_mechanical_draft_for_parsed(
    parsed: ParseResult,
    *,
    bundle: CopyKnowledgeBundle | None = None,
    options: MechanicalDraftOptions | None = None,
) -> MechanicalDraftResult:
    """对已解析输入执行 ②→③-1→机械文案组装。

    :param parsed: 步骤 ① ``parse_input`` 结果。
    :type parsed: ParseResult
    :param bundle: 可选知识资产包。
    :type bundle: CopyKnowledgeBundle | None
    :param options: 机械文案选项。
    :type options: MechanicalDraftOptions | None
    :returns: 机械文案结果。
    :rtype: MechanicalDraftResult
    :raises ValueError: ``parsed.fact_sheet`` 为 ``None`` 时抛出。
    """
    if parsed.fact_sheet is None:
        msg = "ParseResult.fact_sheet 为空，无法执行机械文案路径。"
        raise ValueError(msg)

    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=bundle,
    )
    return generate_mechanical_draft(resolved, options=options)


def join_summary_outline(
    lines: tuple[str, ...],
    *,
    use_numbered_prefix: bool = True,
) -> str:
    """将多条 summary 提纲拼接为单一字符串。

    :param lines: 有效提纲行。
    :type lines: tuple[str, ...]
    :param use_numbered_prefix: 为 ``True`` 时每行前加 ①②③… 前缀。
    :type use_numbered_prefix: bool
    :returns: 拼接后的 summary 正文。
    :rtype: str
    """
    if not lines:
        return ""
    if not use_numbered_prefix:
        return "\n".join(lines)
    parts: list[str] = []
    for index, line in enumerate(lines):
        marker = (
            _SUMMARY_MARKERS[index]
            if index < len(_SUMMARY_MARKERS)
            else f"{index + 1}."
        )
        parts.append(f"{marker}{line}")
    return "\n".join(parts)


def _build_title(
    title_pattern: str,
    filled_slots: dict[str, str],
    *,
    on_missing: str,
    warnings: list[MechanicalDraftWarning],
) -> str:
    """组装 title 字段。

    :param title_pattern: 模板 titlePattern。
    :type title_pattern: str
    :param filled_slots: 槽位字典。
    :type filled_slots: dict[str, str]
    :param on_missing: 缺失槽位策略。
    :type on_missing: str
    :param warnings: 可变警告列表（就地追加）。
    :type warnings: list[MechanicalDraftWarning]
    :returns: 非空标题字符串。
    :rtype: str
    """
    title = substitute_template_text(
        title_pattern,
        filled_slots,
        on_missing=on_missing,
    )
    if has_unresolved_placeholders(title):
        warnings.append(
            MechanicalDraftWarning(
                code=MechanicalDraftWarningCode.UNRESOLVED_PLACEHOLDER_IN_TITLE,
                message="title 仍含未解析占位符，已使用兜底标题。",
                field="title",
            ),
        )
        title = _TITLE_DEGRADED_FALLBACK
    if not title:
        title = _TITLE_DEGRADED_FALLBACK
    return title


def _build_summary(
    summary_outline: tuple[str, ...],
    filled_slots: dict[str, str],
    *,
    required_mentions: tuple[str, ...],
    options: MechanicalDraftOptions,
    warnings: list[MechanicalDraftWarning],
) -> str:
    """组装 summary 字段。

    :param summary_outline: 模板提纲列表。
    :type summary_outline: tuple[str, ...]
    :param filled_slots: 槽位字典。
    :type filled_slots: dict[str, str]
    :param required_mentions: ② 强制提及主题。
    :type required_mentions: tuple[str, ...]
    :param options: 机械文案选项。
    :type options: MechanicalDraftOptions
    :param warnings: 可变警告列表。
    :type warnings: list[MechanicalDraftWarning]
    :returns: 非空 summary 字符串。
    :rtype: str
    """
    dropped_count = len(summary_outline)
    valid_lines = filter_outline_lines(summary_outline, filled_slots)
    dropped_count -= len(valid_lines)
    if dropped_count > 0:
        warnings.append(
            MechanicalDraftWarning(
                code=MechanicalDraftWarningCode.SUMMARY_LINE_DROPPED,
                message=f"已丢弃 {dropped_count} 条含无效占位的 summary 提纲行。",
                field="summary",
            ),
        )

    summary = join_summary_outline(
        valid_lines,
        use_numbered_prefix=options.summary_use_numbered_prefix,
    )

    if not summary:
        warnings.append(
            MechanicalDraftWarning(
                code=MechanicalDraftWarningCode.SUMMARY_DEGRADED,
                message="summary 提纲均无效，已使用极简兜底句。",
                field="summary",
            ),
        )
        summary = _SUMMARY_DEGRADED_FALLBACK

    if options.append_missing_mentions and required_mentions:
        summary, appended = _append_missing_mentions(summary, required_mentions)
        if appended:
            warnings.append(
                MechanicalDraftWarning(
                    code=MechanicalDraftWarningCode.MISSING_MENTIONS_APPENDED,
                    message=f"已向 summary 追加未覆盖主题：{', '.join(appended)}。",
                    field="summary",
                ),
            )

    return summary


def _build_single_field(
    template: str,
    filled_slots: dict[str, str],
    *,
    field_name: str,
    fallback: str,
    warnings: list[MechanicalDraftWarning],
) -> str:
    """组装 recommendation / whenToSeeVet 等单字段模板。

    :param template: 模板字符串。
    :type template: str
    :param filled_slots: 槽位字典。
    :type filled_slots: dict[str, str]
    :param field_name: 输出字段名（用于警告）。
    :type field_name: str
    :param fallback: 组装结果为空时的兜底句。
    :type fallback: str
    :param warnings: 可变警告列表。
    :type warnings: list[MechanicalDraftWarning]
    :returns: 非空字符串。
    :rtype: str
    """
    text = substitute_template_text(template, filled_slots, on_missing="omit")
    if not text:
        code = (
            MechanicalDraftWarningCode.RECOMMENDATION_EMPTY_DEGRADED
            if field_name == "recommendation"
            else MechanicalDraftWarningCode.WHEN_TO_SEE_VET_EMPTY_DEGRADED
        )
        warnings.append(
            MechanicalDraftWarning(
                code=code,
                message=f"{field_name} 模板组装为空，已使用兜底句。",
                field=field_name,
            ),
        )
        return fallback
    return text


def _append_missing_mentions(
    summary: str,
    required_mentions: tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    """向 summary 追加尚未出现的 forcedMentions 主题。

    :param summary: 当前 summary 正文。
    :type summary: str
    :param required_mentions: ② 强制提及列表。
    :type required_mentions: tuple[str, ...]
    :returns: 更新后的 summary 与已追加主题元组。
    :rtype: tuple[str, tuple[str, ...]]
    """
    corpus = summary.casefold()
    missing: list[str] = []
    for mention in required_mentions:
        stripped = mention.strip()
        if not stripped:
            continue
        if stripped.casefold() not in corpus:
            missing.append(stripped)
    if not missing:
        return summary, ()
    appendix = "请同时留意：" + "、".join(missing) + "。"
    return f"{summary}\n{appendix}", tuple(missing)


def _assemble_draft_copy_json(
    *,
    title: str,
    summary: str,
    recommendation: str,
    when_to_see_vet: str,
    locked: LockedDraftFields,
) -> DraftCopyJSON:
    """将组装字段与锁定字段合并为 ``DraftCopyJSON`` 并校验。

    :param title: 标题。
    :type title: str
    :param summary: 摘要。
    :type summary: str
    :param recommendation: 建议。
    :type recommendation: str
    :param when_to_see_vet: 就医升级条件。
    :type when_to_see_vet: str
    :param locked: 锁定字段（evidence / safety / actions）。
    :type locked: LockedDraftFields
    :returns: 校验后的文案草稿。
    :rtype: DraftCopyJSON
    :raises ValueError: Pydantic 校验失败时包装抛出。
    """
    payload: dict[str, Any] = {
        "title": title,
        "summary": summary,
        "evidence": list(locked.evidence),
        "recommendation": recommendation,
        "whenToSeeVet": when_to_see_vet,
        "safetyNotice": locked.safety_notice,
        "primaryAction": locked.primary_action.model_dump(by_alias=True, mode="json"),
        "secondaryAction": (
            locked.secondary_action.model_dump(by_alias=True, mode="json")
            if locked.secondary_action is not None
            else None
        ),
    }
    try:
        return DraftCopyJSON.from_alias_dict(payload)
    except ValidationError as exc:
        msg = f"机械组装的 DraftCopyJSON 校验失败：{exc.error_count()} 项错误。"
        raise ValueError(msg) from exc
