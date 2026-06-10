# `xiaozhua_health_agent.parse` — 输入解析（步骤 ①）

本包对应开发计划 **WP1：① 输入解析（Parse & Fact Extract）**，将 App / mock case 的 JSON 入参转为管道中间对象 **`FactSheet`**，供后续 Triage Core（WP2/WP3）消费。

**设计依据**：

- `docs/implementation/coze/pipeline-design.md` § 三（步骤 ①）
- `docs/plans/coze-workflow-dev-plan.md` § WP1
- 架构：`docs/architecture/overall.md` — L1 接入层、L3 上下文构建层（Fact Set 子集）
- 架构组件：`docs/architecture/components/stateless/L1-stateless-components.md`（L1-01/02/07）
- 架构组件：`docs/architecture/components/stateless/L3-stateless-components.md`（L3-01）

---

## 定位与边界

| 做 | 不做 |
|----|------|
| 编排契约校验 → 归一化 → 事实提取 | 医学风险裁决（属 WP3 Triage Core） |
| 产出客观 **`FactSheet`** 与 **`fact_index`** | 计算 **DerivedFacts**（属 WP2） |
| 表示归一化（trim、数组去重排序） | 补全缺失字段、把 `null` 填为默认值 |
| 失败时返回结构化 **`ParseResult`**，不 silent pass | 鉴权、Session、`/intelligent` 多轮 |
| 复用 **`eval.validate_input`** 做契约校验 | 重复实现 Pydantic 校验逻辑 |

**核心信条**（与 `pipeline-design.md` 一致）：

1. **输入即上下文** — 只引用当次 input 可核对事实  
2. **缺数据不编造** — `null` 显式保留  
3. **薄 Adapter** — 不做医学判断、不修改原始医学含义  

---

## 管道位置

```mermaid
flowchart LR
    IN["App / case JSON"]
    V["eval.validate_input<br/>L1-01"]
    N["normalize_agent_input<br/>L1-02"]
    E["extract_fact_sheet<br/>L3-01 子集"]
    FS["FactSheet"]
    TC["WP2/WP3 Triage Core"]

    IN --> V --> N --> E --> FS --> TC
```

| 步骤 | 函数 | 架构映射 |
|------|------|----------|
| 契约校验 | `eval.validate_input` | L1-01 InputValidator |
| 表示归一化 | `normalize_agent_input` | L1-02 InputNormalizer |
| 事实提取 | `extract_fact_sheet` | L3-01 FactSetExtractor |
| 门面编排 | `parse_input` | L1-07 HealthTriageAdapterFacade 子集 |

---

## 公开 API（门面）

包外代码**只**从 `xiaozhua_health_agent.parse` 导入：

```python
from xiaozhua_health_agent.parse import (
    FactSheet,
    parse_input,
    ParseResult,
    parse_all_case_inputs,
)
```

完整导出见 `__init__.py` 的 `__all__`。

### 包内引用规则

`parse` 子模块之间使用**子模块直引**：

```python
from xiaozhua_health_agent.parse.parse_types import FactSheet
from xiaozhua_health_agent.parse.normalizer import normalize_agent_input
```

**不要**在子模块内 `from xiaozhua_health_agent.parse import ...`，以免循环导入。

### 跨包引用规则

| 依赖包 | 导入方式 | 用途 |
|--------|----------|------|
| `xiaozhua_health_agent.schemas` | 仅从包 `__init__.py` | `AgentInput` 及子模型类型 |
| `xiaozhua_health_agent.eval` | 仅从包 `__init__.py` | `validate_input`、`ValidationResult`、`Violation` |

**禁止**：`parse` → `eval` 子模块直引以外的层（如 `triage`）；`schemas` / `eval` 不得依赖 `parse`。

### 与 `schemas` / `eval` 的分工

| 包 | 职责 |
|----|------|
| **`schemas`** | 契约**定义**（`AgentInput` 等 Pydantic 模型） |
| **`eval`** | 契约**校验**、case 加载、输出评测（WP0） |
| **`parse`** | 校验通过后的**归一化 + 事实提取**（WP1） |

```python
from xiaozhua_health_agent.eval import validate_input
from xiaozhua_health_agent.parse import parse_input

# parse_input 内部已调用 validate_input；一般无需重复校验
result = parse_input(raw_json)
```

---

## 目录结构

```
parse/
├── README.md           # 本文档
├── __init__.py         # 公开 API 门面
├── parse_types.py      # FactSheet 分组模型、NormalizationProfile
├── normalizer.py       # L1-02 入参归一化
├── fact_extractor.py   # L3-01 事实提取与 fact_index
└── parser.py           # 门面编排、ParseResult、批解析
```

### 模块职责

| 模块 | 内容 |
|------|------|
| `parse_types` | `FactSheet` 及 `IdentityFacts` / `VitalsFacts` 等分组；`NormalizationProfile` |
| `normalizer` | `normalize_agent_input`、`timestamp_to_epoch_ms` |
| `fact_extractor` | `extract_fact_sheet`、`build_fact_index`、`get_fact_value` |
| `parser` | `parse_input`、`parse_agent_input`、`parse_all_case_inputs`、`ParseResult` |

---

## 核心类型

### `FactSheet`（步骤 ① 产出）

客观事实清单，按 `pipeline-design.md` §3.2 分组：

| 分组字段 | 内容 |
|----------|------|
| `identity` | caseId、petId、name、species、ageMonths、breed |
| `profile` | sex、weightKg、neutered、慢病/用药/过敏 |
| `device` | deviceOnline、dataQuality、lastSeenAt、warningText 等 |
| `vitals` | 体征数值与 activityLevel / sleepQuality（`null` 保持） |
| `upstream` | healthEvidence 原文（riskLevel、signals[]，作上游「声称」） |
| `user_report` | 用户自述结构化字段 + `text` |
| `context` | recentExercise、ageRisk、notes[] 等 |
| `missing_data` | App 声明的缺失项列表 |
| `fact_index` | 稳定路径 → 原始值（供 evidence 回溯） |

另含顶层：`scene`、`timestamp`、`timestamp_epoch_ms`（管道内部元数据）。

### `ParseResult`（步骤 ① 出站）

| 字段 | 说明 |
|------|------|
| `passed` | 是否校验通过并成功构建 FactSheet |
| `violations` | 失败时的契约违规项（来自 `eval`） |
| `schema_validation` | 完整 `ValidationResult[AgentInput]` |
| `agent_input` | 归一化后的入参（仅 `passed=True`） |
| `fact_sheet` | 事实清单（仅 `passed=True`） |

### `NormalizationProfile`

| 字段 | 默认 | 说明 |
|------|------|------|
| `trim_strings` | `true` | 字符串首尾裁剪 |
| `dedupe_string_arrays` | `true` | 字符串数组去重 |
| `sort_string_arrays` | `true` | 字符串数组稳定排序 |
| `attach_timestamp_epoch_ms` | `true` | 附加 Unix 毫秒时间戳 |

**明确不做**：数值四舍五入、`null` → 默认值、枚举医学含义改写。

---

## `fact_index` 约定

键前缀为 `fact.`（常量 `FACT_INDEX_PREFIX`），示例：

| 路径键 | 含义 |
|--------|------|
| `fact.vitals.temperatureC` | 当前体温或 `null` |
| `fact.healthEvidence.riskLevel` | 上游综合风险 |
| `fact.userReport.seizure` | 用户是否报告抽搐 |
| `fact.device.dataQuality` | 设备数据质量 |
| `fact.missingData` | 缺失项列表 |

读取辅助：

```python
from xiaozhua_health_agent.parse import get_fact_value, fact_index_contains

get_fact_value(sheet, "vitals.temperatureC")      # 可省略 fact. 前缀
fact_index_contains(sheet, "fact.userReport.seizure")
```

显式 `null` 会写入索引（键存在、值为 `None`），便于 L5 证据真实性审查。

---

## 使用示例

### 单条 case 解析

```python
from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.parse import parse_input

dataset = load_health_triage_dataset()
case = dataset.case_by_id("emergency_seizure")

result = parse_input(case.input)
if not result.passed:
    raise RuntimeError(result.violations)

sheet = result.fact_sheet
assert sheet is not None
assert sheet.user_report.seizure is True
```

### 原始 JSON 解析

```python
import json
from pathlib import Path
from xiaozhua_health_agent.parse import parse_input

raw = json.loads(Path("payload.json").read_text(encoding="utf-8"))
result = parse_input(raw)
```

### 20 case 批解析

```python
from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.parse import parse_all_case_inputs, assert_all_parse_passed

dataset = load_health_triage_dataset()
records = parse_all_case_inputs([c.input for c in dataset.cases])
assert_all_parse_passed(records)
```

### 仅归一化 / 仅提取（单测或调试）

```python
from xiaozhua_health_agent.parse import normalize_agent_input, extract_fact_sheet

normalized = normalize_agent_input(agent_input)
sheet = extract_fact_sheet(normalized)
```

---

## 验收与测试

单测目录：`tests/parse/`。

```bash
# 仅 WP1
pytest tests/parse/ -v

# 含 WP0 全量
pytest tests/ -v
```

**WP1 验收要点**（见开发计划）：

| 场景 | 期望 |
|------|------|
| 20 case input | 全部 `passed=True` |
| `missing_vitals` | 核心体征保持 `null` |
| `stale_device_data` | `data_quality == "stale"` |
| 缺必填字段 | `passed=False`，`FIELD_MISSING` |
| 非法 `scene` | 契约校验失败，无 FactSheet |

---

## 错误语义

- 契约失败 → `passed=False`，`fact_sheet=None`，**不进入**后续医学步骤  
- `violations[].path` 为点分 JSON 路径（与 `eval` 一致）  
- 归一化与提取**不抛业务异常**；仅编程错误或未预期状态会抛标准 Python 异常  

---

## 回迁映射（正式架构）

| 本包符号 | 回迁目标 |
|---------|----------|
| `parse_input` | L1 AdapterFacade 入参路径 |
| `normalize_agent_input` | L1-02 InputNormalizer |
| `extract_fact_sheet` / `FactSheet` | L3-01 FactSetExtractor |
| `fact_index` | L3 `factIndex` / Decision Context Package |
| `ParseResult` | L2 管道上下文 DTO（步骤 ① 出站） |

---

## 相关文档

- `docs/plans/coze-workflow-dev-plan.md` — WP1 交付与验收  
- `docs/implementation/coze/pipeline-design.md` — 五模块管道总览  
- `docs/implementation/coze/kb-rule-derived-facts-spec.md` — WP2 DerivedFacts（**不在本包**）  
- `schemas/README.md` — 入参契约模型  
- `eval/README.md` — WP0 契约校验与批跑评测  
