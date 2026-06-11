"""免责声明强制执行检查器。"""

from __future__ import annotations

from xiaozhua_health_agent.copy import DraftCopyJSON
from xiaozhua_health_agent.eval import Violation, ViolationCode, normalize_text
from xiaozhua_health_agent.guard.violation_factory import make_guard_violation
from xiaozhua_health_agent.triage import TriageCoreResult

__all__ = [
    "check_safety_notice",
]


def check_safety_notice(
    draft: DraftCopyJSON,
    triage: TriageCoreResult,
    *,
    min_length: int = 8,
) -> tuple[Violation, ...]:
    """当 ② 要求免责声明时，校验 ``draft.safetyNotice`` 非空且足够长。

    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :param triage: 锁定分诊结论。
    :type triage: TriageCoreResult
    :param min_length: 最小有效长度（归一化后字符数）。
    :type min_length: int
    :returns: 违规列表；不要求或满足长度时为空。
    :rtype: tuple[Violation, ...]
    :raises ValueError: ``min_length`` 小于 1 时抛出。
    """
    if min_length < 1:
        msg = "min_length 必须 >= 1。"
        raise ValueError(msg)

    if not triage.safety_notice_required:
        return ()

    normalized = normalize_text(draft.safety_notice)
    if len(normalized) >= min_length:
        return ()

    return (
        make_guard_violation(
            code=ViolationCode.SAFETY_NOTICE_REQUIRED_MISSING.value,
            path="safetyNotice",
            field="safetyNotice",
            message=(
                f"safetyNoticeRequired 为 true，但 safetyNotice 过短或为空"
                f"（需要至少 {min_length} 个有效字符）。"
            ),
            severity="HIGH",
        ),
    )
