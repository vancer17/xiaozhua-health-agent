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
| Docker Compose 编排（API + 评测 profile） | 已实现 |
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

| 场景 | 依赖 |
|------|------|
| **本地开发** | Python ≥ 3.13、[uv](https://docs.astral.sh/uv/) |
| **容器交付 / 部署** | Docker、Docker Compose v2 |

---

## 快速开始

```bash
git clone <repository-url>
cd xiaozhua-health-agent
cp .env.example .env
# 按需编辑 .env（本地/容器通常保持 XIAOZHUA_PIPELINE_LLM_ENABLED=false）
```

任选一种方式启动服务。

### 方式 A：Docker Compose（推荐交付与联调）

```bash
docker compose up --build -d
curl -sf http://localhost:8080/internal/readyz
```

- 默认使用镜像内嵌的 `assets/`（与 CI 构建一致，可复现）
- 运行时配置从 `.env` 注入；`XIAOZHUA_PROJECT_ROOT=/app` 已在 Compose 中固定
- 宿主机端口映射为 `${HEALTH_API_PUBLISH_PORT:-8080}:8080`（见 `compose.env.example`）

**本地改知识资产、免 rebuild**（可选）：

```bash
cp compose.override.example.yml compose.override.yml
# 若 8080 已被占用，在 .env 中设置 HEALTH_API_PUBLISH_PORT=18080
docker compose up --build
```

`compose.override.yml` 会将 `./assets` 只读挂载到容器，改模板后 `docker compose restart health-agent` 即可。

### 方式 B：本地 uv 开发

```bash
uv sync --all-groups
uv run xiaozhua-health-agent
```

默认监听 `http://0.0.0.0:8080`。

### 调用分诊 API

请求体为 `docs/cases/health_triage_cases.v1.json` 中任意 case 的 `input` 字段（符合 `input_schema.v1`）。

```bash
# 端口按实际映射调整（Compose 默认 8080；override 示例常用 18080）
curl -sS -X POST http://localhost:8080/health \
  -H 'Content-Type: application/json' \
  -d @<(jq '.cases[0].input' docs/cases/health_triage_cases.v1.json)
```

成功时返回 200 及完整 `output_schema.v1` 字段（`riskLevel`、`title`、`summary`、`evidence`、`recommendation`、`safetyNotice` 等）。

### 端点速查

| 用途 | URL（默认端口 8080） |
|------|---------------------|
| OpenAPI 文档 | `http://localhost:8080/docs` |
| 就绪探针 | `http://localhost:8080/internal/readyz` |
| 存活探针 | `http://localhost:8080/internal/healthz` |

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

### LLM（前缀 `QWEN_`，仅 `XIAOZHUA_PIPELINE_LLM_ENABLED=true` 时需要）

| 变量 | 说明 |
|------|------|
| `QWEN_API_KEY` | 通义千问 API Key（**勿提交到仓库**） |
| `QWEN_BASE_URL` | 默认 DashScope 兼容模式端点 |
| `QWEN_MODEL` | 默认 `qwen-plus` |

### Docker Compose 插值（可选，写入 `.env`）

与 `.env.example` 中的应用配置可合并；也可参考 `compose.env.example`。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `IMAGE_TAG` | `local` | 镜像 tag |
| `HEALTH_API_PUBLISH_PORT` | `8080` | 宿主机映射端口 |
| `EVAL_MODE` | `milestone-b` | `eval` profile 批跑模式 |

**配置分工**：运行时开关与密钥走 `.env`；知识资产在**交付环境**使用镜像内嵌 `assets/`，**本地开发**可通过 `compose.override.yml` 挂载覆盖。

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

## Docker 与 Compose

### 镜像构建

```bash
docker build -t xiaozhua-health-agent:local .
# 或
docker compose build
```

采用 **两阶段构建**（`python:3.13-slim-bookworm` + `uv`）：

- 运行镜像含 `/app/.venv` 应用环境与 `/app/assets/` 知识资产
- 非 root 用户（uid `10001`）运行
- 内置 `HEALTHCHECK` 探测 `/internal/readyz`

### Compose 服务

| 服务 | Profile | 说明 |
|------|---------|------|
| `health-agent` | 默认 | 长期运行 API；`restart: unless-stopped` |
| `eval-batch` | `eval` | 一次性 20 case 批跑；挂载 `docs/cases`，报告写入 `logs/eval/report.json` |

```bash
# 启动 API（后台）
docker compose up --build -d

# 查看日志 / 停止
docker compose logs -f health-agent
docker compose down

# 容器内批跑（无需本地 uv）
docker compose --profile eval run --rm eval-batch
```

### 仅用 docker run（不经过 Compose）

```bash
docker run --rm -p 18080:8080 \
  -e XIAOZHUA_PROJECT_ROOT=/app \
  -e XIAOZHUA_PIPELINE_LLM_ENABLED=false \
  xiaozhua-health-agent:local
```

访问：`http://localhost:18080/internal/readyz`、`http://localhost:18080/docs`。

### 路径与资产策略

| 路径 | 说明 |
|------|------|
| `/app/.venv` | Python 虚拟环境（应用包安装于此） |
| `/app/assets/` | 镜像内知识资产（交付默认真源） |
| `XIAOZHUA_PROJECT_ROOT=/app` | 制品相对路径的基准；Dockerfile / Compose 已预设 |

**交付 / 生产**：使用镜像内嵌 `assets/`，保证与 CI 构建、Milestone B 验收一致。  
**本地开发**：可复制 `compose.override.example.yml` → `compose.override.yml`，只读挂载 `./assets`，改 JSON 后重启容器即可，无需 rebuild。

---

## 测试与回归

### 单元测试与静态检查

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
```

### 20 case 批跑

**本地（uv）**：

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

**容器（Compose `eval` profile）**：

```bash
# 默认 milestone-b；报告 logs/eval/report.json
docker compose --profile eval run --rm eval-batch

# 切换模式（在 .env 中设置 EVAL_MODE=full-output 等）
docker compose --profile eval run --rm eval-batch
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
├── docker-compose.yml           # 默认交付编排（health-agent + eval profile）
├── compose.override.example.yml # 本地开发挂载 assets 示例
├── compose.env.example          # Compose 插值变量示例
├── .dockerignore
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
