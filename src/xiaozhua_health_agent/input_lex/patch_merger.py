"""KB-INPUT-LEX 字段补丁合并器（PatchMerger）。

将 :class:`~xiaozhua_health_agent.input_lex.InputLexRuleMatchResult` 中的命中规则
按 ``mergePolicy`` 合并进 ``AgentInput`` JSON 树，产出 enriched payload 与审计
记录。本模块 **不** 执行短语匹配或医学裁决。
"""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Mapping
from typing import Any, Final

from xiaozhua_health_agent.input_lex.input_lex_types import (
    InputLexAppendApplicationRecord,
    InputLexBundle,
    InputLexMergePolicy,
    InputLexMergeResult,
    InputLexPatchApplicationRecord,
    InputLexPatchScalar,
    InputLexPatchSkipReasonLiteral,
    InputLexRuleHit,
    InputLexRuleMatchResult,
    InputLexRuleMergeRecord,
    InputLexRuleModeLiteral,
)
from xiaozhua_health_agent.schemas import AgentInput

__all__ = [
    "PatchMerger",
    "merge_input_lex_patches",
    "merge_input_lex_patches_async",
]

_SUBJECTIVE_NORMAL_INTENT: Final[str] = "subjective_normal"
"""主观「没事」类规则 intent 标识（冲突消解用）。"""

_BOOLEAN_FIELD_PATHS: Final[frozenset[str]] = frozenset(
    {
        "userReport.coughing",
        "userReport.breathingDifficulty",
        "userReport.pain",
        "userReport.limping",
        "userReport.seizure",
        "userReport.trauma",
    },
)
"""``userReport`` 布尔字段点路径集合。"""

_ENUM_FIELD_PATHS: Final[frozenset[str]] = frozenset(
    {
        "userReport.vomiting",
        "userReport.diarrhea",
        "userReport.energy",
        "userReport.appetite",
        "userReport.drinking",
        "context.recentExercise",
    },
)
"""带 ``unknown`` 档位的枚举字段点路径集合。"""


class PatchMerger:
    """KB-INPUT-LEX 字段补丁合并器。

    按命中顺序（``priority`` 升序）将各规则的 ``patches`` / ``append`` 合并进
    入参 JSON 深拷贝，遵守词表 ``mergePolicy``（``fill_if_unknown``、``force``、
    枚举就高、紧急布尔 sticky、主观正常冲突消解）。纯 CPU 逻辑；异步方法通过
    线程池执行，避免大批量规则合并阻塞事件循环。
    """

    def __init__(self, bundle: InputLexBundle) -> None:
        """绑定词表快照与合并策略。

        :param bundle: 已加载的 KB-INPUT-LEX 制品。
        :type bundle: InputLexBundle
        """
        self._bundle: InputLexBundle = bundle
        self._merge_policy: InputLexMergePolicy = bundle.merge_policy

    @property
    def bundle(self) -> InputLexBundle:
        """返回构造时绑定的词表快照。

        :returns: 不可变词表制品。
        :rtype: InputLexBundle
        """
        return self._bundle

    @property
    def merge_policy(self) -> InputLexMergePolicy:
        """返回生效的合并策略。

        :returns: ``mergePolicy`` 快照。
        :rtype: InputLexMergePolicy
        """
        return self._merge_policy

    def merge(
        self,
        agent_input: AgentInput | Mapping[str, Any],
        match_result: InputLexRuleMatchResult,
    ) -> InputLexMergeResult:
        """将规则命中列表合并进入参 JSON（同步）。

        :param agent_input: 原始分诊入参（强类型或 camelCase JSON 映射）。
        :type agent_input: AgentInput | collections.abc.Mapping[str, Any]
        :param match_result: :class:`~xiaozhua_health_agent.input_lex.RuleMatcher`
            产出的命中列表。
        :type match_result: InputLexRuleMatchResult
        :returns: enriched payload 与逐规则审计记录。
        :rtype: InputLexMergeResult
        """
        payload = _coerce_mutable_payload(agent_input)
        return _merge_hits_into_payload(
            payload,
            match_result=match_result,
            merge_policy=self._merge_policy,
            bundle_version=self._bundle.meta.bundle_version,
            schema_version=self._bundle.meta.schema_version,
        )

    async def merge_async(
        self,
        agent_input: AgentInput | Mapping[str, Any],
        match_result: InputLexRuleMatchResult,
    ) -> InputLexMergeResult:
        """将规则命中列表合并进入参 JSON（异步）。

        合并逻辑在线程池中运行，适用于与 IO 密集的加载/匹配串联时避免阻塞
        事件循环。

        :param agent_input: 原始分诊入参。
        :type agent_input: AgentInput | collections.abc.Mapping[str, Any]
        :param match_result: 规则匹配结果。
        :type match_result: InputLexRuleMatchResult
        :returns: enriched payload 与逐规则审计记录。
        :rtype: InputLexMergeResult
        """

        def _merge_sync() -> InputLexMergeResult:
            """在线程池中执行同步合并（闭包）。

            :returns: 合并结果。
            :rtype: InputLexMergeResult
            """
            return self.merge(agent_input, match_result)

        return await asyncio.to_thread(_merge_sync)


def merge_input_lex_patches(
    bundle: InputLexBundle,
    agent_input: AgentInput | Mapping[str, Any],
    match_result: InputLexRuleMatchResult,
) -> InputLexMergeResult:
    """便捷函数：同步合并 LEX 规则补丁。

    :param bundle: KB-INPUT-LEX 词表快照。
    :type bundle: InputLexBundle
    :param agent_input: 原始分诊入参。
    :type agent_input: AgentInput | collections.abc.Mapping[str, Any]
    :param match_result: 规则匹配结果。
    :type match_result: InputLexRuleMatchResult
    :returns: 合并结果。
    :rtype: InputLexMergeResult
    """
    return PatchMerger(bundle).merge(agent_input, match_result)


async def merge_input_lex_patches_async(
    bundle: InputLexBundle,
    agent_input: AgentInput | Mapping[str, Any],
    match_result: InputLexRuleMatchResult,
) -> InputLexMergeResult:
    """便捷函数：异步合并 LEX 规则补丁。

    :param bundle: KB-INPUT-LEX 词表快照。
    :type bundle: InputLexBundle
    :param agent_input: 原始分诊入参。
    :type agent_input: AgentInput | collections.abc.Mapping[str, Any]
    :param match_result: 规则匹配结果。
    :type match_result: InputLexRuleMatchResult
    :returns: 合并结果。
    :rtype: InputLexMergeResult
    """
    return await PatchMerger(bundle).merge_async(agent_input, match_result)


def _coerce_mutable_payload(
    agent_input: AgentInput | Mapping[str, Any],
) -> dict[str, Any]:
    """将入参规范化为可变的 camelCase JSON 根字典深拷贝。

    :param agent_input: 强类型入参或 JSON 映射。
    :type agent_input: AgentInput | collections.abc.Mapping[str, Any]
    :returns: 深拷贝后的可变字典。
    :rtype: dict[str, Any]
    """
    if isinstance(agent_input, AgentInput):
        dumped = agent_input.model_dump(by_alias=True, mode="json")
        return copy.deepcopy(dumped)
    return copy.deepcopy(dict(agent_input))


def _merge_hits_into_payload(
    payload: dict[str, Any],
    *,
    match_result: InputLexRuleMatchResult,
    merge_policy: InputLexMergePolicy,
    bundle_version: str,
    schema_version: str,
) -> InputLexMergeResult:
    """按命中顺序将规则补丁合并进 payload（内部辅助）。

    :param payload: 可变入参 JSON 根对象（将被原地修改）。
    :type payload: dict[str, Any]
    :param match_result: 规则匹配结果。
    :type match_result: InputLexRuleMatchResult
    :param merge_policy: 合并策略。
    :type merge_policy: InputLexMergePolicy
    :param bundle_version: 词表 bundle 版本。
    :type bundle_version: str
    :param schema_version: 词表 schema 版本。
    :type schema_version: str
    :returns: 合并结果快照。
    :rtype: InputLexMergeResult
    """
    rule_records: list[InputLexRuleMergeRecord] = []
    applied_patch_count = 0
    applied_append_count = 0

    for hit in match_result.hits:
        record = _merge_single_rule_hit(
            payload,
            hit,
            merge_policy=merge_policy,
        )
        rule_records.append(record)
        applied_patch_count += sum(
            1 for item in record.patch_applications if item.action == "applied"
        )
        applied_append_count += sum(
            1 for item in record.append_applications if len(item.appended_values) > 0
        )

    return InputLexMergeResult(
        enriched_payload=copy.deepcopy(payload),
        rule_records=tuple(rule_records),
        bundle_version=bundle_version,
        schema_version=schema_version,
        hit_count=len(match_result.hits),
        applied_patch_count=applied_patch_count,
        applied_append_count=applied_append_count,
    )


def _merge_single_rule_hit(
    payload: dict[str, Any],
    hit: InputLexRuleHit,
    *,
    merge_policy: InputLexMergePolicy,
) -> InputLexRuleMergeRecord:
    """将单条命中规则的补丁合并进 payload（内部辅助）。

    :param payload: 可变入参 JSON 根对象。
    :type payload: dict[str, Any]
    :param hit: 单条规则命中记录。
    :type hit: InputLexRuleHit
    :param merge_policy: 合并策略。
    :type merge_policy: InputLexMergePolicy
    :returns: 该规则的合并审计记录。
    :rtype: InputLexRuleMergeRecord
    """
    rule = hit.rule
    patch_applications: list[InputLexPatchApplicationRecord] = []
    append_applications: list[InputLexAppendApplicationRecord] = []

    for field_path, patch_value in rule.patches.items():
        application = _apply_scalar_patch(
            payload,
            field_path=field_path,
            patch_value=patch_value,
            rule_mode=rule.mode,
            rule_intent=rule.intent,
            merge_policy=merge_policy,
        )
        patch_applications.append(application)

    for field_path, values_to_append in rule.append.items():
        application = _apply_append_patch(
            payload,
            field_path=field_path,
            values_to_append=values_to_append,
            merge_policy=merge_policy,
        )
        append_applications.append(application)

    return InputLexRuleMergeRecord(
        rule_id=rule.id,
        intent=rule.intent,
        priority=rule.priority,
        rule_mode=rule.mode,
        patch_applications=tuple(patch_applications),
        append_applications=tuple(append_applications),
    )


def _apply_scalar_patch(
    payload: dict[str, Any],
    *,
    field_path: str,
    patch_value: InputLexPatchScalar,
    rule_mode: InputLexRuleModeLiteral,
    rule_intent: str,
    merge_policy: InputLexMergePolicy,
) -> InputLexPatchApplicationRecord:
    """对单个标量字段路径应用补丁（内部辅助）。

    :param payload: 可变入参 JSON 根对象。
    :type payload: dict[str, Any]
    :param field_path: 点路径（camelCase）。
    :type field_path: str
    :param patch_value: 规则声明的补丁值。
    :type patch_value: InputLexPatchScalar
    :param rule_mode: 规则 ``mode``。
    :type rule_mode: InputLexRuleModeLiteral
    :param rule_intent: 规则 ``intent``。
    :type rule_intent: str
    :param merge_policy: 合并策略。
    :type merge_policy: InputLexMergePolicy
    :returns: 单字段应用记录。
    :rtype: InputLexPatchApplicationRecord
    """
    previous_raw = get_nested_field_value(payload, field_path)
    previous_scalar = _coerce_scalar_snapshot(previous_raw)

    skip_reason = _resolve_patch_skip_reason(
        payload,
        field_path=field_path,
        patch_value=patch_value,
        rule_mode=rule_mode,
        rule_intent=rule_intent,
        merge_policy=merge_policy,
        current_value=previous_scalar,
    )
    if skip_reason is not None:
        return InputLexPatchApplicationRecord(
            field_path=field_path,
            action="skipped",
            previous_value=previous_scalar,
            new_value=previous_scalar,
            skip_reason=skip_reason,
            rule_mode=rule_mode,
        )

    merged_value = _resolve_merged_scalar_value(
        field_path=field_path,
        current_value=previous_scalar,
        patch_value=patch_value,
        merge_policy=merge_policy,
    )

    if merged_value == previous_scalar:
        return InputLexPatchApplicationRecord(
            field_path=field_path,
            action="skipped",
            previous_value=previous_scalar,
            new_value=previous_scalar,
            skip_reason="no_change",
            rule_mode=rule_mode,
        )

    set_nested_field_value(payload, field_path, merged_value)
    return InputLexPatchApplicationRecord(
        field_path=field_path,
        action="applied",
        previous_value=previous_scalar,
        new_value=merged_value,
        skip_reason=None,
        rule_mode=rule_mode,
    )


def _apply_append_patch(
    payload: dict[str, Any],
    *,
    field_path: str,
    values_to_append: tuple[str, ...],
    merge_policy: InputLexMergePolicy,
) -> InputLexAppendApplicationRecord:
    """对数组字段路径执行 ``append`` 合并（内部辅助）。

    :param payload: 可变入参 JSON 根对象。
    :type payload: dict[str, Any]
    :param field_path: 点路径（camelCase）。
    :type field_path: str
    :param values_to_append: 规则声明的追加条目。
    :type values_to_append: tuple[str, ...]
    :param merge_policy: 合并策略。
    :type merge_policy: InputLexMergePolicy
    :returns: 数组追加应用记录。
    :rtype: InputLexAppendApplicationRecord
    """
    previous_raw = get_nested_field_value(payload, field_path)
    previous_list = _coerce_string_list(previous_raw)
    previous_tuple = tuple(previous_list)

    new_list = list(previous_list)
    appended: list[str] = []
    for value in values_to_append:
        if merge_policy.append_deduplicate and value in new_list:
            continue
        new_list.append(value)
        appended.append(value)

    set_nested_field_value(payload, field_path, new_list)
    return InputLexAppendApplicationRecord(
        field_path=field_path,
        appended_values=tuple(appended),
        previous_values=previous_tuple,
        new_values=tuple(new_list),
    )


def _resolve_patch_skip_reason(
    payload: dict[str, Any],
    *,
    field_path: str,
    patch_value: InputLexPatchScalar,
    rule_mode: InputLexRuleModeLiteral,
    rule_intent: str,
    merge_policy: InputLexMergePolicy,
    current_value: InputLexPatchScalar | None,
) -> InputLexPatchSkipReasonLiteral | None:
    """判断标量补丁是否应跳过并返回原因（内部辅助）。

    :param payload: 当前入参 JSON 根对象（只读）。
    :type payload: dict[str, Any]
    :param field_path: 点路径。
    :type field_path: str
    :param patch_value: 候选补丁值。
    :type patch_value: InputLexPatchScalar
    :param rule_mode: 规则 mode。
    :type rule_mode: InputLexRuleModeLiteral
    :param rule_intent: 规则 intent。
    :type rule_intent: str
    :param merge_policy: 合并策略。
    :type merge_policy: InputLexMergePolicy
    :param current_value: 当前字段标量快照。
    :type current_value: InputLexPatchScalar | None
    :returns: 跳过原因；应应用时为 ``None``。
    :rtype: InputLexPatchSkipReasonLiteral | None
    """
    if _blocks_energy_normal_patch(field_path, patch_value, current_value):
        return "energy_normal_blocked_by_lower_state"

    if _is_subjective_normal_deescalation_patch(
        field_path,
        patch_value,
        rule_intent,
    ) and _payload_has_risk_indicators(payload, merge_policy=merge_policy):
        return "risk_escalation_over_subjective_normal"

    if (
        merge_policy.boolean_emergency_sticky
        and field_path in merge_policy.boolean_emergency_fields
        and current_value is True
        and patch_value is False
    ):
        return "emergency_boolean_sticky"

    effective_mode = rule_mode

    if effective_mode == "fill_if_unknown":
        if (
            merge_policy.explicit_ui_wins_over_lexicon
            and is_explicit_ui_value(field_path, current_value)
        ):
            return "explicit_ui_value"
        if not is_lexicon_unknown_value(field_path, current_value):
            return "fill_if_unknown_not_applicable"
        return None

    if effective_mode == "force":
        if (
            field_path in merge_policy.boolean_emergency_fields
            and patch_value is True
        ):
            return None
        if (
            merge_policy.explicit_ui_wins_over_lexicon
            and is_explicit_ui_value(field_path, current_value)
            and field_path not in merge_policy.boolean_emergency_fields
        ):
            return "explicit_ui_value"
        return None

    return None


def _resolve_merged_scalar_value(
    *,
    field_path: str,
    current_value: InputLexPatchScalar | None,
    patch_value: InputLexPatchScalar,
    merge_policy: InputLexMergePolicy,
) -> InputLexPatchScalar:
    """计算合并后的标量字段值（内部辅助）。

    枚举字段按 ``enumEscalation`` 取更严重档位；布尔字段 ``true`` 优先于
    ``false`` / ``null``；其余类型以补丁值覆盖。

    :param field_path: 点路径。
    :type field_path: str
    :param current_value: 当前标量值。
    :type current_value: InputLexPatchScalar | None
    :param patch_value: 规则补丁值。
    :type patch_value: InputLexPatchScalar
    :param merge_policy: 合并策略。
    :type merge_policy: InputLexMergePolicy
    :returns: 合并后的标量值。
    :rtype: InputLexPatchScalar
    """
    if field_path in _BOOLEAN_FIELD_PATHS:
        return _merge_boolean_scalar(current_value, patch_value)

    if field_path in merge_policy.enum_escalation:
        return _merge_enum_scalar(
            field_path,
            current_value=current_value,
            patch_value=patch_value,
            merge_policy=merge_policy,
        )

    return patch_value


def _merge_boolean_scalar(
    current_value: InputLexPatchScalar | None,
    patch_value: InputLexPatchScalar,
) -> bool:
    """合并布尔标量：``true`` 优先（内部辅助）。

    :param current_value: 当前值。
    :type current_value: InputLexPatchScalar | None
    :param patch_value: 补丁值。
    :type patch_value: InputLexPatchScalar
    :returns: 合并后的布尔值。
    :rtype: bool
    :raises TypeError: 补丁值非布尔时抛出。
    """
    if not isinstance(patch_value, bool):
        msg = f"布尔字段补丁值必须为 bool，实际为 {type(patch_value).__name__}"
        raise TypeError(msg)
    if current_value is True:
        return True
    if patch_value is True:
        return True
    if isinstance(current_value, bool):
        return current_value
    return patch_value


def _merge_enum_scalar(
    field_path: str,
    *,
    current_value: InputLexPatchScalar | None,
    patch_value: InputLexPatchScalar,
    merge_policy: InputLexMergePolicy,
) -> str:
    """按 ``enumEscalation`` 合并枚举标量（内部辅助）。

    :param field_path: 点路径。
    :type field_path: str
    :param current_value: 当前枚举值。
    :type current_value: InputLexPatchScalar | None
    :param patch_value: 补丁枚举值。
    :type patch_value: InputLexPatchScalar
    :param merge_policy: 合并策略。
    :type merge_policy: InputLexMergePolicy
    :returns: 就高后的枚举字符串。
    :rtype: str
    :raises TypeError: 补丁值非字符串时抛出。
    """
    if not isinstance(patch_value, str):
        msg = f"枚举字段补丁值必须为 str，实际为 {type(patch_value).__name__}"
        raise TypeError(msg)

    current_str = current_value if isinstance(current_value, str) else "unknown"
    if is_lexicon_unknown_value(field_path, current_str):
        return patch_value

    current_rank = enum_escalation_rank(merge_policy, field_path, current_str)
    patch_rank = enum_escalation_rank(merge_policy, field_path, patch_value)
    if current_rank >= patch_rank:
        return current_str
    return patch_value


def enum_escalation_rank(
    merge_policy: InputLexMergePolicy,
    field_path: str,
    value: str,
) -> int:
    """返回枚举值在 ``enumEscalation`` 表中的严重度序号。

    序号越大表示越严重；未登记的值返回 ``-1``。

    :param merge_policy: 合并策略。
    :type merge_policy: InputLexMergePolicy
    :param field_path: 点路径。
    :type field_path: str
    :param value: 枚举字符串。
    :type value: str
    :returns: 有序档位索引，未知值为 ``-1``。
    :rtype: int
    """
    levels = merge_policy.enum_escalation.get(field_path)
    if levels is None:
        return -1
    try:
        return levels.index(value)
    except ValueError:
        return -1


def is_lexicon_unknown_value(
    field_path: str,
    value: InputLexPatchScalar | None,
) -> bool:
    """判断字段值是否视为词表意义上的「未知」（可补）。

    :param field_path: 点路径。
    :type field_path: str
    :param value: 当前字段值。
    :type value: InputLexPatchScalar | None
    :returns: 布尔字段 ``null``、枚举字段 ``unknown`` 或缺失时为 ``True``。
    :rtype: bool
    """
    if value is None:
        return True
    if field_path in _BOOLEAN_FIELD_PATHS:
        return False
    if field_path in _ENUM_FIELD_PATHS:
        return value == "unknown"
    return False


def is_explicit_ui_value(
    field_path: str,
    value: InputLexPatchScalar | None,
) -> bool:
    """判断字段值是否视为 UI 已明确填写（词表不应覆盖）。

    :param field_path: 点路径。
    :type field_path: str
    :param value: 当前字段值。
    :type value: InputLexPatchScalar | None
    :returns: 非未知的布尔/枚举值为 ``True``。
    :rtype: bool
    """
    return not is_lexicon_unknown_value(field_path, value)


def _blocks_energy_normal_patch(
    field_path: str,
    patch_value: InputLexPatchScalar,
    current_value: InputLexPatchScalar | None,
) -> bool:
    """判断是否应阻止将 ``userReport.energy`` 降为 ``normal``（内部辅助）。

    :param field_path: 点路径。
    :type field_path: str
    :param patch_value: 候选补丁值。
    :type patch_value: InputLexPatchScalar
    :param current_value: 当前值。
    :type current_value: InputLexPatchScalar | None
    :returns: 应阻止时为 ``True``。
    :rtype: bool
    """
    if field_path != "userReport.energy" or patch_value != "normal":
        return False
    return current_value in ("lower", "very_low")


def _is_subjective_normal_deescalation_patch(
    field_path: str,
    patch_value: InputLexPatchScalar,
    rule_intent: str,
) -> bool:
    """判断是否为主观正常类「降风险」补丁（内部辅助）。

    :param field_path: 点路径。
    :type field_path: str
    :param patch_value: 补丁值。
    :type patch_value: InputLexPatchScalar
    :param rule_intent: 规则 intent。
    :type rule_intent: str
    :returns: 属于主观正常降风险补丁时为 ``True``。
    :rtype: bool
    """
    if rule_intent == _SUBJECTIVE_NORMAL_INTENT:
        return True
    return field_path == "userReport.energy" and patch_value == "normal"


def _payload_has_risk_indicators(
    payload: dict[str, Any],
    *,
    merge_policy: InputLexMergePolicy,
) -> bool:
    """判断当前 payload 是否已呈现需保留的风险指示（内部辅助）。

    用于 ``risk_field_escalation_over_subjective_normal`` 冲突消解。

    :param payload: 入参 JSON 根对象。
    :type payload: dict[str, Any]
    :param merge_policy: 合并策略。
    :type merge_policy: InputLexMergePolicy
    :returns: 存在紧急布尔、严重枚举或非空症状列表时为 ``True``。
    :rtype: bool
    """
    user_report = payload.get("userReport")
    if not isinstance(user_report, dict):
        return False

    for field_path in merge_policy.boolean_emergency_fields:
        if get_nested_field_value(payload, field_path) is True:
            return True

    for key in ("pain", "limping"):
        if user_report.get(key) is True:
            return True

    vomiting = user_report.get("vomiting")
    if vomiting == "repeated":
        return True

    diarrhea = user_report.get("diarrhea")
    if diarrhea == "severe":
        return True

    energy = user_report.get("energy")
    if energy in ("lower", "very_low"):
        return True

    symptoms = user_report.get("symptoms")
    if isinstance(symptoms, list) and len(symptoms) > 0:
        return True

    return False


def get_nested_field_value(
    payload: Mapping[str, Any],
    field_path: str,
) -> Any:
    """读取点路径字段值。

    :param payload: JSON 根对象。
    :type payload: collections.abc.Mapping[str, Any]
    :param field_path: 以 ``.`` 分隔的 camelCase 路径。
    :type field_path: str
    :returns: 字段值；路径不存在时为 ``None``。
    :rtype: Any
    """
    current: Any = payload
    for segment in field_path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def set_nested_field_value(
    payload: dict[str, Any],
    field_path: str,
    value: Any,
) -> None:
    """写入点路径字段值，必要时创建中间对象。

    :param payload: 可变 JSON 根对象。
    :type payload: dict[str, Any]
    :param field_path: 以 ``.`` 分隔的 camelCase 路径。
    :type field_path: str
    :param value: 要写入的值。
    :type value: Any
    :returns: ``None``
    :rtype: None
    """
    segments = field_path.split(".")
    current: dict[str, Any] = payload
    for segment in segments[:-1]:
        nested = current.get(segment)
        if not isinstance(nested, dict):
            nested = {}
            current[segment] = nested
        current = nested
    current[segments[-1]] = value


def _coerce_scalar_snapshot(value: Any) -> InputLexPatchScalar | None:
    """将嵌套字段原始值规范化为标量快照（内部辅助）。

    :param value: 原始字段值。
    :type value: Any
    :returns: 标量或 ``None``。
    :rtype: InputLexPatchScalar | None
    """
    if value is None:
        return None
    if isinstance(value, (bool, str, int, float)):
        return value
    return None


def _coerce_string_list(value: Any) -> list[str]:
    """将嵌套字段原始值规范化为字符串列表（内部辅助）。

    :param value: 原始字段值。
    :type value: Any
    :returns: 字符串列表；无法解析时返回空列表。
    :rtype: list[str]
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
