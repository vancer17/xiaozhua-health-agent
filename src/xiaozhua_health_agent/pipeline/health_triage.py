"""机械健康分诊管道公开入口（同步 / 异步，WP5 阶段 1）。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from xiaozhua_health_agent.copy import (
    CopyKnowledgeBundle,
    load_default_copy_knowledge_bundle,
)
from xiaozhua_health_agent.eval import ActualOutputPayload, TriageOutputProvider
from xiaozhua_health_agent.pipeline.mechanical_core import (
    run_mechanical_health_triage_core,
    run_mechanical_health_triage_core_async,
)
from xiaozhua_health_agent.pipeline.pipeline_types import (
    DEFAULT_HEALTH_TRIAGE_PIPELINE_OPTIONS,
    HealthTriagePipelineOptions,
    HealthTriagePipelineResult,
    default_health_triage_pipeline_options,
)
from xiaozhua_health_agent.schemas import AgentInput

__all__ = [
    "DEFAULT_HEALTH_TRIAGE_PIPELINE_OPTIONS",
    "default_health_triage_pipeline_options",
    "make_health_triage_output_provider",
    "run_health_triage",
    "run_health_triage_async",
]


def run_health_triage(
    agent_input: AgentInput | Mapping[str, Any],
    *,
    options: HealthTriagePipelineOptions | None = None,
    copy_bundle: CopyKnowledgeBundle | None = None,
) -> HealthTriagePipelineResult:
    """对单次输入执行机械路径健康分诊管道（同步）。

    编排 ① 解析 → ② 分诊 → ③ WP5 文案重试协调器（含 ④ ValidateContent）
    → ⑤ 合并 → 出站 ``output_schema`` 校验。

    :param agent_input: 符合 input_schema 的 case / App JSON。
    :type agent_input: AgentInput | collections.abc.Mapping[str, Any]
    :param options: 管道配置；省略时使用 :func:`default_health_triage_pipeline_options`。
    :type options: HealthTriagePipelineOptions | None
    :param copy_bundle: 可选预加载知识包；若提供则覆盖 ``options.copy_bundle``。
    :type copy_bundle: CopyKnowledgeBundle | None
    :returns: 管道执行结果。
    :rtype: HealthTriagePipelineResult
    """
    effective_options, resolved_bundle = _resolve_runtime_options(
        options=options,
        copy_bundle_override=copy_bundle,
    )
    return run_mechanical_health_triage_core(
        agent_input,
        options=effective_options,
        copy_bundle=resolved_bundle,
    )


async def run_health_triage_async(
    agent_input: AgentInput | Mapping[str, Any],
    *,
    options: HealthTriagePipelineOptions | None = None,
    copy_bundle: CopyKnowledgeBundle | None = None,
) -> HealthTriagePipelineResult:
    """对单次输入执行机械路径健康分诊管道（异步）。

    IO 密集步骤（知识包加载、重试协调器内 guard 校验）走 ``await``；
    CPU 密集步骤（解析、分诊、模板解析）在协调器内委托 ``asyncio.to_thread``。

    :param agent_input: 符合 input_schema 的 case / App JSON。
    :type agent_input: AgentInput | collections.abc.Mapping[str, Any]
    :param options: 管道配置；省略时使用默认配置。
    :type options: HealthTriagePipelineOptions | None
    :param copy_bundle: 可选预加载知识包；若提供则覆盖 ``options.copy_bundle``。
    :type copy_bundle: CopyKnowledgeBundle | None
    :returns: 管道执行结果。
    :rtype: HealthTriagePipelineResult
    """
    effective_options, resolved_bundle = await _resolve_runtime_options_async(
        options=options,
        copy_bundle_override=copy_bundle,
    )
    return await run_mechanical_health_triage_core_async(
        agent_input,
        options=effective_options,
        copy_bundle=resolved_bundle,
    )


def make_health_triage_output_provider(
    *,
    options: HealthTriagePipelineOptions | None = None,
    copy_bundle: CopyKnowledgeBundle | None = None,
) -> TriageOutputProvider:
    """构造供 ``run_full_output_evaluation_with_provider`` 使用的回调。

    成功时返回 ``AgentOutput``；管道失败时返回 ``None``（评测器记为
    ``CASE_OUTPUT_MISSING``）。

    :param options: 管道配置；省略时使用默认配置。
    :type options: HealthTriagePipelineOptions | None
    :param copy_bundle: 可选预加载知识包。
    :type copy_bundle: CopyKnowledgeBundle | None
    :returns: ``AgentInput`` → ``ActualOutputPayload`` 回调。
    :rtype: TriageOutputProvider
    """
    effective_options = (
        options if options is not None else default_health_triage_pipeline_options()
    )

    def _provider(
        agent_input: AgentInput | Mapping[str, Any],
    ) -> ActualOutputPayload:
        """对单条入参执行机械管道并返回出站载荷（闭包）。

        :param agent_input: App / case 输入。
        :type agent_input: AgentInput | collections.abc.Mapping[str, Any]
        :returns: 成功时的 ``AgentOutput``；失败时为 ``None``。
        :rtype: ActualOutputPayload
        """
        result = run_health_triage(
            agent_input,
            options=effective_options,
            copy_bundle=copy_bundle,
        )
        if not result.passed or result.output is None:
            return None
        return result.output

    return _provider


def _resolve_runtime_options(
    *,
    options: HealthTriagePipelineOptions | None,
    copy_bundle_override: CopyKnowledgeBundle | None,
) -> tuple[HealthTriagePipelineOptions, CopyKnowledgeBundle | None]:
    """解析同步运行期的选项与知识包（内部辅助）。

    :param options: 调用方传入的管道配置。
    :type options: HealthTriagePipelineOptions | None
    :param copy_bundle_override: 显式传入的知识包，优先级最高。
    :type copy_bundle_override: CopyKnowledgeBundle | None
    :returns: ``(effective_options, resolved_bundle)`` 元组。
    :rtype: tuple[HealthTriagePipelineOptions, CopyKnowledgeBundle | None]
    """
    effective_options = (
        options if options is not None else default_health_triage_pipeline_options()
    )
    if copy_bundle_override is not None:
        return effective_options.with_copy_bundle(
            copy_bundle_override
        ), copy_bundle_override

    if effective_options.copy_bundle is not None:
        return effective_options, effective_options.copy_bundle

    if effective_options.load_default_copy_bundle:
        loaded = load_default_copy_knowledge_bundle()
        return effective_options.with_copy_bundle(loaded), loaded

    return effective_options, None


async def _resolve_runtime_options_async(
    *,
    options: HealthTriagePipelineOptions | None,
    copy_bundle_override: CopyKnowledgeBundle | None,
) -> tuple[HealthTriagePipelineOptions, CopyKnowledgeBundle | None]:
    """解析异步运行期的选项与知识包（内部辅助）。

    :param options: 调用方传入的管道配置。
    :type options: HealthTriagePipelineOptions | None
    :param copy_bundle_override: 显式传入的知识包，优先级最高。
    :type copy_bundle_override: CopyKnowledgeBundle | None
    :returns: ``(effective_options, resolved_bundle)`` 元组。
    :rtype: tuple[HealthTriagePipelineOptions, CopyKnowledgeBundle | None]
    """
    effective_options = (
        options if options is not None else default_health_triage_pipeline_options()
    )
    if copy_bundle_override is not None:
        return effective_options.with_copy_bundle(
            copy_bundle_override
        ), copy_bundle_override

    if effective_options.copy_bundle is not None:
        return effective_options, effective_options.copy_bundle

    if effective_options.load_default_copy_bundle:

        async def _load_bundle() -> CopyKnowledgeBundle:
            """在线程池中加载默认知识包（闭包）。

            :returns: 默认 KB-TPL 聚合包。
            :rtype: CopyKnowledgeBundle
            """
            return await asyncio.to_thread(load_default_copy_knowledge_bundle)

        loaded = await _load_bundle()
        return effective_options.with_copy_bundle(loaded), loaded

    return effective_options, None
