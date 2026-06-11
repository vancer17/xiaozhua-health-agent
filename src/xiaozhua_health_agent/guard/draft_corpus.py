"""``DraftCopyJSON`` 语料分段与合并（L5 ValidateContent 专用）。"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeAlias

from xiaozhua_health_agent.copy import DraftCopyJSON
from xiaozhua_health_agent.eval import NormalizationProfileLiteral, normalize_text

__all__ = [
    "DEFAULT_DRAFT_CORPUS_OPTIONS",
    "DraftCorpusBuildOptions",
    "DraftCorpusBundle",
    "DraftTextSegment",
    "DraftTextSegmentCategory",
    "DraftTextSegmentCategoryLiteral",
    "build_draft_corpus_bundle",
    "build_draft_text_corpus",
    "iter_draft_text_segments",
]

DEFAULT_SEGMENT_JOINER: str = "\n"
"""合并 draft 全文语料时的默认分隔符。"""

DraftTextSegmentCategoryLiteral: TypeAlias = Literal["user_facing", "action_label"]


class DraftTextSegmentCategory(StrEnum):
    """Draft 语料分段类别。"""

    USER_FACING = "user_facing"
    ACTION_LABEL = "action_label"


@dataclass(frozen=True, slots=True)
class DraftCorpusBuildOptions:
    """Draft 语料构建配置。

    :ivar include_action_labels: 是否纳入 ``primaryAction.label`` /
        ``secondaryAction.label``。
    :vartype include_action_labels: bool
    :ivar segment_joiner: 合并语料时段间分隔符。
    :vartype segment_joiner: str
    :ivar normalization_profile: 文本归一化策略（委托 ``eval.normalize_text``）。
    :vartype normalization_profile: NormalizationProfileLiteral
    :ivar skip_empty_segments: 归一化后为空白的段是否丢弃。
    :vartype skip_empty_segments: bool
    :ivar exclude_safety_notice: 为 ``True`` 时跳过 ``safetyNotice``（KB 审核免责声明不参与禁止词扫描）。
    :vartype exclude_safety_notice: bool
    """

    include_action_labels: bool = True
    segment_joiner: str = DEFAULT_SEGMENT_JOINER
    normalization_profile: NormalizationProfileLiteral = "v1_zh"
    skip_empty_segments: bool = True
    exclude_safety_notice: bool = False


DEFAULT_DRAFT_CORPUS_OPTIONS: DraftCorpusBuildOptions = DraftCorpusBuildOptions()
"""默认 Draft 语料构建配置。"""


@dataclass(frozen=True, slots=True)
class DraftTextSegment:
    """单段归一化 draft 文案。

    :ivar path: JSON 风格字段路径（如 ``summary``、``evidence[0]``）。
    :vartype path: str
    :ivar field: 顶层字段名。
    :vartype field: str
    :ivar text: 归一化后的段落文本。
    :vartype text: str
    :ivar category: 分段类别。
    :vartype category: DraftTextSegmentCategoryLiteral
    """

    path: str
    field: str
    text: str
    category: DraftTextSegmentCategoryLiteral


@dataclass(frozen=True, slots=True)
class DraftCorpusBundle:
    """Draft 合并语料与分段语料快照。

    :ivar merged: 合并后的归一化全文语料。
    :vartype merged: str
    :ivar segments: 有序分段列表。
    :vartype segments: tuple[DraftTextSegment, ...]
    :ivar options: 构建时使用的配置快照。
    :vartype options: DraftCorpusBuildOptions
    """

    merged: str
    segments: tuple[DraftTextSegment, ...]
    options: DraftCorpusBuildOptions


def iter_draft_text_segments(
    draft: DraftCopyJSON,
    *,
    options: DraftCorpusBuildOptions | None = None,
) -> Iterator[DraftTextSegment]:
    """从 ``DraftCopyJSON`` 迭代产出有序分段语料。

    纳入字段及顺序：

    1. ``title``
    2. ``summary``
    3. ``evidence[i]``
    4. ``recommendation``
    5. ``whenToSeeVet``
    6. ``safetyNotice``
    7. ``primaryAction.label``（可选）
    8. ``secondaryAction.label``（可选）

    :param draft: 步骤 ③ 文案草稿。
    :type draft: DraftCopyJSON
    :param options: 构建配置；省略时使用 ``DEFAULT_DRAFT_CORPUS_OPTIONS``。
    :type options: DraftCorpusBuildOptions | None
    :yields: 按固定顺序排列的 ``DraftTextSegment``。
    :rtype: collections.abc.Iterator[DraftTextSegment]
    """
    resolved_options = options if options is not None else DEFAULT_DRAFT_CORPUS_OPTIONS
    profile = resolved_options.normalization_profile

    yield from _yield_draft_segment(
        path="title",
        field="title",
        raw_text=draft.title,
        category=DraftTextSegmentCategory.USER_FACING.value,
        profile=profile,
        skip_empty=resolved_options.skip_empty_segments,
    )
    yield from _yield_draft_segment(
        path="summary",
        field="summary",
        raw_text=draft.summary,
        category=DraftTextSegmentCategory.USER_FACING.value,
        profile=profile,
        skip_empty=resolved_options.skip_empty_segments,
    )
    for index, evidence_item in enumerate(draft.evidence):
        yield from _yield_draft_segment(
            path=f"evidence[{index}]",
            field="evidence",
            raw_text=evidence_item,
            category=DraftTextSegmentCategory.USER_FACING.value,
            profile=profile,
            skip_empty=resolved_options.skip_empty_segments,
        )
    yield from _yield_draft_segment(
        path="recommendation",
        field="recommendation",
        raw_text=draft.recommendation,
        category=DraftTextSegmentCategory.USER_FACING.value,
        profile=profile,
        skip_empty=resolved_options.skip_empty_segments,
    )
    yield from _yield_draft_segment(
        path="whenToSeeVet",
        field="whenToSeeVet",
        raw_text=draft.when_to_see_vet,
        category=DraftTextSegmentCategory.USER_FACING.value,
        profile=profile,
        skip_empty=resolved_options.skip_empty_segments,
    )
    if not resolved_options.exclude_safety_notice:
        yield from _yield_draft_segment(
            path="safetyNotice",
            field="safetyNotice",
            raw_text=draft.safety_notice,
            category=DraftTextSegmentCategory.USER_FACING.value,
            profile=profile,
            skip_empty=resolved_options.skip_empty_segments,
        )

    if resolved_options.include_action_labels:
        yield from _yield_draft_segment(
            path="primaryAction.label",
            field="primaryAction",
            raw_text=draft.primary_action.label,
            category=DraftTextSegmentCategory.ACTION_LABEL.value,
            profile=profile,
            skip_empty=resolved_options.skip_empty_segments,
        )
        if draft.secondary_action is not None:
            yield from _yield_draft_segment(
                path="secondaryAction.label",
                field="secondaryAction",
                raw_text=draft.secondary_action.label,
                category=DraftTextSegmentCategory.ACTION_LABEL.value,
                profile=profile,
                skip_empty=resolved_options.skip_empty_segments,
            )


def build_draft_text_corpus(
    draft: DraftCopyJSON,
    *,
    options: DraftCorpusBuildOptions | None = None,
) -> str:
    """构建 draft 合并全文语料（供 forcedMentions 子串匹配）。

    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :param options: 构建配置。
    :type options: DraftCorpusBuildOptions | None
    :returns: 合并后的归一化语料字符串。
    :rtype: str
    """
    return build_draft_corpus_bundle(draft, options=options).merged


def build_draft_corpus_bundle(
    draft: DraftCopyJSON,
    *,
    options: DraftCorpusBuildOptions | None = None,
) -> DraftCorpusBundle:
    """一次构建 draft 合并语料与分段语料。

    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :param options: 构建配置。
    :type options: DraftCorpusBuildOptions | None
    :returns: 语料包快照。
    :rtype: DraftCorpusBundle
    """
    resolved_options = options if options is not None else DEFAULT_DRAFT_CORPUS_OPTIONS
    segments: tuple[DraftTextSegment, ...] = tuple(
        iter_draft_text_segments(draft, options=resolved_options)
    )
    merged = resolved_options.segment_joiner.join(segment.text for segment in segments)
    return DraftCorpusBundle(
        merged=merged,
        segments=segments,
        options=resolved_options,
    )


def collect_draft_segment_texts(
    segments: Sequence[DraftTextSegment],
) -> tuple[str, ...]:
    """从分段列表提取归一化文本序列。

    :param segments: 有序 ``DraftTextSegment`` 序列。
    :type segments: collections.abc.Sequence[DraftTextSegment]
    :returns: 各段 ``text`` 的不可变元组。
    :rtype: tuple[str, ...]
    """
    return tuple(segment.text for segment in segments)


def _yield_draft_segment(
    *,
    path: str,
    field: str,
    raw_text: str | None,
    category: DraftTextSegmentCategoryLiteral,
    profile: NormalizationProfileLiteral,
    skip_empty: bool,
) -> Iterator[DraftTextSegment]:
    """归一化单段 draft 文本并按需产出 ``DraftTextSegment``（内部辅助）。

    :param path: JSON 风格路径。
    :type path: str
    :param field: 顶层字段名。
    :type field: str
    :param raw_text: 原始段落文本。
    :type raw_text: str | None
    :param category: 分段类别。
    :type category: DraftTextSegmentCategoryLiteral
    :param profile: 归一化策略。
    :type profile: NormalizationProfileLiteral
    :param skip_empty: 归一化后为空是否跳过。
    :type skip_empty: bool
    :yields: 单个 ``DraftTextSegment``（若未因空段跳过）。
    :rtype: collections.abc.Iterator[DraftTextSegment]
    """
    normalized = normalize_text(raw_text, profile=profile)
    if skip_empty and normalized == "":
        return
    yield DraftTextSegment(
        path=path,
        field=field,
        text=normalized,
        category=category,
    )
