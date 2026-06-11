"""机械健康分诊管道批跑集成（WP5 里程碑 B + WP0 full-output）。

向后兼容入口委托 ``milestone_b_batch``；新代码请优先使用
``run_milestone_b_batch_async`` 与 ``assert_milestone_b_hard_gate``。
"""

from __future__ import annotations

from xiaozhua_health_agent.copy import CopyKnowledgeBundle
from xiaozhua_health_agent.eval import (
    FullEvalOptions,
    FullEvalReport,
    HealthTriageDataset,
    assert_full_output_hard_gate,
)
from xiaozhua_health_agent.pipeline.health_triage import (
    make_health_triage_output_provider,
)
from xiaozhua_health_agent.pipeline.milestone_b_batch import (
    run_milestone_b_batch,
    run_milestone_b_batch_async,
)
from xiaozhua_health_agent.pipeline.pipeline_types import HealthTriagePipelineOptions

__all__ = [
    "assert_mechanical_full_output_hard_gate",
    "make_health_triage_output_provider",
    "run_mechanical_health_triage_full_output_batch",
    "run_mechanical_health_triage_full_output_batch_async",
]


def run_mechanical_health_triage_full_output_batch(
    dataset: HealthTriageDataset | None = None,
    *,
    pipeline_options: HealthTriagePipelineOptions | None = None,
    copy_bundle: CopyKnowledgeBundle | None = None,
    full_eval_options: FullEvalOptions | None = None,
) -> FullEvalReport:
    """对 20 case 执行机械管道并运行 full-output 评测（risk + semantic）。

    委托 :func:`run_milestone_b_batch`；返回其中的 ``full_eval`` 子报告以保持
    与早期 WP5 阶段 1 API 兼容。需要管道失败可观测性时请使用
    :class:`~xiaozhua_health_agent.pipeline.MilestoneBBatchReport`。

    :param dataset: mock case 数据集；省略时加载默认路径。
    :type dataset: HealthTriageDataset | None
    :param pipeline_options: 机械管道配置。
    :type pipeline_options: HealthTriagePipelineOptions | None
    :param copy_bundle: 可选预加载知识包，传给管道。
    :type copy_bundle: CopyKnowledgeBundle | None
    :param full_eval_options: full-output 组合评测配置。
    :type full_eval_options: FullEvalOptions | None
    :returns: full-output 批跑报告。
    :rtype: FullEvalReport
    """
    milestone_report = run_milestone_b_batch(
        dataset,
        pipeline_options=pipeline_options,
        copy_bundle=copy_bundle,
        full_eval_options=full_eval_options,
    )
    return milestone_report.full_eval


async def run_mechanical_health_triage_full_output_batch_async(
    dataset: HealthTriageDataset | None = None,
    *,
    pipeline_options: HealthTriagePipelineOptions | None = None,
    copy_bundle: CopyKnowledgeBundle | None = None,
    full_eval_options: FullEvalOptions | None = None,
) -> FullEvalReport:
    """对 20 case 异步执行机械管道并运行 full-output 评测。

    :param dataset: mock case 数据集；省略时异步加载默认路径。
    :type dataset: HealthTriageDataset | None
    :param pipeline_options: 机械管道配置。
    :type pipeline_options: HealthTriagePipelineOptions | None
    :param copy_bundle: 可选预加载知识包。
    :type copy_bundle: CopyKnowledgeBundle | None
    :param full_eval_options: full-output 组合评测配置。
    :type full_eval_options: FullEvalOptions | None
    :returns: full-output 批跑报告。
    :rtype: FullEvalReport
    """
    milestone_report = await run_milestone_b_batch_async(
        dataset,
        pipeline_options=pipeline_options,
        copy_bundle=copy_bundle,
        full_eval_options=full_eval_options,
    )
    return milestone_report.full_eval


def assert_mechanical_full_output_hard_gate(
    report: FullEvalReport,
    *,
    total: int | None = None,
) -> None:
    """断言 full-output 硬门槛全绿（L7 评测层）。

    里程碑 B 完整闭环（含管道层）请使用
    :func:`assert_milestone_b_hard_gate`。

    :param report: full-output 批跑报告。
    :type report: FullEvalReport
    :param total: 期望 case 总数；省略时使用 ``report.total``。
    :type total: int | None
    :raises AssertionError: 硬门槛未全绿时抛出。
    """
    assert_full_output_hard_gate(report, expected_total=total)
