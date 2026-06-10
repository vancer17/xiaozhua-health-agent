"""全局禁止表述 pattern 真源（WP0 语义评测 / WP5 Guard 共用）。

基线列表与 ``docs/schema/xiaozhua_health_agent_output_schema.v1.json`` 的
``forbiddenOutputPatterns`` 对齐；扩展列表供 KB-FORBID 制品加载。
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Schema 基线（与 docs/schema output_schema.v1 一致）
# ---------------------------------------------------------------------------

DEFAULT_SCHEMA_FORBIDDEN_PATTERNS: Final[tuple[str, ...]] = (
    "确诊为",
    "一定没事",
    "不用看医生",
    "无需就医",
    "保证",
    "百分百",
)
"""output_schema ``forbiddenOutputPatterns`` 的 V1 基线列表（字面量子串匹配）。"""

DEFAULT_EXTENDED_FORBIDDEN_PATTERNS: Final[tuple[str, ...]] = (
    "不用担心",
    "肯定能好",
    "就是胃炎",
    "肯定是感染",
    "继续观察即可",
    "先等等",
)
"""V1 推荐的扩展禁止表述（隐性确诊 / 保证 / 紧急弱化），与 pipeline-design §6.1 对齐。"""


def merge_forbidden_patterns(
    *,
    schema_patterns: tuple[str, ...] | list[str] | None = None,
    extended_patterns: tuple[str, ...] | list[str] | None = None,
) -> tuple[str, ...]:
    """合并 schema 基线与扩展禁止 pattern，去重并保持顺序。

    :param schema_patterns: 可选 schema 基线；省略时使用 ``DEFAULT_SCHEMA_FORBIDDEN_PATTERNS``。
    :type schema_patterns: tuple[str, ...] | list[str] | None
    :param extended_patterns: 可选扩展列表；省略时使用 ``DEFAULT_EXTENDED_FORBIDDEN_PATTERNS``。
    :type extended_patterns: tuple[str, ...] | list[str] | None
    :returns: 去重后的不可变 pattern 元组。
    :rtype: tuple[str, ...]
    """
    base = (
        tuple(schema_patterns)
        if schema_patterns is not None
        else DEFAULT_SCHEMA_FORBIDDEN_PATTERNS
    )
    extra = (
        tuple(extended_patterns)
        if extended_patterns is not None
        else DEFAULT_EXTENDED_FORBIDDEN_PATTERNS
    )
    seen: set[str] = set()
    merged: list[str] = []
    for pattern in (*base, *extra):
        if pattern not in seen:
            seen.add(pattern)
            merged.append(pattern)
    return tuple(merged)
