# Eval 验收制品（V1）

本目录存放 **批跑 / CI 回归** 用的期望矩阵，不属于运行时医学知识库。

| 制品 | 职责 |
|------|------|
| `action_matrix.v1.json` | 20 case 行动路由契约（`primaryFlag` / `primaryActionHint` / `primaryAction` / `secondaryAction`） |

## 与上游真源分工

| 真源 | 内容 |
|------|------|
| `triage/policy_data.py` → `ACTION_BY_FLAG` | `primaryActionHint` |
| `assets/kb-action/actions.v1.json` | hint → `label` / `route` |
| **`action_matrix.v1.json`** | case 级 **组合期望**（集成验收快照） |

改 KB-ACTION 或 `ACTION_BY_FLAG` 时，须同步更新本矩阵并 bump `meta.matrixVersion`。

## 管道 profile

`meta.pipelineProfile = mechanical_merge_v1`：期望对应 **parse → triage → 机械文案 → merge**，不含 LLM。

## 重新生成期望行（开发用）

从项目根目录：

```bash
cd xiaozhua-health-agent
PYTHONPATH=src .venv/bin/python -c "
from xiaozhua_health_agent.eval.action_matrix import derive_action_matrix_entries
from xiaozhua_health_agent.eval.case_dataset import load_health_triage_dataset
import json
entries = derive_action_matrix_entries(load_health_triage_dataset())
print(json.dumps(entries, ensure_ascii=False, indent=2))
"
```

将输出与 `entries` 对比后 intentional 更新 JSON。
