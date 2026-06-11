"""管道级异常类型（WP5 阶段 1 · 机械路径）。"""

from __future__ import annotations

from xiaozhua_health_agent.pipeline.pipeline_types import (
    HealthTriagePipelineStageLiteral,
)

__all__ = [
    "HealthTriagePipelineError",
]


class HealthTriagePipelineError(Exception):
    """机械健康分诊管道在可恢复步骤之外的失败。

    用于包装不应 silent pass 的异常（如合并契约失败）。契约解析失败应通过
    ``HealthTriagePipelineResult`` 的 ``passed=False`` 与 ``violations`` 表达，
    通常不抛出本异常。

    :ivar message: 人类可读错误说明。
    :vartype message: str
    :ivar stage: 失败所在管道阶段标识。
    :vartype stage: HealthTriagePipelineStageLiteral
    """

    def __init__(
        self,
        message: str,
        *,
        stage: HealthTriagePipelineStageLiteral,
    ) -> None:
        """构造管道异常。

        :param message: 错误说明文本。
        :type message: str
        :param stage: 失败阶段（``merge`` / ``final_schema`` 等）。
        :type stage: HealthTriagePipelineStageLiteral
        """
        super().__init__(message)
        self.stage = stage
