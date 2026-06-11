"""步骤 ④-A 文案结构校验器（ValidateStructure，WP5）。

校验 ``DraftCopyJSON`` 的 JSON 形态与必填文案字段，并对 ``primaryAction`` /
``secondaryAction`` 产出明确的 ``ACTION_INVALID`` 违规码（与 ``pipeline-design.md``
§6.1 ValidateStructure 对齐）。

与 ``schema_validator`` 的分工：

- **本模块**：③ 产出 / ④ 入站的 ``DraftCopyJSON``（无 ``riskLevel`` 等裁决字段）。
- **schema_validator**：完整 ``AgentOutput`` / ``RiskOnlyOutput`` 契约校验。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

from pydantic import ValidationError

from xiaozhua_health_agent.eval.validation_result import (
    SchemaKind,
    ValidationResult,
    Violation,
    ViolationCode,
    ViolationCodeLiteral,
    ViolationDomain,
    ViolationSeverity,
)

if TYPE_CHECKING:
    from xiaozhua_health_agent.copy import DraftCopyJSON

DRAFT_STRUCTURE_SCHEMA_VERSION: str = "xiaozhua.health_agent.draft_copy.v1"
"""与 ``DraftCopyJSON`` / ``pipeline-design.md`` §5.3 文案字段子集对齐。"""

_ACTION_ROOT_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "primaryAction",
        "primary_action",
        "secondaryAction",
        "secondary_action",
    },
)
"""JSON 中主/次行动对象的顶层键名（camelCase 与 snake_case）。"""


def _draft_copy_model() -> type[DraftCopyJSON]:
    """延迟加载 ``DraftCopyJSON``，避免 ``eval`` ↔ ``copy`` ↔ ``triage`` 循环导入。

    :returns: ``xiaozhua_health_agent.copy.DraftCopyJSON`` 模型类。
    :rtype: type[DraftCopyJSON]
    """
    from xiaozhua_health_agent.copy import DraftCopyJSON as _DraftCopyJSON

    return _DraftCopyJSON


def validate_structure(
    data: DraftCopyJSON | Mapping[str, Any],
) -> ValidationResult[DraftCopyJSON]:
    """校验文案草稿是否符合 ``DraftCopyJSON`` 结构（ValidateStructure）。

    对 ``primaryAction`` / ``secondaryAction`` 的形态与 ``label`` 必填性使用
    ``ACTION_INVALID``；其余字段沿用 ``PARSE_ERROR`` / ``FIELD_MISSING`` /
    ``TYPE_ERROR`` / ``VALUE_ERROR`` 等契约码。

    :param data: 已解析的 ``DraftCopyJSON``，或 LLM / 机械路径产出的 JSON 对象。
    :type data: DraftCopyJSON | collections.abc.Mapping[str, Any]
    :returns: 含 ``passed``、``violations`` 与可选 ``parsed`` 的结构校验结果。
    :rtype: ValidationResult[DraftCopyJSON]
    """
    draft_model = _draft_copy_model()
    if isinstance(data, draft_model):
        return ValidationResult(
            passed=True,
            schema_kind=SchemaKind.DRAFT_COPY.value,
            schema_version=DRAFT_STRUCTURE_SCHEMA_VERSION,
            mode=None,
            violations=[],
            parsed=data,
        )

    mapping_or_violations = _coerce_draft_mapping(data)
    if isinstance(mapping_or_violations, ValidationResult):
        return mapping_or_violations

    payload = mapping_or_violations
    action_violations = _collect_action_structure_violations(payload)
    model_violations, parsed = _validate_draft_model(payload)
    merged = _merge_structure_violations(action_violations, model_violations)

    if merged:
        return ValidationResult(
            passed=False,
            schema_kind=SchemaKind.DRAFT_COPY.value,
            schema_version=DRAFT_STRUCTURE_SCHEMA_VERSION,
            mode=None,
            violations=merged,
            parsed=None,
        )

    assert parsed is not None
    return ValidationResult(
        passed=True,
        schema_kind=SchemaKind.DRAFT_COPY.value,
        schema_version=DRAFT_STRUCTURE_SCHEMA_VERSION,
        mode=None,
        violations=[],
        parsed=parsed,
    )


def validate_draft_structure(
    data: DraftCopyJSON | Mapping[str, Any],
) -> ValidationResult[DraftCopyJSON]:
    """``validate_structure`` 的语义别名（开发计划 WP5 命名）。

    :param data: 待校验文案草稿或 JSON 对象。
    :type data: DraftCopyJSON | collections.abc.Mapping[str, Any]
    :returns: 结构校验结果。
    :rtype: ValidationResult[DraftCopyJSON]
    """
    return validate_structure(data)


def _coerce_draft_mapping(
    data: object,
) -> Mapping[str, Any] | ValidationResult[DraftCopyJSON]:
    """将入参强制转换为 JSON 对象映射。

    :param data: 任意待校验对象。
    :type data: object
    :returns: 成功时为映射；失败时为未通过的 ``ValidationResult``。
    :rtype: collections.abc.Mapping[str, Any] | ValidationResult[DraftCopyJSON]
    """
    if isinstance(data, Mapping):
        return data

    return ValidationResult(
        passed=False,
        schema_kind=SchemaKind.DRAFT_COPY.value,
        schema_version=DRAFT_STRUCTURE_SCHEMA_VERSION,
        mode=None,
        violations=[
            Violation(
                code=ViolationCode.PARSE_ERROR.value,
                domain=ViolationDomain.SCHEMA.value,
                path="$",
                field=None,
                message=f"期望 JSON 对象（dict），实际为 {type(data).__name__}。",
                severity=ViolationSeverity.HIGH.value,
            )
        ],
        parsed=None,
    )


def _validate_draft_model(
    payload: Mapping[str, Any],
) -> tuple[list[Violation], DraftCopyJSON | None]:
    """使用 Pydantic 校验映射并转为 ``Violation`` 列表（行动路径优先 ``ACTION_INVALID``）。

    :param payload: 待校验的 JSON 对象。
    :type payload: collections.abc.Mapping[str, Any]
    :returns: ``(violations, parsed)``；通过时 ``violations`` 为空且 ``parsed`` 非 ``None``。
    :rtype: tuple[list[Violation], DraftCopyJSON | None]
    """
    draft_model = _draft_copy_model()
    try:
        parsed = draft_model.model_validate(payload)
    except ValidationError as exc:
        return _violations_from_draft_validation_error(exc), None
    except (TypeError, ValueError) as exc:
        return (
            [
                Violation(
                    code=ViolationCode.VALUE_ERROR.value,
                    domain=ViolationDomain.SCHEMA.value,
                    path="$",
                    field=None,
                    message=f"文案结构校验过程发生异常：{exc}",
                    severity=ViolationSeverity.HIGH.value,
                )
            ],
            None,
        )
    return [], parsed


def _merge_structure_violations(
    action_violations: list[Violation],
    model_violations: list[Violation],
) -> list[Violation]:
    """合并显式行动校验与 Pydantic 违规，按 ``path`` 去重（显式优先）。

    :param action_violations: ``_collect_action_structure_violations`` 产出项。
    :type action_violations: list[Violation]
    :param model_violations: Pydantic 映射产出项。
    :type model_violations: list[Violation]
    :returns: 去重后的违规列表。
    :rtype: list[Violation]
    """
    if not action_violations:
        return model_violations
    if not model_violations:
        return action_violations

    action_paths = {item.path for item in action_violations}
    action_roots = {
        _action_root_from_path(item.path)
        for item in action_violations
        if _action_root_from_path(item.path) is not None
    }

    def _keep_model_violation(item: Violation) -> bool:
        """判断是否保留 Pydantic 违规项（不与显式行动项重复）。

        :param item: 单条 Pydantic 映射违规。
        :type item: Violation
        :returns: 为 ``True`` 时保留该条。
        :rtype: bool
        """
        if item.path in action_paths:
            return False
        root = _action_root_from_path(item.path)
        if (
            root is not None
            and root in action_roots
            and item.code == ViolationCode.ACTION_INVALID.value
        ):
            return False
        return True

    filtered_model = [item for item in model_violations if _keep_model_violation(item)]
    return action_violations + filtered_model


def _collect_action_structure_violations(
    payload: Mapping[str, Any],
) -> list[Violation]:
    """显式检查 ``primaryAction`` / ``secondaryAction`` 并产出 ``ACTION_INVALID``。

    仅在对应键**存在**于 payload 时检查形态；缺失 ``primaryAction`` 交由
    Pydantic 产出 ``FIELD_MISSING``。

    :param payload: 文案 JSON 对象。
    :type payload: collections.abc.Mapping[str, Any]
    :returns: ``ACTION_INVALID`` 违规列表（可能为空）。
    :rtype: list[Violation]
    """
    violations: list[Violation] = []

    primary_key = _resolve_present_key(payload, ("primaryAction", "primary_action"))
    if primary_key is not None:
        violations.extend(
            _validate_action_object(
                payload[primary_key],
                json_path=primary_key,
                top_level_field=primary_key,
                required=True,
            ),
        )

    secondary_key = _resolve_present_key(
        payload, ("secondaryAction", "secondary_action")
    )
    if secondary_key is not None:
        violations.extend(
            _validate_action_object(
                payload[secondary_key],
                json_path=secondary_key,
                top_level_field=secondary_key,
                required=False,
            ),
        )

    return violations


def _validate_action_object(
    value: object,
    *,
    json_path: str,
    top_level_field: str,
    required: bool,
) -> list[Violation]:
    """校验单个行动对象（``primaryAction`` 或 ``secondaryAction``）。

    :param value: JSON 中的行动字段值。
    :type value: object
    :param json_path: 违规 ``path`` 前缀（如 ``primaryAction``）。
    :type json_path: str
    :param top_level_field: 违规 ``field`` 顶层名。
    :type top_level_field: str
    :param required: 为 ``True`` 时不允许 ``null``（主行动）。
    :type required: bool
    :returns: ``ACTION_INVALID`` 违规列表。
    :rtype: list[Violation]
    """
    if value is None:
        if required:
            return [
                _make_action_invalid_violation(
                    path=json_path,
                    field=top_level_field,
                    message=f"{json_path} 不能为空（null）。",
                )
            ]
        return []

    if not isinstance(value, Mapping):
        return [
            _make_action_invalid_violation(
                path=json_path,
                field=top_level_field,
                message=f"{json_path} 必须为对象，实际为 {type(value).__name__}。",
            )
        ]

    violations: list[Violation] = []
    label_key = _resolve_present_key(value, ("label",))
    if label_key is None:
        violations.append(
            _make_action_invalid_violation(
                path=f"{json_path}.label",
                field=top_level_field,
                message=f"{json_path}.label 为必填字段。",
            ),
        )
    else:
        label_value = value[label_key]
        if not isinstance(label_value, str):
            violations.append(
                _make_action_invalid_violation(
                    path=f"{json_path}.label",
                    field=top_level_field,
                    message=(
                        f"{json_path}.label 必须为字符串，"
                        f"实际为 {type(label_value).__name__}。"
                    ),
                ),
            )
        elif not label_value.strip():
            violations.append(
                _make_action_invalid_violation(
                    path=f"{json_path}.label",
                    field=top_level_field,
                    message=f"{json_path}.label 不能为空字符串。",
                ),
            )

    route_key = _resolve_present_key(value, ("route",))
    if route_key is not None:
        route_value = value[route_key]
        if route_value is not None and not isinstance(route_value, str):
            violations.append(
                _make_action_invalid_violation(
                    path=f"{json_path}.route",
                    field=top_level_field,
                    message=(
                        f"{json_path}.route 必须为字符串或 null，"
                        f"实际为 {type(route_value).__name__}。"
                    ),
                ),
            )

    return violations


def _make_action_invalid_violation(
    *,
    path: str,
    field: str,
    message: str,
) -> Violation:
    """构造单条 ``ACTION_INVALID`` 结构违规。

    :param path: JSON 点分路径。
    :type path: str
    :param field: 顶层字段名（便于报告聚合）。
    :type field: str
    :param message: 人类可读说明。
    :type message: str
    :returns: 域为 ``schema``、严重度为 ``HIGH`` 的违规记录。
    :rtype: Violation
    """
    return Violation(
        code=ViolationCode.ACTION_INVALID.value,
        domain=ViolationDomain.SCHEMA.value,
        path=path,
        field=field,
        message=message,
        severity=ViolationSeverity.HIGH.value,
    )


def _resolve_present_key(
    payload: Mapping[str, Any],
    candidates: Sequence[str],
) -> str | None:
    """在映射中查找首个存在的候选键名。

    :param payload: JSON 对象。
    :type payload: collections.abc.Mapping[str, Any]
    :param candidates: 按优先级排列的键名序列。
    :type candidates: collections.abc.Sequence[str]
    :returns: 命中的键名；均不存在时返回 ``None``。
    :rtype: str | None
    """
    for key in candidates:
        if key in payload:
            return key
    return None


def _violations_from_draft_validation_error(
    error: ValidationError,
) -> list[Violation]:
    """将 Pydantic ``ValidationError`` 转为文案结构 ``Violation`` 列表。

    :param error: Pydantic 校验异常。
    :type error: pydantic.ValidationError
    :returns: 统一格式的违规项列表。
    :rtype: list[Violation]
    """
    violations: list[Violation] = []

    for item in error.errors():
        loc = item.get("loc", ())
        path = _format_error_location(loc)
        top_level_field = _extract_top_level_field(loc)
        code = _map_draft_pydantic_error_type(
            error_type=str(item.get("type", "")),
            location=loc,
        )
        message = _format_draft_error_message(item)
        violations.append(
            Violation(
                code=code,
                domain=ViolationDomain.SCHEMA.value,
                path=path,
                field=top_level_field,
                message=message,
                severity=ViolationSeverity.HIGH.value,
            )
        )

    return violations


def _map_draft_pydantic_error_type(
    *,
    error_type: str,
    location: Sequence[int | str],
) -> ViolationCodeLiteral:
    """将 Pydantic 错误类型映射为文案结构 ``ViolationCode``。

    当错误路径位于 ``primaryAction`` / ``secondaryAction`` 子树时，优先映射为
    ``ACTION_INVALID``（与 ValidateStructure 表一致）。

    :param error_type: Pydantic ``error['type']`` 字段。
    :type error_type: str
    :param location: Pydantic ``error['loc']`` 元组。
    :type location: collections.abc.Sequence[int | str]
    :returns: ``ViolationCodeLiteral`` 字符串值。
    :rtype: ViolationCodeLiteral
    """
    if _is_action_related_location(location):
        if error_type == "missing" and len(location) == 1:
            return cast(ViolationCodeLiteral, ViolationCode.FIELD_MISSING.value)
        if error_type in {"missing"}:
            return cast(ViolationCodeLiteral, ViolationCode.ACTION_INVALID.value)
        if error_type in {
            "string_type",
            "int_type",
            "float_type",
            "bool_type",
            "dict_type",
            "model_type",
            "list_type",
        }:
            return cast(ViolationCodeLiteral, ViolationCode.ACTION_INVALID.value)
        if error_type in {"string_too_short", "too_short"}:
            return cast(ViolationCodeLiteral, ViolationCode.ACTION_INVALID.value)
        if error_type in {"extra_forbidden"}:
            return cast(ViolationCodeLiteral, ViolationCode.ACTION_INVALID.value)
        return cast(ViolationCodeLiteral, ViolationCode.ACTION_INVALID.value)

    if error_type == "missing":
        return cast(ViolationCodeLiteral, ViolationCode.FIELD_MISSING.value)
    if error_type in {"extra_forbidden"}:
        return cast(ViolationCodeLiteral, ViolationCode.EXTRA_FIELD.value)
    if error_type in {"enum", "literal_error", "enum_type"}:
        return cast(ViolationCodeLiteral, ViolationCode.ENUM_INVALID.value)
    if error_type in {
        "string_type",
        "int_type",
        "float_type",
        "bool_type",
        "list_type",
        "dict_type",
        "model_type",
    }:
        return cast(ViolationCodeLiteral, ViolationCode.TYPE_ERROR.value)
    if error_type in {"string_too_short", "too_short"}:
        return cast(ViolationCodeLiteral, ViolationCode.VALUE_ERROR.value)
    return cast(ViolationCodeLiteral, ViolationCode.VALUE_ERROR.value)


def _is_action_related_location(location: Sequence[int | str]) -> bool:
    """判断 Pydantic 错误路径是否位于行动对象子树内。

    :param location: Pydantic ``error['loc']`` 元组。
    :type location: collections.abc.Sequence[int | str]
    :returns: 路径以 ``primaryAction`` / ``secondaryAction`` 开头时为 ``True``。
    :rtype: bool
    """
    if not location:
        return False
    first = location[0]
    return isinstance(first, str) and first in _ACTION_ROOT_FIELD_NAMES


def _action_root_from_path(path: str) -> str | None:
    """从点分路径提取行动根字段名。

    :param path: 如 ``primaryAction.label`` 的路径。
    :type path: str
    :returns: ``primaryAction`` / ``secondaryAction`` 等；非行动路径时为 ``None``。
    :rtype: str | None
    """
    if path in _ACTION_ROOT_FIELD_NAMES:
        return path
    root, _, _ = path.partition(".")
    if root in _ACTION_ROOT_FIELD_NAMES:
        return root
    return None


def _format_error_location(location: Sequence[int | str]) -> str:
    """格式化 Pydantic 错误路径为点分字符串。

    :param location: Pydantic ``error['loc']`` 元组。
    :type location: collections.abc.Sequence[int | str]
    :returns: 如 ``primaryAction.label`` 的路径；空时为 ``$``。
    :rtype: str
    """
    if not location:
        return "$"
    return ".".join(str(part) for part in location)


def _extract_top_level_field(location: Sequence[int | str]) -> str | None:
    """提取 JSON 顶层字段名。

    :param location: Pydantic ``error['loc']`` 元组。
    :type location: collections.abc.Sequence[int | str]
    :returns: 顶层字段名；无法识别时返回 ``None``。
    :rtype: str | None
    """
    for part in location:
        if isinstance(part, str):
            return part
    return None


def _format_draft_error_message(error_item: Mapping[str, Any]) -> str:
    """生成文案结构校验的中文友好说明。

    :param error_item: Pydantic 单条 ``error.errors()`` 字典。
    :type error_item: collections.abc.Mapping[str, Any]
    :returns: 人类可读错误信息。
    :rtype: str
    """
    error_type = str(error_item.get("type", ""))
    msg = str(error_item.get("msg", "字段不符合文案结构要求。"))

    if error_type == "missing":
        return "缺少必填字段。"
    if error_type == "extra_forbidden":
        return "存在未在文案契约中定义的额外字段。"
    if error_type in {"literal_error", "enum"}:
        return f"枚举或 Literal 取值非法：{msg}"
    if error_type in {"string_too_short", "too_short"}:
        return "字符串字段不能为空。"
    return msg
