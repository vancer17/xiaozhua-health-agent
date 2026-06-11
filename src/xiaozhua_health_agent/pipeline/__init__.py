"""WP5 阶段 1 — 机械健康分诊管道公开 API 门面。

对应开发计划「端到端管道门面」机械路径：① 解析 → ② 分诊 → ③ WP5 文案重试协调器
（含 ④ ValidateContent）→ ⑤ 合并 → 出站 ``output_schema`` 校验。

包外代码应只从本模块导入：

.. code-block:: python

    from xiaozhua_health_agent.pipeline import (
        run_health_triage,
        run_health_triage_async,
        make_health_triage_output_provider,
    )

跨包引用请使用各依赖包的 ``__init__``（``parse``、``triage``、``copy``、
``output``、``eval``、``schemas``），勿直接依赖子模块实现文件。

子模块之间使用子模块直引，勿从本 ``__init__`` 回引，以免循环导入。
"""

from __future__ import annotations

from xiaozhua_health_agent.pipeline.batch import (
    assert_mechanical_full_output_hard_gate,
    run_mechanical_health_triage_full_output_batch,
    run_mechanical_health_triage_full_output_batch_async,
)
from xiaozhua_health_agent.pipeline.health_triage import (
    DEFAULT_HEALTH_TRIAGE_PIPELINE_OPTIONS,
    default_health_triage_pipeline_options,
    make_health_triage_output_provider,
    run_health_triage,
    run_health_triage_async,
)
from xiaozhua_health_agent.pipeline.pipeline_errors import HealthTriagePipelineError
from xiaozhua_health_agent.pipeline.retry_types import (
    DEFAULT_DRAFT_RETRY_OPTIONS,
    DRAFT_RETRY_SCHEMA_VERSION,
    DraftRetryAttemptRecord,
    DraftRetryContext,
    DraftRetryGeneratorKind,
    DraftRetryGeneratorKindLiteral,
    DraftRetryOptions,
    DraftRetryOutcome,
    RETRY_ACTION_STRENGTH,
    RetryAction,
    RetryActionLiteral,
    build_draft_retry_context,
    compare_retry_action_strength,
)
from xiaozhua_health_agent.pipeline.deterministic_repair import (
    DeterministicRepairKind,
    DeterministicRepairKindLiteral,
    DeterministicRepairResult,
    apply_deterministic_repair,
    apply_deterministic_repair_async,
    collect_repair_kinds_from_violations,
)
from xiaozhua_health_agent.pipeline.llm_draft_generation import (
    GuardRepairLlmResult,
    InitialLlmDraftResult,
    LlmDraftGenerationError,
    build_guard_repair_user_content,
    generate_guard_repair_llm_draft_async,
    generate_initial_llm_draft_async,
    resolve_qwen_client,
)
from xiaozhua_health_agent.pipeline.retry_coordinator import (
    DraftRetryCoordinatorState,
    run_draft_retry_coordinator,
    run_draft_retry_coordinator_async,
)
from xiaozhua_health_agent.pipeline.violation_classifier import (
    ClassifyViolationsResult,
    classify_violations,
    classify_violations_async,
    classify_violations_detailed,
    filter_retryable_violations,
    max_retry_action,
)
from xiaozhua_health_agent.pipeline.pipeline_types import (
    DraftGeneratorKind,
    DraftGeneratorKindLiteral,
    HealthTriagePipelineMode,
    HealthTriagePipelineModeLiteral,
    HealthTriagePipelineOptions,
    HealthTriagePipelineResult,
    HealthTriagePipelineStage,
    HealthTriagePipelineStageLiteral,
    MechanicalPipelineArtifacts,
)
from xiaozhua_health_agent.output import (
    DEFAULT_MERGE_READY_OPTIONS,
    MERGE_READY_ERROR_MESSAGE,
    MERGE_READY_SCHEMA_VERSION,
    MergeReadyError,
    MergeReadyOptions,
    MergeReadyResult,
    assert_merge_ready,
    assert_merge_ready_async,
    check_merge_ready,
    check_merge_ready_async,
)
from xiaozhua_health_agent.pipeline.merge_fallback import (
    MERGE_FALLBACK_ERROR_MESSAGE,
    MergeValidateSingleAttemptResult,
    MergeValidateWithFallbackResult,
    attempt_merge_and_validate_once,
    generate_mechanical_draft_for_merge_fallback_async,
    merge_and_validate_with_fallback_async,
    should_attempt_merge_stage_fallback,
)
from xiaozhua_health_agent.pipeline.final_schema_recovery import (
    FINAL_SCHEMA_RECOVERY_ERROR_MESSAGE,
    FinalSchemaRecoveryResult,
    recover_from_final_schema_failure_async,
    should_attempt_final_schema_recovery,
    to_merge_validate_with_fallback_result,
)
from xiaozhua_health_agent.pipeline.milestone_b_batch import (
    DEFAULT_MILESTONE_B_BATCH_CONFIG,
    DEFAULT_MUST_MENTION_SOFT_THRESHOLD,
    MILESTONE_B_SCHEMA_VERSION,
    MilestoneBBatchConfig,
    MilestoneBBatchMode,
    MilestoneBBatchModeLiteral,
    MilestoneBBatchReport,
    PipelineBatchCaseRecord,
    assert_milestone_b_hard_gate,
    assert_milestone_b_pipeline_hard_gate,
    assert_milestone_b_soft_gates,
    format_milestone_b_pipeline_failure_summary,
    format_milestone_b_record_line,
    format_milestone_b_report,
    format_milestone_b_report_summary,
    milestone_b_report_to_dict,
    run_milestone_b_batch,
    run_milestone_b_batch_async,
    write_milestone_b_json_report,
    write_milestone_b_report,
)

__all__ = [
    # --- 常量 / 类型 ---
    "DEFAULT_DRAFT_RETRY_OPTIONS",
    "DEFAULT_HEALTH_TRIAGE_PIPELINE_OPTIONS",
    "default_health_triage_pipeline_options",
    "DRAFT_RETRY_SCHEMA_VERSION",
    "DraftGeneratorKind",
    "DraftGeneratorKindLiteral",
    "DraftRetryAttemptRecord",
    "DraftRetryContext",
    "DraftRetryGeneratorKind",
    "DraftRetryGeneratorKindLiteral",
    "DraftRetryOptions",
    "DraftRetryOutcome",
    "HealthTriagePipelineMode",
    "HealthTriagePipelineModeLiteral",
    "HealthTriagePipelineOptions",
    "HealthTriagePipelineResult",
    "HealthTriagePipelineStage",
    "HealthTriagePipelineStageLiteral",
    "MechanicalPipelineArtifacts",
    "MERGE_FALLBACK_ERROR_MESSAGE",
    "MergeValidateSingleAttemptResult",
    "MergeValidateWithFallbackResult",
    "attempt_merge_and_validate_once",
    "generate_mechanical_draft_for_merge_fallback_async",
    "merge_and_validate_with_fallback_async",
    "should_attempt_merge_stage_fallback",
    "FINAL_SCHEMA_RECOVERY_ERROR_MESSAGE",
    "FinalSchemaRecoveryResult",
    "recover_from_final_schema_failure_async",
    "should_attempt_final_schema_recovery",
    "to_merge_validate_with_fallback_result",
    # --- merge-ready 契约（委托 output 包）---
    "DEFAULT_MERGE_READY_OPTIONS",
    "MERGE_READY_ERROR_MESSAGE",
    "MERGE_READY_SCHEMA_VERSION",
    "MergeReadyError",
    "MergeReadyOptions",
    "MergeReadyResult",
    "assert_merge_ready",
    "assert_merge_ready_async",
    "check_merge_ready",
    "check_merge_ready_async",
    "RETRY_ACTION_STRENGTH",
    "RetryAction",
    "RetryActionLiteral",
    "HealthTriagePipelineError",
    "build_draft_retry_context",
    "compare_retry_action_strength",
    "DraftRetryCoordinatorState",
    "run_draft_retry_coordinator",
    "run_draft_retry_coordinator_async",
    "ClassifyViolationsResult",
    "DeterministicRepairKind",
    "DeterministicRepairKindLiteral",
    "DeterministicRepairResult",
    "apply_deterministic_repair",
    "apply_deterministic_repair_async",
    "collect_repair_kinds_from_violations",
    "classify_violations",
    "classify_violations_async",
    "classify_violations_detailed",
    "filter_retryable_violations",
    "max_retry_action",
    "GuardRepairLlmResult",
    "InitialLlmDraftResult",
    "LlmDraftGenerationError",
    "build_guard_repair_user_content",
    "generate_guard_repair_llm_draft_async",
    "generate_initial_llm_draft_async",
    "resolve_qwen_client",
    # --- 门面 ---
    "run_health_triage",
    "run_health_triage_async",
    "make_health_triage_output_provider",
    # --- 批跑（WP5 里程碑 B）---
    "DEFAULT_MILESTONE_B_BATCH_CONFIG",
    "DEFAULT_MUST_MENTION_SOFT_THRESHOLD",
    "MILESTONE_B_SCHEMA_VERSION",
    "MilestoneBBatchConfig",
    "MilestoneBBatchMode",
    "MilestoneBBatchModeLiteral",
    "MilestoneBBatchReport",
    "PipelineBatchCaseRecord",
    "assert_milestone_b_hard_gate",
    "assert_milestone_b_pipeline_hard_gate",
    "assert_milestone_b_soft_gates",
    "format_milestone_b_pipeline_failure_summary",
    "format_milestone_b_record_line",
    "format_milestone_b_report",
    "format_milestone_b_report_summary",
    "milestone_b_report_to_dict",
    "run_milestone_b_batch",
    "run_milestone_b_batch_async",
    "write_milestone_b_json_report",
    "write_milestone_b_report",
    "run_mechanical_health_triage_full_output_batch",
    "run_mechanical_health_triage_full_output_batch_async",
    "assert_mechanical_full_output_hard_gate",
]
