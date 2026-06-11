"""HTTP JSON 序列化辅助（WP6 阶段 2）。"""

from __future__ import annotations

from typing import Any

from xiaozhua_health_agent.schemas import AgentOutput

__all__ = [
    "serialize_agent_output",
]


def serialize_agent_output(output: AgentOutput) -> dict[str, Any]:
    """将 ``AgentOutput`` 序列化为 camelCase 键的 JSON 兼容字典。

    与 App mock adapter 及 ``output_schema.v1`` 出站约定一致。

    :param output: 管道产出的完整结构化分诊结果。
    :type output: AgentOutput
    :returns: 可 JSON 编码的顶层字典。
    :rtype: dict[str, Any]
    """
    return output.model_dump(by_alias=True, mode="json")
