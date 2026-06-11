# 小爪 AI 健康/兽医分诊 Agent V1 — 实现与架构/开发计划一致性比对报告

**文档类型**：交付存档 / 一致性审计  
**比对范围**：`xiaozhua-health-agent` 当前实现 vs `docs/architecture` + `docs/implementation/coze` + `docs/plans/coze-workflow-dev-plan.md`  
**声明范围**：WP0–WP5（评测与契约 → 验证重试与合并输出）  
**运行时选型**：FastAPI（替代 Coze 工作流编排）  
**报告日期**：2026-06-09  

---

## 摘要

在 **Coze 快速验证版 + WP0–WP5** 范围内，当前 `xiaozhua-health-agent` 实现与架构设计、开发计划在 **医学逻辑、五模块管道语义、契约约束、20 case 验收闭环** 上 **高度一致**。

主要差异集中在三类：

1. **有意简化**：未实现鉴权、Session、`/intelligent`、ConfigRelease、审计持久化、向量 RAG 等（与 V1 计划声明一致）。
2. **工程形态**：采用 **Code-First Python 模块** 替代设计文档中的 **单文件 `triage-core.v1.json`**；采用 **FastAPI** 替代 Coze 节点编排。
3. **默认运行路径**：里程碑 B 验收走 **机械文案 + ValidateContent**；LLM 文案路径已实现但 **默认关闭**（`llm_enabled=False`）。

**里程碑判定（按开发计划）**：

| 里程碑 | 状态 | 说明 |
|--------|------|------|
| A：医学正确（20/20 risk） | 已达成（测试设计） | `test_triage_core_20_cases.py` 等 |
| B：产品可演示（full-output 硬门槛） | 已达成（机械路径） | `test_milestone_b_batch.py` 等 |
| C：可演进（回迁文档） | 未开始 | 属 WP7 |
| WP6：HTTP 集成完整验收 | 部分超前 | API 骨架已有，未按 WP6 全项验收 |

---

## 1. 比对依据

### 1.1 契约与验收真源

| 文档/制品 | 路径 | 角色 |
|-----------|------|------|
| 项目说明 | `docs/README.md` | V1 验收重点、红线 |
| 输入契约 | `docs/schema/xiaozhua_health_agent_input_schema.v1.json` | Agent 入参 |
| 输出契约 | `docs/schema/xiaozhua_health_agent_output_schema.v1.json` | Agent 出参 |
| Mock Case | `docs/cases/health_triage_cases.v1.json` | 20 case 验收真源 |

### 1.2 完整架构（回迁目标）

| 文档 | 路径 | 角色 |
|------|------|------|
| 七层总览 | `docs/architecture/overall.md` | L1–L7 + 横切 + 原则 |
| 组件依赖 | `docs/architecture/rules/component-dependency-rules.md` | 分层边界与禁止项 |
| 全局基础设施 | `docs/architecture/infrastructure-overview.md` | Bootstrap / Redis / Healthz 等 |

### 1.3 快速验证版设计（实现规格）

| 文档 | 路径 | 角色 |
|------|------|------|
| 五模块管道 | `docs/implementation/coze/pipeline-design.md` | ①–⑤ 步骤与中间对象 |
| 决策表规范 | `docs/implementation/coze/triage-core-spec.md` | ② 单文件决策表 schema |
| Case 映射 | `docs/implementation/coze/case-rule-mapping.md` | 规则主表 + 验收总表 |
| 文案模板 | `docs/implementation/coze/kb-tpl-template-spec.md` | KB-TPL 制品规范 |

### 1.4 开发计划

| 文档 | 路径 | 角色 |
|------|------|------|
| WBS 与里程碑 | `docs/plans/coze-workflow-dev-plan.md` | WP0–WP7、硬/软门槛 |

### 1.5 被审计实现

| 项目 | 路径 | 说明 |
|------|------|------|
| 应用代码 | `xiaozhua-health-agent/src/xiaozhua_health_agent/` | 主实现 |
| 知识资产 | `xiaozhua-health-agent/assets/` | KB-TPL、KB-FORBID 等 |
| 测试 | `xiaozhua-health-agent/tests/` | 回归与里程碑断言 |

---

## 2. 总体对齐关系

开发计划要求：**5 步管道 + 3 个中间对象 + 知识资产三分法**（决策表单源、模板管话术、mapping 管验收）。

当前实现用 Python 包承载同一语义：

| 文档概念 | 实现模块 | 对应架构层（简化映射） |
|---------|---------|----------------------|
| ① 输入解析 | `parse/` | L1 精简 + L3 Fact Set 子集 |
| DerivedFacts + evalWhen | `context/` | L3 上下文构建子集 |
| ② 确定性分诊核 | `triage/` | L4 决策核心 |
| ③ 文案生成 | `copy/` | L4 LLM 限权 + 横切 Template |
| ④ 验证与重试 | `guard/` + `pipeline/retry_*` | L5 Safety Guard + L2 Retry 简化 |
| ⑤ 合并与输出 | `output/` + `pipeline/merge_*` | L6 Output Composer |
| 管道编排 | `pipeline/` | L2 Orchestrator 简化 |
| 评测与契约 | `eval/` | L7 Eval（无持久化 Audit） |
| HTTP 接入 | `api/` | L1 接入（部分，超前于 WP5） |

**与完整七层的关系**：实现了 **L3 子集 + L4 + L5 + L6 + L7 评测子集**；**未实现** L1 AccessGate、L2 SessionStore、L4 LLM Pool 有状态、L7 AuditSink 持久化、横切 ConfigRelease、全局 infra——与开发计划 **§1.2 V1 明确不做** 一致。

---

## 3. 管道与中间对象一致性

### 3.1 五模块管道

设计（`pipeline-design.md`）：

```
① 输入解析 → ② 确定性分诊核 → ③ 文案生成 → ④ 验证与重试 → ⑤ 合并与输出
```

实现（`pipeline/mechanical_core.py` + `pipeline/health_triage.py`）：

```
parse_input → run_triage_core → resolve_copy_template
→ run_draft_retry_coordinator_async（含 ValidateContent）
→ merge_and_validate_with_fallback_async → 出站 output_schema 校验
```

**结论**：步骤语义、数据流向、② 裁决字段锁定原则 **一致**。

### 3.2 三个中间对象

| 对象 | 设计产出步骤 | 实现类型 | 锁定约束 |
|------|-------------|---------|---------|
| **FactSheet** | ① | `parse.FactSheet` | 不含医学推断；缺值不补 |
| **TriageCoreResult** | ② | `triage.TriageCoreResult` | ③④⑤ 不得改 `finalRiskLevel`、`confidence`、PolicyTables 锁定字段 |
| **DraftCopyJSON** | ③ | `copy.DraftCopyJSON` | 可重试；失败由机械兜底 |

**结论**：与开发计划 §2.3 状态边界 **一致**。

### 3.3 核心设计信条对照

| 信条 | 实现验证 |
|------|---------|
| risk 由确定性逻辑裁决，LLM 只写文案 | `run_triage_core` 产出 risk；`merge_output` 从 ② 取 `riskLevel` |
| 输入即上下文，不编造 | FactSheet 边界 + `EvidenceAuthenticityChecker` |
| 模板选句式，LLM 填槽，Tool 守合规 | `template_resolver` + `guard/content_validator` |
| 重试是补救，模板兜底是底线 | `retry_coordinator` + `merge_fallback` + `mechanical_draft` |
| 知识库 = 配置非 RAG | 无向量检索；JSON 制品 + Python 规则表 |

---

## 4. 分工作包（WP）逐项比对

### 4.1 WP0：评测与契约基础设施 — **一致（且超出计划）**

#### 计划交付物 vs 实现

| 计划交付物 | 实现位置 | 状态 |
|-----------|---------|------|
| Case 加载器 | `eval/case_dataset.py` | ✅ |
| Schema 校验器 | `eval/schema_validator.py` + `schemas/` | ✅ |
| Risk-only 评测器 | `eval/risk_evaluator.py` | ✅ |
| 语义评测器 | `eval/semantic_evaluator.py` | ✅ |
| 批跑报告 | `eval/batch_runner.py` | ✅ |
| risk-only / full-output 模式 | `BatchRunMode` | ✅ |

#### 超出计划但合理的扩展

- `eval/action_matrix.py`：primaryAction 与 policy/KB-ACTION 交叉验证
- `eval/copy_llm_batch.py`：通义 LLM 文案批跑
- `eval/text_corpus.py`：语义评测语料构建

#### 与完整 L7 的差异

- **有**：结构/风险/语义评测、批跑 CLI、硬门槛断言
- **无**：请求级 AuditSink 持久化、Metrics 后端、RegressionHistory 库

**WP0 结论**：✅ 一致；评测能力满足 WP0 验收，且为 WP3–WP5 提供回归基础设施。

---

### 4.2 WP1：① 输入解析 — **一致**

#### 职责对照

| 要求 | 实现 |
|------|------|
| `scene=health_triage`、必填字段、ISO-8601 | `parse/parser.py` + `schemas/agent_input.py` |
| 枚举归一化 | `parse/normalizer.py` |
| FactSheet 构建（§3.2 分组） | `parse/fact_extractor.py` |
| 缺字段明确失败，不 silent pass | `ParseResult.passed` + 测试 |

#### 测试锚点

- `tests/parse/test_parser.py`：20 case 解析、missing 不补值

**WP1 结论**：✅ 一致；对应 L1 Adapter 精简 + L3 Fact Set Builder 子集。

---

### 4.3 WP2：DerivedFacts + evalWhen — **一致**

#### DerivedFacts（`kb-rule-derived-facts-spec.md`）

实现于 `context/derived_facts.py`，包含 spec 全部关键符号，例如：

| 符号 | 关键用途 | 边界 case |
|------|---------|-----------|
| `hasExerciseContext` | 运动后降级 | #2/#5 vs #3/#4 |
| `severeRestingResp` | EMG-04 门槛 | #4 vs #12 |
| `userSaysNormal` + `deviceShowsRestingFever` | CTX-05 | #11 |
| `hasRestingTachycardia` / `hasRestingTachypnea` | CTX-03 vs CTX-04 | #6 vs #20 |

#### evalWhen 引擎

- 实现：`context/when_evaluator.py`
- 支持：`all` / `any` / `fact` / `field` 结构化条件块
- **未实现**：字符串谓词 DSL（与设计一致）

#### 测试锚点

- `tests/context/test_derived_facts.py`
- `tests/context/test_when_evaluator.py`

**WP2 结论**：✅ 一致。

---

### 4.4 WP3：② 确定性分诊核 — **语义一致，制品形态不同**

#### 4.4.1 执行顺序 — **一致**

`run_triage_core`（`triage/triage_core.py`）严格遵循计划 §4.2：

```
DerivedFacts 预计算
→ 层1 EMG → 层2 DQ → 层3 CTX（按 priority）
→ ResolvePrimaryFlag
→ fusion（max 候选 + floor + 特殊规则）
→ ConfidenceResolver（L → H′ → H → M）
→ PolicyTablesResolve
→ missingDataUser 翻译
→ EvidenceBuilder
→ TriageCoreResult
```

#### 4.4.2 规则覆盖 — **完整**

`rules_v1.py` 规则 ID 清单（22 条）：

| 层级 | 规则 ID |
|------|---------|
| EMG | EMG-01, EMG-02, EMG-03, EMG-04 |
| DQ | DQ-01, DQ-02, DQ-03 |
| CTX | CTX-01 ~ CTX-15（含 CTX-09a/b） |

与 `case-rule-mapping.md` §四 主表 **一一对应**。

#### 4.4.3 TriageCoreResult 字段 — **一致**

| 字段 | 实现来源 |
|------|---------|
| `finalRiskLevel` | `fusion.py` |
| `confidence` | `confidence_resolver.py`（L/H′/H/M） |
| `primaryFlag` | `primary_flag_resolver.py` |
| `forcedMentions` / `forbiddenThemes` | `policy_resolve.py` ← `policy_data.py` |
| `evidenceBullets` | `evidence_builder.py` |
| `missingDataUser` | `missing_data.py` |
| `primaryActionHint` | `policy_data.ACTION_BY_FLAG_RISK` |
| `safetyNoticeRequired` | `policy_data.SAFETY_BY_FLAG` |
| `arbitrationNote` | `fusion.py` |
| `ruleHits` | `rule_engine.py` |
| `bundleVersion` | `BUNDLE_VERSION = "1.0.0"` |

#### 4.4.4 关键医学逻辑检查清单

| 场景 | 计划要求 | 实现要点 | 测试 |
|------|---------|---------|------|
| 运动后体温/心率偏高 | watch，非 warning | CTX-09a/b + CTX-01/02 排除 `hasExerciseContext` | #2/#5 |
| 安静高热/高呼吸 | warning | CTX-01/02 + `isResting` | #3/#4 |
| 仅 `breathingDifficulty=true` | 不 alone 触发 EMG-04 | `severeRestingResp` 组合条件 | #4 |
| 短鼻 + 极高 RR + 张口呼吸 | emergency | EMG-02/EMG-04 | #12 |
| 用户说正常 + 设备安静发热 | warning，不信用户 | CTX-05 | #11 |
| missing/stale | floor ≥ watch，禁止 normal | DQ-01/02 + fusion 钳制 | #10/#19 |
| partial + seizure | confidence 走 H′=high | `confidence_resolver` | #13 |
| USER_DEVICE_CONFLICT | confidence 排除 H → M | `primary_flag != USER_DEVICE_CONFLICT` | #11 |
| 幼犬/老年/慢病 | 加权 warning，不确诊 | CTX-07/08 + policy | #16/#17/#20 |
| CTX-03 vs CTX-04 | 心率 vs 呼吸分流 | DerivedFacts + CTX-02 when 排除 | #6/#20 |

#### 4.4.5 里程碑 A 验收

- `tests/triage/test_triage_core_20_cases.py`：20/20 `riskLevel` + 逐 case `confidence`
- `assert_risk_only_hard_gate` 批跑断言

**WP3 结论**：✅ 医学语义一致；⚠️ 制品形态为 Code-First（见 §6.2）。

#### 4.4.6 与完整 L4 的差异（计划内简化）

| 完整架构能力 | 当前实现 |
|-------------|---------|
| 精细 Signal Trust 打分 | DerivedFacts + 结构化 when 近似 |
| 独立 Contradiction Flags DTO | 逻辑并入规则 when，无独立 flags 对象 |
| Population Priors 独立层 | 阈值在 `context/thresholds.py` + CTX OR 兜底 |
| 20+ 独立 L4 组件类 | 合并为 `triage/` 若干模块 |

---

### 4.5 WP4：KB-TPL + ③ 文案生成 — **一致（默认机械路径）**

#### 4.5.1 知识资产清单

| 资产 | 计划路径 | 实现 | 状态 |
|------|---------|------|------|
| templates.v1.json（20 条） | `assets/kb-tpl/config/` | ✅ 20 `templateId` | ✅ |
| slots.v1.json | 同上 | ✅ | ✅ |
| tone-by-risk.v1.json | 同上 | ✅ | ✅ |
| safety-notices.v1.json | 同上 | ✅ | ✅ |
| fallback-by-risk.v1.json | 同上 | ✅ | ✅ |
| kb-syn.v1.json | `assets/kb-syn/` | ✅ | ✅ |
| KB-FORBID | `assets/kb-forbid/` | ✅ | ✅ |
| KB-ACTION | `assets/kb-action/` | ✅ | ✅ |

#### 4.5.2 职责分工红线

| 职责 | 真源 | 实现 |
|------|------|------|
| forcedMentions / forbiddenThemes / safety / action hint | `policyTables`（②） | `triage/policy_data.py` |
| copy 骨架、语气、槽位 | KB-TPL | `copy/kb_tpl_loader.py` 等 |
| mustMention 评测锚点 | cases expected | `eval/semantic_checkers.py` + KB-SYN |

**结论**：与 `kb-tpl-template-spec.md` §一 分工 **一致**。

#### 4.5.3 ③-1 ResolveTemplate

- 实现：`copy/template_resolver.py`
- 主键：`finalRiskLevel × primaryFlag`（`build_template_id`）
- 不修改 `TriageCoreResult` 裁决字段

#### 4.5.4 ③-2 DraftGenerator

| 模式 | 实现 | 默认 |
|------|------|------|
| 机械填槽 | `copy/mechanical_draft.py` | ✅ `llm_enabled=False` |
| LLM 润色 | `copy/qwen_client.py` + `pipeline/llm_draft_generation.py` | 可选 |

计划允许：「LLM 不可用时可跳过 WP4 部分验收，WP5 兜底必须合法」。当前里程碑 B 走机械路径，**符合计划**。

**WP4 结论**：✅ 一致；默认演示路径为机械文案而非 LLM 主路径（见 §6.3）。

---

### 4.6 WP5：④ 验证重试 + ⑤ 合并输出 — **一致（含增强）**

#### 4.6.1 ④ 两层验证

| 计划组件 | 实现 | 状态 |
|---------|------|------|
| **A. ValidateStructure** | `eval/structure_validator.py`（guard 内委托） | ✅ |
| **B. ForbiddenPatternMatcher** | `guard/checkers/forbidden_pattern.py` | ✅ |
| EmergencyToneGuard | `guard/checkers/emergency_tone.py` | ✅ |
| EvidenceAuthenticityChecker | `guard/checkers/evidence_authenticity.py` | ✅ |
| ForcedMentionChecker | `guard/checkers/forced_mention.py` | ✅ |
| SafetyNoticeEnforcer | `guard/checkers/safety_notice.py` | ✅ |
| RiskTextConsistencyGuard | `guard/checkers/risk_text_consistency.py` | ✅ |

**实现增强**（不违背 L5 精神）：

- `locked_action` 校验（行动与 ③-1 锁定一致）
- `deterministic_repair`（确定性修补）
- `guard_mode`：`strict` / `report_only` / `sanitize`

#### 4.6.2 重试协调器

| 计划参数/约束 | 实现 |
|-------------|------|
| `maxAttempts = 3` | `DraftRetryOptions.max_attempts = 3` |
| `maxLLMRetries = 2` | `max_llm_retries = 2` |
| 不得修改 TriageCoreResult | 协调器仅操作 `DraftCopyJSON` |
| 按失败类型分支重试/兜底 | `violation_classifier.py` |

实现：`pipeline/retry_coordinator.py`

#### 4.6.3 ⑤ 合并与兜底

| output 字段 | 计划来源 | 实现 |
|------------|---------|------|
| `riskLevel`, `confidence` | ② 锁定 | `output/merge_output.py` |
| `scene` | 固定 `health_triage` | ✅ |
| `missingData` | ② `missingDataUser` | ✅ |
| 文案字段 | ③ 通过稿或⑤ 兜底 | `merge_fallback.py` |
| `primaryAction` | KB-ACTION + hint | `copy/action_mapper.py`（③-1 锁定后 merge 原样沿用） |

出站前 **完整 output_schema 校验**：`pipeline/final_schema_recovery.py` + `eval/validate_output`

#### 4.6.4 里程碑 B 验收

`tests/pipeline/test_milestone_b_batch.py`：

- 20 case 管道批跑
- `assert_milestone_b_pipeline_hard_gate`
- `assert_milestone_b_hard_gate`（full-output 硬门槛）
- `assert_milestone_b_soft_gates`（mustMention ≥ 18/20）

**WP5 完成标志对照**：

| 计划标准 | 状态 |
|---------|------|
| 端到端 20 case 硬门槛全绿 | ✅（机械路径测试） |
| mustMention 软门槛 ≥ 18/20 | ✅（测试断言） |
| LLM 全失败时 Fallback 合法 | ✅（默认即机械兜底） |

**WP5 结论**：✅ 一致。

---

## 5. 与完整七层架构的对照

### 5.1 分层映射图

```
┌─────────────────────────────────────────────────────────────┐
│  完整架构（docs/architecture）                                 │
├─────────────────────────────────────────────────────────────┤
│  L1 接入  →  api/（部分）          AccessGate：未实现          │
│  L2 编排  →  pipeline/             SessionStore：未实现         │
│  L3 上下文 → parse/ + context/    精细 Trust：未实现          │
│  L4 决策  →  triage/                                        │
│  L5 安全  →  guard/                                         │
│  L6 输出  →  output/ + copy/                                │
│  L7 评测  →  eval/（无 Audit 持久化）                          │
│  横切     →  assets/* + policy_data.py   ConfigRelease：未实现 │
│  全局infra →  api/lifespan（仅 KB 预加载）  Redis/OTel：未实现   │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 架构级硬红线遵守情况

| 红线 | 状态 | 说明 |
|------|------|------|
| L3–L6 不读 Session / Audit / 质控聚合 | ✅ | 无相关依赖 |
| `finalRiskLevel` 仅 L4 产出 | ✅ | 仅 `triage/fusion` → `TriageCoreResult` |
| 配置变更须版本化（bundleVersion） | ⚠️ | 代码内 `BUNDLE_VERSION`；无 ConfigRelease 发布流 |
| 评测不反哺 serving | ✅ | eval 仅批跑/断言 |
| risk 由规则保底，LLM 不裁决 | ✅ | |
| emergency 不可被文案弱化 | ✅ | EmergencyToneGuard + policy |
| 缺数据不编造 | ✅ | DQ 门禁 + evidence 审查 |
| 禁止确诊/保证性结论 | ✅ | KB-FORBID + forbiddenThemes |

### 5.3 V1 明确不做项 — 实现状态

| 不做项 | 状态 |
|--------|------|
| 鉴权、限流 | ❌ 未实现（符合计划） |
| Session、`/intelligent` | ❌ 未实现（符合计划） |
| ConfigRelease | ❌ 未实现（符合计划） |
| 审计持久化、Metrics | ❌ 未实现（符合计划） |
| 向量 RAG | ❌ 未实现（符合计划） |
| 精细 Signal Trust | ❌ 未实现（符合计划） |

---

## 6. 差异分析（三类）

### 6.1 有意简化（与计划/简化架构一致）

以下差异 **不构成缺陷**，属 V1 验证范围声明：

- 无 AccessGate、SessionStore、`/intelligent` 多轮
- 无 ConfigReleaseStore、RuntimeBundleCache
- 无 AuditSink / MetricsBackend 请求级持久化
- 无全局 infra（Redis、OTel、GracefulShutdown 完整栈）
- 无 Signal Trust 数值化、Tier2 embedding、向量 RAG
- 默认出站为 **机械文案**，非 LLM 润色主路径

### 6.2 工程形态差异（功能等价，回迁需注意）

| 维度 | 设计文档 | 当前实现 | 影响 |
|------|---------|---------|------|
| 决策表真源 | `triage-core.v1.json` 单文件 | `rules_v1.py` + `policy_data.py` 等 Python 模块 | 医学语义一致；回迁需 JSON 导出或 codegen |
| PolicyTables | `policy_tables.template.jsonc` → JSON | `triage/policy_data.py` 运行时真源 | 文档模板与代码可能漂移 |
| 编排运行时 | Coze 工作流节点 | FastAPI + Python pipeline | 语义一致；WP6 验收项表述需映射 |
| 目录结构 | `adapter/`、`decision/`、`guard/` 七层包 | `parse/`、`triage/`、`guard/` 领域包 | 职责正确，分包命名不同 |
| ValidateStructure 归属 | L6 或管道 §6.1 | `eval/structure_validator`，由 `guard` 编排 | 职责正确 |
| Case/Schema 路径 | 与 app 同仓 | `docs/` 在上级 repo，`xiaozhua-health-agent` 测试相对路径引用 | 部署时需注意路径 |

### 6.3 潜在后续风险（非 WP0–WP5 阻塞）

| 风险项 | 描述 | 建议 |
|--------|------|------|
| 制品双轨 | `policy_tables.template.jsonc` vs `policy_data.py` 无自动同步 | WP7 增加导出脚本或单一真源策略 |
| LLM 主路径未作默认验收 | `llm_enabled=True` 的 full-output 需单独批跑 | 使用已有 `copy_llm_batch` 作 smoke |
| 无请求级 audit | 线上 case 失败难以 replay | WP7+ 接 L7 AuditSink |
| WP6 边界模糊 | API 已存在但未完成 WP6 全项验收 | 明确「机械演示 API」vs「LLM 生产 API」 |
| bundleVersion pin | 无环境级制品版本切换 | 引入配置或 ConfigRelease 前需手工对齐 |

---

## 7. 知识资产一致性矩阵

| 资产 ID | 设计职责 | 运行时真源 | 消费步骤 | 一致性 |
|---------|---------|-----------|---------|--------|
| **TRIAGE-CORE** | 规则、融合、置信度、policy、evidence | Python 模块（非 JSON） | ② | 语义 ✅ / 形态 ⚠️ |
| **DerivedFacts** | when 条件事实 | `context/derived_facts.py`（代码） | ② 入口 | ✅ |
| **KB-TPL** | 文案骨架、槽位、兜底 | `assets/kb-tpl/config/*` | ③⑤ | ✅ |
| **KB-FORBID** | 禁止词 | `assets/kb-forbid/` | ③④ | ✅ |
| **KB-ACTION** | primaryAction 映射 | `assets/kb-action/` | ③⑤ | ✅ |
| **KB-SYN** | mustMention 同义词 | `assets/kb-syn/` | ④评测 | ✅ |
| **Cases** | 验收真源 | `docs/cases/` | WP0+ | ✅ |
| **Schemas** | 契约 | `docs/schema/` + `schemas/` | WP0、⑤ | ✅ |
| **case-rule-mapping** | 验收规格 + 规则主表 | 测试断言对齐 §五 | WP3、WP7 | ✅ |

---

## 8. 测试与里程碑证据索引

| 测试文件 | 覆盖范围 | 对应里程碑 |
|---------|---------|-----------|
| `tests/parse/test_parser.py` | WP1 解析 | — |
| `tests/context/test_derived_facts.py` | WP2 边界 | — |
| `tests/context/test_when_evaluator.py` | WP2 evalWhen | — |
| `tests/triage/test_triage_core_20_cases.py` | WP3 20/20 risk+confidence | **里程碑 A** |
| `tests/copy/test_template_resolver.py` | WP4 ③-1 | — |
| `tests/guard/test_content_validator.py` | WP5 ④-B | — |
| `tests/pipeline/test_retry_coordinator.py` | WP5 重试 | — |
| `tests/pipeline/test_merge_fallback.py` | WP5 兜底 | — |
| `tests/pipeline/test_milestone_b_batch.py` | WP5 端到端硬/软门槛 | **里程碑 B** |
| `tests/api/test_health_api.py` | HTTP 接入（WP6 超前） | — |

---

## 9. WP6 超前实现说明（超出 WP0–WP5 声明范围）

当前已存在但未按 WP6 完整验收的 HTTP 层：

| 组件 | 路径 | 说明 |
|------|------|------|
| `POST /health` | `api/routes/health_triage.py` | 机械管道，默认不调用 LLM |
| `/internal/healthz` | `api/routes/ops.py` | Liveness |
| `/internal/readyz` | `api/routes/ops.py` | Readiness（含 KB-TPL 预加载） |
| Lifespan | `api/lifespan.py` | 启动预加载 copy bundle |

**与 WP6 计划差异**：

- 计划原指 Coze 工作流集成；实际为 FastAPI（用户已声明文档可平滑迁移）
- 未验收：Coze API 与本地 risk 一致性（不适用）
- 未默认启用：LLM 全链路 HTTP 演示

---

## 10. 回迁映射参考（WP7 预备）

供后续 WP7 使用，当前 **未交付**：

| Coze / 当前模块 | 回迁目标（完整架构） |
|----------------|---------------------|
| `parse/` | L1 Adapter + L3 Fact Set |
| `context/derived_facts` | L3 Context Builder |
| `rules_v1.py` | L4 RuleEngine + RuleKBRegistry |
| `fusion` + `confidence_resolver` | L4 Fusion + Risk Arbiter |
| `policy_data.py` | 横切 PolicyTables |
| `evidence_builder` | L3/L4 Evidence 组件 |
| `assets/kb-tpl` | TemplateRegistry |
| `assets/kb-forbid` | ForbiddenPatternRegistry |
| `assets/kb-action` | ActionRouteTableRegistry |
| `guard/` | L5 Safety Guard |
| `output/` + `merge_fallback` | L6 Output Composer |
| `eval/` | L7 Eval |

**回迁前置工作**：将 Code-First 决策表导出为版本化 `triage-core.v1.json` 或建立 codegen 流水线。

---

## 11. 总结判定

### 11.1 一致性总评

| 维度 | 评级 | 说明 |
|------|------|------|
| WP0–WP5 功能目标 | **高度一致** | 五模块管道、医学红线、20 case 闭环均已实现并有测试锚点 |
| 简化版架构（Coze spec） | **高度一致** | 有意砍掉的模块均未实现 |
| 完整七层架构 | **子集实现** | L3–L6 核心 + L7 评测；有状态/横切/infra 未做（符合 V1 范围） |
| 制品形态 | **有偏离** | Code-First 替代 JSON 单文件；功能等价 |
| 运行时形态 | **有偏离** | FastAPI 替代 Coze；管道语义等价 |

### 11.2 里程碑状态

| 里程碑 | 计划定义 | 判定 |
|--------|---------|------|
| **A：医学正确** | 20/20 riskLevel，TriageCoreResult 可输出 | **已达成**（测试设计） |
| **B：产品可演示** | full-output 硬门槛全绿（机械路径有效） | **已达成**（机械路径） |
| **C：可演进** | WP7 回迁文档与版本化制品 | **未开始** |

### 11.3 交付结论

**在开发计划 WP0–WP5 范围内，当前 `xiaozhua-health-agent` 实现可作为「快速验证版」的合格交付基线。**

实现 faithfully 遵守了：

- 确定性 risk 裁决与 LLM 限权
- 三个中间对象与字段锁定
- 20 条规则 + 20 格模板 + 知识资产三分法
- 双层校验、有界重试、模板兜底
- 架构级医学安全红线

存档时需同时记录 **两项已知形态差异**：

1. 决策表以 **Python 代码** 为运行时真源，而非设计文档中的 `triage-core.v1.json`
2. 默认产品路径为 **机械文案**，LLM 文案为可选扩展路径

---

## 附录 A：实现包结构速查

```
xiaozhua-health-agent/
├── src/xiaozhua_health_agent/
│   ├── api/          # HTTP（WP6 超前）
│   ├── parse/        # WP1 ①
│   ├── context/      # WP2 DerivedFacts + evalWhen
│   ├── triage/       # WP3 ②
│   ├── copy/         # WP4 ③
│   ├── guard/        # WP5 ④-B
│   ├── output/       # WP5 ⑤
│   ├── pipeline/     # L2 编排 + 重试 + 批跑
│   ├── eval/         # WP0 L7 评测
│   └── schemas/      # 契约模型
├── assets/
│   ├── kb-tpl/config/
│   ├── kb-forbid/
│   ├── kb-action/
│   ├── kb-syn/
│   └── eval/
└── tests/            # 回归与里程碑断言
```

## 附录 B：参考文档清单

- `docs/README.md`
- `docs/schema/*.json`
- `docs/cases/health_triage_cases.v1.json`
- `docs/architecture/overall.md`
- `docs/architecture/rules/component-dependency-rules.md`
- `docs/implementation/coze/pipeline-design.md`
- `docs/implementation/coze/triage-core-spec.md`
- `docs/implementation/coze/case-rule-mapping.md`
- `docs/implementation/coze/kb-tpl-template-spec.md`
- `docs/plans/coze-workflow-dev-plan.md`

---

*本报告仅供项目交付存档；不涉及代码或配置变更。*