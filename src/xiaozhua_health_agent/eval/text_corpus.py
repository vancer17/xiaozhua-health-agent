"""Agent 输出文本语料（corpus）构建（WP0 语义评测 · §3.1）。

从已通过 FULL 契约校验的 ``AgentOutput`` 抽取用户可见文案，经统一归一化后产出：

- **合并语料**（``build_text_corpus``）：供 ``mustMention`` 等全文子串匹配；
- **分段语料**（``iter_text_segments``）：供禁止词 / ``mustNotMention`` 字段级报告。

本模块不含医学判断、不做契约校验、不读取 case 或 KB 资产。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator, Sequence
from enum import StrEnum
from typing import Final, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.schemas import AgentOutput

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_SEGMENT_JOINER: Final[str] = "\n"
"""合并语料时段间默认分隔符。"""

_ZERO_WIDTH_PATTERN: Final[re.Pattern[str]] = re.compile(r"[\u200b\u200c\u200d\ufeff]")
"""需剥离的零宽字符集合（用于绕过禁止词检测的常见手段）。"""

# ---------------------------------------------------------------------------
# 枚举与 Literal
# ---------------------------------------------------------------------------


class NormalizationProfile(StrEnum):
    """文本归一化策略标识。"""

    V1_ZH = "v1_zh"
    """V1 中文为主场景：NFKC、空白折叠、零宽剥离、casefold。"""


NormalizationProfileLiteral: TypeAlias = Literal["v1_zh"]


class TextSegmentCategory(StrEnum):
    """语料分段类别，便于 Guard / 报告过滤。"""

    USER_FACING = "user_facing"
    """卡片主文案（title、summary、evidence 等）。"""

    ACTION_LABEL = "action_label"
    """行动按钮展示文案（primaryAction / secondaryAction.label）。"""

    MISSING_DATA = "missing_data"
    """缺失数据用户可读说明（默认不纳入，可配置开启）。"""


TextSegmentCategoryLiteral: TypeAlias = Literal[
    "user_facing",
    "action_label",
    "missing_data",
]

# ---------------------------------------------------------------------------
# 配置与 DTO
# ---------------------------------------------------------------------------


class CorpusBuildOptions(BaseModel):
    """语料构建运行配置。

    :param include_action_labels: 是否纳入 ``primaryAction.label`` /
        ``secondaryAction.label``。
    :param include_missing_data: 是否纳入 ``missingData[]`` 各条。
    :param segment_joiner: 合并语料时段间分隔符。
    :param normalization_profile: 单段文本归一化策略。
    :param skip_empty_segments: 归一化后为空白的段是否丢弃。
    """

    model_config = ConfigDict(extra="forbid")

    include_action_labels: bool = Field(
        default=True,
        description="是否将 primary/secondary action 的 label 纳入语料。",
    )
    include_missing_data: bool = Field(
        default=False,
        description="是否将 missingData 各条纳入语料（V1 默认否）。",
    )
    segment_joiner: str = Field(
        default=DEFAULT_SEGMENT_JOINER,
        min_length=1,
        description="合并语料时段间分隔符。",
    )
    normalization_profile: NormalizationProfileLiteral = Field(
        default=NormalizationProfile.V1_ZH.value,
        description="文本归一化策略名。",
    )
    skip_empty_segments: bool = Field(
        default=True,
        description="归一化后为空白的段是否跳过。",
    )


DEFAULT_CORPUS_BUILD_OPTIONS: Final[CorpusBuildOptions] = CorpusBuildOptions()
"""WP0 默认语料构建配置。"""


class TextSegment(BaseModel):
    """单段用户可见文案及其在 output JSON 中的定位。

    :param path: JSON 风格字段路径（camelCase），如 ``summary``、``evidence[0]``。
    :param field: 顶层字段名，便于与 ``Violation.field`` 聚合。
    :param text: 归一化后的纯文本。
    :param category: 分段类别。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(
        min_length=1,
        description="JSON 风格路径（camelCase），如 whenToSeeVet、primaryAction.label。",
    )
    field: str = Field(
        min_length=1,
        description="顶层字段名（camelCase），如 summary、primaryAction、evidence。",
    )
    text: str = Field(
        description="归一化后的段落文本；允许空串（通常会被 skip_empty_segments 丢弃）。",
    )
    category: TextSegmentCategoryLiteral = Field(
        description="分段类别：user_facing / action_label / missing_data。",
    )


class CorpusBundle(BaseModel):
    """一次语料构建的完整产物。

    :param merged: 各段按固定顺序拼接后的合并语料。
    :param segments: 有序分段列表（与合并顺序一致）。
    :param options: 构建时使用的配置快照。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    merged: str = Field(description="合并后的全文语料字符串。")
    segments: tuple[TextSegment, ...] = Field(
        description="有序分段语料；合并语料由其中各段拼接而成。",
    )
    options: CorpusBuildOptions = Field(
        description="构建本次语料时使用的配置。",
    )


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class CorpusBuildError(TypeError):
    """语料构建输入类型不合法。

    仅接受已通过 FULL 校验的 ``AgentOutput`` 实例。
    """


# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------


def normalize_text(
    text: str | None,
    *,
    profile: NormalizationProfile
    | NormalizationProfileLiteral = NormalizationProfile.V1_ZH,
) -> str:
    """对单段原始文本执行归一化。

    V1（``v1_zh``）步骤：

    1. ``None`` 视为 ``""``；
    2. Unicode NFKC；
    3. 剥离零宽字符；
    4. 连续空白折叠为单个空格并 strip；
    5. ``casefold()``（兼容中英文混排）。

    :param text: 原始文本；``None`` 按空串处理。
    :type text: str | None
    :param profile: 归一化策略；未知值将抛出 ``ValueError``。
    :type profile: NormalizationProfile | NormalizationProfileLiteral
    :returns: 归一化后的字符串（可能为空）。
    :rtype: str
    :raises ValueError: ``profile`` 不是已支持的策略。
    """
    resolved_profile = _resolve_normalization_profile(profile)
    if resolved_profile != NormalizationProfile.V1_ZH:
        msg = f"不支持的 normalization_profile：{resolved_profile!r}"
        raise ValueError(msg)

    if text is None:
        return ""

    normalized = unicodedata.normalize("NFKC", text)
    normalized = _ZERO_WIDTH_PATTERN.sub("", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.casefold()


# ---------------------------------------------------------------------------
# 分段与合并
# ---------------------------------------------------------------------------


def iter_text_segments(
    output: AgentOutput,
    *,
    options: CorpusBuildOptions | None = None,
) -> Iterator[TextSegment]:
    """从 ``AgentOutput`` 迭代产出有序分段语料。

    纳入字段及顺序（与 ``build_text_corpus`` 一致）：

    1. ``title``
    2. ``summary``
    3. ``evidence[i]``（按数组下标）
    4. ``recommendation``
    5. ``whenToSeeVet``
    6. ``safetyNotice``
    7. ``primaryAction.label``（``include_action_labels`` 时）
    8. ``secondaryAction.label``（存在且 ``include_action_labels`` 时）
    9. ``missingData[i]``（``include_missing_data`` 时）

    枚举字段（``riskLevel``、``confidence``、``scene``）与 ``route`` **不**纳入。

    :param output: 完整 Agent 结构化输出（须为 ``AgentOutput`` 实例）。
    :type output: AgentOutput
    :param options: 构建配置；省略时使用 ``DEFAULT_CORPUS_BUILD_OPTIONS``。
    :type options: CorpusBuildOptions | None
    :yields: 按固定顺序排列的 ``TextSegment``。
    :rtype: collections.abc.Iterator[TextSegment]
    :raises CorpusBuildError: ``output`` 不是 ``AgentOutput`` 实例。
    """
    _assert_agent_output(output)
    resolved_options = options if options is not None else DEFAULT_CORPUS_BUILD_OPTIONS
    profile = resolved_options.normalization_profile

    yield from _yield_segment(
        path="title",
        field="title",
        raw_text=output.title,
        category=TextSegmentCategory.USER_FACING,
        profile=profile,
        skip_empty=resolved_options.skip_empty_segments,
    )
    yield from _yield_segment(
        path="summary",
        field="summary",
        raw_text=output.summary,
        category=TextSegmentCategory.USER_FACING,
        profile=profile,
        skip_empty=resolved_options.skip_empty_segments,
    )
    for index, evidence_item in enumerate(output.evidence):
        yield from _yield_segment(
            path=f"evidence[{index}]",
            field="evidence",
            raw_text=evidence_item,
            category=TextSegmentCategory.USER_FACING,
            profile=profile,
            skip_empty=resolved_options.skip_empty_segments,
        )
    yield from _yield_segment(
        path="recommendation",
        field="recommendation",
        raw_text=output.recommendation,
        category=TextSegmentCategory.USER_FACING,
        profile=profile,
        skip_empty=resolved_options.skip_empty_segments,
    )
    yield from _yield_segment(
        path="whenToSeeVet",
        field="whenToSeeVet",
        raw_text=output.when_to_see_vet,
        category=TextSegmentCategory.USER_FACING,
        profile=profile,
        skip_empty=resolved_options.skip_empty_segments,
    )
    yield from _yield_segment(
        path="safetyNotice",
        field="safetyNotice",
        raw_text=output.safety_notice,
        category=TextSegmentCategory.USER_FACING,
        profile=profile,
        skip_empty=resolved_options.skip_empty_segments,
    )

    if resolved_options.include_action_labels:
        yield from _yield_segment(
            path="primaryAction.label",
            field="primaryAction",
            raw_text=output.primary_action.label,
            category=TextSegmentCategory.ACTION_LABEL,
            profile=profile,
            skip_empty=resolved_options.skip_empty_segments,
        )
        if output.secondary_action is not None:
            yield from _yield_segment(
                path="secondaryAction.label",
                field="secondaryAction",
                raw_text=output.secondary_action.label,
                category=TextSegmentCategory.ACTION_LABEL,
                profile=profile,
                skip_empty=resolved_options.skip_empty_segments,
            )

    if resolved_options.include_missing_data:
        for index, missing_item in enumerate(output.missing_data):
            yield from _yield_segment(
                path=f"missingData[{index}]",
                field="missingData",
                raw_text=missing_item,
                category=TextSegmentCategory.MISSING_DATA,
                profile=profile,
                skip_empty=resolved_options.skip_empty_segments,
            )


def build_text_corpus(
    output: AgentOutput,
    *,
    options: CorpusBuildOptions | None = None,
) -> str:
    """构建合并全文语料。

    内部调用 ``iter_text_segments`` 收集各段 ``text``，以
    ``options.segment_joiner`` 拼接。适用于 ``mustMention`` 等不关心字段位置的检查。

    :param output: 完整 Agent 结构化输出。
    :type output: AgentOutput
    :param options: 构建配置；省略时使用 ``DEFAULT_CORPUS_BUILD_OPTIONS``。
    :type options: CorpusBuildOptions | None
    :returns: 合并后的归一化语料字符串；无有效段时返回 ``""``。
    :rtype: str
    :raises CorpusBuildError: ``output`` 不是 ``AgentOutput`` 实例。
    """
    bundle = build_corpus_bundle(output, options=options)
    return bundle.merged


def build_corpus_bundle(
    output: AgentOutput,
    *,
    options: CorpusBuildOptions | None = None,
) -> CorpusBundle:
    """一次构建合并语料与分段语料。

    避免下游检查器重复遍历 ``AgentOutput`` 或重复归一化。

    :param output: 完整 Agent 结构化输出。
    :type output: AgentOutput
    :param options: 构建配置；省略时使用 ``DEFAULT_CORPUS_BUILD_OPTIONS``。
    :type options: CorpusBuildOptions | None
    :returns: 含 ``merged``、``segments`` 与配置快照的语料包。
    :rtype: CorpusBundle
    :raises CorpusBuildError: ``output`` 不是 ``AgentOutput`` 实例。
    """
    _assert_agent_output(output)
    resolved_options = options if options is not None else DEFAULT_CORPUS_BUILD_OPTIONS
    segments: tuple[TextSegment, ...] = tuple(
        iter_text_segments(output, options=resolved_options)
    )
    merged = resolved_options.segment_joiner.join(segment.text for segment in segments)
    return CorpusBundle(
        merged=merged,
        segments=segments,
        options=resolved_options.model_copy(deep=True),
    )


def collect_segment_texts(
    segments: Sequence[TextSegment],
) -> tuple[str, ...]:
    """从分段列表提取归一化文本序列（保持顺序）。

    :param segments: 有序 ``TextSegment`` 序列。
    :type segments: collections.abc.Sequence[TextSegment]
    :returns: 各段 ``text`` 的不可变元组。
    :rtype: tuple[str, ...]
    """
    return tuple(segment.text for segment in segments)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _resolve_normalization_profile(
    profile: NormalizationProfile | NormalizationProfileLiteral,
) -> NormalizationProfile:
    """将字符串或枚举解析为 ``NormalizationProfile``。

    :param profile: 策略标识。
    :type profile: NormalizationProfile | NormalizationProfileLiteral
    :returns: 解析后的枚举值。
    :rtype: NormalizationProfile
    :raises ValueError: 未知策略字符串。
    """
    if isinstance(profile, NormalizationProfile):
        return profile
    try:
        return NormalizationProfile(profile)
    except ValueError as exc:
        msg = f"不支持的 normalization_profile：{profile!r}"
        raise ValueError(msg) from exc


def _assert_agent_output(output: object) -> None:
    """断言输入为 ``AgentOutput``，否则抛出 ``CorpusBuildError``。

    :param output: 待检查对象。
    :type output: object
    :raises CorpusBuildError: 非 ``AgentOutput`` 实例（含 ``RiskOnlyOutput``、dict）。
    """
    if not isinstance(output, AgentOutput):
        actual_type = type(output).__qualname__
        msg = (
            f"语料构建仅接受 AgentOutput，收到 {actual_type}。"
            "请先执行 validate_output(..., mode=FULL) 并传入 parsed。"
        )
        raise CorpusBuildError(msg)


def _yield_segment(
    *,
    path: str,
    field: str,
    raw_text: str | None,
    category: TextSegmentCategory,
    profile: NormalizationProfileLiteral,
    skip_empty: bool,
) -> Iterator[TextSegment]:
    """归一化单段文本并按需产出 ``TextSegment``。

    :param path: JSON 风格路径。
    :type path: str
    :param field: 顶层字段名。
    :type field: str
    :param raw_text: 原始段落文本。
    :type raw_text: str | None
    :param category: 分段类别。
    :type category: TextSegmentCategory
    :param profile: 归一化策略。
    :type profile: NormalizationProfileLiteral
    :param skip_empty: 归一化后为空是否跳过产出。
    :type skip_empty: bool
    :yields: 单个 ``TextSegment``（若未因空段跳过）。
    :rtype: collections.abc.Iterator[TextSegment]
    """
    normalized = normalize_text(raw_text, profile=profile)
    if skip_empty and normalized == "":
        return
    yield TextSegment(
        path=path,
        field=field,
        text=normalized,
        category=category.value,
    )
