# API 实机验证手册

本文档说明如何在本地或测试环境对 **小爪 AI 健康/兽医分诊 Agent V1** HTTP 服务进行实机验证，帮助使用者：

- 了解当前系统已交付的 API 能力边界；
- 使用官方 20 个 mock case 复现预期分诊结果；
- 验证运维探针、契约校验、KB-INPUT-LEX enrich 等可选能力。

> **适用版本**：WP6 机械路径（`POST /health`）+ 占位对话（`POST /intelligent`）。  
> **默认端口**：`8080`（可通过 `HEALTH_API_PORT` 修改）。

---

## 1. 系统能力范围（实机可验证项）

| 能力 | 端点 | 默认状态 | 实机验证方式 |
|------|------|----------|--------------|
| 机械分诊管道 | `POST /health` | ✅ 启用 | 发送 `input_schema` JSON，获得完整 `output_schema` |
| 存活探针 | `GET /internal/healthz` | ✅ 启用 | 返回 `{"status":"ok"}` |
| 就绪探针 | `GET /internal/readyz` | ✅ 启用 | 检查 KB-TPL 预加载；启用 enrich 时检查 `inputLexBundleReady` |
| 入参契约校验 | `POST /health` | ✅ 启用 | 缺字段 → HTTP 400，`stage=parse` |
| ② 风险裁决锁定 | `POST /health` | ✅ 启用 | 对比响应 `riskLevel` 与 case 预期 |
| ③ 机械文案 + ④ 内容守卫 | `POST /health` | ✅ 启用（守卫默认开启） | 检查 `title` / `summary` / `safetyNotice` 等字段 |
| KB-INPUT-LEX enrich | `POST /health` | ❌ 默认关闭 | 需设置 `XIAOZHUA_PIPELINE_INPUT_LEX_ENABLED=true` |
| LLM 文案路径 | 管道内部 | ❌ 默认关闭 | `XIAOZHUA_PIPELINE_LLM_ENABLED=false` |
| 智能对话占位 | `POST /intelligent` | ✅ 默认启用 | 返回占位信封，**不执行分诊** |

**管道阶段（失败时 `stage` 字段）**：`enrich` → `parse` → `triage` → `resolve` → `mechanical` → `guard` → `merge_ready` → `merge` → `final_schema` → `completed`。

**风险等级（`riskLevel`）**：`normal` | `watch` | `warning` | `emergency`。仅由 ② 分诊核裁决，LLM 不得改写。

---

## 2. 前置条件

### 2.1 环境

```bash
cd /path/to/xiaozhua-health-agent

# 复制并编辑运行时配置
cp .env.example .env

# 安装依赖（若尚未安装）
uv sync
```

### 2.2 启动服务

```bash
# 方式一：控制台脚本
.venv/bin/xiaozhua-health-agent

# 方式二：模块入口
.venv/bin/python -m xiaozhua_health_agent
```

服务默认监听 `http://0.0.0.0:8080`。另开终端执行下文 curl 命令。

### 2.3 关键环境变量（摘录）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HEALTH_API_PORT` | `8080` | HTTP 端口 |
| `HEALTH_API_INTERNAL_PREFIX` | `/internal` | 探针路径前缀 |
| `HEALTH_API_PRELOAD_COPY_BUNDLE` | `true` | 启动预加载 KB-TPL |
| `HEALTH_API_PRELOAD_INPUT_LEX_BUNDLE` | `false` | 启动预加载 KB-INPUT-LEX |
| `XIAOZHUA_PIPELINE_INPUT_LEX_ENABLED` | `false` | parse 前口语 enrich |
| `XIAOZHUA_PIPELINE_LLM_ENABLED` | `false` | LLM 文案（V1 主路径为机械） |

### 2.4 Mock 数据集路径

官方 20 case 位于仓库根目录（相对项目根）：

```text
../docs/cases/health_triage_cases.v1.json
```

绝对路径示例（请按本机调整）：

```text
/home/vancer17/test/agent/docs/cases/health_triage_cases.v1.json
```

依赖 `jq` 提取 case 入参（推荐安装）。

---

## 3. 公共 Shell 辅助函数

在测试终端执行一次，后续命令可直接复用：

```bash
export BASE_URL="http://127.0.0.1:8080"
export CASES_JSON="/home/vancer17/test/agent/docs/cases/health_triage_cases.v1.json"

# 按 caseId 提取官方 mock 入参（完整 input_schema JSON）
case_input() {
  jq -c --arg id "$1" '.cases[] | select(.caseId == $id) | .input' "$CASES_JSON"
}

# 发送 POST /health 并打印关键响应字段
post_health_case() {
  local case_id="$1"
  curl -sS -w "\nHTTP %{http_code}\n" -X POST "$BASE_URL/health" \
    -H "Content-Type: application/json" \
    -d "$(case_input "$case_id")" \
    | tee "/tmp/health_${case_id}.json" \
    | jq '{caseId: .caseId, riskLevel, confidence, title, safetyNotice}' 2>/dev/null \
      || cat "/tmp/health_${case_id}.json"
}
```

---

## 4. 运维探针

### 4.1 存活检查

```bash
curl -sS "$BASE_URL/internal/healthz" | jq .
```

**期望**：`{"status":"ok"}`，HTTP 200。

### 4.2 就绪检查

```bash
curl -sS "$BASE_URL/internal/readyz" | jq .
```

**期望（默认配置）**：

```json
{
  "ready": true,
  "copyBundleReady": true,
  "inputLexBundleReady": true,
  "message": ""
}
```

说明：未启用 enrich 时 `inputLexBundleReady` 恒为 `true`；启用 enrich 且要求预加载词表时，需 `HEALTH_API_PRELOAD_INPUT_LEX_BUNDLE=true` 或运行期能加载默认词表。

---

## 5. 官方 20 Case 对照表

| caseId | 场景简述 | 期望 riskLevel | 期望 confidence |
|--------|----------|----------------|-----------------|
| `normal_dog_daily_check` | 正常健康 | `normal` | `high` |
| `mild_fever_after_exercise` | 运动后轻度发热 | `watch` | `medium` |
| `high_fever_resting` | 安静高热 | `warning` | `high` |
| `respiratory_rate_high_resting` | 安静呼吸率偏高 | `warning` | `high` |
| `heart_rate_high_after_play` | 运动后心率偏高 | `watch` | `medium` |
| `heart_rate_high_resting_warning` | 安静心率异常 | `warning` | `high` |
| `hrv_stress_watch` | HRV 偏低 / 压力 | `watch` | `medium` |
| `limping_pain_watch` | 跛行疼痛 | `watch` | `medium` |
| `recovery_slow_watch` | 恢复偏慢 | `watch` | `medium` |
| `missing_vitals` | 体征缺失 | `watch` | `low` |
| `conflict_user_normal_sensor_fever` | 用户说正常但传感器发热 | `warning` | `medium` |
| `emergency_breathing_difficulty` | 呼吸困难 | `emergency` | `high` |
| `emergency_seizure` | 抽搐 | `emergency` | `high` |
| `persistent_vomiting_warning` | 持续呕吐 | `warning` | `medium` |
| `mild_diarrhea_watch` | 轻度腹泻 | `watch` | `medium` |
| `senior_cat_low_energy` | 老年猫精神差 | `warning` | `medium` |
| `puppy_fever_high_risk` | 幼犬发热 | `warning` | `high` |
| `post_vaccine_tired_watch` | 疫苗后疲倦 | `watch` | `medium` |
| `stale_device_data` | 设备数据过期 | `watch` | `low` |
| `chronic_heart_resp_warning` | 心脏病史 + 呼吸偏高 | `warning` | `high` |

---

## 6. 单 Case 验证命令

定义好第 3 节辅助函数后，按场景分类执行：

```bash
# --- normal ---
post_health_case normal_dog_daily_check

# --- watch ---
post_health_case mild_fever_after_exercise
post_health_case heart_rate_high_after_play
post_health_case hrv_stress_watch
post_health_case limping_pain_watch
post_health_case recovery_slow_watch
post_health_case missing_vitals
post_health_case mild_diarrhea_watch
post_health_case post_vaccine_tired_watch
post_health_case stale_device_data

# --- warning ---
post_health_case high_fever_resting
post_health_case respiratory_rate_high_resting
post_health_case heart_rate_high_resting_warning
post_health_case conflict_user_normal_sensor_fever
post_health_case persistent_vomiting_warning
post_health_case senior_cat_low_energy
post_health_case puppy_fever_high_risk
post_health_case chronic_heart_resp_warning

# --- emergency ---
post_health_case emergency_breathing_difficulty
post_health_case emergency_seizure
```

**单条 curl（不依赖 `post_health_case`）**：

```bash
curl -sS -X POST "$BASE_URL/health" \
  -H "Content-Type: application/json" \
  -d "$(case_input emergency_seizure)" \
  | jq '{riskLevel, confidence, title, safetyNotice}'
```

---

## 7. 批量回归脚本（20 Case 全量）

自动对比每个 case 的 `riskLevel` 是否与预期一致：

```bash
while IFS=$'\t' read -r case_id expected; do
  actual=$(curl -sS -X POST "$BASE_URL/health" \
    -H "Content-Type: application/json" \
    -d "$(case_input "$case_id")" | jq -r '.riskLevel')
  status=$([ "$actual" = "$expected" ] && echo OK || echo FAIL)
  printf "%-36s expected=%-10s actual=%-10s %s\n" "$case_id" "$expected" "$actual" "$status"
done <<'EOF'
normal_dog_daily_check	normal
mild_fever_after_exercise	watch
high_fever_resting	warning
respiratory_rate_high_resting	warning
heart_rate_high_after_play	watch
heart_rate_high_resting_warning	warning
hrv_stress_watch	watch
limping_pain_watch	watch
recovery_slow_watch	watch
missing_vitals	watch
conflict_user_normal_sensor_fever	warning
emergency_breathing_difficulty	emergency
emergency_seizure	emergency
persistent_vomiting_warning	warning
mild_diarrhea_watch	watch
senior_cat_low_energy	warning
puppy_fever_high_risk	warning
post_vaccine_tired_watch	watch
stale_device_data	watch
chronic_heart_resp_warning	warning
EOF
```

**期望**：20 行均为 `OK`。任一行 `FAIL` 表示 ② 裁决或管道与验收数据集不一致，需结合 `/tmp/health_<caseId>.json` 排查。

---

## 8. 重点场景独立载荷

以下示例可直接复制执行（含完整 `input_schema` 字段），用于演示关键能力。

### 8.1 紧急 — 抽搐（`emergency_seizure`）

```bash
curl -sS -X POST "$BASE_URL/health" \
  -H "Content-Type: application/json" \
  -d @- <<'EOF' | jq '{riskLevel, confidence, title, safetyNotice}'
{
  "caseId": "emergency_seizure",
  "scene": "health_triage",
  "timestamp": "2026-06-08T12:00:00+08:00",
  "pet": {"petId": "pet-013", "name": "点点", "species": "cat", "breed": null, "sex": "male", "ageMonths": 18, "weightKg": 3.9, "neutered": false, "chronicConditions": [], "medications": [], "allergies": []},
  "device": {"deviceOnline": true, "batteryLevel": 80, "lastSeenAt": "2026-06-08T11:59:00+08:00", "collarId": "collar-013", "dataQuality": "partial", "warningText": null},
  "vitals": {"temperatureC": null, "heartRateBpm": 190, "respiratoryRateBpm": 55, "hrvMs": null, "stepsToday": 100, "activityLevel": "unknown", "sleepQuality": "unknown", "updatedAt": "2026-06-08T11:59:00+08:00"},
  "healthEvidence": {"riskLevel": "emergency", "riskLabel": "紧急", "displayClaim": "用户报告抽搐", "recommendationText": "建议立即联系兽医。", "confidence": "high", "signals": []},
  "userReport": {"text": "刚刚突然抽搐了一阵。", "duration": "刚刚", "symptoms": ["抽搐"], "appetite": "unknown", "drinking": "unknown", "energy": "very_low", "vomiting": "unknown", "diarrhea": "unknown", "coughing": null, "breathingDifficulty": null, "pain": null, "limping": null, "seizure": true, "trauma": false},
  "context": {"environmentTempC": 24, "recentExercise": "unknown", "recentVaccination": false, "recentMeal": null, "ageRisk": "normal", "notes": []},
  "missingData": ["temperature", "hrv"]
}
EOF
```

**期望**：`riskLevel=emergency`，`safetyNotice` 非空，文案含「立即」「兽医」等语义（见 case `mustMention`）。

### 8.2 正常日常（`normal_dog_daily_check`）

```bash
curl -sS -X POST "$BASE_URL/health" \
  -H "Content-Type: application/json" \
  -d "$(case_input normal_dog_daily_check)" \
  | jq '{riskLevel, confidence, title}'
```

**期望**：`riskLevel=normal`，`confidence=high`。

### 8.3 数据冲突（用户描述 vs 传感器）

```bash
curl -sS -X POST "$BASE_URL/health" \
  -H "Content-Type: application/json" \
  -d "$(case_input conflict_user_normal_sensor_fever)" \
  | jq '{riskLevel, confidence, title}'
```

**期望**：`riskLevel=warning`（设备数据优先于用户「没事」类主观描述）。

### 8.4 设备数据缺失

```bash
curl -sS -X POST "$BASE_URL/health" \
  -H "Content-Type: application/json" \
  -d "$(case_input missing_vitals)" \
  | jq '{riskLevel, confidence, title}'
```

**期望**：`riskLevel=watch`，`confidence=low`，文案应说明数据不足、不得编造「正常」。

---

## 9. 负向测试（契约校验）

```bash
curl -sS -w "\nHTTP %{http_code}\n" -X POST "$BASE_URL/health" \
  -H "Content-Type: application/json" \
  -d '{"caseId":"invalid-only"}' | jq .
```

**期望**：

- HTTP **400**
- `error`: `input_validation_failed`
- `stage`: `parse`
- `violations`: 非空数组

---

## 10. KB-INPUT-LEX Enrich 实机验证（可选）

默认 **关闭** enrich。验证口语 → 结构化字段补全前，在 `.env` 中设置并重启服务：

```bash
XIAOZHUA_PIPELINE_INPUT_LEX_ENABLED=true
XIAOZHUA_PIPELINE_LOAD_DEFAULT_INPUT_LEX_BUNDLE=true
HEALTH_API_PRELOAD_INPUT_LEX_BUNDLE=true
```

### 10.1 口语抽搐（`seizure` 为 null，靠文本匹配）

```bash
curl -sS -X POST "$BASE_URL/health" \
  -H "Content-Type: application/json" \
  -d @- <<'EOF' | jq '{riskLevel, confidence, title}'
{
  "caseId": "manual_colloquial_seizure",
  "scene": "health_triage",
  "timestamp": "2026-06-09T10:00:00+08:00",
  "pet": {"petId": "pet-manual", "name": "测试犬", "species": "dog", "breed": "Corgi", "sex": "male", "ageMonths": 36, "weightKg": 11.2, "neutered": true, "chronicConditions": [], "medications": [], "allergies": []},
  "device": {"deviceOnline": true, "batteryLevel": 82, "lastSeenAt": "2026-06-09T09:59:00+08:00", "collarId": "collar-manual", "dataQuality": "good", "warningText": null},
  "vitals": {"temperatureC": 38.4, "heartRateBpm": 92, "respiratoryRateBpm": 24, "hrvMs": 54, "stepsToday": 3200, "activityLevel": "light", "sleepQuality": "good", "updatedAt": "2026-06-09T09:59:00+08:00"},
  "healthEvidence": {"riskLevel": "normal", "riskLabel": "正常", "displayClaim": "当前健康状态平稳", "recommendationText": "保持日常观察即可。", "confidence": "high", "signals": []},
  "userReport": {
    "text": "刚刚突然抽搐了一阵，口吐白沫",
    "duration": null,
    "symptoms": [],
    "appetite": "unknown",
    "drinking": "unknown",
    "energy": "unknown",
    "vomiting": "unknown",
    "diarrhea": "unknown",
    "coughing": false,
    "breathingDifficulty": null,
    "pain": null,
    "limping": null,
    "seizure": null,
    "trauma": null
  },
  "context": {"environmentTempC": 24, "recentExercise": "light", "recentVaccination": false, "recentMeal": true, "ageRisk": "normal", "notes": []},
  "missingData": []
}
EOF
```

**期望**：enrich 将 `userReport.seizure` 补全为 `true` 后，② 分诊输出 `riskLevel=emergency`。

### 10.2 与官方结构化 case 的关系

启用 enrich 时，已结构化的 20 case 应仍通过 `explicitUiWinsOverLexicon` 保持 **riskLevel 无回归**（自动化测试见 `tests/input_lex/test_enrich_service.py`）。

---

## 11. 智能对话占位端点

`POST /intelligent` **不执行分诊管道**，仅返回占位对话信封（方案 A）。

```bash
curl -sS -X POST "$BASE_URL/intelligent" \
  -H "Content-Type: application/json" \
  -H "X-Session-Id: sess-manual-001" \
  -d "$(case_input normal_dog_daily_check)" \
  | jq '{mode, triageStatus, caseId, messagePreview: .messages[0]}'
```

**期望**：

- `mode`: `placeholder`
- `triage`: `null`
- `triageStatus`: `not_run`
- HTTP 200（无需预加载 KB-TPL）

关闭端点时设置 `HEALTH_API_INTELLIGENT_ENABLED=false`，同一请求应返回 HTTP 404。

---

## 12. 响应字段检查清单

成功分诊（HTTP 200）时，建议抽查以下 `output_schema` 字段：

```bash
curl -sS -X POST "$BASE_URL/health" \
  -H "Content-Type: application/json" \
  -d "$(case_input emergency_seizure)" \
  | jq '{
    riskLevel,
    confidence,
    scene,
    title,
    summary,
    safetyNotice,
    primaryAction,
    evidence: .evidence[0:2]
  }'
```

| 字段 | 说明 |
|------|------|
| `riskLevel` | 必须与 ② 分诊核一致，不得被文案阶段修改 |
| `confidence` | `high` / `medium` / `low` |
| `title` / `summary` | 机械模板或 LLM 文案（默认机械） |
| `safetyNotice` | 中高风险场景通常非空 |
| `primaryAction` | 来自 KB-ACTION 映射 |
| `evidence` | 证据列表，缺数据时不应编造 |

完整响应可落盘：

```bash
curl -sS -X POST "$BASE_URL/health" \
  -H "Content-Type: application/json" \
  -d "$(case_input emergency_seizure)" \
  | jq . > /tmp/emergency_seizure_output.json
```

---

## 13. 常见问题

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| `readyz` 返回 503 | 启动未完成或 `startup_error` 非空 | 查看服务日志；确认 `assets/` 路径正确 |
| `copyBundleReady=false` | 未预加载且运行期加载失败 | 设置 `HEALTH_API_PRELOAD_COPY_BUNDLE=true` |
| `inputLexBundleReady=false` | 启用了 enrich 但词表未就绪 | 设置 `HEALTH_API_PRELOAD_INPUT_LEX_BUNDLE=true` |
| HTTP 400 `stage=parse` | 入参不符合 `input_schema` | 对照 schema 或官方 case JSON |
| HTTP 422 / 500 | merge 或 schema 阶段失败 | 查看响应 `error` 与 `violations` |
| `case_input` 报错 | 未安装 `jq` 或 `CASES_JSON` 路径错误 | 安装 `jq` 并修正路径 |
| 响应慢（~1s/次） | 全管道含守卫与 schema 校验 | 属正常；批量测试请用第 7 节脚本 |

---

## 14. 相关文档

| 文档 | 路径 |
|------|------|
| Mock case 数据集 | `docs/cases/health_triage_cases.v1.json` |
| 输入契约 schema | `docs/schema/xiaozhua_health_agent_input_schema.v1.json` |
| 输出契约 schema | `docs/schema/xiaozhua_health_agent_output_schema.v1.json` |
| 运行时配置示例 | `xiaozhua-health-agent/.env.example` |
| WP0–WP5 实现一致性报告 | `xiaozhua-health-agent/docs/delivery/wp0-wp5-implementation-consistency-report.md` |
| 管道设计 | `docs/implementation/coze/pipeline-design.md` |

---

## 15. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-09 | 初版：WP6 机械 API 实机验证命令与 20 case 对照表 |
