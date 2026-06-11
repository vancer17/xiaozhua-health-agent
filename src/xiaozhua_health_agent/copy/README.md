# WP4 ③ 文案生成

## 已实现

- **③-1 模板解析器**：`resolve_copy_template(fact_sheet, triage)` → `CopyTemplateResolved`
- KB-TPL / KB-ACTION / KB-FORBID 制品加载与默认缓存
- 槽位机械填值、免责声明选用、内联规则、行动映射
- **③-2 LLM**：`DraftCopyJSON`、`draft_parser`、`draft_prompt`、`AsyncQwenClient`、`generate_draft_copy_async`
- **③ 机械文案**：`generate_mechanical_draft`、`template_substitution`、`draft_locked_fields`（WP5 兜底共用）
- **copy-llm / copy-mechanical 批跑**（`xiaozhua_health_agent.eval`）：`run_copy_llm_batch`（`use_mechanical=True`）

## 公开 API

```python
from xiaozhua_health_agent.copy import (
    resolve_copy_template,
    generate_mechanical_draft,
    generate_mechanical_draft_from_input,
)

parsed = parse_input(case_input)
triage = run_triage_core(parsed.fact_sheet)
resolved = resolve_copy_template(parsed.fact_sheet, triage)
draft_result = generate_mechanical_draft(resolved)  # 无 LLM
```

## 未实现（后续 WP5）

- ④ 验证与重试
- ⑤ 合并 output_schema（机械兜底函数已就绪，供 TemplateFallback 调用）
