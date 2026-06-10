# `xiaozhua_health_agent.eval` — 评测与契约校验

本包对应架构 **L7 评测与观测层** 的无状态子集，以及开发计划 **WP0：评测与契约基础设施**。

当前阶段目标：为 20 case 回归、管道出站检查、批跑报告提供**统一、可复用的评测入口**；**不参与医学裁决**，**不反哺**实时分诊 Pipeline。

---

## 定位与边界

| 做 | 不做 |
|----|------|
| 加载 `health_triage_cases.v1.json` | 计算 `riskLevel`（属 WP3 Triage Core） |
| 校验 input / output 是否符合契约 | 调用 LLM、执行分诊管道 |
| risk-only 评测编排与批跑报告 | 读取历史 Audit 反哺决策 |
| 产出结构化 `ValidationResult` / `Violation` / `RiskEvalReport` | 替代 `schemas` 包中的契约模型定义 |

**设计依据**：

- 契约：`docs/schema/xiaozhua_health_agent_input_schema.v1.json`、`output_schema.v1.json`
- Case 真源：`docs/cases/health_triage_cases.v1.json`
- 开发计划：`docs/plans/coze-workflow-dev-plan.md` § WP0
- 架构：`docs/architecture/overall.md` § L7

---

## 公开 API（门面）

包外代码**只**从 `xiaozhua_health_agent.eval` 导入，勿直接引用子模块：

```python
from xiaozhua_health_agent.eval import (
    load_health_triage_dataset,
    validate_output,
    run_risk_only_evaluation_with_provider,
    assert_risk_only_hard_gate,
    RiskEvalOptions,
)
```

完整导出列表见 `__init__.py` 中的 `__all__`。

### 包内引用规则

`eval` 子模块之间（如 `schema_validator` → `case_dataset`）使用**子模块直引**：

```python
from xiaozhua_health_agent.eval.case_dataset import HealthTriageDataset
from xiaozhua_health_agent.eval.risk_eval_types import build_risk_eval_result
```

**不要**在子模块内 `from xiaozhua_health_agent.eval import ...`，以免与 `__init__.py` 形成循环导入。

### 公开 API 与模块内 API

以下符号**已**列入 `__all__`，可从包门面直接导入：

| 符号 | 说明 |
|------|------|
| `build_risk_eval_result` | 组装单条 `RiskEvalResult`（含 violations 一致性校验） |
| `build_risk_eval_record` | 封装 `RiskEvalRecord` |
| `build_risk_eval_report` | 由记录列表构建 `RiskEvalReport` |
| `summarize_risk_eval_records` | 统计 passed / schema / risk / confidence 匹配数 |

以下符号仅在 `risk_eval_types` 模块内使用，**未**加入 `__all__`：

| 符号 | 说明 |
|------|------|
| `flatten_risk_eval_violations` | 扁平合并分维度违规 |
| `compute_risk_eval_passed` | 应用 confidence 硬门槛后的 `passed` |
| `RiskEvalDimension` / `RiskEvalParsedOutput` | 内部类型别名 |

---

## 目录结构

```
eval/
├── README.md                 # 本文档
├── __init__.py               # 公开 API 门面（唯一对外入口）
├── case_dataset.py           # Case 加载器与数据集模型
├── schema_validator.py       # input / output 契约校验
├── validation_result.py      # ValidationResult、Violation 等共用类型
├── risk_eval_types.py        # risk-only 专用 DTO、维度比对、报告组装
├── risk_evaluator.py         # risk-only 评测编排（单条 / 批量 / provider）
└── batch_runner.py           # 批跑入口、文本报告、CLI
```

### 模块职责

| 模块 | 职责 |
|------|------|
| `case_dataset` | 读取并校验 mock case 数据集；产出 `HealthTriageDataset` |
| `schema_validator` | 基于 Pydantic 模型做结构校验；`ValidationError` → `Violation` |
| `validation_result` | 校验结果、违规码/域、输出校验模式等类型定义 |
| `risk_eval_types` | risk-only 评测 DTO、维度比对、报告组装、违规工厂 |
| `risk_evaluator` | 串联 schema → risk/confidence 比对 → `RiskEvalResult` / `RiskEvalReport` |
| `batch_runner` | `run_batch` 批跑编排、文本报告格式化、CLI 入口 |
| `__init__.py` | 聚合 re-export，定义包级公开契约 |

契约模型本身在 **`xiaozhua_health_agent.schemas`**（`AgentInput`、`AgentOutput`、`RiskOnlyOutput`），本包只负责**校验与评测**，不重复定义字段。

---

## 当前交付状态（WP0）

| 能力 | 状态 | 入口 |
|------|------|------|
| Case 加载器 | ✅ 已交付 | `load_health_triage_dataset` |
| Schema 校验器 | ✅ 已交付 | `validate_input` / `validate_output` |
| 统一结果类型 | ✅ 已交付 | `ValidationResult` / `Violation` |
| Risk-only 专用结果类型 | ✅ 已交付 | `RiskEvalResult` / `RiskEvalReport` 等 |
| Risk-only 维度比对与失败占位 | ✅ 已交付 | `compare_risk_levels`、`build_schema_failed_risk_eval_result` 等 |
| Risk-only 评测器（编排） | ✅ 已交付 | `evaluate_risk_output`、`run_risk_only_evaluation_with_provider` |
| 批跑报告与 CLI | ✅ 已交付 | `run_batch`、`run_risk_only_cli`、`format_risk_eval_report` |
| 语义评测器 | ⏳ 待实现 | `mustMention` / `mustNotMention` / 禁止词 / `safetyNotice` |
| `full-output` 运行模式 | ⏳ 待实现 | `BatchRunMode.FULL_OUTPUT`（依赖语义评测器） |

---

## 核心类型

### 数据集（`case_dataset`）

- **`HealthTriageDataset`**：根对象，固定 20 条 case、`datasetVersion` 校验
- **`CaseRecord`**：单条 case = `input`（`AgentInput`）+ `expected`（`CaseExpected`）
- **`CaseExpected`**：验收约束（`riskLevel`、`confidence`、`mustMention` 等），**不属于** Agent `output_schema`
- **`CaseDatasetError`**：文件不存在、JSON 解析失败等加载错误

常量：

- `DEFAULT_DATASET_VERSION` = `xiaozhua.health_triage_cases.v1`
- `EXPECTED_CASE_COUNT` = `20`

默认 case 路径：`docs/cases/health_triage_cases.v1.json`（由 `paths.default_cases_path()` 解析）。

### 校验结果（`validation_result`）

- **`ValidationResult[TParsed]`**：`passed`、`violations`、`parsed`（通过时的强类型对象）
- **`Violation`**：`code`、`domain`、`path`、`field`、`message`、`severity`
- **`ViolationDomain`**：`schema` / `guard` / `risk_eval` / `semantic_eval`（区分违规来源；**`risk_eval` 不得传入 WP5 重试协调器**）
- **`ViolationCode`**：
  - 契约类：`PARSE_ERROR`、`FIELD_MISSING`、`TYPE_ERROR`、`ENUM_INVALID` 等
  - 评测类：`RISK_MISMATCH`、`CONFIDENCE_MISMATCH`、`CASE_OUTPUT_MISSING`、`EVAL_SKIPPED`
- **`OutputValidationMode`**：
  - `FULL` → 对照完整 `AgentOutput`（里程碑 B）
  - `MINIMAL` → 对照 `RiskOnlyOutput`（WP3 risk-only 阶段）

### Risk-only 评测（`risk_eval_types` + `risk_evaluator`）

#### 策略枚举

| 枚举 | 值 | 含义 |
|------|-----|------|
| `ConfidenceCheckMode` | `off` / `exact` / `tier` | confidence 是否比对；WP3 默认 `off` |
| `ConfidenceHardGateMode` | `soft` / `hard` | confidence 不匹配是否拉低 `passed`；默认 `soft` |
| `RiskEvalRunMode` | `risk-only` | 批跑报告模式标识 |

模型字段使用对应 `*Literal` 类型（如 `ConfidenceCheckModeLiteral`），避免 Pydantic 版本差异。

#### 评测配置（`risk_evaluator.RiskEvalOptions`）

| 字段 | 默认 | 说明 |
|------|------|------|
| `confidence_check_mode` | `off` | confidence 比对策略 |
| `confidence_hard_gate` | `soft` | confidence 不匹配是否拉低 `passed` |
| `bundle_version` | `None` | 可选 triage-core `bundleVersion` pin，写入记录与报告 |
| `dataset_version` | `xiaozhua.health_triage_cases.v1` | 报告元数据 |

`DEFAULT_RISK_EVAL_OPTIONS` 为 WP3 里程碑 A 默认配置（仅比 `riskLevel`）。

#### 结果 DTO（由小到大）

| 类型 | 职责 |
|------|------|
| **`RiskDimensionResult`** | 单维度（`risk` / `confidence`）的 `expected` / `actual` / `passed` / `violations` |
| **`RiskEvalResult`** | 单 case 完整结果：`schema_check` + `risk` + `confidence` + `passed` / `hard_passed` / `soft_passed` + `violations` / `warnings` |
| **`RiskEvalRecord`** | 单 case 记录 + `caseName`、可选 `ruleHits` / `bundleVersion` |
| **`RiskEvalReport`** | 20 case 批跑汇总：`passed` / `failed` / `failedCaseIds` / 分维度统计 |

#### `passed` 语义（硬门槛）

默认（`confidence_hard_gate=soft`）：

```
passed = schema（minimal）通过 ∧ riskLevel 与 expected 一致
```

- **`hard_passed`**：仅 schema + risk，不受 confidence 影响
- **`soft_passed`**：hard 通过且（未检查 confidence 或 confidence 通过）
- **`warnings`**：`confidence_hard_gate=soft` 且 confidence 不匹配时填充，**不**拉低 `passed`

`RiskEvalResult` 须通过 `build_risk_eval_result` 构造，以保证扁平 `violations` 与分维度结果一致。

#### 评测编排（`risk_evaluator`）

单条 case 固定流程：

```
actual_output
  → None? → CASE_OUTPUT_MISSING
  → validate_output(mode=MINIMAL)
  → schema 失败? → 结构违规，跳过 risk 比对
  → compare_risk_levels / compare_confidence_levels
  → build_risk_eval_result
```

| 函数 | 职责 |
|------|------|
| `evaluate_risk_output` | 单条输出评测 |
| `evaluate_risk_for_case` | 单条 `CaseRecord` + 可选 `ruleHits` |
| `evaluate_all_cases` | 映射 `outputs_by_case_id` 批量评测 |
| `evaluate_all_cases_with_provider` | 回调 `TriageOutputProvider` 生成并评测 |
| `run_risk_only_evaluation` | 返回 `RiskEvalReport` |
| `run_risk_only_evaluation_with_provider` | provider 版批跑 |
| `make_golden_outputs_from_dataset` | 用 `expected` 构造 stub（评测器自检） |
| `assert_risk_only_hard_gate` | pytest / CI 断言 20/20 |

**`TriageOutputProvider`**：`Callable[[AgentInput], ActualOutputPayload]`，WP3 Triage Core 接入点。  
`ActualOutputPayload` = `dict` / `AgentOutput` / `RiskOnlyOutput` / `None`。  
输出 dict 可含非 schema 调试字段 `ruleHits[]`，评测器会自动抽取到 `RiskEvalRecord`。

#### 批跑（`batch_runner`）

**`BatchRunConfig`** 输出来源优先级：

1. 显式传入 `outputs_by_case_id`
2. 显式传入 `provider`
3. `config.outputs_json_path`
4. `config.use_golden_outputs=True`
5. 否则全部视为缺输出

| 函数 | 职责 |
|------|------|
| `run_batch` | 按配置执行 risk-only 批跑 |
| `load_outputs_from_json` | 从 JSON 加载 caseId → output 映射 |
| `format_risk_eval_report` | 人类可读多行报告 |
| `write_risk_eval_report` | 写入 stdout 或指定流 |
| `run_risk_only_cli` | CLI 入口（`batch_runner.main`） |

**CLI 示例**：

```bash
# 评测器自检（golden stub，应 20/20）
python -m xiaozhua_health_agent.eval.batch_runner --golden

# 对接 pipeline 预置输出
python -m xiaozhua_health_agent.eval.batch_runner --outputs path/to/outputs.json

# 可选 confidence 检查 + JSON 报告
python -m xiaozhua_health_agent.eval.batch_runner \
  --confidence exact \
  --json-report report.json
```

退出码：硬门槛全绿为 `0`，否则为 `1`。

#### 公开辅助函数（`__all__` 已导出）

| 函数 | 职责 |
|------|------|
| `compare_risk_levels` | expected vs actual → `RiskDimensionResult` |
| `compare_confidence_levels` | confidence 维度比对（`off` 时返回未执行占位） |
| `extract_risk_level_from_parsed` / `extract_confidence_from_parsed` | 从 `RiskOnlyOutput` / `AgentOutput` 抽取字段 |
| `build_schema_failed_risk_eval_result` | schema 未通过时的完整失败结果 |
| `build_missing_output_risk_eval_result` / `build_missing_output_risk_eval_record` | 批跑缺输出时的失败结果/记录 |
| `make_risk_mismatch_violation` 等 | 构造 `domain=risk_eval` 的 `Violation` |
| `compute_hard_passed` / `compute_soft_passed` | 聚合 passed 标志 |
| `collect_flat_violations` / `partition_risk_eval_violations` | 硬违规与软警告拆分 |
| `count_violations_by_code` / `iter_all_record_violations` | 批跑报告统计 |
| `minimal_output_validation_mode` | 固定返回 `"minimal"` |

类型别名：`SchemaCheckParsed` = `RiskOnlyOutput | AgentOutput`；`RiskDimensionKind` = `RiskEvalDimension` 的兼容别名。

### Schema 版本

- `INPUT_SCHEMA_VERSION` = `xiaozhua.health_agent.input.v1`
- `OUTPUT_SCHEMA_VERSION` = `xiaozhua.health_agent.output.v1`

与 `docs/schema/*.json` 语义对齐；**可执行真源**为 `schemas` 包中的 Pydantic 模型。

---

## 使用示例

### 加载 20 case

```python
from xiaozhua_health_agent.eval import load_health_triage_dataset

dataset = load_health_triage_dataset()
print(len(dataset.cases))  # 20

case = dataset.case_by_id("emergency_seizure")
agent_input = case.input
expected = case.expected
```

### 校验入参

```python
from xiaozhua_health_agent.eval import validate_input

result = validate_input(agent_input)
if not result.passed:
    for v in result.violations:
        print(v.code, v.domain, v.path, v.message)
else:
    parsed = result.parsed  # AgentInput
```

### 批量校验全部 case 入参

```python
from xiaozhua_health_agent.eval import (
    load_health_triage_dataset,
    validate_all_case_inputs,
    summarize_validation_results,
)

dataset = load_health_triage_dataset()
records = validate_all_case_inputs(dataset)
passed, failed = summarize_validation_results(r.result for r in records)
print(f"input schema: {passed} passed, {failed} failed")
```

### 校验出参（risk-only / full）

```python
from xiaozhua_health_agent.eval import OutputValidationMode, validate_output

# WP3 阶段：仅 risk + 可选 confidence
stub = {"riskLevel": "emergency", "confidence": "high"}
result = validate_output(stub, mode=OutputValidationMode.MINIMAL)

# 里程碑 B：完整 output_schema
full = {
    "riskLevel": "watch",
    "scene": "health_triage",
    "title": "...",
    # ... 其余必填字段
}
result = validate_output(full, mode=OutputValidationMode.FULL)
```

### Risk-only 单条评测

```python
from xiaozhua_health_agent.eval import (
    evaluate_risk_for_case,
    load_health_triage_dataset,
)

dataset = load_health_triage_dataset()
case = dataset.case_by_id("high_fever_resting")

record = evaluate_risk_for_case(
    case,
    {"riskLevel": "warning", "confidence": "high"},
)
print(record.result.passed, record.result.risk.actual)
```

### Risk-only 批跑（预置输出映射）

```python
from xiaozhua_health_agent.eval import (
    load_health_triage_dataset,
    make_golden_outputs_from_dataset,
    run_risk_only_evaluation,
    assert_risk_only_hard_gate,
)

dataset = load_health_triage_dataset()
outputs = make_golden_outputs_from_dataset(dataset)

report = run_risk_only_evaluation(dataset, outputs)
assert_risk_only_hard_gate(report)  # 评测器自检：20/20
```

### Risk-only 批跑（对接 Triage Core，WP3）

```python
from xiaozhua_health_agent.eval import (
    RiskEvalOptions,
    load_health_triage_dataset,
    run_risk_only_evaluation_with_provider,
    assert_risk_only_hard_gate,
)

def triage_stub(agent_input):
    # WP3：替换为 TriageCore.run(agent_input) 的 minimal 输出
    return {"riskLevel": "watch", "confidence": "medium"}

dataset = load_health_triage_dataset()
options = RiskEvalOptions(bundle_version="1.0.0")

report = run_risk_only_evaluation_with_provider(
    dataset,
    triage_stub,
    options=options,
)
assert_risk_only_hard_gate(report)
```

### 批跑 CLI 与程序化入口

```python
from xiaozhua_health_agent.eval import BatchRunConfig, run_batch, write_risk_eval_report

config = BatchRunConfig(use_golden_outputs=True)
report = run_batch(config)
write_risk_eval_report(report)
```

### 管道出站检查（WP5 复用）

分诊管道合并输出后，在返回 App 前调用：

```python
from xiaozhua_health_agent.eval import OutputValidationMode, validate_output

check = validate_output(output_dict, mode=OutputValidationMode.FULL)
if not check.passed:
    # 触发重试或模板兜底，不得修改 TriageCoreResult 中的 risk/confidence
    ...
```

### 低层手动组装（测试或自定义编排）

需要细粒度控制时，可组合 `validate_output` + `compare_risk_levels` + `build_risk_eval_result`；  
日常批跑请优先使用 `evaluate_risk_output` / `run_risk_only_evaluation`，见 `risk_evaluator.py`。

---

## 与 `schemas` 包的分工

| 包 | 职责 |
|----|------|
| `schemas` | 契约**定义**（Pydantic 模型、枚举、Literal） |
| `eval` | 契约**校验**、case **加载**、risk-only **评测与批跑**、未来语义评测 |

推荐引用方式：

```python
# 类型与领域对象
from xiaozhua_health_agent.schemas.agent_input import AgentInput
from xiaozhua_health_agent.schemas.agent_output import AgentOutput

# 校验与评测
from xiaozhua_health_agent.eval import (
    validate_input,
    validate_output,
    run_risk_only_evaluation_with_provider,
)
```

---

## 评测维度与门槛（对照开发计划）

### 结构评测（`schema_validator`，已覆盖）

- input / output 必填字段、类型、枚举合法性
- `extra="forbid"`，拒绝未定义字段

### Risk 评测（`risk_evaluator` + `risk_eval_types`，已覆盖）

| 维度 | 规则 | 门槛 | 状态 |
|------|------|------|------|
| riskLevel | 与 `expected.riskLevel` **精确一致** | **硬** | ✅ |
| confidence | 与 expected 一致（`exact`/`tier`）；默认 `off` 不阻断 `passed` | 软（默认）/ 硬（`confidence_hard_gate=hard`） | ✅ |

### 待实现（WP0 续项 / WP5）

| 维度 | 规则 | 门槛 |
|------|------|------|
| mustMention / mustNotMention | 关键词命中（可借助 KB-SYN） | 软 / 硬 |
| forbiddenPatterns | `output_schema` 禁止词 | **硬** |
| safetyNoticeRequired | 为 true 时 `safetyNotice` 非空 | **硬** |

硬门槛目标（里程碑 A）：**20/20 riskLevel**、0 minimal 结构错误。里程碑 B 再加文案与禁止词硬门槛（`BatchRunMode.FULL_OUTPUT`）。

---

## 失败排查顺序

与 `pipeline-design.md` §9.4 / 开发计划 §7.2 一致：

1. **risk 错** → 改 Triage Core（`triage-core.v1.json` / DerivedFacts），**不要先改 LLM Prompt**
2. **结构错** → `validate_*` 的 `violations`（`domain=schema`）；检查字段缺失或类型
3. **confidence 错** → 决策表 `confidence` 区块（L / H′ / H / M）；评测侧看 `RiskEvalResult.warnings`
4. **mustMention 缺** → `ForcedMentionsByFlag` 或 KB-SYN（语义评测器，待实现）
5. **禁止词 / emergency 语气** → KB-FORBID、policyTables、KB-TPL
6. **case 加载失败** → 检查 `docs/cases/` 路径、`caseId` 一致性、是否满 20 条
7. **批跑缺输出** → `CASE_OUTPUT_MISSING`；检查 pipeline 是否对该 caseId 返回结果

---

## 回迁映射（正式架构）

| 本包模块/能力 | 回迁目标 |
|--------------|----------|
| `case_dataset` | L7 case 加载 + 契约夹具 |
| `schema_validator` | L6 出站 Schema 校验 + L1 入参校验 |
| `validation_result` | L7 评测结果模型（含 `ViolationDomain`） |
| `risk_eval_types` | L7 RiskEvaluator 结果 DTO + 报告组装 |
| `risk_evaluator` | L7 Eval Facade（risk 维度编排） |
| `batch_runner` | L7 Regression Runner（`risk-only` 模式） |
| 未来语义评测 | L7 Eval Facade（语义维度） |
| 未来 `full-output` | `batch_runner` + 语义评测组合 |

---

## 扩展指南

新增评测能力时：

1. 在 `eval/` 下新增模块（如 `semantic_evaluator.py`）
2. 在 `__init__.py` 中 re-export 公开符号并更新 `__all__`
3. 更新本文档「当前交付状态」表
4. 包外调用方**不**改 import 路径

私有实现（`_` 前缀函数、未列入 `__all__` 的组装函数）**不**从包门面导出。

新增 `ViolationCode` 时：

- 契约/守卫类 → `domain=schema` 或 `guard`，可进入 WP5 重试白名单
- 评测类 → `domain=risk_eval` 或 `semantic_eval`，**仅**用于批跑报告

实现 `full-output` 时：在 `batch_runner.run_batch` 中组合语义评测器，勿破坏现有 `risk-only` 路径。

---

## 相关文档

- `docs/README.md` — V1 验收重点
- `docs/plans/coze-workflow-dev-plan.md` — WP0～WP7 完整计划
- `docs/implementation/coze/pipeline-design.md` — ⑤ 出站校验、§9 评测方案
- `docs/architecture/components/stateless/L7-stateless-components.md` — L7 组件设计（回迁参考）
