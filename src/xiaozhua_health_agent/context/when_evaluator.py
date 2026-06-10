"""结构化 ``when`` 条件通用求值器（WP2）。

对 ``triage-core.v1.json`` 中的 ``rules[].when`` 及 ``confidence`` 行条件做纯函数求值。
对应 ``triage-core-spec.md`` §五。
"""

from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Any, Protocol, cast

from xiaozhua_health_agent.context.context_types import (
    EvalContext,
    FieldComparisonOperator,
    WhenBlock,
    WhenEvalResult,
    WhenEvalTraceEntry,
)
from xiaozhua_health_agent.context.derived_facts import get_derived_fact_by_json_name
from xiaozhua_health_agent.context.field_resolver import resolve_field_value
from xiaozhua_health_agent.context.risk_order import risk_gte
from xiaozhua_health_agent.schemas import SignalRiskLevelLiteral

# 字段比较运算符 → 二元谓词工厂
_ComparisonPredicate = Callable[[Any, Any], bool]


class _AppendTraceCallback(Protocol):
    """轨迹记录回调协议（支持 ``detail`` 关键字参数）。"""

    def __call__(
        self,
        path: str,
        block_type: str,
        result: bool,
        detail: str | None = ...,
    ) -> None:
        """追加一条求值轨迹。

        :param path: 条件树路径。
        :type path: str
        :param block_type: 块类型名。
        :type block_type: str
        :param result: 求值结果。
        :type result: bool
        :param detail: 可选说明。
        :type detail: str | None
        :rtype: None
        """


class WhenEvaluationError(Exception):
    """when 条件块结构或符号非法时抛出。"""

    def __init__(
        self,
        message: str,
        *,
        path: str | None = None,
        block: WhenBlock | None = None,
    ) -> None:
        """构造求值异常。

        :param message: 错误说明。
        :type message: str
        :param path: 条件树路径（可选）。
        :type path: str | None
        :param block: 触发错误的条件块（可选）。
        :type block: WhenBlock | None
        """
        detail = message if path is None else f"{message}（路径: {path}）"
        super().__init__(detail)
        self.path = path
        self.block = block


def build_eval_context(fact_sheet: object, derived: object) -> EvalContext:
    """从 FactSheet 与 DerivedFacts 构建求值上下文。

    :param fact_sheet: 步骤 ① 事实清单（运行时为 ``FactSheet``）。
    :type fact_sheet: object
    :param derived: 派生事实（运行时为 ``DerivedFacts``）。
    :type derived: object
    :returns: 不可变求值上下文。
    :rtype: EvalContext
    """
    from xiaozhua_health_agent.context.context_types import DerivedFacts
    from xiaozhua_health_agent.parse import FactSheet

    if not isinstance(fact_sheet, FactSheet):
        msg = f"fact_sheet 类型应为 FactSheet，实际为 {type(fact_sheet)!r}"
        raise TypeError(msg)
    if not isinstance(derived, DerivedFacts):
        msg = f"derived 类型应为 DerivedFacts，实际为 {type(derived)!r}"
        raise TypeError(msg)
    return EvalContext(fact_sheet=fact_sheet, derived=derived)


def eval_when(when: WhenBlock, ctx: EvalContext) -> bool:
    """对结构化 ``when`` 条件块求值。

    :param when: 条件块 JSON 对象。
    :type when: WhenBlock
    :param ctx: 求值上下文。
    :type ctx: EvalContext
    :returns: 条件满足时为 ``True``。
    :rtype: bool
    :raises WhenEvaluationError: 条件块类型未知或结构非法。
    """
    result = eval_when_traced(when, ctx)
    return result.matched


def eval_when_traced(when: WhenBlock, ctx: EvalContext) -> WhenEvalResult:
    """对 ``when`` 求值并返回轨迹（测试 / 调试）。

    :param when: 条件块 JSON 对象。
    :type when: WhenBlock
    :param ctx: 求值上下文。
    :type ctx: EvalContext
    :returns: 匹配结果与深度优先轨迹。
    :rtype: WhenEvalResult
    :raises WhenEvaluationError: 条件块类型未知或结构非法。
    """
    trace: list[WhenEvalTraceEntry] = []

    def _append_trace(
        path: str,
        block_type: str,
        result: bool,
        detail: str | None = None,
    ) -> None:
        """向轨迹列表追加条目（闭包）。

        :param path: 条件树路径。
        :type path: str
        :param block_type: 块类型名。
        :type block_type: str
        :param result: 求值结果。
        :type result: bool
        :param detail: 可选说明。
        :type detail: str | None
        :rtype: None
        """
        trace.append(
            WhenEvalTraceEntry(
                path=path,
                block_type=block_type,
                result=result,
                detail=detail,
            ),
        )

    matched = _eval_block(when, ctx, path="root", append_trace=_append_trace)
    return WhenEvalResult(matched=matched, trace=tuple(trace))


def _eval_block(
    block: WhenBlock,
    ctx: EvalContext,
    *,
    path: str,
    append_trace: _AppendTraceCallback,
) -> bool:
    """递归求值单个条件块。

    :param block: 条件块。
    :type block: WhenBlock
    :param ctx: 求值上下文。
    :type ctx: EvalContext
    :param path: 当前路径。
    :type path: str
    :param append_trace: 轨迹记录回调。
    :type append_trace: _AppendTraceCallback
    :returns: 块求值结果。
    :rtype: bool
    :raises WhenEvaluationError: 未知块类型。
    """
    if not isinstance(block, dict):
        msg = f"条件块必须是对象，实际为 {type(block)!r}"
        raise WhenEvaluationError(msg, path=path, block=cast(WhenBlock, {}))

    if "all" in block:
        return _eval_all(block, ctx, path=path, append_trace=append_trace)
    if "any" in block:
        return _eval_any(block, ctx, path=path, append_trace=append_trace)
    if "not" in block:
        return _eval_not(block, ctx, path=path, append_trace=append_trace)
    if "fact" in block:
        return _eval_fact(block, ctx, path=path, append_trace=append_trace)
    if "field" in block:
        return _eval_field(block, ctx, path=path, append_trace=append_trace)
    if "signal" in block:
        return _eval_signal(block, ctx, path=path, append_trace=append_trace)
    if "derived" in block:
        return _eval_derived(block, ctx, path=path, append_trace=append_trace)

    msg = f"未知条件块类型，键集合: {sorted(block.keys())!r}"
    raise WhenEvaluationError(msg, path=path, block=block)


def _eval_all(
    block: WhenBlock,
    ctx: EvalContext,
    *,
    path: str,
    append_trace: _AppendTraceCallback,
) -> bool:
    """求值 ``all`` 组合块。

    :param block: 含 ``all`` 键的条件块。
    :type block: WhenBlock
    :param ctx: 求值上下文。
    :type ctx: EvalContext
    :param path: 当前路径。
    :type path: str
    :param append_trace: 轨迹记录回调。
    :type append_trace: _AppendTraceCallback
    :returns: 全部子块为真时 ``True``；空列表为真。
    :rtype: bool
    """
    children = block.get("all")
    if not isinstance(children, list):
        msg = "all 的值必须是数组"
        raise WhenEvaluationError(msg, path=path, block=block)

    if not children:
        append_trace(path, "all", True, detail="empty all → true")
        return True

    for index, child in enumerate(children):
        child_path = f"{path}.all[{index}]"
        if not isinstance(child, dict):
            msg = "all 子元素必须是对象"
            raise WhenEvaluationError(msg, path=child_path, block=block)
        if not _eval_block(child, ctx, path=child_path, append_trace=append_trace):
            append_trace(path, "all", False, detail=f"failed at {child_path}")
            return False
    append_trace(path, "all", True, detail=f"{len(children)} children")
    return True


def _eval_any(
    block: WhenBlock,
    ctx: EvalContext,
    *,
    path: str,
    append_trace: _AppendTraceCallback,
) -> bool:
    """求值 ``any`` 组合块。

    :param block: 含 ``any`` 键的条件块。
    :type block: WhenBlock
    :param ctx: 求值上下文。
    :type ctx: EvalContext
    :param path: 当前路径。
    :type path: str
    :param append_trace: 轨迹记录回调。
    :type append_trace: _AppendTraceCallback
    :returns: 任一子块为真时 ``True``；空列表为假。
    :rtype: bool
    """
    children = block.get("any")
    if not isinstance(children, list):
        msg = "any 的值必须是数组"
        raise WhenEvaluationError(msg, path=path, block=block)

    if not children:
        append_trace(path, "any", False, detail="empty any → false")
        return False

    for index, child in enumerate(children):
        child_path = f"{path}.any[{index}]"
        if not isinstance(child, dict):
            msg = "any 子元素必须是对象"
            raise WhenEvaluationError(msg, path=child_path, block=block)
        if _eval_block(child, ctx, path=child_path, append_trace=append_trace):
            append_trace(path, "any", True, detail=f"matched at {child_path}")
            return True
    append_trace(path, "any", False, detail=f"no match in {len(children)} children")
    return False


def _eval_not(
    block: WhenBlock,
    ctx: EvalContext,
    *,
    path: str,
    append_trace: _AppendTraceCallback,
) -> bool:
    """求值 ``not`` 取反块。

    :param block: 含 ``not`` 键的条件块。
    :type block: WhenBlock
    :param ctx: 求值上下文。
    :type ctx: EvalContext
    :param path: 当前路径。
    :type path: str
    :param append_trace: 轨迹记录回调。
    :type append_trace: _AppendTraceCallback
    :returns: 子块结果取反。
    :rtype: bool
    """
    child = block.get("not")
    if not isinstance(child, dict):
        msg = "not 的值必须是对象"
        raise WhenEvaluationError(msg, path=path, block=block)
    child_path = f"{path}.not"
    inner = _eval_block(child, ctx, path=child_path, append_trace=append_trace)
    result = not inner
    append_trace(path, "not", result, detail=f"inner={inner}")
    return result


def _eval_fact(
    block: WhenBlock,
    ctx: EvalContext,
    *,
    path: str,
    append_trace: _AppendTraceCallback,
) -> bool:
    """求值 ``fact`` 派生事实原子。

    :param block: 含 ``fact`` 键的条件块。
    :type block: WhenBlock
    :param ctx: 求值上下文。
    :type ctx: EvalContext
    :param path: 当前路径。
    :type path: str
    :param append_trace: 轨迹记录回调。
    :type append_trace: _AppendTraceCallback
    :returns: 对应 DerivedFacts 布尔为真时 ``True``。
    :rtype: bool
    :raises WhenEvaluationError: 符号未知或非布尔。
    """
    fact_name = block.get("fact")
    if not isinstance(fact_name, str):
        msg = "fact 的值必须是字符串"
        raise WhenEvaluationError(msg, path=path, block=block)

    try:
        value = get_derived_fact_by_json_name(ctx.derived, fact_name)
    except KeyError as exc:
        raise WhenEvaluationError(str(exc), path=path, block=block) from exc

    if not isinstance(value, bool):
        msg = f"fact {fact_name!r} 非布尔值: {value!r}"
        raise WhenEvaluationError(msg, path=path, block=block)

    append_trace(path, "fact", value, detail=f"{fact_name}={value}")
    return value


def _eval_field(
    block: WhenBlock,
    ctx: EvalContext,
    *,
    path: str,
    append_trace: _AppendTraceCallback,
) -> bool:
    """求值 ``field`` 事实字段比较原子。

    :param block: 含 ``field`` 键的条件块。
    :type block: WhenBlock
    :param ctx: 求值上下文。
    :type ctx: EvalContext
    :param path: 当前路径。
    :type path: str
    :param append_trace: 轨迹记录回调。
    :type append_trace: _AppendTraceCallback
    :returns: 字段比较满足时为 ``True``；字段为 null 时比较为假。
    :rtype: bool
    :raises WhenEvaluationError: 缺少比较运算符或运算符非法。
    """
    field_path = block.get("field")
    if not isinstance(field_path, str):
        msg = "field 的值必须是字符串路径"
        raise WhenEvaluationError(msg, path=path, block=block)

    operator, expected = _extract_field_comparison(block, path=path)
    actual = resolve_field_value(ctx.fact_sheet, field_path)

    if actual is None:
        append_trace(
            path,
            "field",
            False,
            detail=f"{field_path} is null",
        )
        return False

    predicate = _comparison_predicate(operator)
    result = predicate(actual, expected)
    append_trace(
        path,
        "field",
        result,
        detail=f"{field_path}={actual!r} {operator} {expected!r}",
    )
    return result


def _extract_field_comparison(
    block: WhenBlock,
    *,
    path: str,
) -> tuple[FieldComparisonOperator, Any]:
    """从 field 块提取比较运算符与期望值。

    :param block: field 条件块。
    :type block: WhenBlock
    :param path: 当前路径。
    :type path: str
    :returns: 运算符与期望值二元组。
    :rtype: tuple[FieldComparisonOperator, Any]
    :raises WhenEvaluationError: 缺少或重复比较键。
    """
    comparison_keys: tuple[FieldComparisonOperator, ...] = (
        "eq",
        "neq",
        "gt",
        "gte",
        "lt",
        "lte",
        "in",
    )
    found: list[tuple[FieldComparisonOperator, Any]] = []
    for key in comparison_keys:
        if key in block:
            found.append((key, block[key]))

    if len(found) != 1:
        msg = f"field 块必须且只能包含一个比较键，实际: {[k for k, _ in found]!r}"
        raise WhenEvaluationError(msg, path=path, block=block)

    return found[0]


def _comparison_predicate(operator: FieldComparisonOperator) -> _ComparisonPredicate:
    """返回指定运算符的二元比较谓词。

    :param operator: 比较运算符。
    :type operator: FieldComparisonOperator
    :returns: 接受 (actual, expected) 的谓词函数。
    :rtype: _ComparisonPredicate
    :raises WhenEvaluationError: 运算符无法识别。
    """

    def _eq(actual: Any, expected: Any) -> bool:
        """等于比较（闭包）。

        :param actual: 实际值。
        :type actual: Any
        :param expected: 期望值。
        :type expected: Any
        :returns: 相等时为 ``True``。
        :rtype: bool
        """
        return actual == expected

    def _neq(actual: Any, expected: Any) -> bool:
        """不等比较（闭包）。

        :param actual: 实际值。
        :type actual: Any
        :param expected: 期望值。
        :type expected: Any
        :returns: 不等时为 ``True``。
        :rtype: bool
        """
        return actual != expected

    def _gt(actual: Any, expected: Any) -> bool:
        """大于比较（闭包）。

        :param actual: 实际值。
        :type actual: Any
        :param expected: 期望值。
        :type expected: Any
        :returns: 大于时为 ``True``。
        :rtype: bool
        """
        return _numeric_compare(actual, expected) > 0

    def _gte(actual: Any, expected: Any) -> bool:
        """大于等于比较（闭包）。

        :param actual: 实际值。
        :type actual: Any
        :param expected: 期望值。
        :type expected: Any
        :returns: 大于等于时为 ``True``。
        :rtype: bool
        """
        return _numeric_compare(actual, expected) >= 0

    def _lt(actual: Any, expected: Any) -> bool:
        """小于比较（闭包）。

        :param actual: 实际值。
        :type actual: Any
        :param expected: 期望值。
        :type expected: Any
        :returns: 小于时为 ``True``。
        :rtype: bool
        """
        return _numeric_compare(actual, expected) < 0

    def _lte(actual: Any, expected: Any) -> bool:
        """小于等于比较（闭包）。

        :param actual: 实际值。
        :type actual: Any
        :param expected: 期望值。
        :type expected: Any
        :returns: 小于等于时为 ``True``。
        :rtype: bool
        """
        return _numeric_compare(actual, expected) <= 0

    def _in(actual: Any, expected: Any) -> bool:
        """集合包含比较（闭包）。

        :param actual: 实际值。
        :type actual: Any
        :param expected: 期望集合。
        :type expected: Any
        :returns: ``actual in expected`` 时为 ``True``。
        :rtype: bool
        """
        if not isinstance(expected, (list, tuple, set, frozenset)):
            msg = "in 运算符的期望值必须是集合类型"
            raise WhenEvaluationError(msg)
        return actual in expected

    mapping: MutableMapping[FieldComparisonOperator, _ComparisonPredicate] = {
        "eq": _eq,
        "neq": _neq,
        "gt": _gt,
        "gte": _gte,
        "lt": _lt,
        "lte": _lte,
        "in": _in,
    }
    try:
        return mapping[operator]
    except KeyError as exc:
        msg = f"未知比较运算符: {operator!r}"
        raise WhenEvaluationError(msg) from exc


def _numeric_compare(actual: Any, expected: Any) -> float:
    """将操作数转为浮点数并比较（供闭包使用）。

    :param actual: 实际值。
    :type actual: Any
    :param expected: 期望值。
    :type expected: Any
    :returns: ``float(actual) - float(expected)``。
    :rtype: float
    :raises WhenEvaluationError: 无法转为数值。
    """
    try:
        return float(actual) - float(expected)
    except (TypeError, ValueError) as exc:
        msg = f"无法对 {actual!r} 与 {expected!r} 做数值比较"
        raise WhenEvaluationError(msg) from exc


def _eval_signal(
    block: WhenBlock,
    ctx: EvalContext,
    *,
    path: str,
    append_trace: _AppendTraceCallback,
) -> bool:
    """求值 ``signal`` 上游信号聚合原子。

    :param block: 含 ``signal`` 键的条件块。
    :type block: WhenBlock
    :param ctx: 求值上下文。
    :type ctx: EvalContext
    :param path: 当前路径。
    :type path: str
    :param append_trace: 轨迹记录回调。
    :type append_trace: _AppendTraceCallback
    :returns: 存在匹配 id 且满足风险下限的 signal 时为 ``True``。
    :rtype: bool
    :raises WhenEvaluationError: signal 块结构非法。
    """
    spec = block.get("signal")
    if not isinstance(spec, dict):
        msg = "signal 的值必须是对象"
        raise WhenEvaluationError(msg, path=path, block=block)

    signal_id = spec.get("id")
    if not isinstance(signal_id, str):
        msg = "signal.id 必须是字符串"
        raise WhenEvaluationError(msg, path=path, block=block)

    minimum_risk: SignalRiskLevelLiteral | None = None
    if "riskGte" in spec:
        risk_value = spec["riskGte"]
        if not isinstance(risk_value, str):
            msg = "signal.riskGte 必须是字符串"
            raise WhenEvaluationError(msg, path=path, block=block)
        minimum_risk = cast(SignalRiskLevelLiteral, risk_value)
    elif "riskEq" in spec:
        risk_value = spec["riskEq"]
        if not isinstance(risk_value, str):
            msg = "signal.riskEq 必须是字符串"
            raise WhenEvaluationError(msg, path=path, block=block)
        minimum_risk = cast(SignalRiskLevelLiteral, risk_value)

    matched = False
    for signal in ctx.fact_sheet.upstream.signals:
        if signal.id != signal_id:
            continue
        if minimum_risk is None:
            matched = True
            break
        if "riskEq" in spec:
            matched = signal.risk_level == minimum_risk
        else:
            matched = risk_gte(signal.risk_level, minimum_risk)
        if matched:
            break

    detail = f"id={signal_id}, riskGte={minimum_risk!r}, matched={matched}"
    append_trace(path, "signal", matched, detail=detail)
    return matched


def _eval_derived(
    block: WhenBlock,
    ctx: EvalContext,
    *,
    path: str,
    append_trace: _AppendTraceCallback,
) -> bool:
    """求值 ``derived`` 预计算聚合量比较原子。

    :param block: 含 ``derived`` 键的条件块。
    :type block: WhenBlock
    :param ctx: 求值上下文。
    :type ctx: EvalContext
    :param path: 当前路径。
    :type path: str
    :param append_trace: 轨迹记录回调。
    :type append_trace: _AppendTraceCallback
    :returns: 聚合量与期望值比较满足时为 ``True``。
    :rtype: bool
    :raises WhenEvaluationError: 缺少比较键或符号未知。
    """
    derived_name = block.get("derived")
    if not isinstance(derived_name, str):
        msg = "derived 的值必须是字符串"
        raise WhenEvaluationError(msg, path=path, block=block)

    try:
        actual = get_derived_fact_by_json_name(ctx.derived, derived_name)
    except KeyError as exc:
        raise WhenEvaluationError(str(exc), path=path, block=block) from exc

    if actual is None:
        append_trace(path, "derived", False, detail=f"{derived_name} is null")
        return False

    operator, expected = _extract_field_comparison(block, path=path)
    predicate = _comparison_predicate(operator)
    result = predicate(actual, expected)
    append_trace(
        path,
        "derived",
        result,
        detail=f"{derived_name}={actual!r} {operator} {expected!r}",
    )
    return result
