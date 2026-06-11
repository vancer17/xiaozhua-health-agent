"""WP5 merge-ready draft 契约 — 类型、常量与异常定义。

``merge-ready`` 表示 ``DraftCopyJSON`` 在调用 ``merge_agent_output`` 之前必须满足的
不变量集合（结构 + 与 ``TriageCoreResult`` 对齐的合并前语义约束）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from xiaozhua_health_agent.copy import DraftCopyJSON
from xiaozhua_health_agent.eval import Violation

__all__ = [
    "DEFAULT_MERGE_READY_OPTIONS",
    "MERGE_READY_ERROR_MESSAGE",
    "MERGE_READY_SCHEMA_VERSION",
    "MergeReadyError",
    "MergeReadyOptions",
    "MergeReadyResult",
]

MERGE_READY_SCHEMA_VERSION: Final[str] = "xiaozhua.health_agent.merge_ready_draft.v1"
"""merge-ready 契约版本标识（与 ``DraftCopyJSON`` / ``TriageCoreResult`` 联合校验）。"""

MERGE_READY_ERROR_MESSAGE: Final[str] = (
    "DraftCopyJSON 未满足 merge-ready 契约，无法进入 merge_agent_output。"
)
"""``assert_merge_ready`` 与 Merge 阶段预检失败时的默认说明。"""


@dataclass(frozen=True, slots=True)
class MergeReadyOptions:
    """merge-ready 契约校验运行配置。

    :ivar min_safety_notice_length: 当 ``TriageCoreResult.safetyNoticeRequired`` 为
        ``True`` 时，``draft.safetyNotice`` 归一化后的最小有效字符数。
    :vartype min_safety_notice_length: int
    :ivar require_non_empty_evidence: 为 ``True`` 时要求 ``evidence`` 至少包含一条
        非空字符串；默认 ``False``（允许空列表，与 ``DraftCopyJSON`` 一致）。
    :vartype require_non_empty_evidence: bool
    """

    min_safety_notice_length: int = 8
    require_non_empty_evidence: bool = False


DEFAULT_MERGE_READY_OPTIONS: Final[MergeReadyOptions] = MergeReadyOptions()
"""默认 merge-ready 校验配置（与 L5 ``ContentGuardOptions`` 免责声明长度对齐）。"""


@dataclass(frozen=True, slots=True)
class MergeReadyResult:
    """单次 merge-ready 契约校验结果。

    :ivar passed: 是否满足进入 ``merge_agent_output`` 的前置条件。
    :vartype passed: bool
    :ivar violations: 未满足契约时的违规列表；通过时为空。
    :vartype violations: tuple[Violation, ...]
    :ivar draft: 结构校验通过后的强类型 ``DraftCopyJSON``；否则为 ``None``。
    :vartype draft: DraftCopyJSON | None
    :ivar schema_version: 本次对照的 merge-ready 契约版本。
    :vartype schema_version: str
    """

    passed: bool
    violations: tuple[Violation, ...]
    draft: DraftCopyJSON | None
    schema_version: str = MERGE_READY_SCHEMA_VERSION


class MergeReadyError(Exception):
    """``DraftCopyJSON`` 未满足 merge-ready 契约时抛出。

    :ivar message: 人类可读错误说明。
    :vartype message: str
    :ivar violations: 结构化违规列表。
    :vartype violations: tuple[Violation, ...]
    """

    def __init__(
        self,
        message: str,
        *,
        violations: tuple[Violation, ...] = (),
    ) -> None:
        """构造 merge-ready 契约异常。

        :param message: 错误说明；省略细节时可使用 ``MERGE_READY_ERROR_MESSAGE``。
        :type message: str
        :param violations: 触发失败的违规项列表。
        :type violations: tuple[Violation, ...]
        """
        super().__init__(message)
        self.message = message
        self.violations = violations
