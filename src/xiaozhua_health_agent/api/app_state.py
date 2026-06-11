"""FastAPI 应用状态容器（WP6 阶段 2）。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from xiaozhua_health_agent.copy import CopyKnowledgeBundle
from xiaozhua_health_agent.input_lex import InputLexBundle
from xiaozhua_health_agent.config import get_default_health_triage_pipeline_options
from xiaozhua_health_agent.pipeline import HealthTriagePipelineOptions

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
    :ivar intelligent_enabled: 是否暴露 ``POST /intelligent`` 占位端点。
    :vartype intelligent_enabled: bool
    :ivar input_lex_bundle: 预加载的 KB-INPUT-LEX 词表；``None`` 时由 enrich 运行期加载。
    :vartype input_lex_bundle: InputLexBundle | None
    :ivar input_lex_bundle_ready: 词表是否已就绪（预加载完成或显式注入）。
    :vartype input_lex_bundle_ready: bool
    """

    pipeline_options: HealthTriagePipelineOptions = field(
        default_factory=get_default_health_triage_pipeline_options,
    )
    copy_bundle: CopyKnowledgeBundle | None = None
    copy_bundle_ready: bool = False
    input_lex_bundle: InputLexBundle | None = None
    input_lex_bundle_ready: bool = False
    service_ready: bool = False
    startup_error: str | None = None
    intelligent_enabled: bool = True

    def resolved_pipeline_options(self) -> HealthTriagePipelineOptions:
        """返回绑定了预加载知识包的管道配置。

        若 ``copy_bundle`` 非空，则关闭运行期默认加载以避免重复 IO。

        :returns: 供 ``run_health_triage_async`` 使用的有效配置。
        :rtype: HealthTriagePipelineOptions
        """
        effective = self.pipeline_options
        if self.copy_bundle is not None:
            effective = replace(
                effective,
                copy_bundle=self.copy_bundle,
                load_default_copy_bundle=False,
            )
        if self.input_lex_bundle is not None:
            effective = replace(
                effective,
                input_lex_bundle=self.input_lex_bundle,
                load_default_input_lex_bundle=False,
            )
        return effective
