# 小爪 AI 健康/兽医分诊 Agent V1 Mock 数据

本目录用于小爪 AI V1 的 Agent 框架测试和 App mock adapter 接入。

## 文件

- `schema/xiaozhua_health_agent_input_schema.v1.json`：Agent 输入字段要求。
- `schema/xiaozhua_health_agent_output_schema.v1.json`：Agent 输出字段要求。
- `cases/health_triage_cases.v1.json`：20 个健康/兽医分诊 mock case。

## 使用要求

- Agent 可以自由选择框架和模型，但必须能消费这些输入语义。
- 每个 case 都应该产生结构化输出，而不是只返回自然语言。
- 如果同事新增字段，必须同步更新 schema 和 case。
- 如果输出不符合预期风险等级，需要说明原因，不能静默忽略。

## V1 验收重点

- `/health` 能展示 Agent 输出的标题、风险、证据、建议、安全提示。
- `/intelligent` 能展示入口、占位或 mock 对话结果。
- 缺数据时不编造。
- 紧急症状必须升级为 `emergency`。
- 模型不能输出确诊结论。
