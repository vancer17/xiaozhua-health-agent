# KB-TPL 设计规范 — 文案与语气制品（Coze V1）

**文档定位**：Coze 管道步骤 **③-1 模板解析** 与 **⑤ 模板兜底** 的架构规格。  
**配套文档**：`pipeline-design.md`、`case-rule-mapping.md`、`triage-core-spec.md`、`kb-rule-emit-spec.md`  
**计划制品路径**（实现阶段）：`docs/implementation/coze/assets/kb-tpl/`  
**版本建议**：`kb-tpl.v1.0.0`，与 `triage-core.v1.json` 的 `meta.bundleVersion` **独立管理**、联合回归。

**V1 阶段**：本文档仅定义架构与逻辑 schema；**暂不提交**实际 JSON 文件。

---

## 一、设计目标与职责边界

### 1.1 目标

| 目标 | 说明 |
|------|------|
| 可查询 | `finalRiskLevel × primaryFlag` 唯一命中一条模板 |
| 可填槽 | 标题/摘要/建议等由槽位 + ② 的 `evidenceBullets` 驱动，LLM 只润色 |
| 可兜底 | ④ 重试耗尽后，同模板机械填槽即可输出 |
| 可回迁 | `templateId` 与 `primaryFlag` 对齐正式 `TemplateRegistry` |

### 1.2 KB-TPL **负责** vs **不负责**

| KB-TPL 负责（「怎么说」） | 其他组件负责（「说什么必须/禁止」） |
|--------------------------|-------------------------------------|
| `titlePattern`、`summaryOutline`、`recommendationTemplate`、`whenToSeeVetTemplate` | `forcedMentions[]` → ② `policyTables.ForcedMentionsByFlag` |
| `llmInstructions`（语气、边界，如 #4 禁止紧急措辞） | `forbiddenThemes[]` → ② `policyTables.ForbiddenByFlag` + KB-FORBID |
| `toneProfileId`、`evidenceStyle` | `safetyNoticeRequired` → ② `policyTables.SafetyByFlag` |
| 槽位填槽（`slots.v1`） | `primaryActionHint` → ② `policyTables.ActionByFlagRisk` → **KB-ACTION** 映射 label/route |
| 免责声明 **片段文本**（`safety-notices`） | `finalRiskLevel`、`confidence` → ② 锁定，③ 不得改 |
| `fallback-by-risk` 极简兜底 | mustMention 评测锚点 → `docs/cases/health_triage_cases.v1.json` |
| | 同义词扩展 → **KB-SYN**（ForcedMentionChecker + 评测） |

**不做**：风险裁决、证据编造、向量 RAG、禁止词机检（属 KB-FORBID + 步骤 ④）。

### 1.3 与 triage-core 单文件策略对齐

- **合规三表**（forced / forbidden / safety / action hint）**单一真源**在 `triage-core.v1.json` 的 `policyTables`；KB-TPL **不重复**维护 `mentionHints`、`forbiddenPhrases`、`safetyNoticePolicy` 等于模板内字段。  
- ~~`case-template-index`~~、~~`overlay-snippets`~~、~~独立 `action-routes`~~ **已取消**（见 §二、§九）。  
- ~~`assets/kb-rule/`~~、~~`kb-rule manifest`~~ **已废弃**；`primaryFlag` 枚举以 [case-rule-mapping.md](./case-rule-mapping.md) §七 与决策表 `rules[].then` 为准。

---

## 二、制品目录结构（V1 最小集）

```
docs/implementation/coze/assets/kb-tpl/
├── README.md
└── config/
    ├── templates.v1.json         # 20 条主模板（核心）：meta + copy + binding + guidance
    ├── slots.v1.json             # 全局槽位注册表
    ├── tone-by-risk.v1.json      # 语气 profile（5 条，极薄）
    ├── safety-notices.v1.json    # 免责声明片段库（snippet 文本）
    ├── fallback-by-risk.v1.json  # 仅按 risk 的兜底模板
    └── kb-syn.v1.json            # 同义词表（按 primaryFlag；ForcedMentionChecker + 评测）
```

| 制品 | V1 | 说明 |
|------|-----|------|
| `templates.v1.json` | **必需** | 文案骨架 + `llmInstructions` |
| `slots.v1.json` | **必需** | 机械填槽 |
| `tone-by-risk.v1.json` | 推荐 | EmergencyToneGuard、LLM 语气 |
| `safety-notices.v1.json` | 推荐 | snippet 文本（boolean 来自 ②） |
| `fallback-by-risk.v1.json` | **必需** | ⑤ 底线 |
| `kb-syn.v1.json` | 推荐 | 同义词；**不**写在各模板内 |
| ~~`manifest.v1.json`~~ | 推迟 | `bundleVersion` 写入 `templates` 顶层 `meta` |
| ~~`action-routes.v1.json`~~ | 取消 | 由 `triage-core.policyTables.ActionByFlagRisk` + **KB-ACTION**（pipeline §8.1）承担 |
| ~~`overlay-snippets.v1.json`~~ | 取消 | 由 resolver 内联规则承担（§九） |
| ~~`case-template-index.v1.json`~~ | 取消 | 评测直接读 `health_triage_cases.v1.json` |

**KB-ACTION**（`primaryAction.label` / `route`）为 pipeline 级薄表，物理路径实现期与 KB-TPL 并列或内嵌 `templates` README 说明；**hint 枚举真源**在决策表 `ActionByFlagRisk`。

---

## 三、查表与索引

### 3.1 主键

```
templateId = "{riskLevel}.{primaryFlag}"
```

示例：`watch.POST_EXERCISE`、`warning.FEVER_RESTING`、`emergency.EMERGENCY_RESPIRATORY`

**POST_EXERCISE（CTX-09a/09b）**：规则 `then.primaryFlag` **直接**为 `POST_EXERCISE`（与 [case-rule-mapping.md](./case-rule-mapping.md) §4.3 一致）；`CTX-09a` vs `CTX-09b` 仅体现在 `ruleHits`，共用模板 `watch.POST_EXERCISE`；#2/#5 差异由 `binding.summarySlotPriority` 择槽（§四），不做 flag 别名归一。

### 3.2 查找顺序

```
1. templates[finalRiskLevel + "." + primaryFlag]
2. fallback-by-risk[finalRiskLevel]
3. fallback-by-risk.DEFAULT
```

### 3.3 一致性校验（加载时 fail-fast）

- `template.riskLevel` 必须等于键前缀 risk 档  
- `template.primaryFlag` 必须等于键后缀  
- `primaryFlag` 须在 [case-rule-mapping.md](./case-rule-mapping.md) §七 ruleId 索引与决策表 `rules[].then` 覆盖的枚举内  
- 每条模板的 `meta.caseIds` 须可追溯到 `health_triage_cases.v1.json`（**不**维护独立 case-template-index）

### 3.4 V1 有效矩阵（20 格）

| # | templateId | caseId(s) |
|---|------------|-----------|
| 1 | normal.NORMAL_DAILY | normal_dog_daily_check |
| 2 | watch.POST_EXERCISE | mild_fever_after_exercise, heart_rate_high_after_play |
| 3 | warning.FEVER_RESTING | high_fever_resting |
| 4 | warning.RESP_RESTING | respiratory_rate_high_resting |
| 5 | warning.HR_RESTING_CHRONIC | heart_rate_high_resting_warning |
| 6 | warning.CHRONIC_HEART_RESP | chronic_heart_resp_warning |
| 7 | warning.USER_DEVICE_CONFLICT | conflict_user_normal_sensor_fever |
| 8 | warning.REPEATED_VOMITING | persistent_vomiting_warning |
| 9 | warning.SENIOR_DECLINE | senior_cat_low_energy |
| 10 | warning.PUPPY_FEVER | puppy_fever_high_risk |
| 11 | watch.HRV_STRESS | hrv_stress_watch |
| 12 | watch.LIMPING_PAIN | limping_pain_watch |
| 13 | watch.SLOW_RECOVERY | recovery_slow_watch |
| 14 | watch.MILD_DIARRHEA | mild_diarrhea_watch |
| 15 | watch.POST_VACCINE | post_vaccine_tired_watch |
| 16 | watch.DATA_MISSING | missing_vitals |
| 17 | watch.DATA_STALE | stale_device_data |
| 18 | emergency.EMERGENCY_RESPIRATORY | emergency_breathing_difficulty |
| 19 | emergency.EMERGENCY_SEIZURE | emergency_seizure |
| 20 | emergency.EMERGENCY_TRAUMA | （扩展占位，对应 EMG-03） |

---

## 四、全局槽位注册表（slots.v1.json）

槽位在解析阶段从 `FactSheet` / `TriageCoreResult` 取值，**LLM 不得自造**。

| slotId | source | path | required | missingBehavior | format / 说明 |
|--------|--------|------|----------|-----------------|---------------|
| petName | factSheet | pet.name | 否 | usePlaceholder「宠物」 | 文本 |
| speciesLabel | factSheet | pet.species | 否 | useGeneric「宠物」 | dog→「狗狗」cat→「猫咪」 |
| temperature | factSheet | vitals.temperatureC | 否 | omit | `{value}°C` |
| heartRate | factSheet | vitals.heartRateBpm | 否 | omit | `{value}次/分` |
| respiratoryRate | factSheet | vitals.respiratoryRateBpm | 否 | omit | `{value}次/分` |
| activityLevel | factSheet | vitals.activityLevel | 否 | omit | 枚举中文 |
| exerciseContext | factSheet | context.recentExercise | 否 | usePhrase「近期活动」 | intense→「刚剧烈运动」 |
| exerciseNote | factSheet | context.notes[] | 否 | omit | 含「刚运动/刚玩耍」 |
| userReportText | factSheet | userReport.text | 否 | omit | 原文截断≤80字 |
| chronicSummary | factSheet | pet.chronicConditions[] | 否 | omit | 映射为可读短语 |
| deviceQuality | factSheet | device.dataQuality | 是(DATA_*) | useGeneric | missing/stale 文案 |
| deviceWarning | factSheet | device.warningText | 否 | omit | 设备告警原文 |
| lastSeenAt | factSheet | device.lastSeenAt | 否 | omit | 相对时间描述 |
| missingList | triageCore | missingDataUser[] | 否 | omit | 拼接 |

**POST_EXERCISE 分支槽位**（同 templateId，按事实择一突出）：

- case #2 优先 `temperature` + `exerciseContext`  
- case #5 优先 `heartRate` + `exerciseContext`  

解析器在 `summaryOutline` 第 ① 点按 `binding.summarySlotPriority` 选择「有值的 vital」。

---

## 五、语气 Profile（tone-by-risk.v1.json）

| profileId | 适用 risk | 语气 | 必选措辞倾向 | 禁用措辞倾向 |
|-----------|-----------|------|-------------|-------------|
| TONE-NORMAL | normal | 平和、肯定 | 平稳、日常观察 | 确诊、过度保证 |
| TONE-WATCH | watch | 关注、可居家观察 | 观察、留意、复查 | 不用看医生、确诊 |
| TONE-WARNING | warning | 明确建议兽医 | 联系兽医、尽快、关注 | 一定没事、继续观察即可 |
| TONE-EMERGENCY | emergency | 紧迫、行动 | 立即、马上、就近就医 | 先观察、等等看、不用就医 |
| TONE-DATA-LIMIT | watch + DATA_* | 诚实、受限 | 无法判断、数据不足/过期 | 正常、健康、当前没事 |

`DATA_MISSING` / `DATA_STALE` 模板使用 `TONE-DATA-LIMIT`（可叠加 watch 约束）。

---

## 六、免责声明库（safety-notices.v1.json）

| snippetId | 文本草案 | 选用规则（resolver） |
|-----------|----------|---------------------|
| SNIP-NONE | `""` | `triage.safetyNoticeRequired === false` |
| SNIP-GENERAL | 以上建议仅供参考，不能替代兽医面诊与专业诊断。 | watch/warning 且 required |
| SNIP-EMERGENCY | 以上为紧急分诊提示，请尽快寻求专业兽医帮助；本服务不提供确诊或治疗保证。 | emergency 且 required |
| SNIP-DATA | 当前结论受监测数据完整性限制，请在数据恢复后重新评估。 | DATA_* 且 optional 时可用 |

**boolean 真源**：`TriageCoreResult.safetyNoticeRequired`（来自 ② `SafetyByFlag`）；KB-TPL 只提供 **片段文本**，不在模板内重复 `safetyNoticePolicy` 字段。

---

## 七、KB-SYN 同义词表（kb-syn.v1.json）

供 **④ ForcedMentionChecker** 与外部 case 评测使用；**不**写入各模板的 `requiredMentionGroups`。

**索引**：`primaryFlag` → `mentionGroups[][]`（每组至少命中一词即通过该组）。

| primaryFlag | mentionGroups 示例（录入实现 JSON 时展开） |
|-------------|------------------------------------------|
| NORMAL_DAILY | `[["状态平稳","平稳"],["日常观察","继续观察"]]` |
| POST_EXERCISE | `[["休息","减少活动"],["补水","饮水"],["复查","再次查看","休息后"],["刚运动","活动后"]]` |
| FEVER_RESTING | `[["体温","发热"],["联系兽医","兽医"],["精神","食欲"]]` |
| RESP_RESTING | `[["呼吸"],["安静","安静状态"],["联系兽医","兽医"]]` |
| HR_RESTING_CHRONIC | `[["安静"],["既往","病史"],["联系兽医","兽医"]]` |
| LIMPING_PAIN | `[["减少运动","少运动"],["步态"],["持续","加重"]]` |
| EMERGENCY_RESPIRATORY | `[["立即","马上"],["兽医","就医","医院"]]` |
| EMERGENCY_SEIZURE | `[["抽搐"],["立即","马上"],["兽医","就医"]]` |
| DATA_MISSING | `[["数据不足","数据不可用"],["设备"],["不能判断","无法判断"]]` |
| DATA_STALE | `[["数据过期","过期"],["设备在线"],["不能依据旧数据","旧数据"]]` |
| … | 其余 primaryFlag 与 [kb-rule-emit-spec.md](./kb-rule-emit-spec.md) §4.1 `ForcedMentionsByFlag` 对齐扩展 |

**评测逻辑**：`mustMention` 以 cases JSON 为准；Checker 对 `triage.forcedMentions` 做包含匹配，对 cases 关键词用 KB-SYN 扩展。

---

## 八、单条模板记录 Schema（templates.v1.json）

每条模板 **仅含文案与语气**；合规与行动由 ② 注入 resolver 的 `llmPack`。

### 8.1 `meta`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| templateId | string | 是 | risk.primaryFlag |
| riskLevel | enum | 是 | normal/watch/warning/emergency |
| primaryFlag | string | 是 | 与决策表一致 |
| bundleVersion | string | 是 | 如 kb-tpl.v1.0.0 |
| name | string | 是 | 中文名称 |
| caseIds | string[] | 是 | 服务的 case（追溯用） |
| toneProfileId | string | 是 | 引用 tone-by-risk |
| evidenceStyle | enum | 是 | bullets_as_is / bullets_light_polish |
| notes | string | 否 | 边界说明 |

### 8.2 `copy`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| titlePattern | string | 是 | 含 {slot} 或固定标题 |
| summaryOutline | string[] | 是 | 3～5 条提纲 |
| recommendationTemplate | string | 是 | 建议骨架 |
| whenToSeeVetTemplate | string | 是 | 升级就医条件 |
| evidenceInstruction | string | 否 | 给 LLM：如何改写 bullets |

### 8.3 `guidance`（原 compliance 精简为语气指令）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| llmInstructions | string | 是 | ③-2 专用：边界语气（如 #4 禁「立即」）；**不**重复 policyTables 关键词列表 |

> ~~`mentionHints`~~、~~`requiredMentionGroups`~~、~~`forbiddenPhrases`~~、~~`safetyNoticePolicy`~~、~~`actions`~~ **已移出模板**；见 §一、§七。

### 8.4 `binding`

| 字段 | 类型 | 说明 |
|------|------|------|
| slots | string[] | 引用的 slotId |
| summarySlotPriority | object | 如 POST_EXERCISE：`primaryVital: temperature>heartRate` |

---

## 九、Resolver 内联规则（取代 overlay-snippets）

在 **③-1** 组装 `summaryOutline` 时，按条件 **追加** 句子（**不**维护独立 overlay 制品）：

| 条件 | 追加内容（示例） |
|------|-----------------|
| `device.dataQuality === partial` | 「部分监测数据可能不完整，结论请结合线下观察。」 |
| `triage.forcedMentions` 已含「不要自行调整药量」（CTX-04 `mentionsAdd`） | 确保 `recommendationTemplate` 不与之矛盾即可；**不**再单独 overlay |
| `primaryFlag === USER_DEVICE_CONFLICT` | 由模板 copy 覆盖；无需 overlay |

~~`triage.flags[]`~~、~~`DATA_PARTIAL` flag~~、~~`AUX-04`~~ **已废弃**；partial 读 `FactSheet.device.dataQuality`。

---

## 十、20 条模板文案草案

以下每条仅列 **copy / guidance / binding**；**合规与行动** 运行时来自 `TriageCoreResult`（② `policyTables` + KB-ACTION）。  
验收锚点：`docs/cases/health_triage_cases.v1.json` 的 `expected`；同义词见 §七 KB-SYN。

---

### T01 — `normal.NORMAL_DAILY`

**case**：normal_dog_daily_check (#1)

| 块 | 内容 |
|----|------|
| titlePattern | `{petName}当前健康状态平稳` |
| summaryOutline | ① 当前体征与日常状态未见明显异常 ② 主人描述与监测数据一致 ③ 建议保持日常观察 |
| recommendationTemplate | 可继续当前作息与饮水习惯，保持适度活动。 |
| whenToSeeVetTemplate | 若出现精神萎靡、食欲骤降、呕吐、呼吸困难等变化，建议联系兽医。 |
| toneProfileId | TONE-NORMAL |
| evidenceStyle | bullets_light_polish |
| llmInstructions | 语气轻松但不保证；不要写「绝对健康」 |
| slots | petName, temperature, heartRate, userReportText |

---

### T02 — `watch.POST_EXERCISE`

**case**：mild_fever_after_exercise (#2), heart_rate_high_after_play (#5)  
**边界**：必须点明运动后情境；#5 不要暗示心脏病诊断

| 块 | 内容 |
|----|------|
| titlePattern | 活动后指标偏高，建议休息后复查 |
| summaryOutline | ① {exerciseContext}后{primaryVital}偏高较常见 ② 当前整体状态需结合运动情境理解 ③ 休息补水后请复查监测数据 |
| recommendationTemplate | 请先让{petName}在阴凉处休息并补充饮水，安静30～60分钟后再查看指标。 |
| whenToSeeVetTemplate | 若休息后体温或心率仍偏高，或出现呕吐、精神萎靡、呼吸困难，建议联系兽医。 |
| toneProfileId | TONE-WATCH |
| evidenceStyle | bullets_light_polish |
| llmInstructions | 必须点明「运动后」情境；#5 不要暗示心脏病诊断 |
| summarySlotPriority | primaryVital: temperature>heartRate |
| slots | petName, exerciseContext, exerciseNote, temperature, heartRate, activityLevel |

---

### T03 — `warning.FEVER_RESTING`

**case**：high_fever_resting (#3)

| 块 | 内容 |
|----|------|
| titlePattern | 安静状态下体温偏高 |
| summaryOutline | ① 安静时体温{temperature}，高于常见范围 ② 精神或食欲有所下降 ③ 建议尽快联系兽医评估 |
| recommendationTemplate | 请尽快复查体温，并联系兽医说明当前精神与食欲情况，避免自行用药。 |
| whenToSeeVetTemplate | 若体温持续偏高、精神变差、拒绝饮水或出现呕吐，请尽快联系兽医。 |
| toneProfileId | TONE-WARNING |
| evidenceStyle | bullets_light_polish |
| llmInstructions | warning 语气；不要写确诊感染 |
| slots | petName, temperature, activityLevel, userReportText |

---

### T04 — `warning.RESP_RESTING`

**case**：respiratory_rate_high_resting (#4)  
**边界**：不得使用 emergency 语气（相对 #12）

| 块 | 内容 |
|----|------|
| titlePattern | 安静状态下呼吸偏快 |
| summaryOutline | ① 休息时呼吸约{respiratoryRate}，偏快 ② 您提到呼吸方面不适 ③ 建议持续观察并联系兽医 |
| recommendationTemplate | 请观察是否出现张口呼吸、咳嗽或精神变差；如有加重，联系兽医。 |
| whenToSeeVetTemplate | 若呼吸持续加快、出现张口呼吸或精神萎靡，请尽快联系兽医。 |
| toneProfileId | TONE-WARNING |
| evidenceStyle | bullets_as_is |
| llmInstructions | **禁止**「立即」「紧急」主导词；risk 为 warning 非 emergency |
| slots | petName, respiratoryRate, activityLevel, userReportText |

---

### T05 — `warning.HR_RESTING_CHRONIC`

**case**：heart_rate_high_resting_warning (#6)

| 块 | 内容 |
|----|------|
| titlePattern | 安静时心率偏快，结合既往史需关注 |
| summaryOutline | ① 安静状态下心率{heartRate}偏快 ② 存在心脏相关既往史 ③ 建议联系兽医进一步评估 |
| recommendationTemplate | 建议联系兽医，说明安静时心率及既往心脏情况，按医嘱随访。 |
| whenToSeeVetTemplate | 若精神变差、呼吸加快、不愿活动或心率持续偏高，请尽快联系兽医。 |
| toneProfileId | TONE-WARNING |
| evidenceStyle | bullets_light_polish |
| llmInstructions | 须体现既往史；不要确诊心脏病 |
| slots | petName, heartRate, chronicSummary, activityLevel |

---

### T06 — `warning.CHRONIC_HEART_RESP`

**case**：chronic_heart_resp_warning (#20)  
**注**：用药禁忌由 ② CTX-04 `mentionsAdd` 注入 `forcedMentions`

| 块 | 内容 |
|----|------|
| titlePattern | 有心脏病史，安静时呼吸偏快 |
| summaryOutline | ① 宠物有心脏病史 ② 安静时呼吸{respiratoryRate}比平时偏快 ③ 建议联系兽医确认是否需要复查 |
| recommendationTemplate | 请联系兽医反馈当前呼吸频率与精神食欲变化，遵循既有治疗方案。 |
| whenToSeeVetTemplate | 若呼吸明显加快、精神萎靡或食欲下降加重，请尽快联系兽医。 |
| toneProfileId | TONE-WARNING |
| evidenceStyle | bullets_light_polish |
| llmInstructions | 有用药时须呼应「不要自行调整药量」（来自 triage.forcedMentions） |
| slots | petName, respiratoryRate, chronicSummary, userReportText |

---

### T07 — `warning.USER_DEVICE_CONFLICT`

**case**：conflict_user_normal_sensor_fever (#11)

| 块 | 内容 |
|----|------|
| titlePattern | 感受与监测不一致，建议复查体温 |
| summaryOutline | ① 您描述宠物状态与平时相近 ② 设备显示安静时体温{temperature}偏高 ③ 建议复查体温并观察精神 |
| recommendationTemplate | 请结合触摸耳腹温度与精神状态复查，不要仅凭单一感受判断；必要时联系兽医。 |
| whenToSeeVetTemplate | 若复查仍提示发热或精神食欲变差，建议联系兽医。 |
| toneProfileId | TONE-WARNING |
| evidenceStyle | bullets_light_polish |
| llmInstructions | 不否定主人观察，也不否定设备读数；强调「不一致需复查」 |
| slots | petName, temperature, userReportText, activityLevel |

---

### T08 — `warning.REPEATED_VOMITING`

**case**：persistent_vomiting_warning (#14)

| 块 | 内容 |
|----|------|
| titlePattern | 反复呕吐需要关注 |
| summaryOutline | ① 报告反复呕吐 ② 活动与精神可能受影响 ③ 建议联系兽医并避免自行用药 |
| recommendationTemplate | 请联系兽医说明呕吐频次与持续时间，暂时勿自行给予人用药物。 |
| whenToSeeVetTemplate | 若呕吐持续、精神萎靡、便血或无法饮水，请尽快联系兽医。 |
| toneProfileId | TONE-WARNING |
| evidenceStyle | bullets_light_polish |
| slots | petName, userReportText |

---

### T09 — `warning.SENIOR_DECLINE`

**case**：senior_cat_low_energy (#16)

| 块 | 内容 |
|----|------|
| titlePattern | 老年宠物精神食欲下降 |
| summaryOutline | ① 老年宠物精神及活动下降 ② 食欲减退 ③ 结合既往病史建议兽医评估 |
| recommendationTemplate | 建议联系兽医，说明老年阶段的精神、食欲变化及既往病史。 |
| whenToSeeVetTemplate | 若拒食、饮水明显减少或精神持续萎靡，请尽快联系兽医。 |
| toneProfileId | TONE-WARNING |
| evidenceStyle | bullets_light_polish |
| llmInstructions | 不要用「只是正常老化」淡化 |
| slots | petName, speciesLabel, chronicSummary, userReportText |

---

### T10 — `warning.PUPPY_FEVER`

**case**：puppy_fever_high_risk (#17)

| 块 | 内容 |
|----|------|
| titlePattern | 幼宠发热需格外谨慎 |
| summaryOutline | ① 幼宠体温{temperature}偏高 ② 精神不佳 ③ 建议尽快联系兽医 |
| recommendationTemplate | 幼宠异常风险更高，请尽快联系兽医，不要仅依赖居家观察。 |
| whenToSeeVetTemplate | 若体温持续偏高、精神变差或拒食，请立即联系兽医。 |
| toneProfileId | TONE-WARNING |
| evidenceStyle | bullets_light_polish |
| llmInstructions | 不要写「继续观察即可」作为唯一建议 |
| slots | petName, temperature, speciesLabel, userReportText |

---

### T11 — `watch.HRV_STRESS`

**case**：hrv_stress_watch (#7)

| 块 | 内容 |
|----|------|
| titlePattern | 压力或恢复指标偏低，建议观察 |
| summaryOutline | ① 恢复/压力相关指标偏低 ② 近期可能存在环境或社交变化 ③ 建议关注睡眠与食欲 |
| recommendationTemplate | 尽量保持安静环境，观察睡眠、食欲与情绪变化数天。 |
| whenToSeeVetTemplate | 若食欲明显下降、持续紧张或精神萎靡，建议联系兽医。 |
| toneProfileId | TONE-WATCH |
| evidenceStyle | bullets_light_polish |
| slots | petName, userReportText |

---

### T12 — `watch.LIMPING_PAIN`

**case**：limping_pain_watch (#8)  
**注**：`dataQuality=partial` 时 resolver 追加 §九 partial 句

| 块 | 内容 |
|----|------|
| titlePattern | 可能存在跛行或疼痛 |
| summaryOutline | ① 报告跛行或疼痛表现 ② 建议减少运动 ③ 观察步态是否改善 |
| recommendationTemplate | 请减少剧烈活动，避免跳跃，观察步态与是否愿意承重。 |
| whenToSeeVetTemplate | 若跛行持续或加重、明显疼痛或肢体不敢着地，建议联系兽医。 |
| toneProfileId | TONE-WATCH |
| evidenceStyle | bullets_light_polish |
| slots | petName, userReportText |

---

### T13 — `watch.SLOW_RECOVERY`

**case**：recovery_slow_watch (#9)

| 块 | 内容 |
|----|------|
| titlePattern | 运动后恢复偏慢，建议调整活动 |
| summaryOutline | ① 运动后恢复较慢 ② 睡眠质量可能下降 ③ 建议降低活动强度并观察 |
| recommendationTemplate | 适当降低运动强度，保证休息，观察数日内恢复情况。 |
| whenToSeeVetTemplate | 若精神持续低迷、食欲下降或恢复无明显改善，建议联系兽医。 |
| toneProfileId | TONE-WATCH |
| evidenceStyle | bullets_light_polish |
| slots | petName, userReportText |

---

### T14 — `watch.MILD_DIARRHEA`

**case**：mild_diarrhea_watch (#15)

| 块 | 内容 |
|----|------|
| titlePattern | 轻度腹泻，可先观察 |
| summaryOutline | ① 轻度腹泻 ② 精神状态目前尚可 ③ 建议观察排便次数与食欲 |
| recommendationTemplate | 注意观察排便频率、粪便性状与精神食欲，保证清洁饮水。 |
| whenToSeeVetTemplate | 若腹泻加重、便血、呕吐或精神变差，建议联系兽医。 |
| toneProfileId | TONE-WATCH |
| evidenceStyle | bullets_light_polish |
| slots | petName, userReportText |

---

### T15 — `watch.POST_VACCINE`

**case**：post_vaccine_tired_watch (#18)

| 块 | 内容 |
|----|------|
| titlePattern | 疫苗后轻度疲倦，可先观察 |
| summaryOutline | ① 近期接种疫苗 ② 轻度疲倦较常见 ③ 建议观察食欲、体温与精神 |
| recommendationTemplate | 接种后1～2天内可适当休息，观察食欲与精神变化。 |
| whenToSeeVetTemplate | 若高热、持续呕吐、面部肿胀或精神极度萎靡，请联系兽医。 |
| toneProfileId | TONE-WATCH |
| evidenceStyle | bullets_light_polish |
| slots | petName, userReportText |

---

### T16 — `watch.DATA_MISSING`

**case**：missing_vitals (#10)

| 块 | 内容 |
|----|------|
| titlePattern | 健康数据不足，暂无法完整评估 |
| summaryOutline | ① 设备离线或核心体征缺失 ② 当前**无法判断**健康状况 ③ 请检查项圈佩戴与电量 |
| recommendationTemplate | 请先确认设备在线、佩戴位置与充电状态，待数据恢复后再查看。 |
| whenToSeeVetTemplate | 若宠物明显精神萎靡、呕吐或呼吸困难，请直接联系兽医，不必等待设备数据。 |
| toneProfileId | TONE-DATA-LIMIT |
| evidenceStyle | bullets_as_is |
| llmInstructions | **严禁**下健康正常结论 |
| slots | petName, deviceQuality, deviceWarning, missingList |

---

### T17 — `watch.DATA_STALE`

**case**：stale_device_data (#19)

| 块 | 内容 |
|----|------|
| titlePattern | 监测数据已过期 |
| summaryOutline | ① 最近健康数据更新时间较久 ② **不能依据旧数据**判断当前状态 ③ 请确认设备在线并获取新数据 |
| recommendationTemplate | 请确认设备在线并刷新数据；在获得最新监测前，请结合线下观察判断。 |
| whenToSeeVetTemplate | 若宠物出现明显不适表现，请直接联系兽医，勿依赖过期数据。 |
| toneProfileId | TONE-DATA-LIMIT |
| evidenceStyle | bullets_as_is |
| llmInstructions | **严禁**「当前正常」「一切正常」 |
| slots | petName, lastSeenAt, deviceQuality, deviceWarning |

---

### T18 — `emergency.EMERGENCY_RESPIRATORY`

**case**：emergency_breathing_difficulty (#12)

| 块 | 内容 |
|----|------|
| titlePattern | 呼吸困难，请立即就医 |
| summaryOutline | ① 安静时呼吸明显异常 ② 存在呼吸困难相关表现 ③ **请立即联系兽医或就近就医** |
| recommendationTemplate | 请立即联系兽医或前往最近的宠物医院，保持通风，减少应激，途中密切观察。 |
| whenToSeeVetTemplate | 当前情况属于紧急状况，**请立即就医**，不要等待居家观察。 |
| toneProfileId | TONE-EMERGENCY |
| evidenceStyle | bullets_as_is |
| llmInstructions | 紧迫就医导向；禁止「继续观察即可」 |
| slots | petName, respiratoryRate, userReportText |

---

### T19 — `emergency.EMERGENCY_SEIZURE`

**case**：emergency_seizure (#13)

| 块 | 内容 |
|----|------|
| titlePattern | 抽搐，请立即联系兽医 |
| summaryOutline | ① 报告抽搐发作 ② 属于紧急状况 ③ 请立即寻求兽医帮助 |
| recommendationTemplate | 请立即联系兽医；若抽搐持续或反复发作，尽快前往宠物医院急诊。 |
| whenToSeeVetTemplate | 抽搐后请尽快就医，即使暂时缓解也应咨询兽医。 |
| toneProfileId | TONE-EMERGENCY |
| evidenceStyle | bullets_as_is |
| slots | petName, userReportText |

---

### T20 — `emergency.EMERGENCY_TRAUMA`（扩展占位）

**case**：无 V1 case，预留 EMG-03

| 块 | 内容 |
|----|------|
| titlePattern | 外伤，请立即就医 |
| summaryOutline | ① 报告外伤 ② 可能危及生命 ③ 立即就医 |
| toneProfileId | TONE-EMERGENCY |
| evidenceStyle | bullets_as_is |

---

## 十一、按 risk 的兜底模板（fallback-by-risk.v1.json）

当 `templateId` 未命中时使用：

| risk | titlePattern | recommendationTemplate | whenToSeeVetTemplate |
|------|--------------|------------------------|---------------------|
| normal | 当前未见明显异常 | 保持日常观察。 | 有异常变化请联系兽医。 |
| watch | 建议继续观察 | 请留意精神、食欲与活动变化。 | 症状加重请联系兽医。 |
| warning | 建议联系兽医 | 当前信号建议尽快联系兽医进一步评估。 | 若精神变差或症状加重，请尽快就医。 |
| emergency | 请立即就医 | 请立即联系兽医或前往宠物医院。 | 立即就医，不要等待。 |
| DEFAULT | 健康分诊提示 | 请根据宠物当前状态采取适当措施。 | 如有疑虑请联系兽医。 |

兜底时：`evidence = evidenceBullets` 原文；`safetyNotice` 按 `triage.safetyNoticeRequired` 选 §六 snippet；`primaryAction` 由 KB-ACTION + `primaryActionHint` 映射。

---

## 十二、评测锚点（无独立 case-template-index）

| 真源 | 用途 |
|------|------|
| `docs/cases/health_triage_cases.v1.json` | `expected.mustMention` / `mustNotMention` / `safetyNoticeRequired` |
| [case-rule-mapping.md](./case-rule-mapping.md) §五 | Triage Core risk/conf/primaryFlag 硬门槛 |
| `kb-syn.v1.json` | mustMention 同义词扩展 |
| ② `policyTables.ForcedMentionsByFlag` | ③ Prompt 与 ForcedMentionChecker 主关键词 |

**禁止** 维护第四份 case 级 expected 副本（原 `case-template-index` 已取消）。

---

## 十三、模板解析器（③-1）流程

```
输入：FactSheet, TriageCoreResult

1. templateId = finalRiskLevel + "." + primaryFlag
2. template = lookup templates[templateId]
      ?? fallback-by-risk[finalRiskLevel]
      ?? fallback DEFAULT
3. assert template.riskLevel == finalRiskLevel（不一致则告警+log）
4. filledSlots = fill(slots.v1, FactSheet, TriageCoreResult)
5. 按 binding.summarySlotPriority 解析 primaryVital 等派生槽
6. 应用 §九 内联规则（如 partial 追加句）
7. safetyNotice = triage.safetyNoticeRequired
      ? resolveSnippet(risk, primaryFlag)   // §六
      : ""
8. actions = map(KB-ACTION, triage.primaryActionHint, finalRiskLevel)
9. llmPack = {
     templateId, toneProfileId,
     titlePattern, summaryOutline, recommendationTemplate, whenToSeeVetTemplate,
     filledSlots, evidenceBullets,
     requiredMentions: triage.forcedMentions,           // 来自 ②，不 union 模板 mentionHints
     forbidden: union(triage.forbiddenThemes, KB-FORBID),
     llmInstructions, evidenceStyle,
     safetyNoticeSnippet: safetyNotice,
     primaryActionHint: triage.primaryActionHint
   }
10. 输出 CopyTemplateResolved
```

**③ 不得修改**：`finalRiskLevel`、`confidence`、`scene`、`missingData`（来自 ②）。

---

## 十四、③-2 / ④ / ⑤ 衔接

### 14.1 ③-2 LLM 输出（DraftCopyJSON）

仅生成：`title, summary, evidence[], recommendation, whenToSeeVet, safetyNotice, primaryAction, secondaryAction?`

### 14.2 ④ 验证对照

| 检查器 | 数据来源 |
|--------|----------|
| ForcedMentionChecker | `triage.forcedMentions` + **KB-SYN**（§七） |
| ForbiddenPatternMatcher | `triage.forbiddenThemes` + KB-FORBID |
| EmergencyToneGuard | `toneProfileId=TONE-EMERGENCY` 或 `finalRisk=emergency` |
| RiskTextConsistencyGuard | `template.riskLevel` vs 文案强度 |
| EvidenceAuthenticityChecker | `evidenceStyle` + `evidenceBullets` |
| SafetyNoticeEnforcer | `triage.safetyNoticeRequired` |

### 14.3 ⑤ 兜底

重试耗尽 → 用 `CopyTemplateResolved` **机械填槽**生成 DraftCopyJSON，不再调用 LLM。

---

## 十五、与 TriageCoreResult 的对齐表

| TriageCoreResult 字段 | 来源 | KB-TPL 消费方式 |
|----------------------|------|----------------|
| finalRiskLevel | ② FUS | 查表键前缀 + tone 校验 |
| primaryFlag | ② ResolvePrimaryFlag（全 ruleHits，见 case-rule-mapping §6.3） | 查表键后缀 |
| forcedMentions[] | ② policyTables + mentionsAdd | ③ Prompt；④ Checker（+ KB-SYN） |
| forbiddenThemes[] | ② policyTables | ③ Prompt；④ + KB-FORBID |
| evidenceBullets[] | ② EvidenceBuilder | evidence 唯一事实来源 |
| primaryActionHint | ② policyTables | → KB-ACTION → primaryAction |
| safetyNoticeRequired | ② policyTables | → §六 snippet 选用 |
| confidence | ② ConfidenceResolver | **不传入模板**（⑤ 直接锁定） |
| missingDataUser[] | ② `postProcess`（**先于** EvidenceBuilder） | output `missingData`；slots.missingList |

> ~~`flags[]`~~ 已废弃；partial 等读 `FactSheet.device.dataQuality`。

---

## 十六、版本与变更

| 变更类型 | bump | 同步更新 |
|----------|------|----------|
| 改模板 copy / llmInstructions | kb-tpl patch | 相关 case 文案评测 |
| 改 mustMention 关键词 | triage-core `ForcedMentionsByFlag` minor | KB-SYN、cases 无需改则不动 |
| 改禁止主题 | triage-core `ForbiddenByFlag` | KB-FORBID 对齐 |
| 新增 primaryFlag | triage-core + KB-TPL minor | 新模板条 + §3.4 矩阵 |
| 改 slot 定义 | kb-tpl minor | 引用 slots 的模板 |

**联合回归**：`triage-core` 改 risk/flag → 必跑 20 case risk；`policyTables` 改 mention → 跑 mustMention；`kb-tpl` 改 copy → 跑文案软门槛。

---

## 十七、回迁正式架构映射

| KB-TPL 制品 | 正式组件 |
|-------------|----------|
| templates.v1.json | X-50 TemplateRegistry |
| safety-notices.v1.json | X-54 SafetyNoticeTemplateRegistry |
| kb-syn.v1.json | SemanticSynonymMapRegistry |
| tone-by-risk.v1.json | CFG-L6-04 OutputPresentationPolicy |
| ③-1 resolver 逻辑 | X-51 TemplateResolveService + L6-01 OutputFieldComposer |
| ~~action-routes~~ | 已在回迁时并入 ActionRouteTableRegistry（与决策表 ActionByFlagRisk 一致） |

`templateId` 命名保持不变即可迁入 ConfigBundle。

---

## 十八、实施顺序

| 阶段 | KB-TPL 交付 | 跳过 |
|------|------------|------|
| **A（Day 1，仅 risk）** | 可不加载 KB-TPL；⑤ 用 bullets + 极简 fallback | 全套模板 |
| **B（Day 2，文案）** | `templates`（copy + guidance）+ `fallback-by-risk` + `slots` | KB-SYN 可后补 |
| **C（Day 4，打磨）** | + `tone-by-risk` + `safety-notices` + **KB-SYN** | 仍不需要 case-template-index |

重点回归边界：**#4/#12**、**#10/#19/#1**、**#2/#3**、**#11**。

---

## 十九、总结

**KB-TPL V1 = 20 条 `risk × primaryFlag` 文案模板 + 槽位/语气/免责/同义词支撑表**；每条模板仅含 **meta、copy、guidance、binding**。  
**合规与行动单一真源在 ② `triage-core.v1.json` 的 `policyTables`**；KB-TPL 只负责 **在安全约束内如何表达**。  
评测读 **cases JSON + KB-SYN**；~~overlay~~、~~case-template-index~~、~~模板内 compliance 重复字段~~ 已按 Coze 快速验证策略取消。
