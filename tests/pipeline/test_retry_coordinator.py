"""WP5 文案重试协调器状态机测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from xiaozhua_health_agent.copy import (
    DraftCopyJSON,
    load_copy_knowledge_bundle,
    resolve_copy_template,
)
from xiaozhua_health_agent.eval import (
    Violation,
    ViolationCode,
    ViolationDomain,
    load_health_triage_dataset,
)
from xiaozhua_health_agent.guard import ContentGuardMode
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.pipeline import (
    DraftRetryContext,
    DraftRetryGeneratorKind,
    DraftRetryOptions,
    RetryAction,
    build_draft_retry_context,
    run_draft_retry_coordinator,
    run_draft_retry_coordinator_async,
)
from xiaozhua_health_agent.triage import run_triage_core


@pytest.fixture
def knowledge_bundle() -> object:
    """加载 copy 知识资产包。

    :returns: ``CopyKnowledgeBundle`` 实例。
    :rtype: object
    """
    return load_copy_knowledge_bundle()


@pytest.fixture
def retry_context(knowledge_bundle: object) -> DraftRetryContext:
    """构造带知识包的 emergency_seizure 重试上下文。

    :param knowledge_bundle: KB-TPL 聚合包。
    :type knowledge_bundle: object
    :returns: ``DraftRetryContext`` 实例。
    :rtype: DraftRetryContext
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


def test_retry_coordinator_mechanical_path_passes_emergency_case(
    retry_context: DraftRetryContext,
) -> None:
    """机械路径协调器应对 emergency case 产出通过 guard 的 draft。"""
    outcome = run_draft_retry_coordinator(retry_context)

    assert outcome.passed is True
    assert outcome.draft is not None
    assert outcome.terminal_action == RetryAction.ACCEPT.value
    assert outcome.generator in (
        DraftRetryGeneratorKind.MECHANICAL,
        DraftRetryGeneratorKind.MECHANICAL_FALLBACK,
    )
    assert len(outcome.violations_history) >= 1
    assert outcome.violations_history[-1].passed is True
    assert outcome.last_guard_result is not None
    assert outcome.last_guard_result.passed is True


def test_retry_coordinator_async_matches_sync(
    retry_context: DraftRetryContext,
) -> None:
    """异步入口应与同步入口产出等价结果。"""
    sync_outcome = run_draft_retry_coordinator(retry_context)
    async_outcome = asyncio.run(run_draft_retry_coordinator_async(retry_context))

    assert async_outcome.passed == sync_outcome.passed
    assert async_outcome.terminal_action == sync_outcome.terminal_action
    assert (
        async_outcome.used_mechanical_fallback == sync_outcome.used_mechanical_fallback
    )
    if sync_outcome.draft is not None and async_outcome.draft is not None:
        assert async_outcome.draft.title == sync_outcome.draft.title


def test_retry_coordinator_all_cases_mechanical_pass(
    knowledge_bundle: object,
) -> None:
    """20 case 机械协调器应全部通过 guard（里程碑 B 前置）。"""
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    dataset = load_health_triage_dataset(cases_path)

    for case in dataset.cases:
        parsed = parse_input(case.input)
        assert parsed.passed and parsed.fact_sheet is not None
        triage = run_triage_core(parsed.fact_sheet)
        resolved = resolve_copy_template(
            parsed.fact_sheet,
            triage,
            bundle=knowledge_bundle,  # type: ignore[arg-type]
        )
        context = build_draft_retry_context(
            parsed=parsed,
            triage=triage,
            resolved=resolved,
            copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
        )
        outcome = run_draft_retry_coordinator(context)
        assert outcome.passed is True, case.case_id
        assert outcome.draft is not None, case.case_id


def test_retry_coordinator_report_only_accepts_med_warnings(
    retry_context: DraftRetryContext,
) -> None:
    """``report_only`` 模式下 MED 违规不应阻断协调器。"""
    options = DraftRetryOptions(
        guard_mode=ContentGuardMode.REPORT_ONLY,
        enforce_forced_mentions_on_retry=False,
    )
    outcome = run_draft_retry_coordinator(retry_context, options=options)

    assert outcome.passed is True
    assert outcome.draft is not None


def test_retry_coordinator_abort_when_no_fallback(
    retry_context: DraftRetryContext,
) -> None:
    """关闭机械兜底且注入不可修复 draft 时应 ``abort``。"""
    bad_draft = DraftCopyJSON.model_validate(
        {
            "title": "测试",
            "summary": "确诊为细菌感染，一定没事，不用看医生。",
            "evidence": ["输入中不存在的数字 99999"],
            "recommendation": "继续观察即可",
            "whenToSeeVet": "无",
            "safetyNotice": "",
            "primaryAction": {
                "label": retry_context.resolved.primary_action_draft.label,
                "route": retry_context.resolved.primary_action_draft.route,
            },
            "secondaryAction": None,
        },
    )

    async def _run_with_bad_first_draft() -> object:
        """用非法首稿替换生成步骤并运行协调器（闭包，单测用）。

        :returns: ``DraftRetryOutcome``。
        :rtype: object
        """
        from xiaozhua_health_agent.pipeline import retry_coordinator as module

        original = module._generate_initial_draft_async

        async def _stub_initial(
            context: DraftRetryContext,
            *,
            options: DraftRetryOptions,
            qwen_client: object | None,
        ) -> module._InitialDraftGeneration:
            """返回注入的非法首稿（闭包）。

            :param context: 协调器上下文。
            :type context: DraftRetryContext
            :param options: 协调器配置。
            :type options: DraftRetryOptions
            :param qwen_client: 未使用。
            :type qwen_client: object | None
            :returns: 含非法 draft 的首轮生成结果。
            :rtype: module._InitialDraftGeneration
            """
            _ = context, options, qwen_client
            return module._InitialDraftGeneration(
                draft=bad_draft,
                generator=DraftRetryGeneratorKind.MECHANICAL,
                llm_generation_count=0,
            )

        module._generate_initial_draft_async = _stub_initial
        try:
            return await module.run_draft_retry_coordinator_async(
                retry_context,
                options=DraftRetryOptions(
                    fallback_to_mechanical=False,
                    max_attempts=1,
                    enable_deterministic_repair=False,
                ),
            )
        finally:
            module._generate_initial_draft_async = original

    outcome = asyncio.run(_run_with_bad_first_draft())

    assert outcome.passed is False  # type: ignore[attr-defined]
    assert outcome.terminal_action == RetryAction.ABORT.value  # type: ignore[attr-defined]


def test_retry_coordinator_uses_fallback_for_high_violations(
    retry_context: DraftRetryContext,
) -> None:
    """HIGH 违规在尝试耗尽后应走机械兜底并成功。"""
    bad_draft = DraftCopyJSON.model_validate(
        {
            "title": "紧急",
            "summary": "确诊为感染，建议继续观察即可。",
            "evidence": list(retry_context.triage.evidence_bullets),
            "recommendation": "先等等",
            "whenToSeeVet": "无",
            "safetyNotice": "本内容仅供参考。",
            "primaryAction": {
                "label": retry_context.resolved.primary_action_draft.label,
                "route": retry_context.resolved.primary_action_draft.route,
            },
            "secondaryAction": None,
        },
    )

    async def _run_with_bad_then_fallback() -> object:
        """注入非法首稿并验证兜底成功（闭包）。

        :returns: ``DraftRetryOutcome``。
        :rtype: object
        """
        from xiaozhua_health_agent.pipeline import retry_coordinator as module

        original = module._generate_initial_draft_async

        async def _stub_initial(
            context: DraftRetryContext,
            *,
            options: DraftRetryOptions,
            qwen_client: object | None,
        ) -> module._InitialDraftGeneration:
            """返回含禁止词的首稿（闭包）。

            :param context: 协调器上下文。
            :type context: DraftRetryContext
            :param options: 协调器配置。
            :type options: DraftRetryOptions
            :param qwen_client: 未使用。
            :type qwen_client: object | None
            :returns: 非法首稿生成结果。
            :rtype: module._InitialDraftGeneration
            """
            _ = context, options, qwen_client
            return module._InitialDraftGeneration(
                draft=bad_draft,
                generator=DraftRetryGeneratorKind.MECHANICAL,
                llm_generation_count=0,
            )

        module._generate_initial_draft_async = _stub_initial
        try:
            return await module.run_draft_retry_coordinator_async(
                retry_context,
                options=DraftRetryOptions(
                    fallback_to_mechanical=True,
                    max_attempts=1,
                    enable_deterministic_repair=False,
                ),
            )
        finally:
            module._generate_initial_draft_async = original

    outcome = asyncio.run(_run_with_bad_then_fallback())

    assert outcome.passed is True  # type: ignore[attr-defined]
    assert outcome.used_mechanical_fallback is True  # type: ignore[attr-defined]
    assert outcome.generator == DraftRetryGeneratorKind.MECHANICAL_FALLBACK  # type: ignore[attr-defined]


def test_build_guard_repair_user_content_lists_violations() -> None:
    """repair 提示应包含违规码与路径。"""
    from xiaozhua_health_agent.pipeline import build_guard_repair_user_content

    violation = Violation(
        code=ViolationCode.FORBIDDEN_PATTERN_HIT.value,
        domain=ViolationDomain.GUARD.value,
        path="summary",
        field="summary",
        message="含禁止词",
    )
    content = build_guard_repair_user_content((violation,))

    assert "FORBIDDEN_PATTERN_HIT" in content
    assert "summary" in content


def test_retry_coordinator_llm_initial_path_passes_with_stub(
    retry_context: DraftRetryContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """启用 LLM 时协调器应通过 ``llm_draft_generation`` 桥接并成功通过 guard。"""
    mechanical_outcome = run_draft_retry_coordinator(retry_context)
    assert mechanical_outcome.passed and mechanical_outcome.draft is not None
    good_draft = mechanical_outcome.draft

    from xiaozhua_health_agent.copy import DraftGenerationRetryResult
    from xiaozhua_health_agent.pipeline import (
        DraftRetryGeneratorKind,
        InitialLlmDraftResult,
    )

    async def _stub_initial(
        context: DraftRetryContext,
        *,
        options: DraftRetryOptions,
        qwen_client: object | None = None,
    ) -> InitialLlmDraftResult:
        """返回已通过 guard 的 stub 首稿（闭包）。

        :param context: 协调器上下文。
        :type context: DraftRetryContext
        :param options: 协调器配置。
        :type options: DraftRetryOptions
        :param qwen_client: 未使用。
        :type qwen_client: object | None
        :returns: stub 首轮 LLM 结果。
        :rtype: InitialLlmDraftResult
        """
        _ = context, options, qwen_client
        return InitialLlmDraftResult(
            draft=good_draft,
            llm_call_count=1,
            inner_result=DraftGenerationRetryResult(
                passed=True,
                draft=good_draft,
                attempt_count=1,
            ),
        )

    monkeypatch.setattr(
        "xiaozhua_health_agent.pipeline.retry_coordinator.generate_initial_llm_draft_async",
        _stub_initial,
    )

    outcome = asyncio.run(
        run_draft_retry_coordinator_async(
            retry_context,
            options=DraftRetryOptions(llm_enabled=True),
        ),
    )

    assert outcome.passed is True
    assert outcome.generator == DraftRetryGeneratorKind.QWEN
    assert outcome.llm_generation_count == 1
    assert outcome.terminal_action == RetryAction.ACCEPT.value
