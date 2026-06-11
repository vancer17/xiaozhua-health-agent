"""FastAPI 应用状态容器（WP6 阶段 2）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from xiaozhua_health_agent.copy import CopyKnowledgeBundle
from xiaozhua_health_agent.pipeline import (
    DEFAULT_HEALTH_TRIAGE_PIPELINE_OPTIONS,
    HealthTriagePipelineOptions,
)

__all__ = [
    "HealthApiAppState",
]


@dataclass
class HealthApiAppState:
    """挂载在 ``FastAPI.state`` 上的共享运行时状态。

    :ivar pipeline_options: 机械分诊管道默认配置（阶段 2 固定 ``mechanical``）。
    :vartype pipeline_options: HealthTriagePipelineOptions
    :ivar copy_bundle: 预加载的 KB-TPL 知识包；``None`` 时由管道运行期加载。
    :vartype copy_bundle: CopyKnowledgeBundle | None
    :ivar copy_bundle_ready: 知识包是否已就绪（预加载完成或显式注入）。
    :vartype copy_bundle_ready: bool
    :ivar service_ready: 服务是否接受分诊流量（lifespan 就绪后为 ``True``）。
    :vartype service_ready: bool
    :ivar startup_error: 启动阶段失败说明；成功时为 ``None``。
    :vartype startup_error: str | None
    """

    pipeline_options: HealthTriagePipelineOptions = field(
        default_factory=lambda: DEFAULT_HEALTH_TRIAGE_PIPELINE_OPTIONS,
    )
    copy_bundle: CopyKnowledgeBundle | None = None
    copy_bundle_ready: bool = False
    service_ready: bool = False
    startup_error: str | None = None

    def resolved_pipeline_options(self) -> HealthTriagePipelineOptions:
        """返回绑定了预加载知识包的管道配置。

        若 ``copy_bundle`` 非空，则关闭运行期默认加载以避免重复 IO。

        :returns: 供 ``run_health_triage_async`` 使用的有效配置。
        :rtype: HealthTriagePipelineOptions
        """
        if self.copy_bundle is None:
            return self.pipeline_options
        return HealthTriagePipelineOptions(
            mode=self.pipeline_options.mode,
            copy_bundle=self.copy_bundle,
            load_default_copy_bundle=False,
            mechanical_options=self.pipeline_options.mechanical_options,
            skip_final_schema_check=self.pipeline_options.skip_final_schema_check,
            guard_mode=self.pipeline_options.guard_mode,
            guard_options=self.pipeline_options.guard_options,
            skip_content_guard=self.pipeline_options.skip_content_guard,
            retry_options=self.pipeline_options.retry_options,
            enable_merge_fallback=self.pipeline_options.enable_merge_fallback,
            enable_final_schema_recovery=self.pipeline_options.enable_final_schema_recovery,
            skip_merge_ready_check=self.pipeline_options.skip_merge_ready_check,
            merge_ready_options=self.pipeline_options.merge_ready_options,
        )
