# `xiaozhua_health_agent.schemas` — Agent 入参 / 出参契约

本包定义小爪 AI 健康/兽医分诊 Agent V1 的**可执行契约模型**（Pydantic），对应文档侧 JSON Schema 与 App mock adapter 的字段语义。

**设计依据**：

- `docs/schema/xiaozhua_health_agent_input_schema.v1.json`
- `docs/schema/xiaozhua_health_agent_output_schema.v1.json`
- `docs/README.md` — V1 契约与验收要求
- 架构：`docs/architecture/overall.md` — L1 接入契约、L6 输出契约

---

## 定位与边界

| 做 | 不做 |
|----|------|
| 定义 `AgentInput` / `AgentOutput` 及子模型 | 执行医学裁决（属 Triage Core） |
| 提供枚举、Literal 类型别名 | 结构校验（属 `eval` 包） |
| 作为管道、API、评测的**强类型边界** | 加载 case 或批跑报告 |
| `extra="forbid"`，拒绝未定义字段 | 向量 RAG、规则知识库 |

**可执行真源**：本包 Pydantic 模型。`pyproject.toml` 虽声明 `jsonschema` 依赖，但 WP0 校验路径为 **Pydantic `model_validate`**，与 `eval.schema_validator` 一致。

**文档 JSON Schema** 用于人类阅读与跨团队对齐；改字段时须**同步**更新 `docs/schema` 与本包模型。

---

## 公开 API（门面）

包外代码**只**从 `xiaozhua_health_agent.schemas` 导入：

```python
from xiaozhua_health_agent.schemas import (
    AgentInput,
    AgentOutput,
    PetProfile,
    DataQualityLiteral,
    OutputRiskLevelLiteral,
)
```

完整导出见 `__init__.py` 的 `__all__`。

### 包内引用规则

`schemas` 子模块之间使用**子模块直引**：

```python
from xiaozhua_health_agent.schemas.input_types import PetProfile
```

**不要**在子模块内 `from xiaozhua_health_agent.schemas import ...`，以免循环导入。

### 与 `eval` 的分工

| 包 | 职责 |
|----|------|
| **`schemas`** | 契约**定义** |
| **`eval`** | 契约**校验**、case 加载、评测 |

```python
from xiaozhua_health_agent.schemas import AgentOutput
from xiaozhua_health_agent.eval import validate_output, OutputValidationMode

result = validate_output(payload, mode=OutputValidationMode.FULL)
```

---

## 目录结构

```
schemas/
├── README.md           # 本文档
├── __init__.py         # 公开 API 门面
├── common_types.py     # 跨 input/output 共用类型（confidence）
├── input_types.py      # 入参子模型、枚举、Literal
├── agent_input.py      # AgentInput 顶层
├── output_types.py     # 出参枚举（riskLevel、action route）
└── agent_output.py     # AgentOutput、RiskOnlyOutput、ActionItem
```

### 模块职责

| 模块 | 内容 |
|------|------|
| `common_types` | `Confidence` / `ConfidenceLiteral` |
| `input_types` | 入参全部子模型与枚举；字段使用 **Literal** 作注解真源 |
| `agent_input` | 单次分诊**入参顶层** `AgentInput` |
| `output_types` | 输出 `riskLevel`（不含 `unknown`）、`ActionRouteKind` |
| `agent_output` | 完整出参 `AgentOutput`、WP3 极简 `RiskOnlyOutput`、`ActionItem` |

---

## 顶层契约

### `AgentInput`（入参）

对应 `input_schema.v1` 全部必填顶层字段：

| 字段（JSON） | Python | 说明 |
|-------------|--------|------|
| `caseId` | `case_id` | 稳定 case / 请求标识 |
| `scene` | `scene` | V1 固定 `health_triage` |
| `timestamp` | `timestamp` | ISO-8601，`datetime` |
| `pet` | `pet` | `PetProfile` |
| `device` | `device` | `DeviceState` |
| `vitals` | `vitals` | `Vitals` |
| `healthEvidence` | `health_evidence` | `HealthEvidence` |
| `userReport` | `user_report` | `UserReport` |
| `context` | `context` | `Context` |
| `missingData` | `missing_data` | `list[MissingDataItemLiteral]` |

配置：`populate_by_name=True`（同时接受 alias 与 snake_case）、`extra="forbid"`。

### `AgentOutput`（完整出参）

对应 `output_schema.v1` 全部必填字段（`secondaryAction` 可选）：

| 字段（JSON） | Python | 约束摘要 |
|-------------|--------|----------|
| `riskLevel` | `risk_level` | `normal` / `watch` / `warning` / `emergency` |
| `scene` | `scene` | `health_triage` |
| `title` / `summary` / … | 同名 snake | 文案类字段 `min_length=1` |
| `evidence` | `evidence` | `list[str]` |
| `missingData` | `missing_data` | 用户可读缺失说明 |
| `confidence` | `confidence` | `low` / `medium` / `high` |
| `safetyNotice` | `safety_notice` | 医疗安全边界 |
| `primaryAction` | `primary_action` | `ActionItem`，`label` 非空 |
| `secondaryAction` | `secondary_action` | 可选 `ActionItem` |

禁止输出语义见 `docs/schema` 的 `forbiddenOutputPatterns`（由 WP5 / `eval` 语义评测 enforcement）。

### `RiskOnlyOutput`（WP3 极简出参）

开发计划 **里程碑 A**（20/20 risk）阶段使用：

| 字段 | 必填 | 说明 |
|------|------|------|
| `riskLevel` | 是 | 唯一硬性必填 |
| `scene` | 否 | 省略时下游默认 `health_triage` |
| `confidence` | 否 | risk-only 评测可选比对 |

由 `eval.validate_output(..., mode="minimal")` 校验。

### `ActionItem`

```python
label: str          # 非空，按钮文案
route: str | None   # App 内路由，无则 null
```

---

## 入参子模型速查

| 模型 | 职责 |
|------|------|
| `PetProfile` | 物种、年龄、体重、慢病史、用药、过敏 |
| `DeviceState` | 在线状态、`dataQuality`、`lastSeenAt`、`warningText` |
| `Vitals` | 体温、心率、呼吸、HRV、活动、睡眠；允许 `null` |
| `HealthSignal` | 上游单条 signal（含 `baseline`、`reason`） |
| `HealthEvidence` | 上游聚合风险、`signals[]`；`riskLevel` 含 `unknown` |
| `UserReport` | 用户文本 + 结构化症状布尔/枚举字段 |
| `Context` | 运动、疫苗、年龄风险档、`notes[]` |

### 关键枚举差异

| 概念 | 入参（上游） | 出参（Agent 最终） |
|------|-------------|-------------------|
| 风险等级 | `UpstreamRiskLevelLiteral`（含 `unknown`） | `OutputRiskLevelLiteral`（**无** `unknown`） |
| 单条 signal | `SignalRiskLevelLiteral` | — |

Agent 不得在缺数据时将 `unknown` 直接输出为 `normal`；裁决逻辑在 WP3 Triage Core。

### `dataQuality` 取值

`good` | `partial` | `stale` | `missing` — 对应 DQ-01/02/03 规则与 confidence L/M/H′ 分支。

### `missingData` 取值

`temperature`、`heart_rate`、`respiratory_rate`、`hrv`、`activity`、`user_report`、`device_freshness`、`pet_profile`、`drinking`、`other`。

---

## 输出侧类型

### `OutputRiskLevel` / `OutputRiskLevelLiteral`

`normal` | `watch` | `warning` | `emergency`

与 case `expected.riskLevel`、`AgentOutput.risk_level` 一致。

### `ActionRouteKind` / `ActionRouteKindLiteral`

WP5 `primaryAction` 映射预留：`contact_vet`、`check_device`、`rest_observe`、`record_symptom`、`unknown`。

---

## 命名与序列化约定

| 约定 | 说明 |
|------|------|
| **JSON 字段** | camelCase（`caseId`、`healthEvidence`） |
| **Python 属性** | snake_case（`case_id`、`health_evidence`） |
| **Pydantic alias** | 模型字段带 `alias`，`populate_by_name=True` |
| **严格模式** | 所有模型 `extra="forbid"` |
| **可空字段** | 与 case JSON 一致；**不**在 schemas 层补默认值掩盖缺失（部分枚举字段有 `"unknown"` 默认） |

导出 JSON 给 App 时：

```python
agent_input.model_dump(mode="json", by_alias=True)
agent_output.model_dump(mode="json", by_alias=True)
```

---

## 使用示例

### 从 case 得到强类型入参

```python
from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.schemas import AgentInput

dataset = load_health_triage_dataset()
agent_input: AgentInput = dataset.case_by_id("emergency_seizure").input
```

### 构造 risk-only 出参（WP3 stub）

```python
from xiaozhua_health_agent.schemas import RiskOnlyOutput

stub = RiskOnlyOutput(risk_level="emergency", confidence="high")
```

### 在管道中引用子结构（WP1 FactSheet / WP2 DerivedFacts）

```python
from xiaozhua_health_agent.schemas import (
    AgentInput,
    DataQuality,
    UserReport,
)

def extract_facts(inp: AgentInput) -> dict:
    return {
        "case_id": inp.case_id,
        "data_quality": inp.device.data_quality,
        "seizure": inp.user_report.seizure,
    }
```

---

## 变更管理

1. **改契约字段** → 同步更新 `docs/schema/*.json`、本包模型、`docs/cases/*.json`（若影响 case）
2. **改枚举取值** → 检查 `triage-core` 规则 when、DerivedFacts、case expected
3. **新增字段** → `extra="forbid"` 下旧 JSON 会失败，需版本化或明确 V1.x 扩展策略
4. **校验逻辑** → 只改 `eval`，不在本包重复实现

Schema 版本字符串（`xiaozhua.health_agent.input.v1` 等）目前定义在 `eval.schema_validator`，不在本包；若需统一可新增 `schemas/versions.py` 并在 `__init__.py` re-export。

---

## 回迁映射（正式架构）

| 本包符号 | 回迁目标 |
|---------|----------|
| `AgentInput` + 子模型 | L1 Adapter 入参 DTO + L3 Fact Set 来源 |
| `AgentOutput` | L6 Output Composer 出站 DTO |
| `RiskOnlyOutput` | L7 risk-only 评测 / WP3 中间产物 |
| 枚举与 Literal | 横切 contracts / schema registry |
| `ActionRouteKind` | ActionRouteTableRegistry（KB-ACTION） |

---

## 相关文档

- `docs/README.md` — V1 验收重点
- `docs/cases/health_triage_cases.v1.json` — 20 case 入参实例
- `docs/plans/coze-workflow-dev-plan.md` — WP0 契约、WP3 risk-only
- `eval/README.md` — 校验与评测用法
- `docs/architecture/components/stateless/L1-stateless-components.md` — Adapter 契约
- `docs/architecture/components/stateless/L6-stateless-components.md` — 输出组装契约