"""KB-TPL 槽位机械填值（``slots.v1``）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from xiaozhua_health_agent.copy.copy_types import SlotDefinition
from xiaozhua_health_agent.parse import FactSheet, get_fact_value
from xiaozhua_health_agent.triage import TriageCoreResult


def fill_template_slots(
    *,
    slot_ids: tuple[str, ...],
    slot_definitions: dict[str, SlotDefinition],
    fact_sheet: FactSheet,
    triage: TriageCoreResult,
    summary_slot_priority: dict[str, list[str]] | None = None,
) -> dict[str, str]:
    """按模板 binding 填充槽位字典。

    ``primaryVital`` 等派生槽位在基础槽填充完成后按 ``summarySlotPriority`` 解析。

    :param slot_ids: 模板 binding 引用的 slotId 列表。
    :type slot_ids: tuple[str, ...]
    :param slot_definitions: 全局槽位注册表。
    :type slot_definitions: dict[str, SlotDefinition]
    :param fact_sheet: 步骤 ① 事实清单。
    :type fact_sheet: FactSheet
    :param triage: 步骤 ② 锁定分诊结果。
    :type triage: TriageCoreResult
    :param summary_slot_priority: 派生槽优先级（如 ``primaryVital``）。
    :type summary_slot_priority: dict[str, list[str]] | None
    :returns: 非 omit 槽位的展示文案；键为 slotId。
    :rtype: dict[str, str]
    :raises KeyError: ``slot_ids`` 引用未注册的 slotId 时抛出。
    """
    filled: dict[str, str] = {}
    priority = summary_slot_priority or {}

    for slot_id in slot_ids:
        if slot_id == "primaryVital":
            continue
        definition = slot_definitions.get(slot_id)
        if definition is None:
            msg = f"未注册的槽位：{slot_id}"
            raise KeyError(msg)
        value = _resolve_slot_value(
            slot_id=slot_id,
            definition=definition,
            fact_sheet=fact_sheet,
            triage=triage,
        )
        if value is not None and value != "":
            filled[slot_id] = value

    primary_vital_priority = priority.get("primaryVital")
    if primary_vital_priority is not None:
        derived = _resolve_primary_vital(
            priority=_adjust_primary_vital_priority(
                base_priority=primary_vital_priority,
                triage=triage,
            ),
            slot_definitions=slot_definitions,
            fact_sheet=fact_sheet,
            triage=triage,
            prefilled=filled,
        )
        if derived is not None and derived != "":
            filled["primaryVital"] = derived
    elif "primaryVital" in slot_ids:
        derived = _resolve_primary_vital(
            priority=[],
            slot_definitions=slot_definitions,
            fact_sheet=fact_sheet,
            triage=triage,
            prefilled=filled,
        )
        if derived is not None and derived != "":
            filled["primaryVital"] = derived

    return filled


def _adjust_primary_vital_priority(
    *,
    base_priority: list[str],
    triage: TriageCoreResult,
) -> list[str]:
    """按 CTX-09a/09b 规则命中调整 ``primaryVital`` 候选顺序。

    case #2（CTX-09a）优先体温；case #5（CTX-09b）优先心率；其余保持制品默认顺序。

    :param base_priority: 模板 ``summarySlotPriority.primaryVital`` 默认列表。
    :type base_priority: list[str]
    :param triage: 分诊结果（读取 ``ruleHits``）。
    :type triage: TriageCoreResult
    :returns: 调整后的候选 slotId 列表。
    :rtype: list[str]
    """
    hits = set(triage.rule_hits)
    if "CTX-09b" in hits and "CTX-09a" not in hits:
        ordered = [
            "heartRate",
            *[item for item in base_priority if item != "heartRate"],
        ]
        return ordered
    if "CTX-09a" in hits and "CTX-09b" not in hits:
        ordered = [
            "temperature",
            *[item for item in base_priority if item != "temperature"],
        ]
        return ordered
    return list(base_priority)


def _resolve_primary_vital(
    *,
    priority: list[str],
    slot_definitions: dict[str, SlotDefinition],
    fact_sheet: FactSheet,
    triage: TriageCoreResult,
    prefilled: dict[str, str],
) -> str | None:
    """按 ``summarySlotPriority`` 解析 ``primaryVital`` 展示文案。

    :param priority: 候选 vital slotId 列表（前者优先）。
    :type priority: list[str]
    :param slot_definitions: 全局槽位注册表。
    :type slot_definitions: dict[str, SlotDefinition]
    :param fact_sheet: 事实清单。
    :type fact_sheet: FactSheet
    :param triage: 分诊结果。
    :type triage: TriageCoreResult
    :param prefilled: 已填充的基础槽位。
    :type prefilled: dict[str, str]
    :returns: 首个有值的 vital 展示文案；均无值时返回 ``None``。
    :rtype: str | None
    """
    for candidate_id in priority:
        if candidate_id in prefilled and prefilled[candidate_id]:
            return prefilled[candidate_id]
        definition = slot_definitions.get(candidate_id)
        if definition is None:
            continue
        value = _resolve_slot_value(
            slot_id=candidate_id,
            definition=definition,
            fact_sheet=fact_sheet,
            triage=triage,
        )
        if value is not None and value != "":
            return value
    return None


def _resolve_slot_value(
    *,
    slot_id: str,
    definition: SlotDefinition,
    fact_sheet: FactSheet,
    triage: TriageCoreResult,
) -> str | None:
    """解析单个槽位的展示文案。

    :param slot_id: 槽位标识。
    :type slot_id: str
    :param definition: 槽位注册定义。
    :type definition: SlotDefinition
    :param fact_sheet: 事实清单。
    :type fact_sheet: FactSheet
    :param triage: 分诊结果。
    :type triage: TriageCoreResult
    :returns: 展示文案；``omit`` 策略下无值时返回 ``None``。
    :rtype: str | None
    """
    if definition.source == "derived":
        return None

    raw_value = _read_raw_slot_value(
        definition=definition,
        fact_sheet=fact_sheet,
        triage=triage,
    )
    return _format_slot_value(
        slot_id=slot_id,
        definition=definition,
        raw_value=raw_value,
        fact_sheet=fact_sheet,
    )


def _read_raw_slot_value(
    *,
    definition: SlotDefinition,
    fact_sheet: FactSheet,
    triage: TriageCoreResult,
) -> Any:
    """从 FactSheet 或 TriageCoreResult 读取槽位原始值。

    :param definition: 槽位定义。
    :type definition: SlotDefinition
    :param fact_sheet: 事实清单。
    :type fact_sheet: FactSheet
    :param triage: 分诊结果。
    :type triage: TriageCoreResult
    :returns: 原始字段值。
    :rtype: Any
    """
    if definition.source == "factSheet":
        path = definition.path or ""
        return get_fact_value(fact_sheet, path)

    if definition.source == "triageCore":
        path = definition.path or ""
        if path == "missingDataUser":
            return list(triage.missing_data_user)
        return None

    return None


def _format_slot_value(
    *,
    slot_id: str,
    definition: SlotDefinition,
    raw_value: Any,
    fact_sheet: FactSheet,
) -> str | None:
    """将原始值格式化为展示字符串并应用缺失策略。

    :param slot_id: 槽位标识（日志用）。
    :type slot_id: str
    :param definition: 槽位定义。
    :type definition: SlotDefinition
    :param raw_value: 原始字段值。
    :type raw_value: Any
    :param fact_sheet: 事实清单（相对时间参考）。
    :type fact_sheet: FactSheet
    :returns: 格式化后的展示文案；``omit`` 且无值时返回 ``None``。
    :rtype: str | None
    """
    if definition.slot_type == "notesMatch":
        return _format_notes_match(definition=definition, raw_value=raw_value)

    if definition.slot_type == "array":
        return _format_array_slot(definition=definition, raw_value=raw_value)

    if raw_value is None or raw_value == "" or raw_value == []:
        return _apply_missing_behavior(definition=definition)

    if isinstance(raw_value, str):
        text = raw_value.strip()
        if definition.max_length is not None and len(text) > definition.max_length:
            text = text[: definition.max_length]
        if definition.enum_map:
            return definition.enum_map.get(text, text)
        return text

    if isinstance(raw_value, (int, float)):
        if definition.format == "relativeTime":
            return _format_relative_time(
                seen_at=_coerce_datetime(raw_value),
                reference=fact_sheet.timestamp,
            )
        if definition.format and "{value}" in definition.format:
            return definition.format.replace("{value}", _format_number(raw_value))
        return _format_number(raw_value)

    if isinstance(raw_value, datetime):
        if definition.format == "relativeTime":
            return _format_relative_time(
                seen_at=raw_value,
                reference=fact_sheet.timestamp,
            )
        return raw_value.isoformat()

    if definition.enum_map and isinstance(raw_value, str):
        return definition.enum_map.get(raw_value, raw_value)

    return str(raw_value)


def _apply_missing_behavior(*, definition: SlotDefinition) -> str | None:
    """应用槽位缺失策略。

    :param definition: 槽位定义。
    :type definition: SlotDefinition
    :returns: 占位/通用/短语文案；``omit`` 时返回 ``None``。
    :rtype: str | None
    """
    behavior = definition.missing_behavior
    if behavior == "omit":
        return None
    if behavior == "usePlaceholder":
        return definition.placeholder or ""
    if behavior == "useGeneric":
        return definition.generic or ""
    if behavior == "usePhrase":
        return definition.phrase or ""
    return None


def _format_notes_match(
    *,
    definition: SlotDefinition,
    raw_value: Any,
) -> str | None:
    """从 context notes 中匹配首条符合模式的备注。

    :param definition: 槽位定义。
    :type definition: SlotDefinition
    :param raw_value: notes 数组或单条字符串。
    :type raw_value: Any
    :returns: 匹配到的备注；无匹配时按缺失策略处理。
    :rtype: str | None
    """
    notes: list[str]
    if isinstance(raw_value, list):
        notes = [str(item) for item in raw_value]
    elif isinstance(raw_value, str):
        notes = [raw_value]
    else:
        return _apply_missing_behavior(definition=definition)

    for note in notes:
        for pattern in definition.match_patterns:
            if pattern in note:
                return note
    return _apply_missing_behavior(definition=definition)


def _format_array_slot(
    *,
    definition: SlotDefinition,
    raw_value: Any,
) -> str | None:
    """格式化数组类槽位（慢病摘要、missingList 等）。

    :param definition: 槽位定义。
    :type definition: SlotDefinition
    :param raw_value: 数组原始值。
    :type raw_value: Any
    :returns: 拼接后的展示文案；空数组时按缺失策略处理。
    :rtype: str | None
    """
    if not isinstance(raw_value, list) or len(raw_value) == 0:
        return _apply_missing_behavior(definition=definition)

    parts: list[str] = []
    for item in raw_value:
        key = str(item)
        if definition.condition_labels:
            parts.append(definition.condition_labels.get(key, key))
        else:
            parts.append(key)
    return definition.join_separator.join(parts)


def _format_relative_time(
    *,
    seen_at: datetime | None,
    reference: datetime,
) -> str | None:
    """将设备上报时间格式化为相对参考时间的描述。

    :param seen_at: 设备最近上报时间。
    :type seen_at: datetime.datetime | None
    :param reference: 参考时间（通常为请求 timestamp）。
    :type reference: datetime.datetime
    :returns: 中文相对时间描述；``seen_at`` 无效时返回 ``None``。
    :rtype: str | None
    """
    if seen_at is None:
        return None
    delta = reference - seen_at
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return seen_at.strftime("%Y-%m-%d %H:%M")
    minutes = total_seconds // 60
    if minutes < 60:
        return f"约{minutes}分钟前"
    hours = minutes // 60
    if hours < 24:
        return f"约{hours}小时前"
    days = hours // 24
    return f"约{days}天前"


def _coerce_datetime(value: Any) -> datetime | None:
    """尝试将值转为 ``datetime``。

    :param value: 任意原始值。
    :type value: Any
    :returns: 解析成功时返回 datetime；否则 ``None``。
    :rtype: datetime.datetime | None
    """
    if isinstance(value, datetime):
        return value
    return None


def _format_number(value: int | float) -> str:
    """将数值格式化为简洁字符串（整数去掉 ``.0``）。

    :param value: 数值。
    :type value: int | float
    :returns: 字符串表示。
    :rtype: str
    """
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
