# KB-TPL 文案与语气制品（V1）

本目录为 WP4 **③ 文案生成** 的知识资产，与 `triage-core` 的 `policyTables` 分工：

| 制品 | 职责 |
|------|------|
| `config/templates.v1.json` | 20 条 `riskLevel × primaryFlag` 文案骨架 |
| `config/slots.v1.json` | 全局槽位注册表（机械填值） |
| `config/tone-by-risk.v1.json` | 语气 profile |
| `config/safety-notices.v1.json` | 免责声明片段（boolean 来自 ②） |
| `config/fallback-by-risk.v1.json` | 查表失败时的按 risk 兜底 |

**合规约束**（forcedMentions、forbiddenThemes、safetyNoticeRequired、primaryActionHint）真源在 `triage/policy_data.py`（将来 `triage-core.v1.json` policyTables），**不在本目录重复维护**。

## 关联制品

| 路径 | 用途 |
|------|------|
| `../kb-syn/kb-syn.v1.json` | mustMention 同义词（评测 + ④） |
| `../kb-forbid/forbidden_patterns.v1.json` | 全局禁止词（评测 + ④） |
| `../kb-action/actions.v1.json` | primaryAction label/route |

## 版本

- `bundleVersion`: **1.0.0**（与 triage-core 独立管理、联合回归）
- 改 copy / llmInstructions → bump kb-tpl patch + 文案评测
- 改 forcedMentions → 改 triage policyTables + 可选同步 kb-syn

## 查表主键

```
templateId = "{finalRiskLevel}.{primaryFlag}"
```

查找顺序：`templates[templateId]` → `fallback-by-risk[risk]` → `fallback-by-risk.DEFAULT`

规格详见：`docs/implementation/coze/kb-tpl-template-spec.md`
