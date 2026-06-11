"""L5 安全与合规层 — ValidateContent 公开 API 门面（WP5 ④-B）。

包外代码应只从本模块导入：

.. code-block:: python

    from xiaozhua_health_agent.guard import (
        ContentGuardInput,
        validate_content,
        validate_content_async,
    )

跨包引用请使用各依赖包的 ``__init__``（``copy``、``parse``、``triage``、
``eval``），勿直接依赖子模块实现文件。
"""

from __future__ import annotations

from xiaozhua_health_agent.guard.content_validator import (
    CONTENT_GUARD_SCHEMA_VERSION,
    DEFAULT_CONTENT_GUARD_OPTIONS,
    build_content_guard_result,
    run_content_guard_checks,
    validate_content,
    validate_content_async,
    validate_content_with_sanitize,
    validate_content_with_sanitize_async,
)
from xiaozhua_health_agent.guard.draft_corpus import (
    DEFAULT_DRAFT_CORPUS_OPTIONS,
    DraftCorpusBuildOptions,
    DraftCorpusBundle,
    DraftTextSegment,
    build_draft_corpus_bundle,
    build_draft_text_corpus,
    iter_draft_text_segments,
)
from xiaozhua_health_agent.guard.guard_types import (
    ContentGuardInput,
    ContentGuardMode,
    ContentGuardModeLiteral,
    ContentGuardOptions,
    ContentGuardResult,
)
from xiaozhua_health_agent.guard.resources import (
    load_synonym_map_async,
    resolve_synonym_map_for_guard,
    resolve_synonym_map_for_guard_async,
)
from xiaozhua_health_agent.guard.sanitizer import sanitize_draft_for_guard

__all__ = [
    "CONTENT_GUARD_SCHEMA_VERSION",
    "DEFAULT_CONTENT_GUARD_OPTIONS",
    "DEFAULT_DRAFT_CORPUS_OPTIONS",
    "ContentGuardInput",
    "ContentGuardMode",
    "ContentGuardModeLiteral",
    "ContentGuardOptions",
    "ContentGuardResult",
    "DraftCorpusBuildOptions",
    "DraftCorpusBundle",
    "DraftTextSegment",
    "build_content_guard_result",
    "build_draft_corpus_bundle",
    "build_draft_text_corpus",
    "iter_draft_text_segments",
    "load_synonym_map_async",
    "resolve_synonym_map_for_guard",
    "resolve_synonym_map_for_guard_async",
    "run_content_guard_checks",
    "sanitize_draft_for_guard",
    "validate_content",
    "validate_content_async",
    "validate_content_with_sanitize",
    "validate_content_with_sanitize_async",
]
