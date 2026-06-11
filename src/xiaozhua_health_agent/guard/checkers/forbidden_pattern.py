"""禁止词 pattern 匹配检查器。"""

from __future__ import annotations

from collections.abc import Sequence

from xiaozhua_health_agent.copy import DraftCopyJSON, merge_forbidden_for_copy
from xiaozhua_health_agent.eval import Violation, ViolationCode, normalize_text
from xiaozhua_health_agent.guard.draft_corpus import (
    DraftCorpusBuildOptions,
    iter_draft_text_segments,
)
from xiaozhua_health_agent.guard.violation_factory import make_guard_violation

__all__ = [
    "check_forbidden_patterns",
    "resolve_forbidden_patterns",
]


def resolve_forbidden_patterns(
    *,
    forbidden_themes: Sequence[str],
    kb_forbid_patterns: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """合并 ② ``forbiddenThemes`` 与 KB-FORBID / schema 基线禁止 pattern。

    :param forbidden_themes: ``TriageCoreResult.forbiddenThemes``。
    :type forbidden_themes: collections.abc.Sequence[str]
    :param kb_forbid_patterns: 可选 KB-FORBID 制品 pattern 列表。
    :type kb_forbid_patterns: collections.abc.Sequence[str] | None
    :returns: 去重后的不可变 pattern 元组。
    :rtype: tuple[str, ...]
    """
    extra: tuple[str, ...] = ()
    if kb_forbid_patterns is not None:
        extra = tuple(kb_forbid_patterns)
    return merge_forbidden_for_copy(
        forbidden_themes=tuple(forbidden_themes),
        kb_forbid_patterns=extra,
    )


def check_forbidden_patterns(
    draft: DraftCopyJSON,
    *,
    patterns: Sequence[str],
    include_action_labels: bool = True,
) -> tuple[Violation, ...]:
    """扫描 draft 用户可见字段是否命中禁止 pattern。

    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :param patterns: 禁止表述 pattern 列表（原始文本，内部归一化后子串匹配）。
    :type patterns: collections.abc.Sequence[str]
    :param include_action_labels: 是否扫描行动 ``label`` 字段。
    :type include_action_labels: bool
    :returns: 违规列表；无命中时为空元组。
    :rtype: tuple[Violation, ...]
    """
    if len(patterns) == 0:
        return ()

    corpus_options = DraftCorpusBuildOptions(
        include_action_labels=include_action_labels,
        exclude_safety_notice=True,
    )
    normalized_patterns: list[tuple[str, str]] = []
    for pattern in patterns:
        normalized = normalize_text(pattern)
        if normalized:
            normalized_patterns.append((pattern, normalized))

    violations: list[Violation] = []
    for segment in iter_draft_text_segments(draft, options=corpus_options):
        for raw_pattern, normalized_pattern in normalized_patterns:
            index = segment.text.find(normalized_pattern)
            if index < 0:
                continue
            snippet = _extract_snippet(segment.text, index, len(normalized_pattern))
            violations.append(
                make_guard_violation(
                    code=ViolationCode.FORBIDDEN_PATTERN_HIT.value,
                    path=segment.path,
                    field=segment.field,
                    message=(
                        f"命中禁止表述「{raw_pattern}」"
                        f"（字段 {segment.path}，片段：{snippet}）。"
                    ),
                    severity="HIGH",
                ),
            )
    return tuple(violations)


def _extract_snippet(text: str, start: int, length: int, *, radius: int = 12) -> str:
    """截取命中位置附近的短片段（内部辅助）。

    :param text: 归一化后的段落全文。
    :type text: str
    :param start: 命中起始下标。
    :type start: int
    :param length: 命中长度。
    :type length: int
    :param radius: 左右扩展字符数。
    :type radius: int
    :returns: 摘要片段。
    :rtype: str
    """
    left = max(0, start - radius)
    right = min(len(text), start + length + radius)
    excerpt = text[left:right]
    if left > 0:
        excerpt = "…" + excerpt
    if right < len(text):
        excerpt = excerpt + "…"
    return excerpt
