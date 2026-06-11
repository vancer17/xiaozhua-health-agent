"""WP5 ⑤ 合并与出站输出 — 公开 API 门面。

将步骤 ② ``TriageCoreResult`` 与步骤 ③ ``DraftCopyJSON`` 合并为完整
``AgentOutput``。包外代码应只从本模块导入：

.. code-block:: python

    from xiaozhua_health_agent.output import merge_agent_output

跨包引用请使用目标包的 ``__init__``（``copy``、``triage``、``schemas``、
``eval``），勿直接依赖子模块实现文件。
"""

from __future__ import annotations

from xiaozhua_health_agent.output.merge_output import (
    merge_agent_output,
    merge_agent_output_to_alias_dict,
)
from xiaozhua_health_agent.output.merge_types import (
    DEFAULT_OPTIONAL_SAFETY_NOTICE,
    MergeOutputError,
)

__all__ = [
    "DEFAULT_OPTIONAL_SAFETY_NOTICE",
    "MergeOutputError",
    "merge_agent_output",
    "merge_agent_output_to_alias_dict",
]
