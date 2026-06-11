"""WP5 ``apply_deterministic_repair`` 确定性修补测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from xiaozhua_health_agent.copy import (
    DraftCopyJSON,
    generate_mechanical_draft,
    load_copy_knowledge_bundle,
    resolve_copy_template,
)
from xiaozhua_health_agent.eval import (
    Violation,
    ViolationCode,
    ViolationDomain,
    ViolationSeverity,
    load_health_triage_dataset,
)
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.pipeline import (
    DeterministicRepairKind,
    DraftRetryOptions,
    apply_deterministic_repair,
    apply_deterministic_repair_async,
    build_draft_retry_context,
    collect_repair_kinds_from_violations,
)
from xiaozhua_health_agent.schemas import ActionItem
from xiaozhua_health_agent.triage import run_triage_core


@pytest.fixture
def knowledge_bundle() -> object:
    """加载 copy 知识资产包。

    :returns: ``CopyKnowledgeBundle`` 实例。
    :rtype: object
    """
    return load_copy_knowledge_bundle()


@pytest.fixture
def emergency_context(knowledge_bundle: object) -> object:
    """构造 emergency_seizure 重试上下文。

    :param knowledge_bundle: KB-TPL 知识包。
    :type knowledge_bundle: object
    :returns: ``DraftRetryContext`` 实例。
    :rtype: object
    """
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    dataset = load_health_triage_dataset(cases_path)
    case = dataset.case_by_id("emergency_seizure")
    parsed = parse_input(case.input)
    assert parsed.passed and parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    return build_draft_retry_context(
        parsed=parsed,
        triage=triage,
        resolved=resolved,
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )


def _violation(
    *,
    code: str,
    path: str = "summary",
    field: str | None = "summary",
    severity: str = ViolationSeverity.HIGH.value,
) -> Violation:
    """构造测试用 guard 违规（内部辅助）。

    :param code: 违规码。
    :type code: str
    :param path: JSON 路径。
    :type path: str
    :param field: 顶层字段名。
    :type field: str | None
    :param severity: 严重度。
    :type severity: str
    :returns: 违规记录。
    :rtype: Violation
    """
    return Violation(
        code=code,  # type: ignore[arg-type]
        domain=ViolationDomain.GUARD.value,
        path=path,
        field=field,
        message="测试违规",
        severity=severity,  # type: ignore[arg-type]
    )


def test_apply_deterministic_repair_noop_on_empty_violations(
    emergency_context: object,
) -> None:
    """无违规时不应修改 draft。"""
    mechanical = generate_mechanical_draft(emergency_context.resolved)  # type: ignore[attr-defined]
    draft = mechanical.draft
    result = apply_deterministic_repair(
        draft,
        (),
        emergency_context,  # type: ignore[arg-type]
    )
    assert result.changed is False
    assert result.applied_repairs == ()
    assert result.draft is draft


def test_apply_deterministic_repair_respects_disabled_flag(
    emergency_context: object,
) -> None:
    """``enable_deterministic_repair=False`` 时不修补。"""
    mechanical = generate_mechanical_draft(emergency_context.resolved)  # type: ignore[attr-defined]
    draft = mechanical.draft
    options = DraftRetryOptions(enable_deterministic_repair=False)
    result = apply_deterministic_repair(
        draft,
        [
            _violation(code=ViolationCode.FORCED_MENTION_MISSING.value),
        ],
        emergency_context,  # type: ignore[arg-type]
        options=options,
    )
    assert result.changed is False


def test_apply_deterministic_repair_action_lock(
    emergency_context: object,
) -> None:
    """行动 route 不一致时应强制回写 draft。"""
    mechanical = generate_mechanical_draft(emergency_context.resolved)  # type: ignore[attr-defined]
    draft = mechanical.draft.model_copy(
        update={
            "primary_action": ActionItem(label="错误标签", route="/wrong"),
        },
        deep=True,
    )
    result = apply_deterministic_repair(
        draft,
        [
            _violation(
                code=ViolationCode.ACTION_ROUTE_MISMATCH.value,
                path="primaryAction.route",
                field="primaryAction",
            ),
        ],
        emergency_context,  # type: ignore[arg-type]
    )
    assert result.changed is True
    assert DeterministicRepairKind.ACTION_LOCK.value in result.applied_repairs
    assert (
        result.draft.primary_action.route
        == emergency_context.resolved.primary_action_draft.route  # type: ignore[attr-defined]
    )


def test_apply_deterministic_repair_evidence_reset(
    emergency_context: object,
) -> None:
    """证据幻觉违规应将 evidence 重置为 bullets。"""
    mechanical = generate_mechanical_draft(emergency_context.resolved)  # type: ignore[attr-defined]
    draft = mechanical.draft.model_copy(
        update={"evidence": ["编造的不存在数值 9999"]},
        deep=True,
    )
    result = apply_deterministic_repair(
        draft,
        [
            _violation(
                code=ViolationCode.EVIDENCE_HALLUCINATION.value,
                path="evidence[0]",
                field="evidence",
            ),
        ],
        emergency_context,  # type: ignore[arg-type],
    )
    assert result.changed is True
    assert DeterministicRepairKind.EVIDENCE_RESET.value in result.applied_repairs
    assert result.draft.evidence == list(
        emergency_context.triage.evidence_bullets  # type: ignore[attr-defined]
    )


def test_apply_deterministic_repair_forced_mentions(
    emergency_context: object,
) -> None:
    """forcedMentions 缺失时应追加至 summary。"""
    mechanical = generate_mechanical_draft(emergency_context.resolved)  # type: ignore[attr-defined]
    draft = mechanical.draft.model_copy(
        update={"summary": "极简摘要无关键词。"},
        deep=True,
    )
    result = apply_deterministic_repair(
        draft,
        [
            _violation(
                code=ViolationCode.FORCED_MENTION_MISSING.value,
                severity=ViolationSeverity.MEDIUM.value,
            ),
        ],
        emergency_context,  # type: ignore[arg-type]
    )
    assert result.changed is True
    assert DeterministicRepairKind.FORCED_MENTIONS.value in result.applied_repairs
    assert "请同时留意：" in result.draft.summary


def test_apply_deterministic_repair_emergency_tone_field_replace(
    emergency_context: object,
) -> None:
    """紧急语气弱化时应以机械参考稿覆盖 recommendation。"""
    mechanical = generate_mechanical_draft(emergency_context.resolved)  # type: ignore[attr-defined]
    draft = mechanical.draft.model_copy(
        update={"recommendation": "继续观察即可，先等等。"},
        deep=True,
    )
    result = apply_deterministic_repair(
        draft,
        [
            _violation(
                code=ViolationCode.EMERGENCY_TONE_WEAK.value,
                path="recommendation",
                field="recommendation",
            ),
        ],
        emergency_context,  # type: ignore[arg-type]
    )
    assert result.changed is True
    assert DeterministicRepairKind.FIELD_FROM_MECHANICAL.value in result.applied_repairs
    assert result.draft.recommendation == mechanical.draft.recommendation
    assert "继续观察即可" not in result.draft.recommendation


def test_apply_deterministic_repair_safety_notice(
    emergency_context: object,
) -> None:
    """免责声明缺失时应补全 safetyNotice。"""
    mechanical = generate_mechanical_draft(emergency_context.resolved)  # type: ignore[attr-defined]
    draft = mechanical.draft.model_copy(
        update={"safety_notice": ""},
        deep=True,
    )
    assert emergency_context.triage.safety_notice_required  # type: ignore[attr-defined]
    result = apply_deterministic_repair(
        draft,
        [
            _violation(
                code=ViolationCode.SAFETY_NOTICE_REQUIRED_MISSING.value,
                path="safetyNotice",
                field="safetyNotice",
                severity=ViolationSeverity.MEDIUM.value,
            ),
        ],
        emergency_context,  # type: ignore[arg-type]
    )
    assert result.changed is True
    assert DeterministicRepairKind.SAFETY_NOTICE.value in result.applied_repairs
    assert len(result.draft.safety_notice.strip()) >= 8


def test_collect_repair_kinds_from_violations() -> None:
    """``collect_repair_kinds_from_violations`` 应映射多种违规码。"""
    kinds = collect_repair_kinds_from_violations(
        [
            _violation(code=ViolationCode.ACTION_ROUTE_MISMATCH.value),
            _violation(code=ViolationCode.EVIDENCE_HALLUCINATION.value),
            _violation(
                code=ViolationCode.MUST_MENTION_MISSING.value,
                field="summary",
            ),
        ],
    )
    assert DeterministicRepairKind.ACTION_LOCK.value in kinds
    assert DeterministicRepairKind.EVIDENCE_RESET.value in kinds
    assert DeterministicRepairKind.FORCED_MENTIONS.value not in kinds


def test_apply_deterministic_repair_async_matches_sync(
    emergency_context: object,
) -> None:
    """异步入口应与同步修补结果一致。"""
    mechanical = generate_mechanical_draft(emergency_context.resolved)  # type: ignore[attr-defined]
    draft = mechanical.draft.model_copy(
        update={"evidence": ["幻觉 12345"]},
        deep=True,
    )
    violations = [
        _violation(
            code=ViolationCode.EVIDENCE_HALLUCINATION.value,
            path="evidence[0]",
            field="evidence",
        ),
    ]

    sync_result = apply_deterministic_repair(
        draft,
        violations,
        emergency_context,  # type: ignore[arg-type]
    )

    async def _run_async() -> DraftCopyJSON:
        """运行异步修补并返回 draft（闭包）。

        :returns: 修补后的文案草稿。
        :rtype: DraftCopyJSON
        """
        async_result = await apply_deterministic_repair_async(
            draft,
            violations,
            emergency_context,  # type: ignore[arg-type]
        )
        return async_result.draft

    async_draft = asyncio.run(_run_async())
    assert async_draft.evidence == sync_result.draft.evidence
