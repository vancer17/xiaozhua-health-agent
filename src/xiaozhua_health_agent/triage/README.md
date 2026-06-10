# `xiaozhua_health_agent.triage` — 确定性分诊核（WP3）

对应管道步骤 **② Triage Core**，产出锁定的 `TriageCoreResult`。

## 公开 API

```python
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.triage import run_triage_core, run_triage_risk_batch

parsed = parse_input(case_input)
result = run_triage_core(parsed.fact_sheet)

# 20 case risk-only 批跑
report = run_triage_risk_batch()
```

## 模块职责

| 模块 | 职责 |
|------|------|
| `triage_core.py` | 十步编排门面 |
| `rules_v1.py` | `rules[]` 机器真源 |
| `policy_data.py` | PolicyTables、Evidence、postProcess 数据 |
| `rule_engine.py` | EMG → DQ → CTX 规则评估 |
| `primary_flag_resolver.py` | ResolvePrimaryFlag |
| `fusion.py` | FUS-00 多源 max 融合 |
| `confidence_resolver.py` | L / H′ / H / M |
| `policy_resolve.py` | PolicyTablesResolve |
| `missing_data.py` | missingDataUser 翻译 |
| `evidence_builder.py` | evidenceBullets 组装 |
| `batch.py` | WP0 risk-only 批跑集成 |

## 验收

```bash
pytest tests/triage/test_triage_core_20_cases.py
```

硬门槛：20/20 `riskLevel` + 逐 case `confidence` 对齐 `case-rule-mapping.md` §五。
