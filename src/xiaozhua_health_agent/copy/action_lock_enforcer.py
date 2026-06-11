"""WP4 ③-2 主/次行动锁定（``primaryAction`` / ``secondaryAction`` route 与 label）。

LLM 输出的 ``route`` / ``label`` 必须与 ③-1 ``CopyTemplateResolved`` 中的
``primary_action_draft`` / ``secondary_action_draft`` 一致；不一致时强制回写 draft，
或在关闭 enforce 时供重试协调器检测。

对应开发计划「LLM 改 route 时强制回写 draft 或触发重试」。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Literal, TypeAlias

from xiaozhua_health_agent.copy.copy_types import CopyTemplateResolved
from xiaozhua_health_agent.copy.draft_parser import (
    DraftParseWarning,
    DraftParseWarningCode,
)
from xiaozhua_health_agent.schemas import ActionItem

__all__ = [
    "ActionLockOptions",
    "LockedActionField",
    "LockedActionMismatch",
    "collect_locked_action_mismatches",
    "collect_locked_action_mismatches_from_draft",
    "enforce_locked_actions",
    "is_retryable_locked_action_mismatch",
]

LockedActionFieldLiteral: TypeAlias = Literal["route", "label", "presence"]


class LockedActionField(StrEnum):
    """锁定行动字段不一致的类型。"""

    ROUTE = "route"
    LABEL = "label"
    PRESENCE = "presence"


_PRIMARY_ACTION_KEYS: Final[tuple[str, ...]] = ("primaryAction", "primary_action")
_SECONDARY_ACTION_KEYS: Final[tuple[str, ...]] = ("secondaryAction", "secondary_action")


@dataclass(frozen=True, slots=True)
class ActionLockOptions:
    """行动锁定行为配置。

    :ivar enforce: 为 ``True`` 时在解析阶段强制回写 draft；为 ``False`` 时仅检测不一致。
    :vartype enforce: bool
    :ivar lock_label: 为 ``True`` 时 ``label`` 与 draft 不一致也视为需纠正/重试。
    :vartype lock_label: bool
    """

    enforce: bool = True
    lock_label: bool = True


@dataclass(frozen=True, slots=True)
class LockedActionMismatch:
    """单条主/次行动与 ③-1 draft 的不一致记录。

    :ivar json_path: JSON 路径，如 ``primaryAction.route``。
    :vartype json_path: str
    :ivar field: 顶层字段名（``primaryAction`` / ``secondaryAction``）。
    :vartype field: str
    :ivar mismatch_kind: 不一致类型（route / label / presence）。
    :vartype mismatch_kind: LockedActionField
    :ivar expected: draft 期望值（字符串化；``null`` 表示应为 absent/null）。
    :vartype expected: str | None
    :ivar actual: LLM 实际值（字符串化）。
    :vartype actual: str | None
    :ivar message: 人类可读说明。
    :vartype message: str
    """

    json_path: str
    field: str
    mismatch_kind: LockedActionField
    expected: str | None
    actual: str | None
    message: str


def collect_locked_action_mismatches(
    payload: Mapping[str, Any],
    resolved: CopyTemplateResolved,
    *,
    lock_label: bool = True,
) -> tuple[LockedActionMismatch, ...]:
    """从 LLM 文案 JSON 对象收集与 ③-1 draft 不一致的主/次行动项。

    :param payload: 已解析的文案 JSON 对象（camelCase 或 snake_case 键均可）。
    :type payload: collections.abc.Mapping[str, Any]
    :param resolved: 步骤 ③-1 模板解析包（draft 真源）。
    :type resolved: CopyTemplateResolved
    :param lock_label: 是否将 ``label`` 不一致也计为 mismatch。
    :type lock_label: bool
    :returns: 不一致记录元组；无问题时为空元组。
    :rtype: tuple[LockedActionMismatch, ...]
    """
    mismatches: list[LockedActionMismatch] = []

    primary_key, primary_raw = _read_action_raw(payload, _PRIMARY_ACTION_KEYS)
    mismatches.extend(
        _compare_action_to_draft(
            action_raw=primary_raw,
            json_path_prefix=primary_key or "primaryAction",
            field_name="primaryAction",
            draft=resolved.primary_action_draft,
            required=True,
            lock_label=lock_label,
        ),
    )

    secondary_key, secondary_raw = _read_action_raw(payload, _SECONDARY_ACTION_KEYS)
    mismatches.extend(
        _compare_action_to_draft(
            action_raw=secondary_raw,
            json_path_prefix=secondary_key or "secondaryAction",
            field_name="secondaryAction",
            draft=resolved.secondary_action_draft,
            required=False,
            lock_label=lock_label,
        ),
    )

    return tuple(mismatches)


def collect_locked_action_mismatches_from_draft(
    draft: ActionItem | None,
    *,
    expected: ActionItem | None,
    json_path_prefix: str,
    field_name: str,
    required: bool,
    lock_label: bool = True,
) -> tuple[LockedActionMismatch, ...]:
    """比较已解析 ``ActionItem`` 与期望 draft（供 ``eval`` 守卫复用）。

    :param draft: 实际文案草稿中的行动项；``required=False`` 且期望为 ``None`` 时可为 ``None``。
    :type draft: ActionItem | None
    :param expected: ③-1 draft 行动项。
    :type expected: ActionItem | None
    :param json_path_prefix: 违规路径前缀。
    :type json_path_prefix: str
    :param field_name: 顶层字段名。
    :type field_name: str
    :param required: 是否必须存在。
    :type required: bool
    :param lock_label: 是否校验 ``label``。
    :type lock_label: bool
    :returns: 不一致记录元组。
    :rtype: tuple[LockedActionMismatch, ...]
    """
    if expected is None and not required:
        if draft is not None:
            return (
                LockedActionMismatch(
                    json_path=json_path_prefix,
                    field=field_name,
                    mismatch_kind=LockedActionField.PRESENCE,
                    expected=None,
                    actual=_format_action_summary(draft),
                    message=(f"{field_name} 应为 null，但模型输出了行动对象。"),
                ),
            )
        return ()

    if expected is None:
        return ()

    if draft is None:
        return (
            LockedActionMismatch(
                json_path=json_path_prefix,
                field=field_name,
                mismatch_kind=LockedActionField.PRESENCE,
                expected=_format_action_summary(expected),
                actual=None,
                message=f"{field_name} 缺失，与 ③-1 draft 不一致。",
            ),
        )

    return tuple(
        _compare_normalized_actions(
            actual_label=draft.label,
            actual_route=draft.route,
            expected=expected,
            json_path_prefix=json_path_prefix,
            field_name=field_name,
            lock_label=lock_label,
        ),
    )


def enforce_locked_actions(
    payload: dict[str, Any],
    resolved: CopyTemplateResolved,
    *,
    options: ActionLockOptions | None = None,
) -> tuple[dict[str, Any], tuple[DraftParseWarning, ...]]:
    """强制将 LLM 输出的主/次行动回写为 ③-1 draft（route / label 锁定）。

    :param payload: 可变文案 JSON 对象（浅拷贝后修改）。
    :type payload: dict[str, Any]
    :param resolved: 步骤 ③-1 模板解析包。
    :type resolved: CopyTemplateResolved
    :param options: 锁定选项；省略时使用默认 ``enforce=True``、``lock_label=True``。
    :type options: ActionLockOptions | None
    :returns: 修正后的 payload 与纠正警告列表。
    :rtype: tuple[dict[str, Any], tuple[DraftParseWarning, ...]]
    """
    effective = options if options is not None else ActionLockOptions()
    if not effective.enforce:
        return payload, ()

    working: dict[str, Any] = dict(payload)
    warnings: list[DraftParseWarning] = []

    primary_warnings = _enforce_single_action(
        working,
        keys=_PRIMARY_ACTION_KEYS,
        canonical_key="primaryAction",
        draft=resolved.primary_action_draft,
        required=True,
        lock_label=effective.lock_label,
    )
    warnings.extend(primary_warnings)

    secondary_warnings = _enforce_single_action(
        working,
        keys=_SECONDARY_ACTION_KEYS,
        canonical_key="secondaryAction",
        draft=resolved.secondary_action_draft,
        required=False,
        lock_label=effective.lock_label,
    )
    warnings.extend(secondary_warnings)

    return working, tuple(warnings)


def is_retryable_locked_action_mismatch(mismatch: LockedActionMismatch) -> bool:
    """判断单条行动不一致是否应触发 LLM 重试（route / label / 多余次行动）。

    :param mismatch: 不一致记录。
    :type mismatch: LockedActionMismatch
    :returns: 可重试时返回 ``True``。
    :rtype: bool
    """
    return mismatch.mismatch_kind in {
        LockedActionField.ROUTE,
        LockedActionField.LABEL,
        LockedActionField.PRESENCE,
    }


def _enforce_single_action(
    working: dict[str, Any],
    *,
    keys: Sequence[str],
    canonical_key: str,
    draft: ActionItem | None,
    required: bool,
    lock_label: bool,
) -> list[DraftParseWarning]:
    """对单个主/次行动字段执行锁定回写（内部辅助）。

    :param working: 可变 payload。
    :type working: dict[str, Any]
    :param keys: 允许的 JSON 键名（camelCase / snake_case）。
    :type keys: collections.abc.Sequence[str]
    :param canonical_key: 回写时使用的 canonical camelCase 键。
    :type canonical_key: str
    :param draft: 期望 draft；次行动可为 ``None``。
    :type draft: ActionItem | None
    :param required: 是否必须存在。
    :type required: bool
    :param lock_label: 是否锁定 ``label``。
    :type lock_label: bool
    :returns: 纠正警告列表。
    :rtype: list[DraftParseWarning]
    """
    warnings: list[DraftParseWarning] = []
    present_key, action_raw = _read_action_raw(working, keys)

    for alias in keys:
        if alias != canonical_key and alias in working:
            del working[alias]

    if draft is None and not required:
        if action_raw is not None:
            working[canonical_key] = None
            warnings.append(
                DraftParseWarning(
                    code=_secondary_presence_warning_code(canonical_key),
                    message=f"{canonical_key} 不应存在，已强制设为 null。",
                    field=canonical_key,
                ),
            )
        else:
            working[canonical_key] = None
        return warnings

    assert draft is not None

    if not _action_dict_is_valid(action_raw):
        working[canonical_key] = draft.model_dump(by_alias=True, mode="json")
        warnings.append(
            DraftParseWarning(
                code=_primary_backfill_warning_code(canonical_key),
                message=f"{canonical_key} 由 ③-1 draft 整对象回写（形态无效或缺失）。",
                field=canonical_key,
            ),
        )
        return warnings

    assert isinstance(action_raw, dict)
    mismatches = _compare_normalized_actions(
        actual_label=_read_label(action_raw),
        actual_route=_normalize_route(action_raw.get("route")),
        expected=draft,
        json_path_prefix=canonical_key,
        field_name=canonical_key,
        lock_label=lock_label,
    )

    if not mismatches:
        working[canonical_key] = _normalize_action_dict(action_raw, draft=draft)
        return warnings

    working[canonical_key] = draft.model_dump(by_alias=True, mode="json")
    for mismatch in mismatches:
        warnings.append(
            DraftParseWarning(
                code=_warning_code_for_mismatch(mismatch),
                message=mismatch.message,
                field=canonical_key,
            ),
        )
    return warnings


def _compare_action_to_draft(
    *,
    action_raw: Any,
    json_path_prefix: str,
    field_name: str,
    draft: ActionItem | None,
    required: bool,
    lock_label: bool,
) -> list[LockedActionMismatch]:
    """比较 JSON 中的行动对象与 draft（内部辅助）。

    :param action_raw: 原始 JSON 值。
    :type action_raw: Any
    :param json_path_prefix: 路径前缀。
    :type json_path_prefix: str
    :param field_name: 顶层字段名。
    :type field_name: str
    :param draft: 期望 draft。
    :type draft: ActionItem | None
    :param required: 是否必须存在。
    :type required: bool
    :param lock_label: 是否校验 label。
    :type lock_label: bool
    :returns: 不一致列表。
    :rtype: list[LockedActionMismatch]
    """
    if draft is None and not required:
        if action_raw is None:
            return []
        if action_raw is False:
            return []
        return [
            LockedActionMismatch(
                json_path=json_path_prefix,
                field=field_name,
                mismatch_kind=LockedActionField.PRESENCE,
                expected=None,
                actual=_format_raw_action(action_raw),
                message=f"{field_name} 应为 null，但模型输出了行动对象。",
            ),
        ]

    if draft is None:
        return []

    if not _action_dict_is_valid(action_raw):
        return [
            LockedActionMismatch(
                json_path=json_path_prefix,
                field=field_name,
                mismatch_kind=LockedActionField.PRESENCE,
                expected=_format_action_summary(draft),
                actual=_format_raw_action(action_raw),
                message=f"{field_name} 缺失或形态非法，与 ③-1 draft 不一致。",
            ),
        ]

    assert isinstance(action_raw, dict)
    return _compare_normalized_actions(
        actual_label=_read_label(action_raw),
        actual_route=_normalize_route(action_raw.get("route")),
        expected=draft,
        json_path_prefix=json_path_prefix,
        field_name=field_name,
        lock_label=lock_label,
    )


def _compare_normalized_actions(
    *,
    actual_label: str | None,
    actual_route: str | None,
    expected: ActionItem,
    json_path_prefix: str,
    field_name: str,
    lock_label: bool,
) -> list[LockedActionMismatch]:
    """比较规范化后的 label/route 与 draft（内部辅助）。

    :param actual_label: 实际 label；无效时为 ``None``。
    :type actual_label: str | None
    :param actual_route: 实际 route（已规范化）。
    :type actual_route: str | None
    :param expected: 期望 draft。
    :type expected: ActionItem
    :param json_path_prefix: 路径前缀。
    :type json_path_prefix: str
    :param field_name: 顶层字段名。
    :type field_name: str
    :param lock_label: 是否校验 label。
    :type lock_label: bool
    :returns: 不一致列表。
    :rtype: list[LockedActionMismatch]
    """
    mismatches: list[LockedActionMismatch] = []
    expected_route = _normalize_route(expected.route)

    if actual_route != expected_route:
        mismatches.append(
            LockedActionMismatch(
                json_path=f"{json_path_prefix}.route",
                field=field_name,
                mismatch_kind=LockedActionField.ROUTE,
                expected=_stringify_nullable(expected_route),
                actual=_stringify_nullable(actual_route),
                message=(
                    f"{field_name}.route 与 ③-1 draft 不一致："
                    f"期望 {_stringify_nullable(expected_route)!r}，"
                    f"实际 {_stringify_nullable(actual_route)!r}。"
                ),
            ),
        )

    if lock_label:
        expected_label = expected.label.strip()
        actual_normalized = (
            actual_label.strip() if isinstance(actual_label, str) else None
        )
        if actual_normalized != expected_label:
            mismatches.append(
                LockedActionMismatch(
                    json_path=f"{json_path_prefix}.label",
                    field=field_name,
                    mismatch_kind=LockedActionField.LABEL,
                    expected=expected_label,
                    actual=actual_normalized,
                    message=(
                        f"{field_name}.label 与 ③-1 draft 不一致："
                        f"期望 {expected_label!r}，"
                        f"实际 {actual_normalized!r}。"
                    ),
                ),
            )

    return mismatches


def _read_action_raw(
    payload: Mapping[str, Any],
    keys: Sequence[str],
) -> tuple[str | None, Any]:
    """读取 payload 中首个匹配键的行动对象（内部辅助）。

    :param payload: JSON 对象。
    :type payload: collections.abc.Mapping[str, Any]
    :param keys: 候选键名。
    :type keys: collections.abc.Sequence[str]
    :returns: ``(命中的键名, 值)``；未命中时 ``(None, None)``。
    :rtype: tuple[str | None, Any]
    """
    for key in keys:
        if key in payload:
            return key, payload[key]
    return None, None


def _action_dict_is_valid(action_raw: Any) -> bool:
    """判断行动 JSON 是否为含非空 ``label`` 的对象（内部辅助）。

    :param action_raw: 原始值。
    :type action_raw: Any
    :returns: 合法对象时返回 ``True``。
    :rtype: bool
    """
    if not isinstance(action_raw, dict):
        return False
    label = action_raw.get("label")
    return isinstance(label, str) and bool(label.strip())


def _read_label(action_raw: Mapping[str, Any]) -> str | None:
    """从行动对象读取 label（内部辅助）。

    :param action_raw: 行动 JSON 对象。
    :type action_raw: collections.abc.Mapping[str, Any]
    :returns: 非空 label 或 ``None``。
    :rtype: str | None
    """
    label = action_raw.get("label")
    if not isinstance(label, str):
        return None
    stripped = label.strip()
    return stripped if stripped else None


def _normalize_route(route: Any) -> str | None:
    """规范化 ``route`` 为 ``str | None``（内部辅助）。

    :param route: 原始 route 值。
    :type route: Any
    :returns: 非空字符串或 ``None``；非法类型视为 ``None``（触发 mismatch）。
    :rtype: str | None
    """
    if route is None:
        return None
    if not isinstance(route, str):
        return None
    stripped = route.strip()
    return stripped if stripped else None


def _normalize_action_dict(
    action_raw: Mapping[str, Any],
    *,
    draft: ActionItem,
) -> dict[str, Any]:
    """将行动对象规范为 camelCase 且 route 类型合法（内部辅助）。

    :param action_raw: 原始行动对象。
    :type action_raw: collections.abc.Mapping[str, Any]
    :param draft: 用于 route 非法时回退的 draft。
    :type draft: ActionItem
    :returns: ``{"label": ..., "route": ...}`` 字典。
    :rtype: dict[str, Any]
    """
    label = _read_label(action_raw)
    route = _normalize_route(action_raw.get("route"))
    if label is None:
        return draft.model_dump(by_alias=True, mode="json")
    if action_raw.get("route") is not None and route is None:
        return draft.model_dump(by_alias=True, mode="json")
    return {"label": label, "route": route}


def _format_action_summary(action: ActionItem) -> str:
    """格式化 ``ActionItem`` 供 mismatch 消息使用（内部辅助）。

    :param action: 行动项。
    :type action: ActionItem
    :returns: 摘要字符串。
    :rtype: str
    """
    return f"label={action.label!r}, route={_stringify_nullable(action.route)!r}"


def _format_raw_action(action_raw: Any) -> str | None:
    """格式化原始 JSON 行动值（内部辅助）。

    :param action_raw: 原始值。
    :type action_raw: Any
    :returns: 摘要或 ``None``。
    :rtype: str | None
    """
    if action_raw is None:
        return None
    if isinstance(action_raw, dict):
        label = action_raw.get("label")
        route = action_raw.get("route")
        return f"label={label!r}, route={route!r}"
    return repr(action_raw)


def _stringify_nullable(value: str | None) -> str | None:
    """将 nullable 字符串格式化为日志/compare 用（内部辅助）。

    :param value: 值。
    :type value: str | None
    :returns: 原值或 ``null`` 占位说明。
    :rtype: str | None
    """
    if value is None:
        return None
    return value


def _warning_code_for_mismatch(mismatch: LockedActionMismatch) -> DraftParseWarningCode:
    """将 mismatch 映射为解析警告码（内部辅助）。

    :param mismatch: 不一致记录。
    :type mismatch: LockedActionMismatch
    :returns: 对应的 ``DraftParseWarningCode``。
    :rtype: DraftParseWarningCode
    """
    if mismatch.field == "secondaryAction":
        if mismatch.mismatch_kind == LockedActionField.ROUTE:
            return DraftParseWarningCode.SECONDARY_ACTION_ROUTE_CORRECTED
        if mismatch.mismatch_kind == LockedActionField.LABEL:
            return DraftParseWarningCode.SECONDARY_ACTION_LABEL_CORRECTED
        return DraftParseWarningCode.SECONDARY_ACTION_PRESENCE_CORRECTED

    if mismatch.mismatch_kind == LockedActionField.ROUTE:
        return DraftParseWarningCode.PRIMARY_ACTION_ROUTE_CORRECTED
    if mismatch.mismatch_kind == LockedActionField.LABEL:
        return DraftParseWarningCode.PRIMARY_ACTION_LABEL_CORRECTED
    return DraftParseWarningCode.PRIMARY_ACTION_BACKFILLED


def _primary_backfill_warning_code(field_name: str) -> DraftParseWarningCode:
    """返回主/次行动整对象回写警告码（内部辅助）。

    :param field_name: 字段名。
    :type field_name: str
    :returns: 警告码。
    :rtype: DraftParseWarningCode
    """
    if field_name == "secondaryAction":
        return DraftParseWarningCode.SECONDARY_ACTION_BACKFILLED
    return DraftParseWarningCode.PRIMARY_ACTION_BACKFILLED


def _secondary_presence_warning_code(field_name: str) -> DraftParseWarningCode:
    """返回次行动 presence 纠正警告码（内部辅助）。

    :param field_name: 字段名。
    :type field_name: str
    :returns: 警告码。
    :rtype: DraftParseWarningCode
    """
    if field_name == "secondaryAction":
        return DraftParseWarningCode.SECONDARY_ACTION_PRESENCE_CORRECTED
    return DraftParseWarningCode.PRIMARY_ACTION_BACKFILLED
