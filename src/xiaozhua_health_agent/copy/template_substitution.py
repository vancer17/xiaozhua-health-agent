"""KB-TPL 模板占位符机械替换（``{slotId}`` → 展示文案）。

供 ③ 机械文案路径与 WP5 模板兜底共用；不读取 FactSheet，仅消费
``CopyTemplateResolved.filled_slots``。
"""

from __future__ import annotations

import re
from typing import Final

__all__ = [
    "PLACEHOLDER_PATTERN",
    "filter_outline_lines",
    "has_unresolved_placeholders",
    "substitute_template_text",
]

PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\{([a-zA-Z][a-zA-Z0-9_]*)\}",
)
"""模板占位符正则：``{petName}``、``{primaryVital}`` 等。"""


def substitute_template_text(
    template: str,
    filled_slots: dict[str, str],
    *,
    on_missing: str = "omit",
) -> str:
    """将模板字符串中的 ``{slotId}`` 替换为 ``filled_slots`` 中的展示文案。

    :param template: 含占位符的模板字符串（title / recommendation 等）。
    :type template: str
    :param filled_slots: ③-1 槽位填值结果；键为 slotId。
    :type filled_slots: dict[str, str]
    :param on_missing: 槽位缺失时的策略；``omit`` 删除占位符，``keep`` 保留原样。
    :type on_missing: str
    :returns: 替换后的字符串（首尾空白已去除）。
    :rtype: str
    :raises ValueError: ``on_missing`` 非 ``omit`` / ``keep`` 时抛出。
    """
    if on_missing not in {"omit", "keep"}:
        msg = f"on_missing 必须为 omit 或 keep，实际为 {on_missing!r}。"
        raise ValueError(msg)

    def _replacer(match: re.Match[str]) -> str:
        slot_id = match.group(1)
        value = filled_slots.get(slot_id)
        if value is None or value == "":
            if on_missing == "keep":
                return match.group(0)
            return ""
        return value

    return PLACEHOLDER_PATTERN.sub(_replacer, template).strip()


def has_unresolved_placeholders(text: str) -> bool:
    """判断文本中是否仍含未替换的 ``{slotId}`` 占位符。

    :param text: 待检查文本。
    :type text: str
    :returns: 存在 ``{...}`` 占位符时返回 ``True``。
    :rtype: bool
    """
    return PLACEHOLDER_PATTERN.search(text) is not None


def filter_outline_lines(
    outline_lines: tuple[str, ...],
    filled_slots: dict[str, str],
) -> tuple[str, ...]:
    """对 ``summaryOutline`` 逐条替换占位符并丢弃无效行。

    无效行定义：替换后为空、或仍含未解析占位符、或仅含标点/空白。

    :param outline_lines: 模板原始提纲列表。
    :type outline_lines: tuple[str, ...]
    :param filled_slots: 槽位填值字典。
    :type filled_slots: dict[str, str]
    :returns: 可用于拼接 ``summary`` 的有效行元组。
    :rtype: tuple[str, ...]
    """
    valid: list[str] = []
    for line in outline_lines:
        substituted = substitute_template_text(line, filled_slots, on_missing="omit")
        if not substituted:
            continue
        if has_unresolved_placeholders(substituted):
            continue
        if not _has_meaningful_content(substituted):
            continue
        valid.append(substituted)
    return tuple(valid)


def _has_meaningful_content(text: str) -> bool:
    """判断文本在去除空白与常见标点后是否仍有实质内容。

    :param text: 待判断文本。
    :type text: str
    :returns: 有实质内容时返回 ``True``。
    :rtype: bool
    """
    stripped = text.strip()
    if not stripped:
        return False
    reduced = re.sub(r"[\s，。、；：！？,.;:!?\-—]+", "", stripped)
    return len(reduced) > 0
