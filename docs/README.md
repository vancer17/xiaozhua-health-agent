# 小爪健康分诊 Agent — 项目文档

本目录存放 **xiaozhua-health-agent** 实现侧文档（交付报告、开发计划、实机验证等）。

## 目录

| 路径 | 说明 |
|------|------|
| [manual-testing/api-manual-verification.md](manual-testing/api-manual-verification.md) | **API 实机验证手册**（curl 命令、20 case 对照、能力范围） |
| [delivery/](delivery/) | 里程碑交付与一致性报告 |
| [plans/](plans/) | 开发计划 |
| [implementation/coze/](implementation/coze/) | 管道与模块实现规格 |
| [architecture/](architecture/) | 七层架构与组件说明 |

## 契约与 Mock 数据（仓库根 `docs/`）

- `../docs/schema/`：input / output JSON Schema
- `../docs/cases/health_triage_cases.v1.json`：20 个验收 mock case

## 快速开始实机测试

```bash
cd xiaozhua-health-agent
cp .env.example .env
.venv/bin/xiaozhua-health-agent
```

详见 [API 实机验证手册](manual-testing/api-manual-verification.md)。
