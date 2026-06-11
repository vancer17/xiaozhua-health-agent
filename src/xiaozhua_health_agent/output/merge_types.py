"""WP5 ⑤ MergeOutput 异常与常量定义。"""

from __future__ import annotations

__all__ = [
    "DEFAULT_OPTIONAL_SAFETY_NOTICE",
    "MergeOutputError",
]

#: 当 ``TriageCoreResult.safetyNoticeRequired`` 为 ``False`` 且文案草稿
#: ``safetyNotice`` 为空时，用于满足 ``AgentOutput.safetyNotice`` 最小长度约束的
#: 通用免责声明（不替代 ② 的 ``safetyNoticeRequired`` 语义）。
DEFAULT_OPTIONAL_SAFETY_NOTICE: str = "本内容仅供参考，不能替代兽医面诊与专业诊断。"


class MergeOutputError(Exception):
    """``DraftCopyJSON`` 与 ``TriageCoreResult`` 合并为 ``AgentOutput`` 失败。

    :ivar message: 人类可读错误说明。
    :vartype message: str
    """

    def __init__(self, message: str) -> None:
        """构造合并错误。

        :param message: 错误说明。
        :type message: str
        """
        super().__init__(message)
