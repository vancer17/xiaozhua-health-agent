# `xiaozhua_health_agent.context` — DerivedFacts 与 evalWhen（步骤 ② 入口）

本包对应开发计划 **WP2**，在 ``FactSheet`` 之上预计算派生事实，并提供结构化 ``when`` 通用求值器，供 WP3 Triage Core 消费。

**设计依据**：

- `docs/implementation/coze/kb-rule-derived-facts-spec.md`
- `docs/implementation/coze/triage-core-spec.md` §五
- `docs/plans/coze-workflow-dev-plan.md` § WP2

## 公开 API

```python
from xiaozhua_health_agent.context import (
    DerivedFacts,
    EvalContext,
    compute_derived_facts,
    eval_when,
    build_eval_context,
)
from xiaozhua_health_agent.parse import parse_input

result = parse_input(case_input)
derived = compute_derived_facts(result.fact_sheet)
ctx = build_eval_context(result.fact_sheet, derived)
matched = eval_when(rule_when_block, ctx)
```

## 模块职责

| 模块 | 职责 |
|------|------|
| `context_types.py` | ``DerivedFacts``、``EvalContext``、when 类型别名 |
| `derived_facts.py` | ``compute_derived_facts`` |
| `when_evaluator.py` | ``eval_when`` / ``eval_when_traced`` |
| `field_resolver.py` | camelCase 路径 → FactSheet 字段 |
| `risk_order.py` | 风险档位序比较 |
| `thresholds.py` | 物种/体征阈值配置 |
| `text_matchers.py` | 中文短语匹配 |

## 边界

- **不做** 风险融合、primaryFlag 仲裁、output 组装（属 WP3+）
- **不修改** ``FactSheet``；**不补全** null 默认值
- 跨包引用请使用 ``xiaozhua_health_agent.parse`` / ``eval`` 的 ``__init__`` 导出
