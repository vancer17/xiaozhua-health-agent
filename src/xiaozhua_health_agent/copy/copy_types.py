"""WP4 ③-1 模板解析中间类型定义。

定义 KB-TPL / KB-ACTION / KB-FORBID 加载模型与 ``CopyTemplateResolved`` 输出结构。
对应 ``kb-tpl-template-spec.md`` §八、§十三 与 ``pipeline-design.md`` §5.2。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.schemas import ActionItem

EvidenceStyleLiteral = Literal["bullets_as_is", "bullets_light_polish"]
"""证据列表在 ③-2 中的润色强度。"""

SlotSourceLiteral = Literal["factSheet", "triageCore", "derived"]
"""槽位取值来源。"""

SlotMissingBehaviorLiteral = Literal[
    "omit",
    "usePlaceholder",
    "useGeneric",
    "usePhrase",
]
"""槽位缺失时的填充策略。"""

FallbackLookupKeyLiteral = Literal[
    "normal",
    "watch",
    "warning",
    "emergency",
    "DEFAULT",
]
"""``fallback-by-risk`` 查找键。"""


class SlotDefinition(BaseModel):
    """``slots.v1.json`` 中单条槽位注册定义。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source: SlotSourceLiteral = Field(
        description="取值来源：FactSheet / TriageCore / 派生。"
    )
    path: str | None = Field(
        default=None,
        description="点分路径；``derived`` 槽位无路径。",
    )
    required: bool = Field(default=False, description="是否必填（DATA_* 等场景）。")
    missing_behavior: SlotMissingBehaviorLiteral = Field(
        alias="missingBehavior",
        description="缺失时的填充策略。",
    )
    placeholder: str | None = Field(
        default=None,
        description="``usePlaceholder`` 时使用的占位文案。",
    )
    generic: str | None = Field(
        default=None,
        description="``useGeneric`` 时使用的通用文案。",
    )
    phrase: str | None = Field(
        default=None,
        description="``usePhrase`` 时使用的短语。",
    )
    enum_map: dict[str, str] = Field(
        default_factory=dict,
        alias="enumMap",
        description="枚举值到展示文案的映射。",
    )
    format: str | None = Field(
        default=None,
        description="数值格式化模板，如 ``{value}°C``；``relativeTime`` 为特殊值。",
    )
    slot_type: str | None = Field(
        default=None,
        alias="type",
        description="特殊槽位类型：``notesMatch`` / ``array`` 等。",
    )
    match_patterns: list[str] = Field(
        default_factory=list,
        alias="matchPatterns",
        description="``notesMatch`` 类型的匹配子串列表。",
    )
    condition_labels: dict[str, str] = Field(
        default_factory=dict,
        alias="conditionLabels",
        description="``array`` 类型慢病代码到可读标签的映射。",
    )
    join_separator: str = Field(
        default="、",
        alias="joinSeparator",
        description="``array`` 类型拼接分隔符。",
    )
    max_length: int | None = Field(
        default=None,
        alias="maxLength",
        description="字符串截断上限。",
    )
    description: str | None = Field(
        default=None,
        description="人类可读说明（如 ``primaryVital`` 派生规则）。",
    )


class TemplateCopyBlock(BaseModel):
    """单条模板的 copy 文案骨架。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    title_pattern: str = Field(alias="titlePattern")
    summary_outline: list[str] = Field(alias="summaryOutline")
    recommendation_template: str = Field(alias="recommendationTemplate")
    when_to_see_vet_template: str = Field(alias="whenToSeeVetTemplate")
    evidence_instruction: str | None = Field(
        default=None,
        alias="evidenceInstruction",
    )


class TemplateGuidanceBlock(BaseModel):
    """单条模板的 LLM 语气与边界指令。"""

    model_config = ConfigDict(extra="forbid")

    llm_instructions: str = Field(alias="llmInstructions")


class TemplateBindingBlock(BaseModel):
    """单条模板的槽位绑定与派生优先级。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    slots: list[str] = Field(description="引用的 slotId 列表。")
    summary_slot_priority: dict[str, list[str]] = Field(
        default_factory=dict,
        alias="summarySlotPriority",
        description="派生槽优先级，如 ``primaryVital: [temperature, heartRate]``。",
    )


class TemplateMetaBlock(BaseModel):
    """单条模板的元数据。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    template_id: str = Field(alias="templateId")
    risk_level: str = Field(alias="riskLevel")
    primary_flag: str = Field(alias="primaryFlag")
    bundle_version: str = Field(alias="bundleVersion")
    name: str
    case_ids: list[str] = Field(alias="caseIds")
    tone_profile_id: str = Field(alias="toneProfileId")
    evidence_style: EvidenceStyleLiteral = Field(alias="evidenceStyle")
    notes: str | None = None


class TemplateEntry(BaseModel):
    """``templates.v1.json`` 中单条完整模板记录。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    meta: TemplateMetaBlock
    copy_block: TemplateCopyBlock = Field(alias="copy")
    guidance: TemplateGuidanceBlock
    binding: TemplateBindingBlock


class FallbackTemplateEntry(BaseModel):
    """``fallback-by-risk.v1.json`` 中单条兜底模板。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    title_pattern: str = Field(alias="titlePattern")
    summary_outline: list[str] = Field(alias="summaryOutline")
    recommendation_template: str = Field(alias="recommendationTemplate")
    when_to_see_vet_template: str = Field(alias="whenToSeeVetTemplate")
    tone_profile_id: str = Field(alias="toneProfileId")
    evidence_style: EvidenceStyleLiteral = Field(alias="evidenceStyle")


class ToneProfile(BaseModel):
    """``tone-by-risk.v1.json`` 中单条语气 profile。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    applicable_risk: list[str] = Field(alias="applicableRisk")
    tone: str
    preferred_phrases: list[str] = Field(alias="preferredPhrases")
    avoid_phrases: list[str] = Field(alias="avoidPhrases")
    applicable_primary_flags: list[str] = Field(
        default_factory=list,
        alias="applicablePrimaryFlags",
    )


class SafetyNoticeRule(BaseModel):
    """``safety-notices.v1.json`` 中单条 snippet 选用规则。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    when: dict[str, Any]
    snippet_id: str = Field(alias="snippetId")


class KbTplBundle(BaseModel):
    """KB-TPL 配置制品聚合（templates / slots / fallback / tone / safety）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_version: str = Field(
        description="制品 bundleVersion（取自 templates meta）。"
    )
    templates: dict[str, TemplateEntry]
    slots: dict[str, SlotDefinition]
    fallbacks: dict[str, FallbackTemplateEntry]
    tone_profiles: dict[str, ToneProfile]
    safety_snippets: dict[str, str]
    safety_resolve_rules: tuple[SafetyNoticeRule, ...]


class ActionMappingEntry(BaseModel):
    """KB-ACTION 中单条行动映射。"""

    model_config = ConfigDict(extra="forbid")

    label: str
    route: str | None = None


class KbActionBundle(BaseModel):
    """KB-ACTION 制品聚合。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_version: str
    actions: dict[str, ActionMappingEntry]
    secondary_actions: dict[str, ActionMappingEntry]
    secondary_by_primary_flag: dict[str, str]


class KbForbidBundle(BaseModel):
    """KB-FORBID 制品聚合。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_version: str
    forbidden_patterns: tuple[str, ...]


class CopyKnowledgeBundle(BaseModel):
    """③-1 解析所需的全部知识资产聚合。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kb_tpl: KbTplBundle
    kb_action: KbActionBundle
    kb_forbid: KbForbidBundle


class TemplateLookupResult(BaseModel):
    """模板查表结果（含兜底来源信息）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_template_id: str
    resolved_lookup_key: str
    used_fallback: bool
    title_pattern: str
    summary_outline: tuple[str, ...]
    recommendation_template: str
    when_to_see_vet_template: str
    tone_profile_id: str
    evidence_style: EvidenceStyleLiteral
    binding_slots: tuple[str, ...]
    summary_slot_priority: dict[str, list[str]]
    llm_instructions: str
    risk_level_mismatch: bool = Field(
        description="主模板 riskLevel 与 triage.finalRiskLevel 不一致时为 True。",
    )


class CopyTemplateResolved(BaseModel):
    """步骤 ③-1 产出的已解析文案模板包（供 ③-2 / ④ / ⑤ 消费）。

    不含 ``riskLevel`` / ``confidence``；医学裁决字段由 ``TriageCoreResult`` 在 WP5 合并。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str = Field(description="请求的主键 ``{risk}.{primaryFlag}``。")
    resolved_lookup_key: str = Field(
        description="实际命中的模板或 fallback 键。",
    )
    used_fallback: bool = Field(description="是否走了 fallback-by-risk。")
    risk_level_mismatch: bool = Field(
        description="主模板存在但 riskLevel 与 triage 不一致。",
    )
    tone_profile_id: str
    evidence_style: EvidenceStyleLiteral
    title_pattern: str
    summary_outline: tuple[str, ...]
    recommendation_template: str
    when_to_see_vet_template: str
    filled_slots: dict[str, str] = Field(
        description="机械填槽结果；仅含非 omit 的 slotId。",
    )
    evidence_bullets: tuple[str, ...] = Field(
        description="来自 ② EvidenceBuilder，③ 不得增删事实点。",
    )
    required_mentions: tuple[str, ...] = Field(
        description="② ``forcedMentions``，③ Prompt 与 ④ Checker 使用。",
    )
    forbidden: tuple[str, ...] = Field(
        description="② ``forbiddenThemes`` ∪ KB-FORBID patterns。",
    )
    llm_instructions: str
    safety_notice_snippet: str = Field(
        description="已选定的免责声明片段；``safetyNoticeRequired=false`` 时为空串。",
    )
    primary_action_hint: str = Field(description="② 锁定的行动意图枚举。")
    primary_action_draft: ActionItem = Field(
        description="KB-ACTION 映射后的主行动草稿。",
    )
    secondary_action_draft: ActionItem | None = Field(
        default=None,
        description="按 primaryFlag 映射的次要行动草稿（可选）。",
    )
    tone_profile: ToneProfile | None = Field(
        default=None,
        description="语气 profile 详情，供 ③-2 Prompt 引用。",
    )
    evidence_instruction: str | None = Field(
        default=None,
        description="模板 copy 中的 evidence 改写说明（可选）。",
    )
