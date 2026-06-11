"""健康分诊管道运行时开关（环境变量，非业务规则）。"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from xiaozhua_health_agent.guard import ContentGuardMode, ContentGuardOptions
from xiaozhua_health_agent.pipeline.pipeline_types import HealthTriagePipelineOptions
from xiaozhua_health_agent.pipeline.retry_types import DraftRetryOptions

__all__ = [
    "XiaozhuaPipelineSettings",
    "clear_xiaozhua_pipeline_settings_cache",
    "get_default_health_triage_pipeline_options",
    "get_xiaozhua_pipeline_settings",
]

GuardModeLiteral = Literal["strict", "report_only", "sanitize"]


class XiaozhuaPipelineSettings(BaseSettings):
    """机械分诊管道调试与行为开关。

    环境变量前缀 ``XIAOZHUA_PIPELINE_``（如 ``XIAOZHUA_PIPELINE_SKIP_CONTENT_GUARD``）。

    :ivar skip_content_guard: 跳过 ④-B ValidateContent（仅调试）。
    :vartype skip_content_guard: bool
    :ivar skip_final_schema_check: 跳过出站 output_schema 全量校验（仅调试）。
    :vartype skip_final_schema_check: bool
    :ivar skip_merge_ready_check: 跳过 merge-ready 预检（仅调试）。
    :vartype skip_merge_ready_check: bool
    :ivar guard_mode: 内容守卫失败处理模式。
    :vartype guard_mode: GuardModeLiteral
    :ivar llm_enabled: 文案路径是否启用 LLM（默认机械路径为 false）。
    :vartype llm_enabled: bool
    :ivar enable_merge_fallback: merge 失败后是否机械兜底。
    :vartype enable_merge_fallback: bool
    :ivar enable_final_schema_recovery: FinalSchema 失败后是否再机械合并。
    :vartype enable_final_schema_recovery: bool
    :ivar load_default_copy_bundle: ``copy_bundle`` 为 None 时是否加载默认 KB-TPL 等。
    :vartype load_default_copy_bundle: bool
    :ivar load_default_synonym_map: ValidateContent 是否加载默认 KB-SYN。
    :vartype load_default_synonym_map: bool
    :ivar enforce_forced_mentions: ``FORCED_MENTION_MISSING`` 是否拉低 guard passed。
    :vartype enforce_forced_mentions: bool
    :ivar input_lex_enabled: 是否在 ``parse_input`` 之前执行 KB-INPUT-LEX enrich。
    :vartype input_lex_enabled: bool
    :ivar load_default_input_lex_bundle: enrich 时是否在未注入 bundle 的情况下加载默认词表。
    :vartype load_default_input_lex_bundle: bool
    """

    model_config = SettingsConfigDict(
        env_prefix="XIAOZHUA_PIPELINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    skip_content_guard: bool = Field(
        default=False,
        description="跳过 ValidateContent。",
    )
    skip_final_schema_check: bool = Field(
        default=False,
        description="跳过出站 output_schema 校验。",
    )
    skip_merge_ready_check: bool = Field(
        default=False,
        description="跳过 merge-ready 预检。",
    )
    guard_mode: GuardModeLiteral = Field(
        default=ContentGuardMode.STRICT,
        description="strict / report_only / sanitize。",
    )
    llm_enabled: bool = Field(
        default=False,
        description="启用 LLM 文案生成与外层重试协调器。",
    )
    enable_merge_fallback: bool = Field(
        default=True,
        description="Merge 阶段失败时机械兜底。",
    )
    enable_final_schema_recovery: bool = Field(
        default=True,
        description="FinalSchema 失败时机械 recovery。",
    )
    load_default_copy_bundle: bool = Field(
        default=True,
        description="运行期加载默认 copy 知识包。",
    )
    load_default_synonym_map: bool = Field(
        default=True,
        description="守卫阶段加载默认 KB-SYN。",
    )
    enforce_forced_mentions: bool = Field(
        default=False,
        description="mustMention 类 MED 违规是否阻断 guard。",
    )
    input_lex_enabled: bool = Field(
        default=False,
        description="启用 KB-INPUT-LEX enrich（parse 之前口语补全）。",
    )
    load_default_input_lex_bundle: bool = Field(
        default=True,
        description="enrich 时自动加载默认 KB-INPUT-LEX 制品。",
    )

    def to_pipeline_options(self) -> HealthTriagePipelineOptions:
        """映射为 ``HealthTriagePipelineOptions``。

        :returns: 管道运行配置。
        :rtype: HealthTriagePipelineOptions
        """
        guard_options = ContentGuardOptions(
            enforce_forced_mentions=self.enforce_forced_mentions,
            load_default_synonym_map=self.load_default_synonym_map,
        )
        retry_options: DraftRetryOptions | None = None
        if self.llm_enabled:
            retry_options = DraftRetryOptions(
                llm_enabled=True,
                guard_mode=self.guard_mode,
                guard_options=guard_options,
            )
        return HealthTriagePipelineOptions(
            load_default_copy_bundle=self.load_default_copy_bundle,
            skip_final_schema_check=self.skip_final_schema_check,
            guard_mode=self.guard_mode,
            guard_options=guard_options,
            skip_content_guard=self.skip_content_guard,
            retry_options=retry_options,
            enable_merge_fallback=self.enable_merge_fallback,
            enable_final_schema_recovery=self.enable_final_schema_recovery,
            skip_merge_ready_check=self.skip_merge_ready_check,
            input_lex_enabled=self.input_lex_enabled,
            load_default_input_lex_bundle=self.load_default_input_lex_bundle,
        )


@lru_cache(maxsize=1)
def get_xiaozhua_pipeline_settings() -> XiaozhuaPipelineSettings:
    """加载并缓存管道开关配置。

    :returns: 自环境变量解析的配置实例。
    :rtype: XiaozhuaPipelineSettings
    """
    return XiaozhuaPipelineSettings()


def get_default_health_triage_pipeline_options() -> HealthTriagePipelineOptions:
    """从环境变量构建默认管道配置。

    :returns: 当前进程环境下的管道选项。
    :rtype: HealthTriagePipelineOptions
    """
    return get_xiaozhua_pipeline_settings().to_pipeline_options()


def clear_xiaozhua_pipeline_settings_cache() -> None:
    """清空管道配置 LRU 缓存（单测用）。

    :rtype: None
    """
    get_xiaozhua_pipeline_settings.cache_clear()
