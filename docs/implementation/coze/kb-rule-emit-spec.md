# 规则 `then`（瘦 emit）与 PolicyTables — 字段说明

`triage-core.v1.json` 中 `rules[].then` 是规则 **命中后** 写入分诊中间结果的指令包（原称 `emit`）。  
它不直接等于最终 App 的 `output_schema`，而是 **步骤 ②** 的产出，供 **fusion → confidence → PolicyTablesResolve → missingDataUser → EvidenceBuilder → ③ → ④** 使用。

**制品位置**（见 [triage-core-spec.md](./triage-core-spec.md)）：

| 内容 | 决策表 section |
|------|----------------|
| 瘦 `then` | `rules[]` |
| FUS / 置信度 | `fusion`、`confidence` |
| PolicyTables 四表 | `policyTables` |
| Evidence 映射 | `evidenceByFlag` |

**Coze V1 策略**：`then` 只保留 **医学裁决与叙事主键**；文案合规元数据在 **`policyTables`** 按 `primaryFlag` 查表。  
**置信度**：由决策表 `confidence` 区块（L / **H′** / H / M）计算；**H′** 补 case #13，不依赖 `then` 或 `flags`。

**与 KB-TPL 分工**（见 [kb-tpl-template-spec.md](./kb-tpl-template-spec.md) §一）：`policyTables` 提供 `forcedMentions` / `forbiddenThemes` / `safetyNoticeRequired` / `primaryActionHint`；KB-TPL **不重复**维护上述字段，只负责 copy 骨架与 `llmInstructions`。

---

## 一、在管道中的位置

```mermaid
flowchart LR
    R["规则命中 emit（最小集）"]
    ACC["多条 emit 累积"]
    FUS["FUS 融合"]
    CR["ConfidenceResolver<br/>L / H′ / H / M"]
    PT["PolicyTablesResolve"]
    MDU["missingDataUser"]
    EB["EvidenceBuilder"]
    TCR["TriageCoreResult"]
    TPL["③ KB-TPL"]
    LLM["③ LLM 填槽"]
    VAL["④ 验证"]

    R --> ACC --> PF["ResolvePrimaryFlag"] --> FUS --> CR --> PT --> MDU --> EB --> TCR
    TCR --> TPL --> LLM --> VAL
```

| 阶段 | 输入 | 产出 |
|------|------|------|
| 规则评估 | FactSheet + DerivedFacts | 瘦 `then`、`ruleHits[]`（见第二节） |
| ResolvePrimaryFlag | 全部命中规则的 `then.primaryFlag` | 唯一 `primaryFlag`（见 [triage-core-spec.md](./triage-core-spec.md) §七步骤 4） |
| FUS | 各层 emit + upstream | `finalRiskLevel`、`arbitrationNote` |
| ConfidenceResolver | risk、dataQuality、primaryFlag、ruleHits、userReport | `confidence`（**含 H′**） |
| PolicyTablesResolve | `primaryFlag`、`finalRiskLevel`、条件追加 | `forbiddenThemes`、`safetyNoticeRequired`、`primaryActionHint`、合并 `forcedMentions` |
| missingDataUser | `FactSheet.missingData[]`、`postProcess` 翻译表 | `missingDataUser[]` |
| EvidenceBuilder | `primaryFlag`、FactSheet、**`missingDataUser`**（须先翻译） | `evidenceBullets[]` |

- **单条规则** 可只产出部分最小集字段（例如 DQ-03 **零 emit**）。  
- **附属语义**（原 AUX 层）已并入 DQ/CTX；用药合规等 **条件追加** 仅保留 `forcedMentions`（见 5.3）。  
- **③ 不得修改** `finalRiskLevel`、`confidence` 及 PolicyTables 锁定的约束字段。

---

## 二、规则 `then` 最小集（`rules[]` 唯一允许的产出字段）

决策表 JSON 字段名以 `then` 为准；下表「逻辑名」便于与旧文档对照。

| 决策表字段 | 逻辑名 | 必填 | 含义 | 消费方 |
|-----------|--------|------|------|--------|
| `risk` | candidateRisk | EMG/CTX 建议填 | 本规则候选风险 | fusion `max()` |
| `riskFloor` | riskFloor | **仅 DQ-01/02** | 风险下限 | fusion `max()` |
| `primaryFlag` | primaryFlag | 主叙事规则填 | 情境主键 | KB-TPL、policyTables、Resolver **H** |
| `mentionsAdd` | forcedMentions 追加 | **可选** | 默认由表提供，规则仅追加 | ③ Prompt、④ Checker |

### 2.1 已从 `then` 推迟的字段（→ `policyTables` 或内置逻辑）

| 原字段 | Coze V1 归属 | 说明 |
|--------|-------------|------|
| `flags[]` | **废弃** | 与 `primaryFlag` 冗余；`DATA_PARTIAL` 改读 `dataQuality=partial`；Resolver **H** 改读 `primaryFlag !== USER_DEVICE_CONFLICT` |
| `forbiddenThemes[]` | `ForbiddenByFlag` | 按 primaryFlag 查表 |
| `primaryActionHint` | `ActionByFlagRisk` | 按 primaryFlag × finalRiskLevel 查表 |
| `safetyNoticeRequired` | `SafetyByFlag` | 按 primaryFlag 查表（对齐 §五 case 总表） |
| `evidenceKeys[]` | `EvidenceByFlag` | 由 EvidenceBuilder 按 primaryFlag 取 FactSheet 路径 |
| `confidenceHint` | **ConfidenceResolver** | 已废弃；**H′** 补 case #13 |

### 2.2 按 layer 填写最小集

| layer | 典型 emit | 备注 |
|-------|-----------|------|
| **EMG** | `candidateRisk`, `primaryFlag` | forcedMentions 默认走 `ForcedMentionsByFlag` |
| **DQ-01/02** | `riskFloor`, `candidateRisk`, `primaryFlag` | 同档 watch |
| **DQ-03** | **（空 / 省略）** | partial 仅影响 Resolver，不抬 risk |
| **CTX** | `candidateRisk`, `primaryFlag` | CTX-04 用药、CTX-06 呕吐可 **追加** forcedMentions；CTX-01/02 的 **OR 兜底分支**（原 POP-01/02）与临床分支 **共用同一 emit**，不单独 ruleId |

---

## 三、最小集字段说明

### 3.1 `candidateRisk`

本条规则单独判断时的建议等级：`normal` / `watch` / `warning` / `emergency`。进入 FUS `candidates[]` 参与 `max()`；**不是**最终 `finalRiskLevel`。

### 3.2 `riskFloor`

**仅 DQ-01/02 使用**。底线约束：`finalRiskLevel` 不得低于此值（典型 `watch`，禁止 normal）。与 `candidateRisk` 语义不同：floor 强调「不能更轻」。

### 3.3 `primaryFlag`

各条规则 `then.primaryFlag` 仅为 **候选**（EMG → `EMERGENCY_*`；DQ-01/02 → `DATA_MISSING` / `DATA_STALE`；CTX → 情境键如 `FEVER_RESTING`）。  
**最终** `TriageCoreResult.primaryFlag` 由 **ResolvePrimaryFlag** 在 **全部 `ruleHits`** 上统一选定，**不是** CTX 按 priority 首个命中。

算法与叙事层级见 [case-rule-mapping.md](./case-rule-mapping.md) §6.3、[triage-core-spec.md](./triage-core-spec.md) §七步骤 4 / §7.1。

**与 ConfidenceResolver 的关系**：

- `primaryFlag === USER_DEVICE_CONFLICT` → 规则 **H** 不满足 → 通常 **M**（case #11）  
- 不再维护 `flags[]` 中的 `USER_DEVICE_CONFLICT`

### 3.4 `forcedMentions[]`（可选追加）

**默认来源**：`ForcedMentionsByFlag[primaryFlag]`（PolicyTables）。  
**规则追加**（唯一建议保留在规则层的文案约束）：

| 条件 | 追加 |
|------|------|
| CTX-04 且 `medications` 非空或 notes 含用药 | 「不要自行调整药量」 |
| CTX-06 `vomiting=repeated` | 「不要自行用药」（若表默认未含） |

合并顺序：表默认 → 各命中规则 `emit.forcedMentions` 去重追加 → 传入 `TriageCoreResult`。

---

## 四、PolicyTables（`triage-core.v1.json` 内 `policyTables` section）

表体 **物理存放**于单文件决策表；本文定义 **字段语义与表体内容**。  
在 **confidence 评估之后**执行 `PolicyTablesResolve(primaryFlag, finalRiskLevel, …)`；其后为 **`missingDataUser` → EvidenceBuilder**（见 [triage-core-spec.md](./triage-core-spec.md) §七）。

### 4.1 `ForcedMentionsByFlag`

| primaryFlag | 默认 forcedMentions |
|-------------|---------------------|
| NORMAL_DAILY | 状态平稳、日常观察 |
| POST_EXERCISE | 休息、补水、复查 |
| FEVER_RESTING | 体温、联系兽医、精神状态 |
| RESP_RESTING | 呼吸、安静状态、联系兽医 |
| HR_RESTING_CHRONIC | 安静状态、既往史、联系兽医 |
| CHRONIC_HEART_RESP | 心脏病史、安静呼吸、联系兽医 |
| USER_DEVICE_CONFLICT | 用户描述、体温、复查 |
| REPEATED_VOMITING | 反复呕吐、联系兽医、不要自行用药 |
| SENIOR_DECLINE | 老年、食欲、联系兽医 |
| PUPPY_FEVER | 幼犬、体温、联系兽医 |
| HRV_STRESS | 压力、睡眠、环境变化 |
| LIMPING_PAIN | 减少运动、观察步态、持续或加重 |
| SLOW_RECOVERY | 恢复、睡眠、降低活动强度 |
| MILD_DIARRHEA | 腹泻、观察、精神 |
| POST_VACCINE | 疫苗、观察、食欲 |
| DATA_MISSING | 数据不足、设备、不能判断 |
| DATA_STALE | 数据过期、设备在线、不能依据旧数据判断 |
| EMERGENCY_SEIZURE | 抽搐、立即、兽医 |
| EMERGENCY_RESPIRATORY | 立即、兽医、就医 |
| EMERGENCY_TRAUMA | 立即、兽医、就医 |

### 4.2 `ForbiddenByFlag`

| primaryFlag | forbiddenThemes |
|-------------|-----------------|
| NORMAL_DAILY | 确诊、立即就医 |
| POST_EXERCISE / HRV_STRESS / SLOW_RECOVERY / MILD_DIARRHEA / POST_VACCINE / HR_RESTING_CHRONIC 等 | 确诊 |
| FEVER_RESTING | 一定没事 |
| RESP_RESTING | 不用看医生 |
| USER_DEVICE_CONFLICT | 忽略设备数据 |
| DATA_MISSING | 正常、一定没事 |
| DATA_STALE | 当前正常、一切正常 |
| REPEATED_VOMITING | 一定没事 |
| PUPPY_FEVER | 继续观察即可 |
| SENIOR_DECLINE | 只是正常老化 |
| CHRONIC_HEART_RESP | 自行调整药量 |
| EMERGENCY_* | 继续观察即可、不用看医生 |
| **全局兜底** | 与 KB-FORBID 禁止词对齐 |

### 4.3 `SafetyByFlag`

| safetyNoticeRequired | primaryFlag |
|---------------------|-------------|
| **false** | HRV_STRESS、SLOW_RECOVERY、DATA_MISSING、DATA_STALE |
| **true** | 其余（含 POST_EXERCISE、MILD_DIARRHEA、所有 warning/emergency） |

与 [case-rule-mapping.md](./case-rule-mapping.md) §五总表 `SN` 列一致。

### 4.4 `ActionByFlagRisk`

| primaryFlag | primaryActionHint |
|-------------|-----------------|
| EMERGENCY_* | emergency_now |
| DATA_MISSING / DATA_STALE | check_device |
| POST_EXERCISE | rest_observe |
| NORMAL_DAILY | rest_observe |
| 多数 warning CTX | contact_vet |

⑤ 合并时经 KB-ACTION 映射为 `primaryAction.label` / `route`。

### 4.5 `evidenceByFlag`（决策表 section，供 EvidenceBuilder）

| primaryFlag | 典型 FactSheet 路径 |
|-------------|---------------------|
| DATA_MISSING | device.*, missingData |
| DATA_STALE | device.lastSeenAt, device.dataQuality, device.warningText |
| POST_EXERCISE | vitals.temperatureC 或 heartRateBpm, context.recentExercise, userReport.text |
| FEVER_RESTING | vitals.temperatureC, vitals.activityLevel, userReport.energy, userReport.appetite |
| RESP_RESTING | vitals.respiratoryRateBpm, vitals.activityLevel, userReport.text |
| USER_DEVICE_CONFLICT | userReport.text, vitals.temperatureC, device.dataQuality |
| EMERGENCY_RESPIRATORY | vitals.respiratoryRateBpm, userReport.symptoms, userReport.breathingDifficulty |
| EMERGENCY_SEIZURE | userReport.seizure, userReport.text |
| CHRONIC_HEART_RESP | pet.chronicConditions, vitals.respiratoryRateBpm, pet.medications |
| … | 其余 `primaryFlag` 按 FactSheet 字段模板录入本表（验收见 cases `expected`） |

**全局规则**（不写在单条规则 emit 上）：

- `input.missingData` 非空 → bullets 可提及缺失项（与 `missingDataUser` 一致）  
- 禁止引用 FactSheet 中不存在的数值  

---

## 五、confidence 区块与瘦 `then` 的衔接（含 H′）

`confidence` **非 `then` 字段**；定义于决策表 `confidence` section，在 fusion 之后、PolicyTables 之前计算。

| 代号 | 条件 | confidence | 典型 case |
|------|------|------------|-----------|
| **L** | `dataQuality=missing` 或 `vitalsCoreMissing` 或 `dataQuality=stale` | low | #10、#19 |
| **H′** | `finalRisk=emergency` 且 `ruleHits` 含 `EMG-*` 且 `userReport.seizure=true` | high | **#13** |
| **H** | `dataQuality=good` 且 **`primaryFlag !== USER_DEVICE_CONFLICT`** 且（normal 且 missingData 空 **或** warning/emergency 多源一致且无 arbitrationNote） | high | #1、#3、#4、#6、#12、#17、#20 |
| **M** | 其余 | medium | #2、#5、#7～#9、#11、#14～#16、#18 |

**H′ 补全逻辑缺口**：case #13 在 `dataQuality=partial`（原 DQ-03 / `DATA_PARTIAL`）下，规则 **H** 因 `good` 不满足会落 **M**，但 expected 为 `high`。H′ 在用户 **硬报告抽搐 + EMG 命中** 时强制 `high`，**不** 依赖 `emit.flags` 或 `confidenceHint`。

**partial 一般路径**：`dataQuality=partial` → 不满足 H → **M**（#8、#14、#16）；**不** 阻挡 emergency risk。

---

## 六、字段在融合后的去向

| 来源 | 进入 TriageCoreResult | ③ 是否可改 |
|------|----------------------|------------|
| emit：`candidateRisk` + `riskFloor` + FUS | `finalRiskLevel` | **否** |
| ConfidenceResolver | `confidence` | **否** |
| ResolvePrimaryFlag | `primaryFlag` | **否** |
| PolicyTables + 规则追加 | `forcedMentions`、`forbiddenThemes` | 作约束，非 output 直出 |
| PolicyTables | `safetyNoticeRequired`、`primaryActionHint` | 约束 ③④⑤ |
| EvidenceBuilder | `evidenceBullets[]` | 事实锁定，③ 仅润色 |
| missingDataUser | `missingDataUser[]` | output `missingData`；供 EvidenceBuilder |
| FUS 元数据 | `ruleHits[]`、`arbitrationNote` | 调试/审计 |

**`TriageCoreResult.flags[]`（可选）**：调试时可由 `primaryFlag` + `dataQuality=partial` 派生，**不要求**规则 emit `flags`。

---

## 七、瘦 `then` 示例

### 示例 A — `CTX-09a` / `CTX-09b`（运动后轻度发热 / 运动后心率偏高）

两条规则 **`then` 相同**（`primaryFlag` 均为 `POST_EXERCISE`）；区分靠 `rules[].id` → `ruleHits`（`CTX-09a` vs `CTX-09b`），**无** `POST_EXERCISE_FEVER` / `POST_EXERCISE_HR`，**无** `postProcess` 别名表。

**`CTX-09a` 的 `rules[].then`**（`CTX-09b` 同为 `watch` + `POST_EXERCISE`）：

| 字段 | 值 |
|------|-----|
| risk | watch |
| primaryFlag | POST_EXERCISE |

**`policyTables` 展开**（同文件查表，不写进 `then`）：

| 字段 | 值 |
|------|-----|
| forcedMentions | 休息、补水、复查 |
| forbiddenThemes | 确诊 |
| safetyNoticeRequired | true |
| primaryActionHint | rest_observe |
| evidenceBullets | 来自 EvidenceByFlag[POST_EXERCISE] |

### 示例 B — `DQ-01`（数据缺失）

**`rules[].then`**：

| 字段 | 值 |
|------|-----|
| riskFloor | watch |
| risk | watch |
| primaryFlag | DATA_MISSING |

**`policyTables` 展开**：见 §4.1～4.5。

### 示例 C — `CTX-05`（用户/设备冲突）

**`rules[].then`**：`risk: warning`，`primaryFlag: USER_DEVICE_CONFLICT`。Resolver **H** 排除 → **M**。

### 示例 D — `CTX-04` + 用药（条件追加）

**`rules[].then`**：`risk: warning`，`primaryFlag: CHRONIC_HEART_RESP`，`mentionsAdd: ["不要自行调整药量"]`。

### 示例 E — `DQ-03`（partial）

**`rules[].then`**：`null`（零产出）。`dataQuality=partial` 由 confidence 区块读入；case #13 走 **H′**。

---

## 八、`missingDataUser`（非 emit）

| 项 | 说明 |
|----|------|
| **来源** | ② **`postProcess.missingDataUser`**：`input.missingData` 非空即翻译写入 |
| **执行顺序** | **PolicyTablesResolve 之后、EvidenceBuilder 之前**（P0-2 定案） |
| **与 PolicyTables** | DQ-01 命中时 evidence 路径与 `EvidenceByFlag[DATA_MISSING]` 一致 |
| **与 EvidenceBuilder** | EB 可读 `missingDataUser[]` 追加 bullets；#8 体现 activity 缺失，勿编造步态 |
| **典型 case** | #10（DQ-01）；#8（仅 activity 缺失，无 DQ-01） |

---

## 九、回迁完整架构时的扩展

| Coze V1 | 回迁后 |
|---------|--------|
| PolicyTables 四张表 | 迁入 `TemplateRegistry`、`ForbiddenPatternRegistry`、`ActionRouteTableRegistry`、Evidence 策略 |
| 规则瘦 emit | 可恢复 `forbiddenThemes` 等作为 **规则 override**（表为 default，emit 为 exception） |
| 无 `flags[]` | 正式架构可恢复独立 flags 若需细粒度审计 |
| ConfidenceResolver | 可拆为 CONF 策略表；**保留 H′ 语义** 或等价策略 |

---

## 十、记忆

- **`rules[].then`**：只答 **多严重** + **讲什么故事** + **少数追加必提词**  
- **`policyTables`**：答 **能说什么、不能说什么、按钮与免责**  
- **`evidenceByFlag`**：答 **证据从哪来**  
- **`confidence`**：答 **有多确信**（含 H′）  
- **LLM**：只在上述硬约束内写人话，不改裁决

完整决策表结构见 [triage-core-spec.md](./triage-core-spec.md)。
