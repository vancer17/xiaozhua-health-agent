"""证据真实性审查检查器。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from xiaozhua_health_agent.copy import DraftCopyJSON
from xiaozhua_health_agent.eval import Violation, ViolationCode, normalize_text
from xiaozhua_health_agent.guard.rules.evidence_policy import (
    DATA_QUALITY_NORMAL_CLAIM_PHRASES,
    UNSUPPORTED_TREND_PHRASES,
)
from xiaozhua_health_agent.guard.violation_factory import make_guard_violation
from xiaozhua_health_agent.parse import FactSheet
from xiaozhua_health_agent.triage import TriageCoreResult

__all__ = [
    "check_evidence_authenticity",
]

_NUMBER_PATTERN: re.Pattern[str] = re.compile(r"\d+(?:\.\d+)?")
"""从文案中提取阿拉伯数字的正则。"""

_DATA_QUALITY_FLAGS: frozenset[str] = frozenset(
    {
        "DATA_MISSING",
        "DATA_STALE",
    },
)
"""数据质量相关 ``primaryFlag``。"""


def check_evidence_authenticity(
    draft: DraftCopyJSON,
    triage: TriageCoreResult,
    fact_sheet: FactSheet,
) -> tuple[Violation, ...]:
    """审查 ``evidence[]`` 与关键文案是否编造事实、数值或趋势。

    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :param triage: 锁定分诊结论（含 ``evidenceBullets``）。
    :type triage: TriageCoreResult
    :param fact_sheet: 客观事实清单（含 ``fact_index``）。
    :type fact_sheet: FactSheet
    :returns: 违规列表；通过时为空元组。
    :rtype: tuple[Violation, ...]
    """
    violations: list[Violation] = []
    allowed_numbers = _collect_allowed_numbers(triage, fact_sheet)
    normalized_bullets = tuple(
        normalize_text(item) for item in triage.evidence_bullets if item.strip()
    )

    for index, evidence_line in enumerate(draft.evidence):
        path = f"evidence[{index}]"
        normalized_line = normalize_text(evidence_line)
        if not normalized_line:
            continue

        violations.extend(
            _check_unsupported_trend(path, normalized_line),
        )
        violations.extend(
            _check_evidence_numbers(
                path=path,
                normalized_line=normalized_line,
                allowed_numbers=allowed_numbers,
            ),
        )
        if normalized_bullets and not _line_aligns_with_bullets(
            normalized_line,
            normalized_bullets,
        ):
            violations.append(
                make_guard_violation(
                    code=ViolationCode.EVIDENCE_HALLUCINATION.value,
                    path=path,
                    field="evidence",
                    message=(
                        f"evidence 条目与 ② evidenceBullets 无法对齐，"
                        f"可能存在编造或过度改写：「{evidence_line}」。"
                    ),
                    severity="HIGH",
                ),
            )

    if _requires_data_quality_guard(triage, fact_sheet):
        violations.extend(
            _check_data_quality_normal_claims(draft),
        )

    return tuple(violations)


def _collect_allowed_numbers(
    triage: TriageCoreResult,
    fact_sheet: FactSheet,
) -> frozenset[str]:
    """收集允许出现在 evidence 中的数字字符串集合（内部辅助）。

    :param triage: 分诊结论。
    :type triage: TriageCoreResult
    :param fact_sheet: 事实清单。
    :type fact_sheet: FactSheet
    :returns: 归一化数字字符串集合（不含前导零变体合并）。
    :rtype: frozenset[str]
    """
    sources: list[str] = list(triage.evidence_bullets)
    sources.append(fact_sheet.user_report.text)

    for value in fact_sheet.fact_index.values():
        sources.extend(_stringify_fact_value(value))

    numbers: set[str] = set()
    for source in sources:
        normalized = normalize_text(source)
        for match in _NUMBER_PATTERN.finditer(normalized):
            numbers.add(match.group(0))
    return frozenset(numbers)


def _stringify_fact_value(value: Any) -> list[str]:
    """将 fact_index 中的值转为可扫描字符串列表（内部辅助）。

    :param value: 索引中的原始值。
    :type value: Any
    :returns: 字符串表示列表。
    :rtype: list[str]
    """
    if value is None:
        return []
    if isinstance(value, bool):
        return [str(value).lower()]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        results: list[str] = []
        for item in value:
            results.extend(_stringify_fact_value(item))
        return results
    return [str(value)]


def _check_unsupported_trend(
    path: str,
    normalized_line: str,
) -> tuple[Violation, ...]:
    """检测 evidence 是否含未支持的趋势表述（内部辅助）。

    :param path: 字段路径。
    :type path: str
    :param normalized_line: 归一化后的 evidence 行。
    :type normalized_line: str
    :returns: 违规元组。
    :rtype: tuple[Violation, ...]
    """
    for phrase in UNSUPPORTED_TREND_PHRASES:
        normalized_phrase = normalize_text(phrase)
        if normalized_phrase and normalized_phrase in normalized_line:
            return (
                make_guard_violation(
                    code=ViolationCode.EVIDENCE_HALLUCINATION.value,
                    path=path,
                    field="evidence",
                    message=(f"evidence 不得声称输入未提供的趋势；命中「{phrase}」。"),
                    severity="HIGH",
                ),
            )
    return ()


def _check_evidence_numbers(
    *,
    path: str,
    normalized_line: str,
    allowed_numbers: frozenset[str],
) -> tuple[Violation, ...]:
    """检测 evidence 是否含不允许的具体数字（内部辅助）。

    :param path: 字段路径。
    :type path: str
    :param normalized_line: 归一化 evidence 行。
    :type normalized_line: str
    :param allowed_numbers: 允许数字集合。
    :type allowed_numbers: frozenset[str]
    :returns: 违规元组。
    :rtype: tuple[Violation, ...]
    """
    violations: list[Violation] = []
    for match in _NUMBER_PATTERN.finditer(normalized_line):
        number = match.group(0)
        if number not in allowed_numbers:
            violations.append(
                make_guard_violation(
                    code=ViolationCode.EVIDENCE_HALLUCINATION.value,
                    path=path,
                    field="evidence",
                    message=(
                        f"evidence 出现输入中不存在的具体数值「{number}」，"
                        "不得编造监测数据。"
                    ),
                    severity="HIGH",
                ),
            )
    return tuple(violations)


def _line_aligns_with_bullets(
    normalized_line: str,
    normalized_bullets: tuple[str, ...],
) -> bool:
    """判断 evidence 行是否与某条 bullet 语义对齐（内部辅助）。

    允许轻度改写：归一化后相等、互为子串、或 Jaccard 字符重叠率 ≥ 0.55。

    :param normalized_line: 归一化 evidence 行。
    :type normalized_line: str
    :param normalized_bullets: 归一化 bullets。
    :type normalized_bullets: tuple[str, ...]
    :returns: 可对齐时为 ``True``。
    :rtype: bool
    """
    for bullet in normalized_bullets:
        if not bullet:
            continue
        if normalized_line == bullet:
            return True
        if normalized_line in bullet or bullet in normalized_line:
            return True
        if _char_overlap_ratio(normalized_line, bullet) >= 0.55:
            return True
    return False


def _char_overlap_ratio(left: str, right: str) -> float:
    """计算两字符串字符集合重叠率（内部辅助）。

    :param left: 左字符串。
    :type left: str
    :param right: 右字符串。
    :type right: str
    :returns: 重叠率，范围 [0, 1]。
    :rtype: float
    """
    if not left or not right:
        return 0.0
    left_chars = set(left)
    right_chars = set(right)
    union = left_chars | right_chars
    if not union:
        return 0.0
    return len(left_chars & right_chars) / len(union)


def _requires_data_quality_guard(
    triage: TriageCoreResult,
    fact_sheet: FactSheet,
) -> bool:
    """是否启用数据质量场景「禁止声称正常」审查（内部辅助）。

    :param triage: 分诊结论。
    :type triage: TriageCoreResult
    :param fact_sheet: 事实清单。
    :type fact_sheet: FactSheet
    :returns: 需要审查时为 ``True``。
    :rtype: bool
    """
    if triage.primary_flag in _DATA_QUALITY_FLAGS:
        return True
    data_quality = fact_sheet.device.data_quality
    return data_quality in ("missing", "stale")


def _check_data_quality_normal_claims(
    draft: DraftCopyJSON,
) -> tuple[Violation, ...]:
    """数据缺失/过期场景检测「当前正常」类表述（内部辅助）。

    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :returns: 违规元组。
    :rtype: tuple[Violation, ...]
    """
    fields: tuple[tuple[str, str], ...] = (
        ("summary", draft.summary),
        ("recommendation", draft.recommendation),
    )
    violations: list[Violation] = []
    for path, raw_text in fields:
        normalized = normalize_text(raw_text)
        for phrase in DATA_QUALITY_NORMAL_CLAIM_PHRASES:
            normalized_phrase = normalize_text(phrase)
            if normalized_phrase and normalized_phrase in normalized:
                violations.append(
                    make_guard_violation(
                        code=ViolationCode.EVIDENCE_HALLUCINATION.value,
                        path=path,
                        field=path,
                        message=(
                            f"数据不足或过期时不得暗示当前健康正常；"
                            f"字段 {path} 命中「{phrase}」。"
                        ),
                        severity="HIGH",
                    ),
                )
    for index, evidence_line in enumerate(draft.evidence):
        normalized = normalize_text(evidence_line)
        for phrase in DATA_QUALITY_NORMAL_CLAIM_PHRASES:
            normalized_phrase = normalize_text(phrase)
            if normalized_phrase and normalized_phrase in normalized:
                violations.append(
                    make_guard_violation(
                        code=ViolationCode.EVIDENCE_HALLUCINATION.value,
                        path=f"evidence[{index}]",
                        field="evidence",
                        message=(
                            "数据不足或过期时 evidence 不得暗示当前健康正常；"
                            f"命中「{phrase}」。"
                        ),
                        severity="HIGH",
                    ),
                )
    return tuple(violations)
