"""合并 ② forbiddenThemes 与 KB-FORBID 禁止 pattern。"""

from __future__ import annotations


def merge_forbidden_for_copy(
    *,
    forbidden_themes: tuple[str, ...],
    kb_forbid_patterns: tuple[str, ...],
) -> tuple[str, ...]:
    """合并禁止表述列表，去重并保持顺序。

    :param forbidden_themes: ② ``TriageCoreResult.forbidden_themes``。
    :type forbidden_themes: tuple[str, ...]
    :param kb_forbid_patterns: KB-FORBID 全局 pattern。
    :type kb_forbid_patterns: tuple[str, ...]
    :returns: 不可变合并结果。
    :rtype: tuple[str, ...]
    """
    seen: set[str] = set()
    merged: list[str] = []
    for item in (*forbidden_themes, *kb_forbid_patterns):
        if item not in seen:
            seen.add(item)
            merged.append(item)
    return tuple(merged)
