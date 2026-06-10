"""WP1 输入解析 — 公开 API 门面。

对应管道步骤 ①（Parse & Fact Extract），将 App / case JSON 转为客观 ``FactSheet``。

包外代码应只从本模块导入，避免直接依赖 ``parse`` 子模块实现文件：

.. code-block:: python

    from xiaozhua_health_agent.parse import (
        FactSheet,
        parse_input,
        ParseResult,
    )

契约结构校验请使用 ``xiaozhua_health_agent.eval.validate_input``；
本包在 ``parse_input`` 内编排校验 + 归一化 + 事实提取。

子模块之间使用子模块直引，勿从本 ``__init__`` 回引，以免循环导入。
"""

from __future__ import annotations

from xiaozhua_health_agent.parse.fact_extractor import (
    build_fact_index,
    extract_fact_sheet,
    fact_index_contains,
    get_fact_value,
)
from xiaozhua_health_agent.parse.normalizer import (
    normalize_agent_input,
    timestamp_to_epoch_ms,
)
from xiaozhua_health_agent.parse.parse_types import (
    DEFAULT_NORMALIZATION_PROFILE,
    DEFAULT_NORMALIZATION_PROFILE_ID,
    FACT_INDEX_PREFIX,
    ContextFacts,
    DeviceFacts,
    FactSheet,
    IdentityFacts,
    NormalizationProfile,
    ProfileFacts,
    UpstreamFacts,
    UserReportFacts,
    VitalsFacts,
)
from xiaozhua_health_agent.parse.parser import (
    CaseParseRecord,
    ParseResult,
    assert_all_parse_passed,
    parse_agent_input,
    parse_all_case_inputs,
    parse_input,
)

__all__ = [
    # --- 常量 ---
    "DEFAULT_NORMALIZATION_PROFILE",
    "DEFAULT_NORMALIZATION_PROFILE_ID",
    "FACT_INDEX_PREFIX",
    # --- FactSheet 分组 ---
    "FactSheet",
    "IdentityFacts",
    "ProfileFacts",
    "DeviceFacts",
    "VitalsFacts",
    "UpstreamFacts",
    "UserReportFacts",
    "ContextFacts",
    "NormalizationProfile",
    # --- 解析结果 ---
    "ParseResult",
    "CaseParseRecord",
    # --- 门面 ---
    "parse_input",
    "parse_agent_input",
    "parse_all_case_inputs",
    "assert_all_parse_passed",
    # --- 子步骤（可单独测试）---
    "normalize_agent_input",
    "extract_fact_sheet",
    "build_fact_index",
    "get_fact_value",
    "fact_index_contains",
    "timestamp_to_epoch_ms",
]
