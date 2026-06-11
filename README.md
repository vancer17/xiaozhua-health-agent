# 小爪 AI 健康/兽医分诊 Agent V1

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

受约束的宠物健康/兽医分诊决策服务（FastAPI）。消费 `input_schema.v1` 健康快照，产出符合 `output_schema.v1` 的结构化 JSON，供 App `/health` 卡片直接渲染。

**核心能力**：确定性风险分级、证据融合、模板化文案、安全合规守卫、缺数据诚实表达。  
**非目标**：确诊、保证性结论、在无依据时编造历史或趋势。

---

## 功能概览

| 能力 | 状态 |
|------|------|
| 单次健康分诊 `POST /health` | 已实现（机械管道 + 可选 LLM 文案） |
| 20 case 批跑与里程碑硬门槛 | 已实现（WP0–WP5） |
| 运维探针 `/internal/healthz`、`/internal/readyz` | 已实现 |
| 智能对话 `POST /intelligent` | V1 静态占位（不执行分诊管道） |
| Docker 镜像交付 | 已实现 |
| Session / 鉴权 / ConfigRelease | V1 未实现 |

### 分诊管道（五模块）

```text
① 输入解析 → ② 确定性分诊核 → ③ 文案生成 → ④ 验证与重试 → ⑤ 合并与输出
```

- **② 医学裁决**由确定性规则引擎完成，`riskLevel` / `confidence` 不由 LLM 单独决定。
- **③** 默认走机械模板填槽；设置 `XIAOZHUA_PIPELINE_LLM_ENABLED=true` 并配置通义千问后可启用 LLM 润色。
- **④⑤** 含禁止词、证据真实性、紧急语气等守卫，以及模板兜底，保证出站 JSON 合法。

---

## 环境要求

- **Python** ≥ 3.13
- **[uv](https://docs.astral.sh/uv/)**（依赖与虚拟环境管理）
- **Docker**（可选，用于容器化部署）

---

## 快速开始

### 1. 克隆与安装

```bash
git clone <repository-url>
cd xiaozhua-health-agent

cp .env.example .env
# 按需编辑 .env（本地开发通常保持 LLM_ENABLED=false 即可）

uv sync --all-groups
```

### 2. 启动 HTTP 服务

```bash
uv run xiaozhua-health-agent
```

默认监听 `http://0.0.0.0:8080`。

- **OpenAPI 文档**：`http://localhost:8080/docs`
- **就绪探针**：`http://localhost:8080/internal/readyz`
- **存活探针**：`http://localhost:8080/internal/healthz`

### 3. 调用分诊 API

请求体为 `docs/cases/health_triage_cases.v1.json` 中任意 case 的 `input` 字段（符合 `input_schema.v1`）。

```bash
curl -sS -X POST http://localhost:8080/health \
  -H 'Content-Type: application/json' \
  -d @<(jq '.cases[0].input' docs/cases/health_triage_cases.v1.json)
```

成功时返回 200 及完整 `output_schema.v1` 字段（`riskLevel`、`title`、`summary`、`evidence`、`recommendation`、`safetyNotice` 等）。

---

## 配置说明

运行时配置通过环境变量加载（可参考 `.env.example`）。业务规则不在此修改，规则变更应走代码/知识资产版本发布与 20 case 回归。

### HTTP 服务（前缀 `HEALTH_API_`）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HEALTH_API_HOST` | `0.0.0.0` | 监听地址 |
| `HEALTH_API_PORT` | `8080` | 监听端口 |
| `HEALTH_API_PRELOAD_COPY_BUNDLE` | `true` | 启动时预加载 KB-TPL（影响 `readyz`） |
| `HEALTH_API_INTERNAL_PREFIX` | `/internal` | 运维探针路径前缀 |
| `HEALTH_API_INTELLIGENT_ENABLED` | `true` | 是否挂载 `POST /intelligent` |

### 管道行为（前缀 `XIAOZHUA_PIPELINE_`）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `XIAOZHUA_PIPELINE_LLM_ENABLED` | `false` | 是否启用 LLM 文案生成 |
| `XIAOZHUA_PIPELINE_ENABLE_MERGE_FALLBACK` | `true` | LLM/校验失败时模板兜底 |
| `XIAOZHUA_PIPELINE_GUARD_MODE` | `strict` | 内容守卫严格度 |

### 制品路径（前缀 `XIAOZHUA_`）

相对路径基于 **项目根目录**。本地开发可省略 `XIAOZHUA_PROJECT_ROOT`（自动推断）；**Docker 镜像内必须设为 `/app`**（已在 Dockerfile 中固定）。

| 变量 | 默认相对路径 |
|------|-------------|
| `XIAOZHUA_CASES_PATH` | `docs/cases/health_triage_cases.v1.json` |
| `KB_TPL_DIR` / `XIAOZHUA_KB_TPL_DIR` | `assets/kb-tpl/config` |
| `XIAOZHUA_KB_FORBID_PATH` | `assets/kb-forbid/forbidden_patterns.v1.json` |
| `XIAOZHUA_KB_SYN_PATH` | `assets/kb-syn/kb-syn.v1.json` |
| `XIAOZHUA_KB_ACTION_PATH` | `assets/kb-action/actions.v1.json` |

### LLM（前缀 `QWEN_`，仅 `LLM_ENABLED=true` 时需要）

| 变量 | 说明 |
|------|------|
| `QWEN_API_KEY` | 通义千问 API Key（**勿提交到仓库**） |
| `QWEN_BASE_URL` | 默认 DashScope 兼容模式端点 |
| `QWEN_MODEL` | 默认 `qwen-plus` |

---

## HTTP API

| 方法 | 路径 | 用途 |
|------|------|------|
| `POST` | `/health` | **产品 API**：健康/兽医分诊，返回 `output_schema.v1` |
| `POST` | `/intelligent` | V1 占位对话（静态模板，`triageStatus=not_run`） |
| `GET` | `/internal/healthz` | **运维**：存活探针（进程活着即可） |
| `GET` | `/internal/readyz` | **运维**：就绪探针（知识包加载完成后接流量） |

> 注意：运维探针路径为 `/internal/healthz`，与产品分诊 API `POST /health` 不同，避免与 K8s 习惯命名混淆。

### 错误语义（`POST /health`）

| HTTP 状态 | 典型原因 |
|-----------|----------|
| `400` | 输入契约校验失败 |
| `422` | merge-ready 或出站 schema 不满足 |
| `500` | 管道内部失败 |
| `503` | 服务未就绪（如 KB-TPL 加载失败） |

---

## Docker

### 构建

```bash
docker build -t xiaozhua-health-agent:local .
```

采用 **两阶段构建**（`python:3.13-slim-bookworm` + `uv`）：运行镜像内含应用虚拟环境与 `assets/` 知识资产，以非 root 用户运行。

### 运行

```bash
docker run --rm -p 18080:8080 \
  -e XIAOZHUA_PROJECT_ROOT=/app \
  -e XIAOZHUA_PIPELINE_LLM_ENABLED=false \
  xiaozhua-health-agent:local
```

访问：`http://localhost:18080/internal/readyz`、`http://localhost:18080/health`。

**端口冲突**：若宿主机 `8080` 已被占用，将左侧映射端口改为 `18080`（或任意空闲端口），例如 `-p 18080:8080`。容器内应用仍监听 `8080`。

### 镜像内路径说明

包安装于 `/app/.venv`，知识资产位于 `/app/assets/`。必须通过 `XIAOZHUA_PROJECT_ROOT=/app` 解析制品路径；该变量已在 Dockerfile 中预设，手动 `docker run` 时请勿省略。

---

## 测试与回归

### 单元测试与静态检查

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
```

### 20 case 批跑

```bash
# 仅 riskLevel 硬门槛（② 分诊核）
uv run python -m xiaozhua_health_agent.eval.batch_runner --mode risk-only

# 里程碑 B：机械管道全链路硬门槛（CI 门禁）
uv run python -m xiaozhua_health_agent.eval.batch_runner --mode milestone-b

# 完整输出评测（结构 + 语义 + 禁止词等）
uv run python -m xiaozhua_health_agent.eval.batch_runner --mode full-output

# LLM 文案批跑（需 QWEN_API_KEY）
uv run python -m xiaozhua_health_agent.eval.batch_runner --mode copy-llm
```

### 硬门槛 vs 软门槛

| 类型 | 标准 |
|------|------|
| **硬门槛** | 20/20 `riskLevel` 正确；0 结构错误；0 禁止词；`safetyNoticeRequired=true` 时 `safetyNotice` 非空 |
| **软门槛** | `confidence` 对齐；`mustMention` ≥ 18/20（可借助 KB-SYN 同义词） |

**排查原则**：`riskLevel` 错误先查 ② 规则引擎，不要先改 LLM Prompt。

---

## 持续集成

GitHub Actions 工作流 `.github/workflows/backend-ci.yml`（Pull Request 触发）：

1. **Backend**：Ruff lint/format → Pytest → Milestone B 20 case 硬门槛  
2. **Docker**：构建镜像 → 启动容器 → `curl /internal/readyz` 冒烟测试  

---

## 项目结构

```text
xiaozhua-health-agent/
├── src/xiaozhua_health_agent/   # 应用源码
│   ├── api/                     # FastAPI 路由、探针、HTTP 映射
│   ├── triage/                  # ② 确定性分诊核（规则、融合、策略表）
│   ├── pipeline/                # 管道编排、重试、兜底
│   ├── copy/                    # ③ 模板解析与 LLM 文案
│   ├── guard/                   # ④ 内容合规守卫
│   ├── output/                  # ⑤ 合并与出站校验
│   ├── eval/                    # 批跑评测器
│   ├── schemas/                 # input/output 契约类型
│   └── intelligent/             # /intelligent 占位
├── assets/                      # 知识资产（KB-TPL、禁止词、同义词、动作表）
├── docs/                        # 契约、case、架构与实现设计文档
├── tests/                       # 单元与集成测试
├── Dockerfile
├── pyproject.toml
└── uv.lock
```

---

## 知识资产

| 目录 | 用途 |
|------|------|
| `assets/kb-tpl/config/` | 文案模板、槽位、语气、兜底（③⑤） |
| `assets/kb-forbid/` | 全局禁止词（④ + 评测） |
| `assets/kb-syn/` | mustMention 同义词（评测 + ④） |
| `assets/kb-action/` | `primaryAction` label/route |
| `assets/eval/` | action 矩阵评测 fixture |

医学裁决与合规约束（`forcedMentions`、`primaryFlag` 等）真源在 `src/xiaozhua_health_agent/triage/`（`policy_data.py`、`rules_v1.py`）；KB-TPL 仅负责「怎么说」。

**版本原则**：改规则 → 代码/策略表 + 回归；改文案 → KB-TPL + 回归；二者独立版本、联合验收。

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [docs/README.md](docs/README.md) | 契约与 case 使用说明 |
| [docs/schema/](docs/schema/) | `input_schema` / `output_schema` JSON |
| [docs/cases/health_triage_cases.v1.json](docs/cases/health_triage_cases.v1.json) | 20 个 mock case |
| [docs/architecture/overall.md](docs/architecture/overall.md) | 完整七层架构设计 |
| [docs/implementation/coze/pipeline-design.md](docs/implementation/coze/pipeline-design.md) | 快速验证版五模块管道 |
| [docs/plans/coze-workflow-dev-plan.md](docs/plans/coze-workflow-dev-plan.md) | WP0–WP7 开发计划 |
| [docs/delivery/wp0-wp5-implementation-consistency-report.md](docs/delivery/wp0-wp5-implementation-consistency-report.md) | 实现一致性报告 |

---

## V1 边界与红线

- 紧急症状必须升级为 `emergency`
- 缺数据时不编造；数据缺失/过期不得输出「当前正常」
- 禁止确诊与保证性结论（见 `output_schema` 的 `forbiddenOutputPatterns`）
- `/intelligent` 不执行分诊管道；多轮会话、鉴权、限流、ConfigRelease 留待后续版本
- 评测与观测不反哺实时 serving 行为

---

## 许可证

本项目采用 [MIT License](LICENSE) 发布。

Copyright (c) 2026 vancer17
