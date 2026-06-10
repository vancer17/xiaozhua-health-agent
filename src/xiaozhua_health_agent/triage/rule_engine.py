"""规则评估引擎（WP3）。"""

from __future__ import annotations

from xiaozhua_health_agent.context import EvalContext, eval_when
from xiaozhua_health_agent.context.text_matchers import notes_indicate_medication
from xiaozhua_health_agent.parse import FactSheet
from xiaozhua_health_agent.triage.rules_v1 import TRIAGE_RULES_V1
from xiaozhua_health_agent.triage.triage_types import RuleHitRecord, RuleLayerLiteral, RuleThen, TriageRule

_LAYER_ORDER: tuple[RuleLayerLiteral, ...] = ("EMG", "DQ", "CTX")


def evaluate_rules(
    ctx: EvalContext,
    *,
    rules: tuple[TriageRule, ...] = TRIAGE_RULES_V1,
) -> list[RuleHitRecord]:
    """按层序评估全部规则并返回命中记录。

    :param ctx: when 求值上下文。
    :type ctx: EvalContext
    :param rules: 规则表。
    :type rules: tuple[TriageRule, ...]
    :returns: 命中规则列表（保持评估顺序）。
    :rtype: list[RuleHitRecord]
    """
    hits: list[RuleHitRecord] = []
    for layer in _LAYER_ORDER:
        layer_rules = [rule for rule in rules if rule.layer == layer]
        if layer == "CTX":
            layer_rules.sort(key=lambda rule: rule.priority if rule.priority is not None else 999)
        for rule in layer_rules:
            if not eval_when(rule.when, ctx):
                continue
            then = _resolve_then(rule, ctx.fact_sheet)
            hits.append(
                RuleHitRecord(
                    rule_id=rule.id,
                    layer=rule.layer,
                    priority=rule.priority,
                    then=then,
                ),
            )
    return hits


def _resolve_then(rule: TriageRule, fact_sheet: FactSheet) -> RuleThen | None:
    """解析规则 emit，含条件追加（如 CTX-04 用药）。"""
    if rule.then is None:
        return None
    then = rule.then.model_copy(deep=True)
    if rule.id == "CTX-04":
        extra: list[str] = list(then.mentions_add)
        if fact_sheet.profile.medications or notes_indicate_medication(
            fact_sheet.context.notes,
        ):
            mention = "不要自行调整药量"
            if mention not in extra:
                extra.append(mention)
        then.mentions_add = extra
    return then
