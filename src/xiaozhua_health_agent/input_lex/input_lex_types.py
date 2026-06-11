"""KB-INPUT-LEX 制品逻辑类型（口语 → 结构化 input 词表）。"""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

INPUT_LEX_SCHEMA_VERSION: str = "xiaozhua.kb_input_lex.v1"
"""``input-lex.v1.json`` 根对象 ``meta.schemaVersion`` 期望值。"""

InputLexRuleModeLiteral: TypeAlias = Literal["force", "fill_if_unknown"]
"""单条规则或默认合并模式。"""

InputLexMatchModeLiteral: TypeAlias = Literal["substring"]
"""短语匹配模式（V1 仅子串）。"""

InputLexConflictResolutionLiteral: TypeAlias = Literal[
    "risk_field_escalation_over_subjective_normal"
]
"""多条规则冲突时的默认消解策略标识。"""

InputLexPatchScalar: TypeAlias = bool | str | int | float
"""``patches`` 单字段允许写入的标量值类型。"""

InputLexMatchSourceLiteral: TypeAlias = Literal[
    "userReport.text",
    "userReport.symptoms",
    "context.notes",
]


class InputLexMeta(BaseModel):
    """``input-lex.v1.json`` 元数据区块。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(
        alias="schemaVersion",
        description="制品 schema 版本标识。",
    )
    bundle_version: str = Field(
        alias="bundleVersion",
        description="词表 bundle 语义化版本。",
    )
    description: str = Field(description="人类可读说明。")
    contract: str = Field(description="锚定的 input_schema 文档路径。")
    agent_bundle_pin: str = Field(
        alias="agentBundlePin",
        description="配套的 Agent triage-core bundle 版本。",
    )
    match_sources: tuple[InputLexMatchSourceLiteral, ...] = Field(
        alias="matchSources",
        description="接入层构建匹配语料时读取的 JSON 路径列表。",
    )
    patch_path_convention: str = Field(
        alias="patchPathConvention",
        description="patches/append 点路径命名约定说明。",
    )


class InputLexMergePolicy(BaseModel):
    """多条规则命中后的字段合并策略。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    description: str = Field(description="策略说明。")
    default_mode: InputLexRuleModeLiteral = Field(
        alias="defaultMode",
        description="规则未显式指定 mode 时的默认合并模式。",
    )
    boolean_emergency_fields: tuple[str, ...] = Field(
        alias="booleanEmergencyFields",
        description="视为紧急布尔字段的点路径列表。",
    )
    boolean_emergency_sticky: bool = Field(
        alias="booleanEmergencySticky",
        description="紧急布尔字段一旦为 true 是否不可回退。",
    )
    enum_escalation: dict[str, tuple[str, ...]] = Field(
        alias="enumEscalation",
        description="枚举字段就高不就低时的有序档位表。",
    )
    explicit_ui_wins_over_lexicon: bool = Field(
        alias="explicitUiWinsOverLexicon",
        description="UI 已明确填写的字段是否优先于词表补丁。",
    )
    append_deduplicate: bool = Field(
        alias="appendDeduplicate",
        description="append 数组字段是否去重。",
    )
    conflict_resolution: InputLexConflictResolutionLiteral = Field(
        alias="conflictResolution",
        description="风险相关字段与主观正常类规则的冲突消解策略。",
    )

    @field_validator("enum_escalation", mode="before")
    @classmethod
    def _coerce_enum_escalation(
        cls,
        value: object,
    ) -> dict[str, tuple[str, ...]]:
        """将 ``enumEscalation`` 各档列表规范化为不可变元组。

        :param value: JSON 原始值。
        :type value: object
        :returns: 字段路径 → 有序档位元组。
        :rtype: dict[str, tuple[str, ...]]
        :raises ValueError: 结构不符合预期时抛出。
        """
        if not isinstance(value, dict):
            msg = "mergePolicy.enumEscalation 必须为对象。"
            raise ValueError(msg)
        result: dict[str, tuple[str, ...]] = {}
        for key, levels in value.items():
            if not isinstance(key, str):
                msg = "enumEscalation 的键必须为字符串。"
                raise ValueError(msg)
            if not isinstance(levels, list) or not all(
                isinstance(item, str) for item in levels
            ):
                msg = f"enumEscalation[{key!r}] 必须为字符串数组。"
                raise ValueError(msg)
            result[key] = tuple(levels)
        return result


class InputLexMatchDefaults(BaseModel):
    """全局短语匹配默认参数。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: InputLexMatchModeLiteral = Field(description="匹配算法标识。")
    normalize_whitespace: bool = Field(
        alias="normalizeWhitespace",
        description="匹配前是否折叠空白。",
    )
    case_insensitive: bool = Field(
        alias="caseInsensitive",
        description="是否忽略大小写（V1 中文场景通常为 false）。",
    )
    min_phrase_length: int = Field(
        alias="minPhraseLength",
        ge=1,
        description="短语最小长度（字符数，空白折叠后）。",
    )


class InputLexEnumerations(BaseModel):
    """枚举字段合法值与标准症状标签表。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    user_report_vomiting: tuple[str, ...] = Field(
        alias="userReport.vomiting",
        description="userReport.vomiting 合法枚举。",
    )
    user_report_diarrhea: tuple[str, ...] = Field(
        alias="userReport.diarrhea",
        description="userReport.diarrhea 合法枚举。",
    )
    user_report_energy: tuple[str, ...] = Field(
        alias="userReport.energy",
        description="userReport.energy 合法枚举。",
    )
    user_report_appetite: tuple[str, ...] = Field(
        alias="userReport.appetite",
        description="userReport.appetite 合法枚举。",
    )
    user_report_drinking: tuple[str, ...] = Field(
        alias="userReport.drinking",
        description="userReport.drinking 合法枚举。",
    )
    context_recent_exercise: tuple[str, ...] = Field(
        alias="context.recentExercise",
        description="context.recentExercise 合法枚举。",
    )
    pet_chronic_conditions_tags: tuple[str, ...] = Field(
        alias="pet.chronicConditionsTags",
        description="pet.chronicConditions 推荐标签。",
    )
    canonical_symptom_labels: tuple[str, ...] = Field(
        alias="canonicalSymptomLabels",
        description="标准症状标签词表。",
    )

    @field_validator(
        "user_report_vomiting",
        "user_report_diarrhea",
        "user_report_energy",
        "user_report_appetite",
        "user_report_drinking",
        "context_recent_exercise",
        "pet_chronic_conditions_tags",
        "canonical_symptom_labels",
        mode="before",
    )
    @classmethod
    def _coerce_string_tuple(cls, value: object) -> tuple[str, ...]:
        """将 JSON 字符串数组规范化为元组。

        :param value: JSON 原始值。
        :type value: object
        :returns: 不可变字符串元组。
        :rtype: tuple[str, ...]
        :raises ValueError: 类型不符合预期时抛出。
        """
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            msg = "enumerations 字段必须为字符串数组。"
            raise ValueError(msg)
        return tuple(value)


class InputLexRuleMatch(BaseModel):
    """单条规则的短语匹配配置。"""

    model_config = ConfigDict(extra="forbid")

    phrases: tuple[str, ...] = Field(
        min_length=1,
        description="触发短语列表（子串匹配）。",
    )

    @field_validator("phrases", mode="before")
    @classmethod
    def _coerce_phrases(cls, value: object) -> tuple[str, ...]:
        """将 ``phrases`` JSON 数组规范化为元组。

        :param value: JSON 原始值。
        :type value: object
        :returns: 不可变短语元组。
        :rtype: tuple[str, ...]
        :raises ValueError: 类型或空列表时抛出。
        """
        if not isinstance(value, list) or not value:
            msg = "match.phrases 必须为非空字符串数组。"
            raise ValueError(msg)
        if not all(isinstance(item, str) and item.strip() for item in value):
            msg = "match.phrases 各项必须为非空字符串。"
            raise ValueError(msg)
        return tuple(value)


class InputLexRule(BaseModel):
    """口语映射规则（``rules[]`` 单条记录）。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(min_length=1, description="全局唯一规则标识。")
    intent: str = Field(min_length=1, description="业务意图标识。")
    priority: int = Field(description="命中评估顺序（越小越先）。")
    mode: InputLexRuleModeLiteral = Field(description="本规则 patches 合并模式。")
    maps_to_agent_rules: tuple[str, ...] = Field(
        alias="mapsToAgentRules",
        default_factory=tuple,
        description="对应的 Agent 规则 ID 追溯列表（维护追溯用，可为空）。",
    )
    species: tuple[str, ...] | None = Field(
        default=None,
        description='可选物种过滤（如 ``["dog"]``）；省略表示全物种。',
    )
    match: InputLexRuleMatch = Field(description="短语匹配配置。")
    patches: dict[str, InputLexPatchScalar] = Field(
        default_factory=dict,
        description="点路径 → 标量补丁。",
    )
    append: dict[str, tuple[str, ...]] = Field(
        default_factory=dict,
        description="点路径 → 追加字符串列表。",
    )
    notes: str | None = Field(
        default=None,
        description="维护说明或边界提示。",
    )

    @field_validator("maps_to_agent_rules", mode="before")
    @classmethod
    def _coerce_maps_to_agent_rules(cls, value: object) -> tuple[str, ...]:
        """规范化 ``mapsToAgentRules`` 为字符串元组。

        :param value: JSON 原始值。
        :type value: object
        :returns: Agent 规则 ID 元组。
        :rtype: tuple[str, ...]
        :raises ValueError: 类型不符合预期时抛出。
        """
        if value is None:
            return ()
        if not isinstance(value, list):
            msg = "mapsToAgentRules 必须为字符串数组。"
            raise ValueError(msg)
        if not all(isinstance(item, str) and item.strip() for item in value):
            msg = "mapsToAgentRules 各项必须为非空字符串。"
            raise ValueError(msg)
        return tuple(value)

    @field_validator("species", mode="before")
    @classmethod
    def _coerce_species(cls, value: object) -> tuple[str, ...] | None:
        """规范化可选 ``species`` 过滤列表。

        :param value: JSON 原始值。
        :type value: object
        :returns: 物种代码元组或 ``None``。
        :rtype: tuple[str, ...] | None
        :raises ValueError: 类型不符合预期时抛出。
        """
        if value is None:
            return None
        if not isinstance(value, list) or not value:
            msg = "species 必须为非空字符串数组。"
            raise ValueError(msg)
        if not all(isinstance(item, str) and item.strip() for item in value):
            msg = "species 各项必须为非空字符串。"
            raise ValueError(msg)
        return tuple(value)

    @field_validator("patches", mode="before")
    @classmethod
    def _coerce_patches(cls, value: object) -> dict[str, InputLexPatchScalar]:
        """规范化 ``patches`` 对象为标量字典。

        :param value: JSON 原始值。
        :type value: object
        :returns: 点路径 → 标量值。
        :rtype: dict[str, InputLexPatchScalar]
        :raises ValueError: 类型不符合预期时抛出。
        """
        if value is None:
            return {}
        if not isinstance(value, dict):
            msg = "patches 必须为对象。"
            raise ValueError(msg)
        result: dict[str, InputLexPatchScalar] = {}
        for key, raw in value.items():
            if not isinstance(key, str) or not key.strip():
                msg = "patches 的键必须为非空字符串点路径。"
                raise ValueError(msg)
            if not isinstance(raw, (bool, str, int, float)):
                msg = f"patches[{key!r}] 必须为标量（bool/str/number）。"
                raise ValueError(msg)
            result[key] = raw
        return result

    @field_validator("append", mode="before")
    @classmethod
    def _coerce_append(cls, value: object) -> dict[str, tuple[str, ...]]:
        """规范化 ``append`` 对象为字符串列表元组字典。

        :param value: JSON 原始值。
        :type value: object
        :returns: 点路径 → 字符串元组。
        :rtype: dict[str, tuple[str, ...]]
        :raises ValueError: 类型不符合预期时抛出。
        """
        if value is None:
            return {}
        if not isinstance(value, dict):
            msg = "append 必须为对象。"
            raise ValueError(msg)
        result: dict[str, tuple[str, ...]] = {}
        for key, raw_list in value.items():
            if not isinstance(key, str) or not key.strip():
                msg = "append 的键必须为非空字符串点路径。"
                raise ValueError(msg)
            if not isinstance(raw_list, list) or not all(
                isinstance(item, str) and item.strip() for item in raw_list
            ):
                msg = f"append[{key!r}] 必须为非空字符串数组。"
                raise ValueError(msg)
            result[key] = tuple(raw_list)
        return result


class InputLexBundle(BaseModel):
    """KB-INPUT-LEX 完整制品快照（加载后只读）。"""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    meta: InputLexMeta = Field(description="制品元数据。")
    merge_policy: InputLexMergePolicy = Field(
        alias="mergePolicy",
        description="字段合并策略。",
    )
    match_defaults: InputLexMatchDefaults = Field(
        alias="matchDefaults",
        description="全局匹配默认参数。",
    )
    enumerations: InputLexEnumerations = Field(description="枚举与标签表。")
    rules: tuple[InputLexRule, ...] = Field(
        min_length=1,
        description="按 priority 排序前的规则列表（加载后应已排序）。",
    )

    @field_validator("rules", mode="before")
    @classmethod
    def _coerce_rules(cls, value: object) -> tuple[InputLexRule, ...]:
        """将 ``rules`` JSON 数组规范化为规则元组。

        :param value: JSON 原始值。
        :type value: object
        :returns: 规则元组。
        :rtype: tuple[InputLexRule, ...]
        :raises ValueError: 结构不符合预期时抛出。
        """
        if not isinstance(value, list) or not value:
            msg = "rules 必须为非空数组。"
            raise ValueError(msg)
        return tuple(value)

    @model_validator(mode="after")
    def _validate_bundle_integrity(self) -> InputLexBundle:
        """校验规则 ID 唯一性并按 priority 稳定排序。

        :returns: 排序后的同一实例（通过 object.__setattr__ 更新 rules）。
        :rtype: InputLexBundle
        :raises ValueError: 规则 ID 重复时抛出。
        """
        seen: set[str] = set()
        duplicates: list[str] = []
        for rule in self.rules:
            if rule.id in seen:
                duplicates.append(rule.id)
            seen.add(rule.id)
        if duplicates:
            msg = f"rules 中存在重复 id：{sorted(set(duplicates))}"
            raise ValueError(msg)

        sorted_rules = tuple(
            sorted(self.rules, key=lambda item: (item.priority, item.id))
        )
        object.__setattr__(self, "rules", sorted_rules)
        return self

    def rules_by_priority(self) -> tuple[InputLexRule, ...]:
        """返回按 priority 升序排列的规则视图。

        :returns: 与 ``rules`` 相同（加载时已排序）。
        :rtype: tuple[InputLexRule, ...]
        """
        return self.rules

    def rule_by_id(self, rule_id: str) -> InputLexRule | None:
        """按规则 ID 查找单条规则。

        :param rule_id: 规则标识，如 ``LEX-EMG-SEIZURE-01``。
        :type rule_id: str
        :returns: 命中规则；不存在时为 ``None``。
        :rtype: InputLexRule | None
        """
        for rule in self.rules:
            if rule.id == rule_id:
                return rule
        return None

    def enumeration_for_path(self, field_path: str) -> tuple[str, ...] | None:
        """按点路径查询 ``enumerations`` 中的合法值列表。

        :param field_path: 如 ``userReport.vomiting``。
        :type field_path: str
        :returns: 合法枚举元组；非枚举字段时为 ``None``。
        :rtype: tuple[str, ...] | None
        """
        mapping: dict[str, tuple[str, ...]] = {
            "userReport.vomiting": self.enumerations.user_report_vomiting,
            "userReport.diarrhea": self.enumerations.user_report_diarrhea,
            "userReport.energy": self.enumerations.user_report_energy,
            "userReport.appetite": self.enumerations.user_report_appetite,
            "userReport.drinking": self.enumerations.user_report_drinking,
            "context.recentExercise": self.enumerations.context_recent_exercise,
            "pet.chronicConditionsTags": self.enumerations.pet_chronic_conditions_tags,
            "canonicalSymptomLabels": self.enumerations.canonical_symptom_labels,
        }
        return mapping.get(field_path)


class InputLexCorpusSegment(BaseModel):
    """单条匹配语料分段（接入层 RuleMatcher 用）。

    :param source: ``meta.matchSources`` 中的 JSON 点路径。
    :param index: 同一 ``source`` 下的序号（``userReport.text`` 固定为 0）。
    :param raw_text: 归一化前的原始文本。
    :param normalized_text: 按 ``matchDefaults`` 归一化后的文本。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: InputLexMatchSourceLiteral = Field(
        description="语料来源字段路径（camelCase）。",
    )
    index: int = Field(
        ge=0,
        description="同一 source 内的分段序号。",
    )
    raw_text: str = Field(description="原始文本片段。")
    normalized_text: str = Field(description="用于子串匹配的归一化文本。")


class InputLexMatchCorpus(BaseModel):
    """从 ``AgentInput`` 构建的短语匹配语料包。

    :param merged: 各分段 ``normalized_text`` 拼接后的合并语料（无分隔符）。
    :param segments: 有序分段列表（按 ``match_sources`` 声明顺序展开）。
    :param match_sources: 构建时使用的来源路径快照。
    :param match_defaults: 构建时使用的匹配默认参数快照。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    merged: str = Field(
        description="合并归一化语料，供全局子串匹配。",
    )
    segments: tuple[InputLexCorpusSegment, ...] = Field(
        description="分段语料列表。",
    )
    match_sources: tuple[InputLexMatchSourceLiteral, ...] = Field(
        description="语料来源路径快照。",
    )
    match_defaults: InputLexMatchDefaults = Field(
        description="匹配默认参数快照。",
    )

    def normalized_texts_for_source(
        self,
        source: InputLexMatchSourceLiteral,
    ) -> tuple[str, ...]:
        """返回指定来源下所有分段的归一化文本。

        :param source: 语料来源路径。
        :type source: InputLexMatchSourceLiteral
        :returns: 归一化文本元组（保持分段顺序）。
        :rtype: tuple[str, ...]
        """
        return tuple(
            segment.normalized_text
            for segment in self.segments
            if segment.source == source
        )

    def contains_normalized_phrase(self, phrase: str) -> bool:
        """判断合并语料是否包含归一化后的短语子串。

        调用方应传入已按同一 ``match_defaults`` 归一化的 ``phrase``，
        或使用 :func:`xiaozhua_health_agent.input_lex.normalize_match_text`
        预处理规则短语。

        :param phrase: 归一化后的候选短语。
        :type phrase: str
        :returns: 命中时为 ``True``。
        :rtype: bool
        """
        if not phrase:
            return False
        return phrase in self.merged


class InputLexPhraseMatchDetail(BaseModel):
    """单条规则短语在语料中的命中明细（RuleMatcher 产出）。

    :param raw_phrase: 词表 ``match.phrases`` 中的原始短语。
    :param normalized_phrase: 按 ``matchDefaults`` 归一化后用于子串匹配的文本。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_phrase: str = Field(
        min_length=1,
        description="规则配置的原始触发短语。",
    )
    normalized_phrase: str = Field(
        description="归一化后的触发短语（可为空串，表示归一化后不可匹配）。",
    )


class InputLexRuleHit(BaseModel):
    """单条 LEX 规则对当前语料的命中记录（RuleMatcher 产出）。

    :param rule: 命中的完整规则快照（含 ``patches`` / ``append``，供 PatchMerger 消费）。
    :param matched_phrases: 在合并语料中实际命中的短语明细（至少一条）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule: InputLexRule = Field(description="命中的 LEX 规则快照。")
    matched_phrases: tuple[InputLexPhraseMatchDetail, ...] = Field(
        min_length=1,
        description="触发该规则命中的短语列表。",
    )


class InputLexRuleMatchResult(BaseModel):
    """对一份匹配语料执行全表规则评估后的结果（RuleMatcher 产出）。

    :param hits: 按规则 ``priority`` 升序排列的命中列表（仅含至少命中一个短语的规则）。
    :param bundle_version: 评估时使用的词表 ``meta.bundleVersion``。
    :param schema_version: 评估时使用的词表 ``meta.schemaVersion``。
    :param evaluated_rule_count: 实际参与短语匹配评估的规则条数（不含物种过滤跳过）。
    :param skipped_species_filter_count: 因 ``species`` 过滤或上下文缺失而跳过的规则条数。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    hits: tuple[InputLexRuleHit, ...] = Field(
        default_factory=tuple,
        description="命中规则列表，按 priority 升序。",
    )
    bundle_version: str = Field(
        min_length=1,
        description="词表 bundleVersion 快照。",
    )
    schema_version: str = Field(
        min_length=1,
        description="词表 schemaVersion 快照。",
    )
    evaluated_rule_count: int = Field(
        ge=0,
        description="参与评估的规则条数。",
    )
    skipped_species_filter_count: int = Field(
        ge=0,
        description="因物种过滤跳过的规则条数。",
    )


InputLexPatchActionLiteral: TypeAlias = Literal["applied", "skipped"]
"""单字段补丁应用结果：已写入或已跳过。"""

InputLexPatchSkipReasonLiteral: TypeAlias = Literal[
    "explicit_ui_value",
    "fill_if_unknown_not_applicable",
    "emergency_boolean_sticky",
    "risk_escalation_over_subjective_normal",
    "energy_normal_blocked_by_lower_state",
    "no_change",
]
"""补丁被跳过时的原因标识。"""


class InputLexPatchApplicationRecord(BaseModel):
    """单条 ``patches`` 字段路径的应用记录（PatchMerger 产出）。

    :param field_path: 点路径，如 ``userReport.seizure``。
    :param action: ``applied`` 或 ``skipped``。
    :param previous_value: 合并前的字段值（缺失时为 ``None``）。
    :param new_value: 合并后的字段值；跳过时通常与 ``previous_value`` 相同。
    :param skip_reason: ``action=skipped`` 时的原因；应用成功时为 ``None``。
    :param rule_mode: 触发本条补丁的规则 ``mode``。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    field_path: str = Field(min_length=1, description="JSON 点路径（camelCase）。")
    action: InputLexPatchActionLiteral = Field(description="应用或跳过。")
    previous_value: InputLexPatchScalar | list[str] | None = Field(
        default=None,
        description="合并前的标量或数组快照。",
    )
    new_value: InputLexPatchScalar | list[str] | None = Field(
        default=None,
        description="合并后的标量或数组快照。",
    )
    skip_reason: InputLexPatchSkipReasonLiteral | None = Field(
        default=None,
        description="跳过原因；``applied`` 时为 ``None``。",
    )
    rule_mode: InputLexRuleModeLiteral = Field(
        description="产出本条记录的规则合并模式。",
    )


class InputLexAppendApplicationRecord(BaseModel):
    """单条 ``append`` 字段路径的应用记录（PatchMerger 产出）。

    :param field_path: 点路径，如 ``userReport.symptoms``。
    :param appended_values: 本次实际追加的字符串列表（去重后）。
    :param previous_values: 合并前的数组快照。
    :param new_values: 合并后的数组快照。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    field_path: str = Field(min_length=1, description="JSON 点路径（camelCase）。")
    appended_values: tuple[str, ...] = Field(
        description="本次新追加的条目（不含重复）。",
    )
    previous_values: tuple[str, ...] = Field(
        description="合并前数组内容。",
    )
    new_values: tuple[str, ...] = Field(
        description="合并后数组内容。",
    )


class InputLexRuleMergeRecord(BaseModel):
    """单条命中规则的补丁合并明细（PatchMerger 产出）。

    :param rule_id: LEX 规则标识。
    :param intent: 规则业务意图。
    :param priority: 规则优先级。
    :param rule_mode: 规则 ``mode``。
    :param patch_applications: 各 ``patches`` 字段的应用记录。
    :param append_applications: 各 ``append`` 字段的应用记录。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(min_length=1, description="LEX 规则 ID。")
    intent: str = Field(min_length=1, description="规则 intent。")
    priority: int = Field(description="规则 priority。")
    rule_mode: InputLexRuleModeLiteral = Field(description="规则 mode。")
    patch_applications: tuple[InputLexPatchApplicationRecord, ...] = Field(
        default_factory=tuple,
        description="标量补丁应用记录。",
    )
    append_applications: tuple[InputLexAppendApplicationRecord, ...] = Field(
        default_factory=tuple,
        description="数组追加应用记录。",
    )


class InputLexMergeResult(BaseModel):
    """PatchMerger 对单次入参与规则命中列表的合并结果。

    :param enriched_payload: 合并后的 input JSON 根对象（camelCase，可送 ``parse_input``）。
    :param rule_records: 按命中顺序排列的逐规则合并明细。
    :param bundle_version: 词表 ``bundleVersion`` 快照。
    :param schema_version: 词表 ``schemaVersion`` 快照。
    :param hit_count: 参与合并的命中规则条数。
    :param applied_patch_count: 实际写入的标量补丁条数。
    :param applied_append_count: 实际发生追加的数组字段条数。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enriched_payload: dict[str, Any] = Field(
        description="深拷贝后合并补丁的 input 根对象（camelCase JSON 树）。",
    )
    rule_records: tuple[InputLexRuleMergeRecord, ...] = Field(
        default_factory=tuple,
        description="逐规则合并审计记录。",
    )
    bundle_version: str = Field(
        min_length=1,
        description="词表 bundleVersion。",
    )
    schema_version: str = Field(
        min_length=1,
        description="词表 schemaVersion。",
    )
    hit_count: int = Field(
        ge=0,
        description="处理的命中规则条数。",
    )
    applied_patch_count: int = Field(
        ge=0,
        description="``action=applied`` 的补丁条数合计。",
    )
    applied_append_count: int = Field(
        ge=0,
        description="``appended_values`` 非空的 append 条数合计。",
    )


INPUT_LEX_ENRICH_AUDIT_SCHEMA_VERSION: str = "xiaozhua.input_lex.enrich_audit.v1"
""":class:`InputLexEnrichAuditRecord` 审计记录 schema 版本标识。"""

InputLexFieldChangeKindLiteral: TypeAlias = Literal["patch", "append"]
"""字段变更种类：标量补丁或数组追加。"""

InputLexEnrichAuditPersistFormatLiteral: TypeAlias = Literal["json", "jsonl"]
"""审计记录持久化格式。"""


class InputLexMatchedPhraseAudit(BaseModel):
    """规则命中短语审计快照（EnrichAudit 产出）。

    :param raw_phrase: 词表配置的原始触发短语。
    :param normalized_phrase: 归一化后用于子串匹配的短语。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_phrase: str = Field(
        serialization_alias="rawPhrase",
        min_length=1,
        description="原始触发短语。",
    )
    normalized_phrase: str = Field(
        serialization_alias="normalizedPhrase",
        description="归一化后的触发短语。",
    )


class InputLexRuleHitAudit(BaseModel):
    """单条 LEX 规则在 enrich 全流程中的审计摘要（EnrichAudit 产出）。

    聚合 :class:`InputLexRuleHit` 的匹配信息与
    :class:`InputLexRuleMergeRecord` 的合并明细，供排障与线上 replay。

    :param rule_id: LEX 规则标识。
    :param intent: 规则业务意图。
    :param priority: 规则优先级。
    :param rule_mode: 规则 ``mode``。
    :param maps_to_agent_rules: 对应的 Agent 规则 ID 追溯列表。
    :param matched_phrases: 实际触发命中的短语列表。
    :param patch_applications: 标量补丁应用记录。
    :param append_applications: 数组追加应用记录。
    :param has_effective_change: 是否存在已应用的补丁或追加。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(
        serialization_alias="ruleId",
        min_length=1,
        description="LEX 规则 ID。",
    )
    intent: str = Field(min_length=1, description="规则 intent。")
    priority: int = Field(description="规则 priority。")
    rule_mode: InputLexRuleModeLiteral = Field(
        serialization_alias="ruleMode",
        description="规则 mode。",
    )
    maps_to_agent_rules: tuple[str, ...] = Field(
        serialization_alias="mapsToAgentRules",
        default_factory=tuple,
        description="mapsToAgentRules 追溯列表。",
    )
    matched_phrases: tuple[InputLexMatchedPhraseAudit, ...] = Field(
        serialization_alias="matchedPhrases",
        default_factory=tuple,
        description="触发命中的短语审计列表。",
    )
    patch_applications: tuple[InputLexPatchApplicationRecord, ...] = Field(
        serialization_alias="patchApplications",
        default_factory=tuple,
        description="标量补丁应用记录。",
    )
    append_applications: tuple[InputLexAppendApplicationRecord, ...] = Field(
        serialization_alias="appendApplications",
        default_factory=tuple,
        description="数组追加应用记录。",
    )
    has_effective_change: bool = Field(
        serialization_alias="hasEffectiveChange",
        description="是否存在 ``applied`` 补丁或非空 ``append``。",
    )


class InputLexFieldChangeAudit(BaseModel):
    """单次 enrich 中的字段级变更审计（EnrichAudit 产出）。

    :param field_path: JSON 点路径（camelCase）。
    :param change_kind: ``patch`` 或 ``append``。
    :param source_rule_id: 产出该变更的 LEX 规则 ID。
    :param previous_value: 变更前的字段值快照。
    :param new_value: 变更后的字段值快照。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    field_path: str = Field(
        serialization_alias="fieldPath",
        min_length=1,
        description="JSON 点路径。",
    )
    change_kind: InputLexFieldChangeKindLiteral = Field(
        serialization_alias="changeKind",
        description="变更种类。",
    )
    source_rule_id: str = Field(
        serialization_alias="sourceRuleId",
        min_length=1,
        description="来源 LEX 规则 ID。",
    )
    previous_value: InputLexPatchScalar | list[str] | tuple[str, ...] | None = Field(
        serialization_alias="previousValue",
        default=None,
        description="变更前值。",
    )
    new_value: InputLexPatchScalar | list[str] | tuple[str, ...] | None = Field(
        serialization_alias="newValue",
        default=None,
        description="变更后值。",
    )


class InputLexCorpusAuditSummary(BaseModel):
    """匹配语料审计摘要（EnrichAudit 产出）。

    :param segment_count: 语料分段数量。
    :param merged_text_length: 合并语料字符长度（归一化后）。
    :param merged_text_preview: 合并语料预览（可能截断）。
    :param match_sources: 语料来源路径快照。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    segment_count: int = Field(
        serialization_alias="segmentCount",
        ge=0,
        description="``InputLexMatchCorpus.segments`` 条数。",
    )
    merged_text_length: int = Field(
        serialization_alias="mergedTextLength",
        ge=0,
        description="合并语料 ``merged`` 字符数。",
    )
    merged_text_preview: str = Field(
        serialization_alias="mergedTextPreview",
        description="合并语料预览文本。",
    )
    match_sources: tuple[InputLexMatchSourceLiteral, ...] = Field(
        serialization_alias="matchSources",
        description="语料来源路径快照。",
    )


class InputLexEnrichAuditBuildOptions(BaseModel):
    """构建 :class:`InputLexEnrichAuditRecord` 时的可选行为。

    :param include_original_payload: 是否在审计记录中嵌入原始 input 快照。
    :param include_enriched_payload: 是否在审计记录中嵌入 enriched input 快照。
    :param include_corpus_summary: 是否写入语料摘要。
    :param corpus_merged_preview_max_chars: 语料预览最大字符数。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    include_original_payload: bool = Field(
        default=False,
        description="是否嵌入原始 input JSON（默认否，避免冗余与 PII 扩散）。",
    )
    include_enriched_payload: bool = Field(
        default=False,
        description="是否嵌入 enriched input JSON（默认否）。",
    )
    include_corpus_summary: bool = Field(
        default=True,
        description="是否包含语料摘要。",
    )
    corpus_merged_preview_max_chars: int = Field(
        default=240,
        ge=0,
        description="``merged_text_preview`` 最大长度；0 表示空预览。",
    )


DEFAULT_ENRICH_AUDIT_BUILD_OPTIONS: InputLexEnrichAuditBuildOptions = (
    InputLexEnrichAuditBuildOptions()
)
"""EnrichAudit 默认构建选项。"""


class InputLexEnrichAuditPersistOptions(BaseModel):
    """审计记录持久化选项（EnrichAudit 产出写入磁盘）。

    :param path: 目标文件路径（``json`` 单文件或 ``jsonl`` 追加行）。
    :param format: ``json`` 美化单条记录，或 ``jsonl`` 每行一条。
    :param ensure_parent_dirs: 写入前是否创建父目录。
    :param json_indent: ``format=json`` 时的缩进；``None`` 表示紧凑 JSON。
    :param append_when_jsonl: ``format=jsonl`` 时是否以追加模式写入。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(
        min_length=1,
        description="持久化目标文件路径。",
    )
    format: InputLexEnrichAuditPersistFormatLiteral = Field(
        default="jsonl",
        description="持久化格式。",
    )
    ensure_parent_dirs: bool = Field(
        default=True,
        description="是否自动创建父目录。",
    )
    json_indent: int | None = Field(
        default=None,
        ge=0,
        description="JSON 美化缩进；仅 ``format=json`` 生效。",
    )
    append_when_jsonl: bool = Field(
        default=True,
        description="``jsonl`` 模式下是否追加写入。",
    )


class InputLexEnrichAuditPersistResult(BaseModel):
    """审计记录持久化结果（EnrichAudit 产出）。

    :param path: 实际写入的文件路径（绝对路径字符串）。
    :param bytes_written: 写入字节数。
    :param format: 使用的持久化格式。
    :param appended: 是否为追加写入。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1, description="写入路径。")
    bytes_written: int = Field(
        ge=0,
        description="写入字节数。",
    )
    format: InputLexEnrichAuditPersistFormatLiteral = Field(
        description="持久化格式。",
    )
    appended: bool = Field(
        description="是否以追加模式写入。",
    )


class InputLexEnrichAuditRecord(BaseModel):
    """单次 KB-INPUT-LEX enrich 操作的完整审计记录（EnrichAudit 产出）。

    聚合语料构建、规则匹配与补丁合并的可追溯摘要，**不**进入
    ``input_schema`` / ``output_schema``，供日志、JSONL 落盘与排障 replay。

    :param audit_schema_version: 审计记录结构版本。
    :param case_id: 入参 ``caseId`` 快照。
    :param input_timestamp: 入参 ``timestamp`` ISO 字符串快照。
    :param lex_bundle_version: 词表 ``bundleVersion``。
    :param lex_schema_version: 词表 ``schemaVersion``。
    :param agent_bundle_pin: 词表 ``agentBundlePin``。
    :param evaluated_rule_count: RuleMatcher 评估的规则条数。
    :param skipped_species_filter_count: 物种过滤跳过的规则条数。
    :param hit_count: 命中规则条数。
    :param applied_patch_count: 实际应用的标量补丁条数。
    :param applied_append_count: 实际发生追加的数组字段条数。
    :param rule_hits: 逐规则命中与合并审计列表（按 priority 升序）。
    :param field_changes: 扁平化的字段变更列表（按规则处理顺序）。
    :param corpus_summary: 可选语料摘要。
    :param original_payload: 可选原始 input JSON 嵌入。
    :param enriched_payload: 可选 enriched input JSON 嵌入。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_schema_version: str = Field(
        serialization_alias="auditSchemaVersion",
        default=INPUT_LEX_ENRICH_AUDIT_SCHEMA_VERSION,
        description="审计记录 schema 版本。",
    )
    case_id: str | None = Field(
        serialization_alias="caseId",
        default=None,
        description="入参 caseId。",
    )
    input_timestamp: str | None = Field(
        serialization_alias="inputTimestamp",
        default=None,
        description="入参 timestamp（ISO-8601 字符串）。",
    )
    lex_bundle_version: str = Field(
        serialization_alias="lexBundleVersion",
        min_length=1,
        description="词表 bundleVersion。",
    )
    lex_schema_version: str = Field(
        serialization_alias="lexSchemaVersion",
        min_length=1,
        description="词表 schemaVersion。",
    )
    agent_bundle_pin: str = Field(
        serialization_alias="agentBundlePin",
        min_length=1,
        description="词表 agentBundlePin。",
    )
    evaluated_rule_count: int = Field(
        serialization_alias="evaluatedRuleCount",
        ge=0,
        description="参与短语匹配评估的规则条数。",
    )
    skipped_species_filter_count: int = Field(
        serialization_alias="skippedSpeciesFilterCount",
        ge=0,
        description="因物种过滤跳过的规则条数。",
    )
    hit_count: int = Field(
        serialization_alias="hitCount",
        ge=0,
        description="命中规则条数。",
    )
    applied_patch_count: int = Field(
        serialization_alias="appliedPatchCount",
        ge=0,
        description="实际应用的标量补丁条数。",
    )
    applied_append_count: int = Field(
        serialization_alias="appliedAppendCount",
        ge=0,
        description="实际发生追加的数组字段条数。",
    )
    rule_hits: tuple[InputLexRuleHitAudit, ...] = Field(
        serialization_alias="ruleHits",
        default_factory=tuple,
        description="逐规则审计摘要。",
    )
    field_changes: tuple[InputLexFieldChangeAudit, ...] = Field(
        serialization_alias="fieldChanges",
        default_factory=tuple,
        description="字段级变更扁平列表。",
    )
    corpus_summary: InputLexCorpusAuditSummary | None = Field(
        serialization_alias="corpusSummary",
        default=None,
        description="语料构建摘要。",
    )
    original_payload: dict[str, Any] | None = Field(
        serialization_alias="originalPayload",
        default=None,
        description="可选嵌入的原始 input JSON。",
    )
    enriched_payload: dict[str, Any] | None = Field(
        serialization_alias="enrichedPayload",
        default=None,
        description="可选嵌入的 enriched input JSON。",
    )


INPUT_LEX_ENRICH_RESULT_SCHEMA_VERSION: str = "xiaozhua.input_lex.enrich_result.v1"
""":class:`InputLexEnrichResult` 编排结果 schema 版本标识。"""


class InputLexEnrichOptions(BaseModel):
    """KB-INPUT-LEX 单次 enrich 编排可选行为。

    :param build_audit: 是否构建 :class:`InputLexEnrichAuditRecord`。
    :param audit_build_options: 审计记录构建选项；省略时使用默认配置。
    :param persist_audit: 是否在 enrich 完成后异步持久化审计记录。
    :param audit_persist_options: 审计持久化目标；``persist_audit=True`` 时必填。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    build_audit: bool = Field(
        default=True,
        description="是否产出 enrich 审计记录。",
    )
    audit_build_options: InputLexEnrichAuditBuildOptions | None = Field(
        default=None,
        description="审计记录构建选项。",
    )
    persist_audit: bool = Field(
        default=False,
        description="是否将审计记录写入磁盘。",
    )
    audit_persist_options: InputLexEnrichAuditPersistOptions | None = Field(
        default=None,
        description="审计持久化选项。",
    )


DEFAULT_INPUT_LEX_ENRICH_OPTIONS: InputLexEnrichOptions = InputLexEnrichOptions()
"""enrich 编排默认选项（构建审计、不持久化）。"""


class InputLexEnrichResult(BaseModel):
    """KB-INPUT-LEX 单次 enrich 编排完整结果。

    聚合语料构建、规则匹配、补丁合并与可选审计产物，供 L1 接入层与
    L2 管道在 ``parse_input`` 之前消费。

    :param schema_version: 本结果 DTO 的 schema 版本。
    :param enriched_payload: 合并补丁后的 input JSON（camelCase，可送 ``parse_input``）。
    :param merge_result: PatchMerger 合并明细。
    :param match_result: RuleMatcher 命中列表。
    :param corpus: 短语匹配语料快照。
    :param audit: 可选 enrich 审计记录。
    :param audit_persist_result: 可选审计持久化结果。
    :param skipped: 为 ``True`` 表示未执行 enrich（调用方主动跳过）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(
        default=INPUT_LEX_ENRICH_RESULT_SCHEMA_VERSION,
        description="enrich 结果 DTO schema 版本。",
    )
    enriched_payload: dict[str, Any] = Field(
        description="enriched input 根对象（camelCase）。",
    )
    merge_result: InputLexMergeResult = Field(
        description="补丁合并结果。",
    )
    match_result: InputLexRuleMatchResult = Field(
        description="规则匹配结果。",
    )
    corpus: InputLexMatchCorpus = Field(
        description="匹配语料快照。",
    )
    audit: InputLexEnrichAuditRecord | None = Field(
        default=None,
        description="可选 enrich 审计记录。",
    )
    audit_persist_result: InputLexEnrichAuditPersistResult | None = Field(
        default=None,
        description="可选审计持久化结果。",
    )
    skipped: bool = Field(
        default=False,
        description="是否跳过 enrich（未修改入参）。",
    )
