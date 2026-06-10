"""WP2 上下文构建 — 公开 API 门面。

对应管道步骤 ② 入口的 DerivedFacts 预计算与 ``when`` 通用求值器。

包外代码应只从本模块导入：

.. code-block:: python

    from xiaozhua_health_agent.context import (
        DerivedFacts,
        EvalContext,
        compute_derived_facts,
        eval_when,
    )

子模块之间使用子模块直引，勿从本 ``__init__`` 回引，以免循环导入。
跨包引用请使用目标包的 ``__init__``（如 ``xiaozhua_health_agent.parse``）。
"""

from __future__ import annotations

from xiaozhua_health_agent.context.context_types import (
    DerivedFacts,
    EvalContext,
    FieldComparisonOperator,
    MaxSignalRiskLiteral,
    TriageRiskLiteral,
    WhenBlock,
    WhenEvalResult,
    WhenEvalTraceEntry,
)
from xiaozhua_health_agent.context.derived_facts import (
    DERIVED_FACT_JSON_NAMES,
    compute_derived_facts,
    get_derived_fact_by_json_name,
)
from xiaozhua_health_agent.context.field_resolver import (
    resolve_field_path,
    resolve_field_value,
)
from xiaozhua_health_agent.context.risk_order import (
    RISK_ORDER,
    compare_risk,
    is_upstream_comparable_risk,
    max_risk_level,
    risk_gte,
    risk_rank,
)
from xiaozhua_health_agent.context.thresholds import (
    BRACHYCEPHALIC_BREED_KEYWORDS,
    BRACHYCEPHALIC_CONDITION_TAG,
    CHRONIC_HEART_CONDITION_TAGS,
    DEFAULT_DERIVED_FACTS_THRESHOLDS,
    DEVICE_RESTING_FEVER_THRESHOLD_CAT_C,
    DEVICE_RESTING_FEVER_THRESHOLD_DOG_C,
    PUPPY_KITTEN_MAX_AGE_MONTHS,
    RESTING_TACHYCARDIA_HEART_RATE_BPM,
    RESTING_TACHYPNEA_RESPIRATORY_RATE_BPM,
    SENIOR_AGE_MONTHS_CAT,
    SENIOR_AGE_MONTHS_DOG,
    SEVERE_RESTING_RESPIRATORY_RATE_BPM,
    DerivedFactsThresholds,
    device_resting_fever_threshold_c,
    senior_age_threshold_months,
)
from xiaozhua_health_agent.context.when_evaluator import (
    WhenEvaluationError,
    build_eval_context,
    eval_when,
    eval_when_traced,
)

__all__ = [
    # --- 类型 ---
    "DerivedFacts",
    "EvalContext",
    "WhenBlock",
    "WhenEvalResult",
    "WhenEvalTraceEntry",
    "WhenEvaluationError",
    "TriageRiskLiteral",
    "MaxSignalRiskLiteral",
    "FieldComparisonOperator",
    "DerivedFactsThresholds",
    # --- 常量 ---
    "DERIVED_FACT_JSON_NAMES",
    "RISK_ORDER",
    "DEFAULT_DERIVED_FACTS_THRESHOLDS",
    "CHRONIC_HEART_CONDITION_TAGS",
    "BRACHYCEPHALIC_CONDITION_TAG",
    "BRACHYCEPHALIC_BREED_KEYWORDS",
    "DEVICE_RESTING_FEVER_THRESHOLD_DOG_C",
    "DEVICE_RESTING_FEVER_THRESHOLD_CAT_C",
    "SEVERE_RESTING_RESPIRATORY_RATE_BPM",
    "RESTING_TACHYPNEA_RESPIRATORY_RATE_BPM",
    "RESTING_TACHYCARDIA_HEART_RATE_BPM",
    "SENIOR_AGE_MONTHS_CAT",
    "SENIOR_AGE_MONTHS_DOG",
    "PUPPY_KITTEN_MAX_AGE_MONTHS",
    # --- DerivedFacts ---
    "compute_derived_facts",
    "get_derived_fact_by_json_name",
    # --- evalWhen ---
    "build_eval_context",
    "eval_when",
    "eval_when_traced",
    # --- 字段解析 ---
    "resolve_field_path",
    "resolve_field_value",
    # --- 风险序 ---
    "compare_risk",
    "risk_gte",
    "risk_rank",
    "max_risk_level",
    "is_upstream_comparable_risk",
    # --- 阈值 ---
    "device_resting_fever_threshold_c",
    "senior_age_threshold_months",
]
