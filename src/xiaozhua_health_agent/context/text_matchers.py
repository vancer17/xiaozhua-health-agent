"""DerivedFacts 中文文本匹配器（WP2）。

将用户自述、情境备注与上游 signal.reason 中的短语匹配逻辑集中管理，
避免主计算函数内嵌大量字符串判断。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from xiaozhua_health_agent.context.thresholds import BRACHYCEPHALIC_BREED_KEYWORDS

# ---------------------------------------------------------------------------
# 短语表
# ---------------------------------------------------------------------------

USER_NORMAL_PHRASES: tuple[str, ...] = (
    "没事",
    "正常",
    "和平时一样",
    "挺正常",
    "看起来没事",
    "和往常一样",
)
"""``user_says_normal`` 用户主观「一切正常」短语。"""

EXERCISE_CONTEXT_NOTE_PHRASES: tuple[str, ...] = (
    "刚运动",
    "刚玩耍",
    "刚跑",
    "刚玩",
)
"""情境备注中表明刚运动/玩耍的短语。"""

EXERCISE_CONTEXT_REASON_KEYWORDS: tuple[str, ...] = (
    "运动",
    "玩耍",
    "跑",
    "玩球",
)
"""上游 ``signal.reason`` 中表明运动情境的关键词。"""

OPEN_MOUTH_BREATHING_PHRASE: str = "张口呼吸"
"""用户报告张口呼吸的匹配短语。"""


def _normalize_text(value: str) -> str:
    """裁剪并压缩空白，便于子串匹配。

    :param value: 原始文本。
    :type value: str
    :returns: 归一化后的文本。
    :rtype: str
    """
    return re.sub(r"\s+", "", value.strip())


def text_contains_any_phrase(text: str, phrases: Iterable[str]) -> bool:
    """判断文本是否包含任一短语（子串匹配）。

    :param text: 待搜索文本。
    :type text: str
    :param phrases: 候选短语序列。
    :type phrases: Iterable[str]
    :returns: 命中任一时为 ``True``。
    :rtype: bool
    """
    normalized = _normalize_text(text)
    if not normalized:
        return False
    return any(phrase in normalized for phrase in phrases)


def texts_contain_any_phrase(texts: Iterable[str], phrases: Iterable[str]) -> bool:
    """判断文本集合中是否有任一字符串命中短语表。

    :param texts: 待搜索文本序列。
    :type texts: Iterable[str]
    :param phrases: 候选短语序列。
    :type phrases: Iterable[str]
    :returns: 命中任一时为 ``True``。
    :rtype: bool
    """
    return any(text_contains_any_phrase(text, phrases) for text in texts)


def user_text_says_normal(text: str) -> bool:
    """判断用户自由文本是否表达「一切正常」。

    :param text: 用户自述原文。
    :type text: str
    :returns: 命中正常短语时为 ``True``。
    :rtype: bool
    """
    return text_contains_any_phrase(text, USER_NORMAL_PHRASES)


def notes_indicate_exercise_context(notes: Iterable[str]) -> bool:
    """判断情境备注是否表明刚运动/玩耍。

    :param notes: 情境备注列表。
    :type notes: Iterable[str]
    :returns: 命中运动备注短语时为 ``True``。
    :rtype: bool
    """
    return texts_contain_any_phrase(notes, EXERCISE_CONTEXT_NOTE_PHRASES)


def signal_reasons_indicate_exercise_context(reasons: Iterable[str]) -> bool:
    """判断上游 signal.reason 是否表明运动情境。

    :param reasons: 各 signal 的 reason 文本序列。
    :type reasons: Iterable[str]
    :returns: 命中运动关键词时为 ``True``。
    :rtype: bool
    """
    return texts_contain_any_phrase(reasons, EXERCISE_CONTEXT_REASON_KEYWORDS)


def reports_open_mouth_breathing(
    *,
    text: str,
    symptoms: Iterable[str],
) -> bool:
    """判断用户是否报告张口呼吸。

    :param text: 用户自由文本。
    :type text: str
    :param symptoms: 结构化症状关键词列表。
    :type symptoms: Iterable[str]
    :returns: text 或 symptoms 含「张口呼吸」时为 ``True``。
    :rtype: bool
    """
    if text_contains_any_phrase(text, (OPEN_MOUTH_BREATHING_PHRASE,)):
        return True
    return texts_contain_any_phrase(symptoms, (OPEN_MOUTH_BREATHING_PHRASE,))


def breed_matches_brachycephalic(breed: str | None) -> bool:
    """判断品种名是否命中短鼻参考列表（大小写不敏感）。

    :param breed: 品种字符串或 ``None``。
    :type breed: str | None
    :returns: 命中配置品种关键词时为 ``True``。
    :rtype: bool
    """
    if breed is None:
        return False
    normalized = breed.strip().lower()
    if not normalized:
        return False
    return any(keyword in normalized for keyword in BRACHYCEPHALIC_BREED_KEYWORDS)
