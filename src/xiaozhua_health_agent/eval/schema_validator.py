"""input / output 契约 Schema 校验器（WP0）。

基于 Pydantic 模型作为可执行契约真源，将 ``ValidationError`` 转为统一的
``ValidationResult``，供批跑报告与后续管道出站检查复用。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar, cast

from pydantic import BaseModel, ValidationError

from xiaozhua_health_agent.eval.case_dataset import HealthTriageDataset
from xiaozhua_health_agent.eval.validation_result import (
    CaseInputValidationRecord,
    OutputValidationMode,
    OutputValidationModeLiteral,
    SchemaKind,
    ValidationResult,
    Violation,
    ViolationCode,
    ViolationCodeLiteral,
    ViolationDomain,
    ViolationDomainLiteral,
    ViolationSeverity,
)
from xiaozhua_health_agent.schemas import (
    AgentInput,
    AgentOutput,
    RiskOnlyOutput,
)

INPUT_SCHEMA_VERSION: str = "xiaozhua.health_agent.input.v1"
"""与 ``docs/schema/xiaozhua_health_agent_input_schema.v1.json`` 对齐。"""

OUTPUT_SCHEMA_VERSION: str = "xiaozhua.health_agent.output.v1"
"""与 ``docs/schema/xiaozhua_health_agent_output_schema.v1.json`` 对齐。"""

TModel = TypeVar("TModel", bound=BaseModel)
TParsed = TypeVar("TParsed")


def validate_input(
    data: AgentInput | Mapping[str, Any],
) -> ValidationResult[AgentInput]:
    """校验 Agent 入参是否符合 input_schema.v1。

    :param data: 原始 JSON 字典，或已构造的 ``AgentInput`` 实例。
    :type data: AgentInput | collections.abc.Mapping[str, Any]
    :returns: 含 ``passed``、``violations`` 与可选 ``parsed`` 的校验结果。
    :rtype: ValidationResult[AgentInput]
    """
    if isinstance(data, AgentInput):
        return ValidationResult[AgentInput](
            passed=True,
            schema_kind=SchemaKind.INPUT.value,
            schema_version=INPUT_SCHEMA_VERSION,
            mode=None,
            violations=[],
            parsed=data,
        )

    mapping_or_violations = _coerce_mapping(data, schema_kind=SchemaKind.INPUT)
    if isinstance(mapping_or_violations, ValidationResult):
        return cast(ValidationResult[AgentInput], mapping_or_violations)

    return _validate_model(
        payload=mapping_or_violations,
        model_type=AgentInput,
        schema_kind=SchemaKind.INPUT,
        schema_version=INPUT_SCHEMA_VERSION,
        mode=None,
    )


def validate_output(
    data: AgentOutput | RiskOnlyOutput | Mapping[str, Any],
    *,
    mode: OutputValidationMode
    | OutputValidationModeLiteral = OutputValidationMode.FULL,
) -> ValidationResult[AgentOutput | RiskOnlyOutput]:
    """校验 Agent 输出是否符合 output_schema.v1。

    :param data: 原始 JSON 字典，或已构造的输出模型实例。
    :type data: AgentOutput | RiskOnlyOutput | collections.abc.Mapping[str, Any]
    :param mode: ``full`` 校验完整 output；``minimal`` 仅校验 risk-only 子集。
    :type mode: OutputValidationMode | OutputValidationModeLiteral
    :returns: 校验结果；``parsed`` 在通过时为 ``AgentOutput`` 或 ``RiskOnlyOutput``。
    :rtype: ValidationResult[AgentOutput | RiskOnlyOutput]
    """
    resolved_mode = _resolve_output_mode(mode)
    model_type: type[AgentOutput] | type[RiskOnlyOutput]
    if resolved_mode == OutputValidationMode.FULL:
        model_type = AgentOutput
    else:
        model_type = RiskOnlyOutput

    if isinstance(data, AgentOutput) and resolved_mode == OutputValidationMode.FULL:
        return ValidationResult[AgentOutput | RiskOnlyOutput](
            passed=True,
            schema_kind=SchemaKind.OUTPUT.value,
            schema_version=OUTPUT_SCHEMA_VERSION,
            mode=_output_mode_literal(resolved_mode),
            violations=[],
            parsed=data,
        )

    if (
        isinstance(data, RiskOnlyOutput)
        and resolved_mode == OutputValidationMode.MINIMAL
    ):
        return ValidationResult[AgentOutput | RiskOnlyOutput](
            passed=True,
            schema_kind=SchemaKind.OUTPUT.value,
            schema_version=OUTPUT_SCHEMA_VERSION,
            mode=_output_mode_literal(resolved_mode),
            violations=[],
            parsed=data,
        )

    if isinstance(data, BaseModel):
        return ValidationResult[AgentOutput | RiskOnlyOutput](
            passed=False,
            schema_kind=SchemaKind.OUTPUT.value,
            schema_version=OUTPUT_SCHEMA_VERSION,
            mode=_output_mode_literal(resolved_mode),
            violations=[
                Violation(
                    code=ViolationCode.TYPE_ERROR.value,
                    path="$",
                    field=None,
                    message=(
                        f"已解析模型类型 {type(data).__name__} 与校验模式 "
                        f"{resolved_mode.value!r} 不匹配。"
                    ),
                    severity=ViolationSeverity.HIGH.value,
                )
            ],
            parsed=None,
        )

    mapping_or_violations = _coerce_mapping(data, schema_kind=SchemaKind.OUTPUT)
    if isinstance(mapping_or_violations, ValidationResult):
        return cast(
            ValidationResult[AgentOutput | RiskOnlyOutput], mapping_or_violations
        )

    return _validate_model(
        payload=mapping_or_violations,
        model_type=model_type,
        schema_kind=SchemaKind.OUTPUT,
        schema_version=OUTPUT_SCHEMA_VERSION,
        mode=resolved_mode,
    )


def validate_all_case_inputs(
    dataset: HealthTriageDataset,
) -> list[CaseInputValidationRecord]:
    """批量校验数据集中全部 case 的 ``input`` 字段。

    :param dataset: 已加载的 mock case 数据集。
    :type dataset: HealthTriageDataset
    :returns: 与 ``dataset.cases`` 顺序一致的逐条校验记录。
    :rtype: list[CaseInputValidationRecord]
    """
    records: list[CaseInputValidationRecord] = []

    def _validate_one(
        case_id: str, payload: AgentInput | Mapping[str, Any]
    ) -> CaseInputValidationRecord:
        """校验单条 case 入参并封装为批跑记录。

        :param case_id: case 唯一标识。
        :type case_id: str
        :param payload: 该 case 的入参对象或原始字典。
        :type payload: AgentInput | collections.abc.Mapping[str, Any]
        :returns: 带 ``caseId`` 的校验记录。
        :rtype: CaseInputValidationRecord
        """
        result = validate_input(payload)
        return CaseInputValidationRecord(caseId=case_id, result=result)

    for case in dataset.cases:
        records.append(_validate_one(case.case_id, case.input))

    return records


def summarize_validation_results(
    results: Sequence[ValidationResult[Any]],
) -> tuple[int, int]:
    """统计一批校验结果的通过/失败数量。

    :param results: 校验结果序列。
    :type results: collections.abc.Sequence[ValidationResult[Any]]
    :returns: ``(passed_count, failed_count)`` 元组。
    :rtype: tuple[int, int]
    """
    passed_count = sum(1 for item in results if item.passed)
    failed_count = len(results) - passed_count
    return passed_count, failed_count


def _output_mode_literal(
    mode: OutputValidationMode | None,
) -> OutputValidationModeLiteral | None:
    """将 ``OutputValidationMode`` 转为 ``ValidationResult.mode`` 的 Literal 类型。

    :param mode: 输出校验模式枚举；输入校验时传 ``None``。
    :type mode: OutputValidationMode | None
    :returns: ``full`` / ``minimal`` 字面量或 ``None``。
    :rtype: OutputValidationModeLiteral | None
    """
    if mode is None:
        return None
    return cast(OutputValidationModeLiteral, mode.value)


def _resolve_output_mode(
    mode: OutputValidationMode | OutputValidationModeLiteral,
) -> OutputValidationMode:
    """将模式参数规范化为 ``OutputValidationMode`` 枚举。

    :param mode: 字符串或枚举形式的校验模式。
    :type mode: OutputValidationMode | OutputValidationModeLiteral
    :returns: 规范化后的枚举值。
    :rtype: OutputValidationMode
    :raises ValueError: 传入未知模式字符串时抛出。
    """
    if isinstance(mode, OutputValidationMode):
        return mode
    try:
        return OutputValidationMode(mode)
    except ValueError as exc:
        msg = f"不支持的 output 校验模式：{mode!r}，允许 full / minimal。"
        raise ValueError(msg) from exc


def _coerce_mapping(
    data: object,
    *,
    schema_kind: SchemaKind,
) -> Mapping[str, Any] | ValidationResult[Any]:
    """将入参强制转换为 JSON 对象映射。

    :param data: 任意待校验对象。
    :type data: object
    :param schema_kind: 契约种类，用于填充失败结果元数据。
    :type schema_kind: SchemaKind
    :returns: 成功时为 ``dict`` 映射；失败时为未通过的 ``ValidationResult``。
    :rtype: collections.abc.Mapping[str, Any] | ValidationResult[Any]
    """
    if isinstance(data, Mapping):
        return data

    schema_version = (
        INPUT_SCHEMA_VERSION
        if schema_kind == SchemaKind.INPUT
        else OUTPUT_SCHEMA_VERSION
    )
    return ValidationResult[Any](
        passed=False,
        schema_kind=schema_kind.value,
        schema_version=schema_version,
        mode=None,
        violations=[
            Violation(
                code=ViolationCode.PARSE_ERROR.value,
                path="$",
                field=None,
                message=f"期望 JSON 对象（dict），实际为 {type(data).__name__}。",
                severity=ViolationSeverity.HIGH.value,
            )
        ],
        parsed=None,
    )


def _validate_model(
    *,
    payload: Mapping[str, Any],
    model_type: type[TModel],
    schema_kind: SchemaKind,
    schema_version: str,
    mode: OutputValidationMode | None,
) -> ValidationResult[TModel]:
    """使用指定 Pydantic 模型校验映射并生成统一结果。

    :param payload: 待校验的 JSON 对象。
    :type payload: collections.abc.Mapping[str, Any]
    :param model_type: 目标 Pydantic 模型类。
    :type model_type: type[TModel]
    :param schema_kind: 契约种类。
    :type schema_kind: SchemaKind
    :param schema_version: schema 版本字符串。
    :type schema_version: str
    :param mode: 输出校验模式；输入校验时传 ``None``。
    :type mode: OutputValidationMode | None
    :returns: 校验结果。
    :rtype: ValidationResult[TModel]
    """
    try:
        parsed = model_type.model_validate(payload)
    except ValidationError as exc:
        violations = _violations_from_validation_error(exc)
        return ValidationResult[TModel](
            passed=False,
            schema_kind=schema_kind.value,
            schema_version=schema_version,
            mode=_output_mode_literal(mode),
            violations=violations,
            parsed=None,
        )
    except (TypeError, ValueError) as exc:
        return ValidationResult[TModel](
            passed=False,
            schema_kind=schema_kind.value,
            schema_version=schema_version,
            mode=_output_mode_literal(mode),
            violations=[
                Violation(
                    code=ViolationCode.VALUE_ERROR.value,
                    path="$",
                    field=None,
                    message=f"校验过程发生异常：{exc}",
                    severity=ViolationSeverity.HIGH.value,
                )
            ],
            parsed=None,
        )

    return ValidationResult[TModel](
        passed=True,
        schema_kind=schema_kind.value,
        schema_version=schema_version,
        mode=_output_mode_literal(mode),
        violations=[],
        parsed=parsed,
    )


def _violations_from_validation_error(error: ValidationError) -> list[Violation]:
    """将 Pydantic ``ValidationError`` 转为 ``Violation`` 列表。

    :param error: Pydantic 校验异常。
    :type error: pydantic.ValidationError
    :returns: 统一格式的违规项列表（可能多条）。
    :rtype: list[Violation]
    """
    return list(
        violations_from_pydantic_validation_error(
            error,
            domain=ViolationDomain.SCHEMA.value,
        ),
    )


def violations_from_pydantic_validation_error(
    error: ValidationError,
    *,
    domain: ViolationDomain | ViolationDomainLiteral = ViolationDomain.SCHEMA,
) -> tuple[Violation, ...]:
    """将 Pydantic ``ValidationError`` 转为 ``Violation`` 元组（公开 API）。

    供 ``output.merge_violations``、管道 merge 失败与 schema 校验复用。

    :param error: Pydantic 校验异常。
    :type error: pydantic.ValidationError
    :param domain: 违规来源域；Merge / schema 校验默认 ``schema``。
    :type domain: ViolationDomain | ViolationDomainLiteral
    :returns: 统一格式的违规项元组（可能多条）。
    :rtype: tuple[Violation, ...]
    """
    resolved_domain = domain.value if isinstance(domain, ViolationDomain) else domain
    violations: list[Violation] = []

    for item in error.errors():
        loc = item.get("loc", ())
        path = _format_error_location(loc)
        top_level_field = _extract_top_level_field(loc)
        code = _map_pydantic_error_type(item.get("type", ""))
        message = _format_error_message(item)
        violations.append(
            Violation(
                code=code,
                domain=resolved_domain,
                path=path,
                field=top_level_field,
                message=message,
                severity=ViolationSeverity.HIGH.value,
            ),
        )

    return tuple(violations)


def _format_error_location(location: Sequence[int | str]) -> str:
    """格式化 Pydantic 错误路径为点分字符串。

    :param location: Pydantic ``error['loc']`` 元组。
    :type location: collections.abc.Sequence[int | str]
    :returns: 如 ``healthEvidence.signals.0.riskLevel`` 的路径。
    :rtype: str
    """
    if not location:
        return "$"
    return ".".join(str(part) for part in location)


def _extract_top_level_field(location: Sequence[int | str]) -> str | None:
    """提取 JSON 顶层字段名（优先 alias 名）。

    :param location: Pydantic ``error['loc']`` 元组。
    :type location: collections.abc.Sequence[int | str]
    :returns: 顶层字段名；无法识别时返回 ``None``。
    :rtype: str | None
    """
    for part in location:
        if isinstance(part, str):
            return part
    return None


def _map_pydantic_error_type(error_type: str) -> ViolationCodeLiteral:
    """将 Pydantic 内部错误类型映射为 ``ViolationCode`` 字符串。

    :param error_type: Pydantic ``error['type']`` 字段。
    :type error_type: str
    :returns: ``ViolationCodeLiteral`` 字符串值。
    :rtype: ViolationCodeLiteral
    """
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
    if "action" in error_type:
        return cast(ViolationCodeLiteral, ViolationCode.ACTION_INVALID.value)
    return cast(ViolationCodeLiteral, ViolationCode.VALUE_ERROR.value)


def _format_error_message(error_item: Mapping[str, Any]) -> str:
    """生成中文友好的违规说明。

    :param error_item: Pydantic 单条 ``error.errors()`` 字典。
    :type error_item: collections.abc.Mapping[str, Any]
    :returns: 人类可读错误信息。
    :rtype: str
    """
    error_type = str(error_item.get("type", ""))
    msg = str(error_item.get("msg", "字段不符合契约要求。"))

    if error_type == "missing":
        return "缺少必填字段。"
    if error_type == "extra_forbidden":
        return "存在未在契约中定义的额外字段。"
    if error_type in {"literal_error", "enum"}:
        return f"枚举或 Literal 取值非法：{msg}"
    if error_type in {"string_too_short", "too_short"}:
        return "字符串字段不能为空。"
    return msg
