"""WP4 ③ 文案生成 — 公开 API 门面。

当前实现步骤 **③-1 模板解析器**（``resolve_copy_template``）与 **③-2**
（``DraftCopyJSON``、``AsyncQwenClient``、``draft_parser``、``generate_draft_copy_async``）。

包外代码应只从本模块导入，避免直接依赖 ``copy`` 子模块实现文件：

.. code-block:: python

    from xiaozhua_health_agent.copy import (
        CopyTemplateResolved,
        resolve_copy_template,
        load_copy_knowledge_bundle,
    )

跨包引用请使用目标包的 ``__init__``（如 ``xiaozhua_health_agent.parse``、
``xiaozhua_health_agent.triage``、``xiaozhua_health_agent.eval``）。

子模块之间使用子模块直引，勿从本 ``__init__`` 回引，以免循环导入。
"""

from __future__ import annotations

from xiaozhua_health_agent.copy.action_mapper import (
    ActionMappingError,
    map_primary_action,
    map_secondary_action,
)
from xiaozhua_health_agent.copy.action_lock_enforcer import (
    ActionLockOptions,
    LockedActionField,
    LockedActionMismatch,
    collect_locked_action_mismatches,
    collect_locked_action_mismatches_from_draft,
    enforce_locked_actions,
    is_retryable_locked_action_mismatch,
)
from xiaozhua_health_agent.copy.copy_bundle import (
    clear_default_copy_knowledge_cache,
    load_copy_knowledge_bundle,
    load_default_copy_knowledge_bundle,
)
from xiaozhua_health_agent.copy.copy_llm_pipeline import (
    CopyLlmCaseResult,
    CopyLlmGeneratorKind,
    CopyLlmGeneratorKindLiteral,
    CopyLlmPipelineError,
    generate_draft_copy_async,
    generate_draft_copy_for_parsed_async,
)
from xiaozhua_health_agent.copy.draft_retry import (
    DraftGenerationRetryOptions,
    DraftGenerationRetryResult,
    DraftRetryFailureKind,
    DraftRetryFailureKindLiteral,
    append_draft_repair_user_message,
    build_draft_repair_user_content,
    run_draft_llm_with_retry_async,
)
from xiaozhua_health_agent.copy.draft_parser import (
    DraftParseError,
    DraftParseResult,
    DraftParseWarning,
    DraftParseWarningCode,
    DraftParseWarningCodeLiteral,
    backfill_draft_payload,
    extract_json_object_text,
    parse_draft_copy_from_model_text,
    parse_json_object_from_text,
)
from xiaozhua_health_agent.copy.draft_prompt import (
    DRAFT_COPY_JSON_FIELD_NAMES,
    build_draft_chat_completion_request,
    build_draft_prompt_user_payload,
    build_draft_system_prompt,
)
from xiaozhua_health_agent.copy.draft_locked_fields import (
    LockedDraftFields,
    build_locked_draft_fields,
)
from xiaozhua_health_agent.copy.draft_types import DraftCopyJSON
from xiaozhua_health_agent.copy.mechanical_draft import (
    MechanicalDraftOptions,
    MechanicalDraftResult,
    MechanicalDraftWarning,
    MechanicalDraftWarningCode,
    MechanicalDraftWarningCodeLiteral,
    generate_mechanical_draft,
    generate_mechanical_draft_for_parsed,
    generate_mechanical_draft_from_input,
    join_summary_outline,
)
from xiaozhua_health_agent.copy.qwen_client import (
    AsyncQwenClient,
    QwenApiError,
    QwenChatCompletionRequest,
    QwenChatCompletionResponse,
    QwenChatMessage,
    QwenChatRole,
    QwenClientError,
    QwenConfigurationError,
    QwenResponseFormat,
    QwenTimeoutError,
    QwenTokenUsage,
    create_default_qwen_client,
)
from xiaozhua_health_agent.copy.qwen_settings import (
    DEFAULT_QWEN_BASE_URL,
    DEFAULT_QWEN_MODEL,
    QwenClientSettings,
    QwenSettingsError,
    get_qwen_client_settings,
)
from xiaozhua_health_agent.copy.copy_types import (
    CopyKnowledgeBundle,
    CopyTemplateResolved,
    EvidenceStyleLiteral,
    FallbackTemplateEntry,
    KbActionBundle,
    KbForbidBundle,
    KbTplBundle,
    SlotDefinition,
    TemplateEntry,
    TemplateLookupResult,
    ToneProfile,
)
from xiaozhua_health_agent.copy.forbidden_union import merge_forbidden_for_copy
from xiaozhua_health_agent.copy.inline_rules import apply_inline_summary_rules
from xiaozhua_health_agent.copy.kb_action_loader import (
    KbActionLoadError,
    load_kb_action_bundle,
)
from xiaozhua_health_agent.copy.kb_forbid_loader import (
    KbForbidLoadError,
    load_kb_forbid_bundle,
)
from xiaozhua_health_agent.copy.kb_tpl_loader import (
    KbTplLoadError,
    load_kb_tpl_bundle,
)
from xiaozhua_health_agent.copy.safety_notice_resolver import (
    resolve_safety_notice_snippet,
)
from xiaozhua_health_agent.copy.slot_filler import fill_template_slots
from xiaozhua_health_agent.copy.template_lookup import (
    build_template_id,
    lookup_template,
)
from xiaozhua_health_agent.copy.template_resolver import resolve_copy_template
from xiaozhua_health_agent.copy.template_substitution import (
    PLACEHOLDER_PATTERN,
    filter_outline_lines,
    has_unresolved_placeholders,
    substitute_template_text,
)

__all__ = [
    # --- 异常 ---
    "ActionMappingError",
    "CopyLlmPipelineError",
    "DraftParseError",
    "KbActionLoadError",
    "KbForbidLoadError",
    "KbTplLoadError",
    "QwenApiError",
    "QwenClientError",
    "QwenConfigurationError",
    "QwenSettingsError",
    "QwenTimeoutError",
    # --- 类型 ---
    "ActionLockOptions",
    "CopyKnowledgeBundle",
    "CopyLlmCaseResult",
    "CopyLlmGeneratorKind",
    "CopyLlmGeneratorKindLiteral",
    "DraftGenerationRetryOptions",
    "DraftGenerationRetryResult",
    "DraftRetryFailureKind",
    "DraftRetryFailureKindLiteral",
    "LockedActionField",
    "LockedActionMismatch",
    "DraftCopyJSON",
    "LockedDraftFields",
    "MechanicalDraftOptions",
    "MechanicalDraftResult",
    "MechanicalDraftWarning",
    "MechanicalDraftWarningCode",
    "MechanicalDraftWarningCodeLiteral",
    "DraftParseResult",
    "DraftParseWarning",
    "DraftParseWarningCode",
    "DraftParseWarningCodeLiteral",
    "CopyTemplateResolved",
    "EvidenceStyleLiteral",
    "FallbackTemplateEntry",
    "KbActionBundle",
    "KbForbidBundle",
    "KbTplBundle",
    "SlotDefinition",
    "TemplateEntry",
    "TemplateLookupResult",
    "ToneProfile",
    "QwenChatCompletionRequest",
    "QwenChatCompletionResponse",
    "QwenChatMessage",
    "QwenChatRole",
    "QwenClientSettings",
    "QwenResponseFormat",
    "QwenTokenUsage",
    # --- 常量 ---
    "DEFAULT_QWEN_BASE_URL",
    "DEFAULT_QWEN_MODEL",
    "PLACEHOLDER_PATTERN",
    # --- 加载 ---
    "load_copy_knowledge_bundle",
    "load_default_copy_knowledge_bundle",
    "clear_default_copy_knowledge_cache",
    "load_kb_tpl_bundle",
    "load_kb_action_bundle",
    "load_kb_forbid_bundle",
    # --- ③-1 门面 ---
    "resolve_copy_template",
    "build_template_id",
    "lookup_template",
    "fill_template_slots",
    "apply_inline_summary_rules",
    "resolve_safety_notice_snippet",
    "merge_forbidden_for_copy",
    "map_primary_action",
    "map_secondary_action",
    "collect_locked_action_mismatches",
    "collect_locked_action_mismatches_from_draft",
    "enforce_locked_actions",
    "is_retryable_locked_action_mismatch",
    "substitute_template_text",
    "has_unresolved_placeholders",
    "filter_outline_lines",
    "build_locked_draft_fields",
    # --- ③ 机械文案 ---
    "generate_mechanical_draft",
    "generate_mechanical_draft_from_input",
    "generate_mechanical_draft_for_parsed",
    "join_summary_outline",
    # --- ③-2 Qwen 客户端 ---
    "AsyncQwenClient",
    "create_default_qwen_client",
    "get_qwen_client_settings",
    # --- ③-2 Prompt / 解析 / 管道 ---
    "DRAFT_COPY_JSON_FIELD_NAMES",
    "build_draft_system_prompt",
    "build_draft_prompt_user_payload",
    "build_draft_chat_completion_request",
    "extract_json_object_text",
    "parse_json_object_from_text",
    "backfill_draft_payload",
    "parse_draft_copy_from_model_text",
    "run_draft_llm_with_retry_async",
    "build_draft_repair_user_content",
    "append_draft_repair_user_message",
    "generate_draft_copy_async",
    "generate_draft_copy_for_parsed_async",
]
