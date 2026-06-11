"""L5 ValidateContent 输入、配置与结果 DTO（WP5）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from xiaozhua_health_agent.copy import (
    CopyKnowledgeBundle,
    CopyTemplateResolved,
    DraftCopyJSON,
)
from xiaozhua_health_agent.eval import SynonymMap, Violation
from xiaozhua_health_agent.parse import FactSheet
from xiaozhua_health_agent.triage import TriageCoreResult

__all__ = [
    "CONTENT_GUARD_SCHEMA_VERSION",
    "ContentGuardInput",
    "ContentGuardMode",
    "ContentGuardModeLiteral",
    "ContentGuardOptions",
    "ContentGuardResult",
    "DEFAULT_CONTENT_GUARD_OPTIONS",
]

CONTENT_GUARD_SCHEMA_VERSION: str = "xiaozhua.health_agent.content_guard.v1"
"""ValidateContent 逻辑版本标识（写入校验结果 ``schema_version``）。"""

ContentGuardModeLiteral: TypeAlias = Literal["strict", "report_only", "sanitize"]
"""管道级内容守卫失败处理模式。"""


class ContentGuardMode:
    """内容守卫失败处理模式常量。"""

    STRICT: ContentGuardModeLiteral = "strict"
    REPORT_ONLY: ContentGuardModeLiteral = "report_only"
    SANITIZE: ContentGuardModeLiteral = "sanitize"


@dataclass(frozen=True, slots=True)
class ContentGuardOptions:
    """ValidateContent 运行配置。

    :ivar enforce_forced_mentions: 为 ``True`` 时 ``FORCED_MENTION_MISSING``（MED）
        亦拉低 ``passed``；默认仅记入 ``warnings``。
    :vartype enforce_forced_mentions: bool
    :ivar min_safety_notice_length: ``safetyNoticeRequired=true`` 时免责声明最小有效长度。
    :vartype min_safety_notice_length: int
    :ivar include_action_labels_in_forbidden_scan: 禁止词扫描是否包含行动 ``label``。
    :vartype include_action_labels_in_forbidden_scan: bool
    :ivar skip_risk_text_consistency: 是否跳过风险—文案一致性检查。
    :vartype skip_risk_text_consistency: bool
    :ivar lock_action_label: 行动锁定是否同时校验 ``label``。
    :vartype lock_action_label: bool
    :ivar load_default_synonym_map: 未注入 ``synonym_map`` 时是否异步加载默认 KB-SYN。
    :vartype load_default_synonym_map: bool
    """

    enforce_forced_mentions: bool = False
    min_safety_notice_length: int = 8
    include_action_labels_in_forbidden_scan: bool = True
    skip_risk_text_consistency: bool = False
    lock_action_label: bool = True
    load_default_synonym_map: bool = True


DEFAULT_CONTENT_GUARD_OPTIONS: ContentGuardOptions = ContentGuardOptions()
"""ValidateContent 默认配置（机械路径推荐）。"""


@dataclass(frozen=True, slots=True)
class ContentGuardInput:
    """单次 ValidateContent 审查上下文。

    :ivar draft: 待审查文案草稿（步骤 ③ 产出）。
    :vartype draft: DraftCopyJSON
    :ivar triage: 锁定的分诊结论与文案约束（步骤 ②）。
    :vartype triage: TriageCoreResult
    :ivar fact_sheet: 客观事实清单（步骤 ①）。
    :vartype fact_sheet: FactSheet
    :ivar resolved: 模板解析包（步骤 ③-1），供行动锁定比对。
    :vartype resolved: CopyTemplateResolved
    :ivar copy_bundle: 可选知识资产包（KB-FORBID / KB-TPL 等）。
    :vartype copy_bundle: CopyKnowledgeBundle | None
    :ivar synonym_map: 可选同义词表；省略时由异步入口按配置加载。
    :vartype synonym_map: SynonymMap | None
    """

    draft: DraftCopyJSON
    triage: TriageCoreResult
    fact_sheet: FactSheet
    resolved: CopyTemplateResolved
    copy_bundle: CopyKnowledgeBundle | None = None
    synonym_map: SynonymMap | None = None


@dataclass(frozen=True, slots=True)
class ContentGuardResult:
    """ValidateContent 聚合结果。

    :ivar passed: 是否通过内容守卫（由 ``hard_passed`` 与 ``enforce_forced_mentions`` 决定）。
    :vartype passed: bool
    :ivar hard_passed: 无 HIGH 严重度 ``domain=guard`` 违规。
    :vartype hard_passed: bool
    :ivar soft_passed: ``hard_passed`` 且无 MED 违规（含 forcedMentions）。
    :vartype soft_passed: bool
    :ivar violations: 全部守卫违规（含 HIGH 与 MED）。
    :vartype violations: tuple[Violation, ...]
    :ivar warnings: MED 违规且未拉低 ``passed`` 时的副本（便于报告）。
    :vartype warnings: tuple[Violation, ...]
    :ivar draft: 审查后的文案草稿（可能经 ``sanitize`` 修补）。
    :vartype draft: DraftCopyJSON
    :ivar sanitized: 是否对 ``draft`` 做过确定性修补。
    :vartype sanitized: bool
    """

    passed: bool
    hard_passed: bool
    soft_passed: bool
    violations: tuple[Violation, ...]
    warnings: tuple[Violation, ...]
    draft: DraftCopyJSON
    sanitized: bool = False
