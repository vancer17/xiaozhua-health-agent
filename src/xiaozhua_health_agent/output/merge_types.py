"""WP5 ⑤ MergeOutput 异常、常量与失败类型定义。"""

from __future__ import annotations

from typing import Final, Literal, TypeAlias

from xiaozhua_health_agent.eval import Violation

__all__ = [
    "DEFAULT_OPTIONAL_SAFETY_NOTICE",
    "MERGE_OUTPUT_SCHEMA_VERSION",
    "MergeOutputError",
    "MergeOutputFailureKind",
    "MergeOutputFailureKindLiteral",
]

#: 当 ``TriageCoreResult.safetyNoticeRequired`` 为 ``False`` 且文案草稿
#: ``safetyNotice`` 为空时，用于满足 ``AgentOutput.safetyNotice`` 最小长度约束的
#: 通用免责声明（不替代 ② 的 ``safetyNoticeRequired`` 语义）。
DEFAULT_OPTIONAL_SAFETY_NOTICE: Final[str] = (
    "本内容仅供参考，不能替代兽医面诊与专业诊断。"
)

MERGE_OUTPUT_SCHEMA_VERSION: Final[str] = "xiaozhua.health_agent.output.v1"
"""``merge_agent_output`` 合并后对照的出站契约版本（与 ``eval.OUTPUT_SCHEMA_VERSION`` 对齐）。"""

MergeOutputFailureKindLiteral: TypeAlias = Literal[
    "safety_notice_required_missing",
    "agent_output_validation_failed",
    "unknown",
]
"""``MergeOutputError`` 失败原因分类。"""


class MergeOutputFailureKind:
    """``MergeOutputError`` 失败原因常量（便于批跑报告与 HTTP 错误映射）。"""

    SAFETY_NOTICE_REQUIRED_MISSING: MergeOutputFailureKindLiteral = (
        "safety_notice_required_missing"
    )
    AGENT_OUTPUT_VALIDATION_FAILED: MergeOutputFailureKindLiteral = (
        "agent_output_validation_failed"
    )
    UNKNOWN: MergeOutputFailureKindLiteral = "unknown"


class MergeOutputError(Exception):
    """``DraftCopyJSON`` 与 ``TriageCoreResult`` 合并为 ``AgentOutput`` 失败。

    :ivar message: 人类可读错误说明。
    :vartype message: str
    :ivar violations: 结构化违规列表（供管道 ``stage=merge`` 与 HTTP 错误体消费）。
    :vartype violations: tuple[Violation, ...]
    :ivar failure_kind: 失败原因分类。
    :vartype failure_kind: MergeOutputFailureKindLiteral
    """

    def __init__(
        self,
        message: str,
        *,
        violations: tuple[Violation, ...] = (),
        failure_kind: MergeOutputFailureKindLiteral = MergeOutputFailureKind.UNKNOWN,
    ) -> None:
        """构造合并错误。

        :param message: 错误说明。
        :type message: str
        :param violations: 与失败原因对应的结构化违规项；默认空元组。
        :type violations: tuple[Violation, ...]
        :param failure_kind: 失败原因分类；默认 ``unknown``。
        :type failure_kind: MergeOutputFailureKindLiteral
        """
        super().__init__(message)
        self.message = message
        self.violations = violations
        self.failure_kind = failure_kind
