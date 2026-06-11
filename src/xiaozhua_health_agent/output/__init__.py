"""WP5 ⑤ 合并与出站输出 — 公开 API 门面。

将步骤 ② ``TriageCoreResult`` 与步骤 ③ ``DraftCopyJSON`` 合并为完整
``AgentOutput``；并提供 **merge-ready draft 契约** 预检（进入 merge 前）。

包外代码应只从本模块导入：

.. code-block:: python

    from xiaozhua_health_agent.output import (
        check_merge_ready,
        merge_agent_output,
    )

跨包引用请使用目标包的 ``__init__``（``copy``、``triage``、``schemas``、
``eval``），勿直接依赖子模块实现文件。
"""

from __future__ import annotations

from xiaozhua_health_agent.output.merge_output import (
    merge_agent_output,
    merge_agent_output_to_alias_dict,
)
from xiaozhua_health_agent.output.merge_ready import (
    assert_merge_ready,
    assert_merge_ready_async,
    check_merge_ready,
    check_merge_ready_async,
)
from xiaozhua_health_agent.output.merge_ready_types import (
    DEFAULT_MERGE_READY_OPTIONS,
    MERGE_READY_ERROR_MESSAGE,
    MERGE_READY_SCHEMA_VERSION,
    MergeReadyError,
    MergeReadyOptions,
    MergeReadyResult,
)
from xiaozhua_health_agent.output.merge_violations import (
    MERGE_SAFETY_NOTICE_MISSING_MESSAGE,
    build_merge_output_error_for_safety_notice,
    build_merge_output_error_for_validation,
    make_merge_safety_notice_missing_violation,
    violations_from_merge_output_error,
    violations_from_merge_output_error_async,
)
from xiaozhua_health_agent.output.merge_types import (
    DEFAULT_OPTIONAL_SAFETY_NOTICE,
    MERGE_OUTPUT_SCHEMA_VERSION,
    MergeOutputError,
    MergeOutputFailureKind,
)

__all__ = [
    "DEFAULT_MERGE_READY_OPTIONS",
    "DEFAULT_OPTIONAL_SAFETY_NOTICE",
    "MERGE_OUTPUT_SCHEMA_VERSION",
    "MERGE_READY_ERROR_MESSAGE",
    "MERGE_READY_SCHEMA_VERSION",
    "MERGE_SAFETY_NOTICE_MISSING_MESSAGE",
    "MergeOutputError",
    "MergeOutputFailureKind",
    "MergeReadyError",
    "MergeReadyOptions",
    "MergeReadyResult",
    "assert_merge_ready",
    "assert_merge_ready_async",
    "build_merge_output_error_for_safety_notice",
    "build_merge_output_error_for_validation",
    "check_merge_ready",
    "check_merge_ready_async",
    "make_merge_safety_notice_missing_violation",
    "merge_agent_output",
    "merge_agent_output_to_alias_dict",
    "violations_from_merge_output_error",
    "violations_from_merge_output_error_async",
]
