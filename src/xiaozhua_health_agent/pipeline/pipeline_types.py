"""机械健康分诊管道 DTO 与配置类型（WP5 阶段 1）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from xiaozhua_health_agent.copy import (
    CopyKnowledgeBundle,
    CopyTemplateResolved,
    DraftCopyJSON,
    MechanicalDraftOptions,
    MechanicalDraftWarning,
)
from xiaozhua_health_agent.eval import Violation
from xiaozhua_health_agent.guard import (
    ContentGuardMode,
    ContentGuardModeLiteral,
    ContentGuardOptions,
    ContentGuardResult,
    DEFAULT_CONTENT_GUARD_OPTIONS,
)
from xiaozhua_health_agent.output import (
    DEFAULT_MERGE_READY_OPTIONS,
    MergeReadyOptions,
)
from xiaozhua_health_agent.parse import ParseResult
from xiaozhua_health_agent.pipeline.retry_types import DraftRetryOptions
from xiaozhua_health_agent.schemas import AgentOutput
from xiaozhua_health_agent.triage import TriageCoreResult

__all__ = [
    "DEFAULT_CONTENT_GUARD_OPTIONS",
    "DEFAULT_HEALTH_TRIAGE_PIPELINE_OPTIONS",
    "default_health_triage_pipeline_options",
    "ContentGuardMode",
    "ContentGuardModeLiteral",
    "ContentGuardOptions",
    "ContentGuardResult",
    "DraftGeneratorKind",
    "DraftGeneratorKindLiteral",
    "HealthTriagePipelineMode",
    "HealthTriagePipelineModeLiteral",
    "HealthTriagePipelineOptions",
    "HealthTriagePipelineResult",
    "HealthTriagePipelineStage",
    "HealthTriagePipelineStageLiteral",
    "MechanicalPipelineArtifacts",
    "DEFAULT_MERGE_READY_OPTIONS",
    "MergeReadyOptions",
]

HealthTriagePipelineModeLiteral: TypeAlias = Literal["mechanical"]
"""阶段 1 仅支持机械文案路径；后续可扩展 ``llm`` / ``llm_with_guard``。"""

HealthTriagePipelineStageLiteral: TypeAlias = Literal[
    "parse",
    "triage",
    "resolve",
    "mechanical",
    "guard",
    "merge_ready",
    "merge",
    "final_schema",
    "completed",
]
"""管道执行阶段标识；``completed`` 表示已成功产出 ``AgentOutput``。"""

DraftGeneratorKindLiteral: TypeAlias = Literal["mechanical"]
"""文案生成器种类（阶段 1 固定为机械路径）。"""


class HealthTriagePipelineMode:
    """管道运行模式常量（阶段 1）。"""

    MECHANICAL: HealthTriagePipelineModeLiteral = "mechanical"


class HealthTriagePipelineStage:
    """管道阶段常量。"""

    PARSE: HealthTriagePipelineStageLiteral = "parse"
    TRIAGE: HealthTriagePipelineStageLiteral = "triage"
    RESOLVE: HealthTriagePipelineStageLiteral = "resolve"
    MECHANICAL: HealthTriagePipelineStageLiteral = "mechanical"
    GUARD: HealthTriagePipelineStageLiteral = "guard"
    MERGE_READY: HealthTriagePipelineStageLiteral = "merge_ready"
    MERGE: HealthTriagePipelineStageLiteral = "merge"
    FINAL_SCHEMA: HealthTriagePipelineStageLiteral = "final_schema"
    COMPLETED: HealthTriagePipelineStageLiteral = "completed"


class DraftGeneratorKind:
    """文案生成器种类常量。"""

    MECHANICAL: DraftGeneratorKindLiteral = "mechanical"


@dataclass(frozen=True, slots=True)
class HealthTriagePipelineOptions:
    """机械健康分诊管道运行配置。

    :ivar mode: 管道模式；阶段 1 仅 ``mechanical``。
    :vartype mode: HealthTriagePipelineModeLiteral
    :ivar copy_bundle: 可选预加载 KB-TPL 知识包；为 ``None`` 且
        ``load_default_copy_bundle=True`` 时在运行期加载默认制品。
    :vartype copy_bundle: CopyKnowledgeBundle | None
    :ivar load_default_copy_bundle: 是否在 ``copy_bundle`` 为 ``None`` 时加载默认知识包。
    :vartype load_default_copy_bundle: bool
    :ivar mechanical_options: 机械文案组装选项；省略时使用
        ``MechanicalDraftOptions(append_missing_mentions=True)``。
    :vartype mechanical_options: MechanicalDraftOptions | None
    :ivar skip_final_schema_check: 为 ``True`` 时跳过出站 ``output_schema`` 全量校验（仅调试）。
    :vartype skip_final_schema_check: bool
    :ivar guard_mode: 内容守卫失败处理模式（``strict`` / ``report_only`` / ``sanitize``）。
    :vartype guard_mode: ContentGuardModeLiteral
    :ivar guard_options: ValidateContent 运行配置。
    :vartype guard_options: ContentGuardOptions
    :ivar skip_content_guard: 为 ``True`` 时跳过 ④-B ValidateContent（仅调试）。
    :vartype skip_content_guard: bool
    :ivar retry_options: 可选 WP5 重试协调器配置；省略时由
        :meth:`resolved_draft_retry_options` 从管道字段派生。
    :vartype retry_options: DraftRetryOptions | None
    :ivar enable_merge_fallback: 为 ``True`` 时，``merge`` / ``merge_ready`` 失败后再
        以机械文案重试一次合并（不修改 ② 裁决字段）。
    :vartype enable_merge_fallback: bool
    :ivar enable_final_schema_recovery: 为 ``True`` 时，FinalSchemaCheck 失败后再
        以机械文案重试一次合并与校验（不修改 ② 裁决字段）。
    :vartype enable_final_schema_recovery: bool
    :ivar skip_merge_ready_check: 为 ``True`` 时跳过 merge-ready 预检（仅调试）。
    :vartype skip_merge_ready_check: bool
    :ivar merge_ready_options: merge-ready 契约校验配置。
    :vartype merge_ready_options: MergeReadyOptions | None
    """

    mode: HealthTriagePipelineModeLiteral = HealthTriagePipelineMode.MECHANICAL
    copy_bundle: CopyKnowledgeBundle | None = None
    load_default_copy_bundle: bool = True
    mechanical_options: MechanicalDraftOptions | None = None
    skip_final_schema_check: bool = False
    guard_mode: ContentGuardModeLiteral = ContentGuardMode.STRICT
    guard_options: ContentGuardOptions = DEFAULT_CONTENT_GUARD_OPTIONS
    skip_content_guard: bool = False
    retry_options: DraftRetryOptions | None = None
    enable_merge_fallback: bool = True
    enable_final_schema_recovery: bool = True
    skip_merge_ready_check: bool = False
    merge_ready_options: MergeReadyOptions | None = None

    def resolved_mechanical_options(self) -> MechanicalDraftOptions:
        """解析有效的机械文案选项。

        :returns: 显式配置或默认机械文案选项。
        :rtype: MechanicalDraftOptions
        """
        if self.mechanical_options is not None:
            return self.mechanical_options
        return MechanicalDraftOptions(append_missing_mentions=True)

    def resolved_draft_retry_options(self) -> DraftRetryOptions:
        """将管道配置映射为 WP5 文案重试协调器选项。

        机械路径默认 ``llm_enabled=False``、``fallback_to_mechanical=True``；
        ``guard_mode`` / ``guard_options`` / ``mechanical_options`` 与管道对齐。

        :returns: 协调器运行配置。
        :rtype: DraftRetryOptions
        """
        if self.retry_options is not None:
            return self.retry_options
        return DraftRetryOptions(
            llm_enabled=False,
            fallback_to_mechanical=True,
            guard_mode=self.guard_mode,
            guard_options=self.guard_options,
            mechanical_options=self.mechanical_options,
        )

    def resolved_merge_ready_options(self) -> MergeReadyOptions:
        """解析有效的 merge-ready 契约校验配置。

        :returns: 显式配置或 ``DEFAULT_MERGE_READY_OPTIONS``。
        :rtype: MergeReadyOptions
        """
        if self.merge_ready_options is not None:
            return self.merge_ready_options
        return DEFAULT_MERGE_READY_OPTIONS

    def with_copy_bundle(
        self,
        bundle: CopyKnowledgeBundle | None,
    ) -> HealthTriagePipelineOptions:
        """返回替换了 ``copy_bundle`` 的新配置（不可变更新）。

        :param bundle: 新的知识包引用；可为 ``None``。
        :type bundle: CopyKnowledgeBundle | None
        :returns: 更新后的配置副本。
        :rtype: HealthTriagePipelineOptions
        """
        return HealthTriagePipelineOptions(
            mode=self.mode,
            copy_bundle=bundle,
            load_default_copy_bundle=self.load_default_copy_bundle,
            mechanical_options=self.mechanical_options,
            skip_final_schema_check=self.skip_final_schema_check,
            guard_mode=self.guard_mode,
            guard_options=self.guard_options,
            skip_content_guard=self.skip_content_guard,
            retry_options=self.retry_options,
            enable_merge_fallback=self.enable_merge_fallback,
            enable_final_schema_recovery=self.enable_final_schema_recovery,
            skip_merge_ready_check=self.skip_merge_ready_check,
            merge_ready_options=self.merge_ready_options,
        )


def default_health_triage_pipeline_options() -> HealthTriagePipelineOptions:
    """从环境变量加载默认管道配置。

    :returns: 当前进程环境下的管道选项。
    :rtype: HealthTriagePipelineOptions
    """
    from xiaozhua_health_agent.config.pipeline_settings import (
        get_default_health_triage_pipeline_options,
    )

    return get_default_health_triage_pipeline_options()


DEFAULT_HEALTH_TRIAGE_PIPELINE_OPTIONS: HealthTriagePipelineOptions = (
    HealthTriagePipelineOptions()
)
"""静态默认管道配置（不读环境变量）；运行时代码请用 :func:`default_health_triage_pipeline_options`。"""


@dataclass(frozen=True, slots=True)
class MechanicalPipelineArtifacts:
    """机械管道中间产物快照（便于批跑报告与调试）。

    :ivar parse_result: 步骤 ① 解析结果。
    :vartype parse_result: ParseResult
    :ivar triage: 步骤 ② 锁定分诊结论。
    :vartype triage: TriageCoreResult
    :ivar resolved: 步骤 ③-1 模板解析包。
    :vartype resolved: CopyTemplateResolved
    :ivar draft: 步骤 ③ 机械文案草稿。
    :vartype draft: DraftCopyJSON
    :ivar template_id: 命中模板主键。
    :vartype template_id: str
    :ivar mechanical_warnings: 机械文案组装警告。
    :vartype mechanical_warnings: tuple[MechanicalDraftWarning, ...]
    """

    parse_result: ParseResult
    triage: TriageCoreResult
    resolved: CopyTemplateResolved
    draft: DraftCopyJSON
    template_id: str
    mechanical_warnings: tuple[MechanicalDraftWarning, ...] = ()


@dataclass(frozen=True, slots=True)
class HealthTriagePipelineResult:
    """单次机械健康分诊管道执行结果。

    :ivar passed: 是否成功产出并通过（可选）出站 schema 校验的 ``AgentOutput``。
    :vartype passed: bool
    :ivar case_id: 用例标识；解析失败时尽力从入参读取，否则为 ``unknown``。
    :vartype case_id: str
    :ivar stage: 终止阶段；成功时为 ``completed``。
    :vartype stage: HealthTriagePipelineStageLiteral
    :ivar output: 成功时的完整结构化输出。
    :vartype output: AgentOutput | None
    :ivar violations: 契约或 schema 违规列表；成功时通常为空。
    :vartype violations: tuple[Violation, ...]
    :ivar triage: 步骤 ② 结果；成功路径保留。
    :vartype triage: TriageCoreResult | None
    :ivar artifacts: 成功或部分成功时的中间产物；解析失败时为 ``None``。
    :vartype artifacts: MechanicalPipelineArtifacts | None
    :ivar draft_generator: 实际文案生成器种类。
    :vartype draft_generator: DraftGeneratorKindLiteral
    :ivar primary_flag: ② 叙事主键；解析失败时为 ``None``。
    :vartype primary_flag: str | None
    :ivar bundle_version: triage-core 制品版本；解析失败时为 ``None``。
    :vartype bundle_version: str | None
    :ivar error_message: 管道级错误说明（merge 失败等）。
    :vartype error_message: str | None
    :ivar guard_result: 步骤 ④-B ValidateContent 结果；跳过时为 ``None``。
    :vartype guard_result: ContentGuardResult | None
    :ivar guard_warnings: ``report_only`` 模式下未阻断的 MED 违规副本。
    :vartype guard_warnings: tuple[Violation, ...]
    :ivar attempt_count: WP5 重试协调器有效尝试次数；未走协调器时为 ``0``。
    :vartype attempt_count: int
    :ivar used_mechanical_fallback: 协调器是否使用过终端机械兜底。
    :vartype used_mechanical_fallback: bool
    :ivar used_merge_fallback: Merge 阶段是否在合并/schema 失败后执行过机械兜底。
    :vartype used_merge_fallback: bool
    :ivar merge_fallback_attempted: 是否曾尝试 Merge 阶段兜底（含仍失败的情形）。
    :vartype merge_fallback_attempted: bool
    :ivar used_final_schema_recovery: FinalSchema recovery 是否成功完成。
    :vartype used_final_schema_recovery: bool
    :ivar final_schema_recovery_attempted: 是否曾尝试 FinalSchema recovery（含仍失败）。
    :vartype final_schema_recovery_attempted: bool
    :ivar pre_recovery_output: FinalSchema recovery 前已合并但未通过校验的 output。
    :vartype pre_recovery_output: AgentOutput | None
    :ivar pre_recovery_violations: FinalSchema recovery 前首次 schema 失败违规副本。
    :vartype pre_recovery_violations: tuple[Violation, ...]
    """

    passed: bool
    case_id: str
    stage: HealthTriagePipelineStageLiteral
    output: AgentOutput | None
    violations: tuple[Violation, ...] = ()
    triage: TriageCoreResult | None = None
    artifacts: MechanicalPipelineArtifacts | None = None
    draft_generator: DraftGeneratorKindLiteral = DraftGeneratorKind.MECHANICAL
    primary_flag: str | None = None
    bundle_version: str | None = None
    error_message: str | None = None
    guard_result: ContentGuardResult | None = None
    guard_warnings: tuple[Violation, ...] = ()
    attempt_count: int = 0
    used_mechanical_fallback: bool = False
    used_merge_fallback: bool = False
    merge_fallback_attempted: bool = False
    used_final_schema_recovery: bool = False
    final_schema_recovery_attempted: bool = False
    pre_recovery_output: AgentOutput | None = None
    pre_recovery_violations: tuple[Violation, ...] = ()

    @property
    def rule_hits(self) -> tuple[str, ...]:
        """② 规则命中摘要（供 L7 批跑记录）。

        :returns: ``ruleHits`` 元组；无分诊结果时为空。
        :rtype: tuple[str, ...]
        """
        if self.triage is None:
            return ()
        return self.triage.rule_hits

    @property
    def template_id(self) -> str | None:
        """③-1 模板主键。

        :returns: 模板 id；无中间产物时为 ``None``。
        :rtype: str | None
        """
        if self.artifacts is None:
            return None
        return self.artifacts.template_id
