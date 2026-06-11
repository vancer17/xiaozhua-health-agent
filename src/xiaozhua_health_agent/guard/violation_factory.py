"""L5 内容守卫违规项工厂（``domain=guard``）。"""

from __future__ import annotations

from typing import cast

from xiaozhua_health_agent.eval import (
    Violation,
    ViolationCode,
    ViolationCodeLiteral,
    ViolationDomain,
    ViolationSeverity,
    ViolationSeverityLiteral,
)

__all__ = [
    "make_guard_violation",
]


def make_guard_violation(
    *,
    code: ViolationCodeLiteral,
    path: str,
    message: str,
    field: str | None = None,
    severity: ViolationSeverityLiteral = ViolationSeverity.HIGH.value,
) -> Violation:
    """构造 ``domain=guard`` 的 ``Violation`` 记录。

    :param code: 违规类型码。
    :type code: ViolationCodeLiteral
    :param path: JSON 字段路径。
    :type path: str
    :param message: 人类可读说明（中文）。
    :type message: str
    :param field: 顶层字段名；省略时从 ``path`` 推断。
    :type field: str | None
    :param severity: 严重度，默认 HIGH。
    :type severity: ViolationSeverityLiteral
    :returns: 守卫域违规记录。
    :rtype: Violation
    """
    resolved_field = field if field is not None else _top_level_field(path)
    return Violation(
        code=code,
        domain=ViolationDomain.GUARD.value,
        path=path,
        field=resolved_field,
        message=message,
        severity=severity,
    )


def _top_level_field(path: str) -> str | None:
    """从点分路径提取顶层字段名（内部辅助）。

    :param path: 如 ``evidence[0]`` 或 ``primaryAction.label``。
    :type path: str
    :returns: 顶层字段名；无法解析时为 ``None``。
    :rtype: str | None
    """
    if not path:
        return None
    head = path.split(".", maxsplit=1)[0]
    bracket_index = head.find("[")
    if bracket_index >= 0:
        head = head[:bracket_index]
    return head or None


def guard_code(name: str) -> ViolationCodeLiteral:
    """将 ``ViolationCode`` 枚举名解析为字面量（内部辅助）。

    :param name: 枚举成员名，如 ``EMERGENCY_TONE_WEAK``。
    :type name: str
    :returns: 违规码字面量。
    :rtype: ViolationCodeLiteral
    """
    return cast(ViolationCodeLiteral, getattr(ViolationCode, name).value)
