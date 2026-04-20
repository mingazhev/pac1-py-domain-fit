from __future__ import annotations

from uuid import uuid4

from domain.process import (
    NextStepEvidenceSource,
    WorkItem,
    continuation_work_item,
    decide_continue,
    decide_unsupported,
    emit_next_typed_step,
)
from domain.process.continuation import ContinuationBudget, ContinuationBudgetError

from .continuation_common import (
    ContinuationExecutionResult,
    blocked_result,
    clarify_result,
    continuation_budget_or_default,
    enrich_inbox_typed_command,
    inbox_prompt_content,
    stamp_workflow_authorization,
)


INBOX_TYPED_CONTINUATION_INTENTS: frozenset[str] = frozenset(
    {
        "account_lookup",
        "contact_lookup",
        "capture_lookup",
        "project_query",
        "entity_query",
        "message_query",
        "finance_lookup",
        "finance_mutation",
        "outbound_email_lookup",
        "outbox_draft",
        "queue_mutation",
        "queue_state_lookup",
    }
)


def execute_inbox_typed_continuation(
    continuation_intent: str,
    *,
    source_text: str,
    context,
    continuation_budget: ContinuationBudget | None,
    vm: object | None,
    workflow_interpretation_port,
    inbox_ref: str | None,
    finance_record_index: str,
    typed_step_execution_port,
) -> ContinuationExecutionResult:
    budget = continuation_budget or ContinuationBudget.initial(max_depth=1, max_steps=1)
    if budget.exhausted:
        return blocked_result(
            "Inbox workflow refused to re-enter: continuation budget is exhausted.",
            reason_code="continuation_budget_exhausted",
            refs=(inbox_ref,) if inbox_ref else (),
        )
    extractor = (
        workflow_interpretation_port.extract_for_typed_intent
        if workflow_interpretation_port is not None
        else None
    )
    if extractor is None:
        return ContinuationExecutionResult(
            decision=decide_unsupported(reason_code="inbox_sub_task_requires_interpreter"),
            message=(
                "Inbox workflow emitted a typed continuation intent but no "
                "workflow interpreter is available to extract its typed payload."
            ),
            refs=(inbox_ref,) if inbox_ref else (),
        )
    normalized_intent = str(continuation_intent).strip()
    if normalized_intent not in INBOX_TYPED_CONTINUATION_INTENTS:
        return ContinuationExecutionResult(
            decision=decide_unsupported(reason_code="inbox_typed_intent_unsupported"),
            message=(
                "Inbox workflow emitted a continuation intent that the "
                "clean runtime does not execute from inbox."
            ),
            refs=(inbox_ref,) if inbox_ref else (),
        )
    inbox_prompt = inbox_prompt_content(inbox_ref, context=context, source_text=source_text)
    extracted = extractor(
        source_text,
        normalized_intent,
        supported_intents=INBOX_TYPED_CONTINUATION_INTENTS,
        workspace_policies=context.workspace_policies,
        finance_record_index=finance_record_index,
        user_content=inbox_prompt,
    )
    if extracted.typed_command is None:
        return clarify_result(
            "Inbox item could not be extracted into a valid typed payload.",
            reason_code="inbox_sub_task_typed_missing",
            refs=(inbox_ref,) if inbox_ref else (),
        )
    try:
        descended = budget.descend().consume(1)
    except ContinuationBudgetError as exc:
        return blocked_result(
            str(exc),
            reason_code="continuation_budget_exhausted",
            refs=(inbox_ref,) if inbox_ref else (),
        )
    enriched = enrich_inbox_typed_command(
        workflow_interpretation_port,
        extracted.typed_command,
        source_text=source_text,
    )
    stamped = stamp_workflow_authorization(workflow_interpretation_port, enriched)
    return typed_step_execution_port.execute(
        stamped,
        extracted.effective_task_text or source_text,
        context,
        descended,
        vm,
    )


def execute_inbox_sub_task(
    sub_task_text: str,
    *,
    context,
    continuation_budget: ContinuationBudget | None,
    vm: object | None,
    workflow_interpretation_port,
    inbox_ref: str | None,
    finance_record_index: str,
    supported_intents: frozenset[str],
    typed_step_execution_port,
) -> ContinuationExecutionResult:
    budget = continuation_budget or ContinuationBudget.initial(max_depth=1, max_steps=1)
    if budget.exhausted:
        return blocked_result(
            "Inbox workflow refused to re-enter: continuation budget is exhausted.",
            reason_code="continuation_budget_exhausted",
            refs=(inbox_ref,) if inbox_ref else (),
        )
    router = (
        workflow_interpretation_port.route_sub_task
        if workflow_interpretation_port is not None
        else None
    )
    if router is None:
        return ContinuationExecutionResult(
            decision=decide_unsupported(reason_code="inbox_sub_task_requires_interpreter"),
            message=(
                "Inbox workflow emitted a sub-task but no workflow interpreter is "
                "available to re-interpret it."
            ),
            refs=(inbox_ref,) if inbox_ref else (),
        )
    routed = router(
        sub_task_text,
        supported_intents=supported_intents,
        workspace_policies=context.workspace_policies,
        finance_record_index=finance_record_index,
    )
    normalized_intent = str(routed.intent or "").strip()
    if not normalized_intent:
        return clarify_result(
            "Inbox sub-task could not be classified into a typed family.",
            reason_code="inbox_sub_task_route_unknown",
            refs=(inbox_ref,) if inbox_ref else (),
        )
    if normalized_intent not in supported_intents:
        return ContinuationExecutionResult(
            decision=decide_unsupported(reason_code="inbox_sub_task_unsupported"),
            message="Inbox sub-task landed on an unsupported intent.",
            refs=(inbox_ref,) if inbox_ref else (),
        )
    if routed.typed_command is None:
        return clarify_result(
            "Inbox sub-task produced no typed payload.",
            reason_code="inbox_sub_task_typed_missing",
            refs=(inbox_ref,) if inbox_ref else (),
        )
    try:
        descended = budget.descend().consume(1)
    except ContinuationBudgetError as exc:
        return blocked_result(
            str(exc),
            reason_code="continuation_budget_exhausted",
            refs=(inbox_ref,) if inbox_ref else (),
        )
    enriched = enrich_inbox_typed_command(
        workflow_interpretation_port,
        routed.typed_command,
        source_text=sub_task_text,
    )
    stamped = stamp_workflow_authorization(workflow_interpretation_port, enriched)
    return typed_step_execution_port.execute(
        stamped,
        routed.effective_task_text or sub_task_text,
        context,
        descended,
        vm,
    )


def continue_with_inbox_typed_intent(
    continuation_intent: str,
    *,
    source_text: str,
    context,
    current_work_item: WorkItem,
    continuation_budget: ContinuationBudget | None,
    workflow_interpretation_port,
    inbox_ref: str | None,
    finance_record_index: str,
) -> ContinuationExecutionResult:
    budget = continuation_budget_or_default(continuation_budget)
    if budget.exhausted:
        return blocked_result(
            "Inbox workflow refused to continue: continuation budget is exhausted.",
            reason_code="continuation_budget_exhausted",
            refs=(inbox_ref,) if inbox_ref else (),
        )
    extractor = (
        workflow_interpretation_port.extract_for_typed_intent
        if workflow_interpretation_port is not None
        else None
    )
    if extractor is None:
        return ContinuationExecutionResult(
            decision=decide_unsupported(reason_code="inbox_sub_task_requires_interpreter"),
            message=(
                "Inbox workflow emitted a typed continuation intent but no "
                "workflow interpreter is available to extract its typed payload."
            ),
            refs=(inbox_ref,) if inbox_ref else (),
        )
    normalized_intent = str(continuation_intent).strip()
    if normalized_intent not in INBOX_TYPED_CONTINUATION_INTENTS:
        return ContinuationExecutionResult(
            decision=decide_unsupported(reason_code="inbox_typed_intent_unsupported"),
            message=(
                "Inbox workflow emitted a continuation intent that the "
                "clean runtime does not execute from inbox."
            ),
            refs=(inbox_ref,) if inbox_ref else (),
        )
    inbox_prompt = inbox_prompt_content(inbox_ref, context=context, source_text=source_text)
    extracted = extractor(
        source_text,
        normalized_intent,
        supported_intents=INBOX_TYPED_CONTINUATION_INTENTS,
        workspace_policies=context.workspace_policies,
        finance_record_index=finance_record_index,
        user_content=inbox_prompt,
    )
    if extracted.typed_command is None:
        return clarify_result(
            "Inbox item could not be extracted into a valid typed payload.",
            reason_code="inbox_sub_task_typed_missing",
            refs=(inbox_ref,) if inbox_ref else (),
        )
    enriched = enrich_inbox_typed_command(
        workflow_interpretation_port,
        extracted.typed_command,
        source_text=source_text,
    )
    stamped = stamp_workflow_authorization(workflow_interpretation_port, enriched)
    return emit_typed_command_continue(
        current_work_item=current_work_item,
        continuation_budget=budget,
        command=stamped,
        task_text=extracted.effective_task_text or source_text,
        evidence_refs=(inbox_ref,) if inbox_ref else (),
        consumed_inbox_ref=inbox_ref,
        message="Inbox workflow emitted a grounded typed continuation as a new work item.",
    )


def continue_with_inbox_sub_task(
    sub_task_text: str,
    *,
    context,
    current_work_item: WorkItem,
    continuation_budget: ContinuationBudget | None,
    workflow_interpretation_port,
    inbox_ref: str | None,
    finance_record_index: str,
    supported_intents: frozenset[str],
) -> ContinuationExecutionResult:
    budget = continuation_budget_or_default(continuation_budget)
    if budget.exhausted:
        return blocked_result(
            "Inbox workflow refused to continue: continuation budget is exhausted.",
            reason_code="continuation_budget_exhausted",
            refs=(inbox_ref,) if inbox_ref else (),
        )
    router = (
        workflow_interpretation_port.route_sub_task
        if workflow_interpretation_port is not None
        else None
    )
    if router is None:
        return ContinuationExecutionResult(
            decision=decide_unsupported(reason_code="inbox_sub_task_requires_interpreter"),
            message=(
                "Inbox workflow emitted a sub-task but no workflow interpreter is "
                "available to re-interpret it."
            ),
            refs=(inbox_ref,) if inbox_ref else (),
        )
    routed = router(
        sub_task_text,
        supported_intents=supported_intents,
        workspace_policies=context.workspace_policies,
        finance_record_index=finance_record_index,
    )
    normalized_intent = str(routed.intent or "").strip()
    if not normalized_intent:
        return clarify_result(
            "Inbox sub-task could not be classified into a typed family.",
            reason_code="inbox_sub_task_route_unknown",
            refs=(inbox_ref,) if inbox_ref else (),
        )
    if normalized_intent not in supported_intents:
        return ContinuationExecutionResult(
            decision=decide_unsupported(reason_code="inbox_sub_task_unsupported"),
            message="Inbox sub-task landed on an unsupported intent.",
            refs=(inbox_ref,) if inbox_ref else (),
        )
    if routed.typed_command is None:
        return clarify_result(
            "Inbox sub-task produced no typed payload.",
            reason_code="inbox_sub_task_typed_missing",
            refs=(inbox_ref,) if inbox_ref else (),
        )
    enriched = enrich_inbox_typed_command(
        workflow_interpretation_port,
        routed.typed_command,
        source_text=sub_task_text,
    )
    stamped = stamp_workflow_authorization(workflow_interpretation_port, enriched)
    return emit_typed_command_continue(
        current_work_item=current_work_item,
        continuation_budget=budget,
        command=stamped,
        task_text=routed.effective_task_text or sub_task_text,
        evidence_refs=(inbox_ref,) if inbox_ref else (),
        consumed_inbox_ref=inbox_ref,
        message="Inbox workflow re-entered as a new typed work item.",
    )


def emit_typed_command_continue(
    *,
    current_work_item: WorkItem,
    continuation_budget: ContinuationBudget,
    command: object,
    task_text: str,
    evidence_refs: tuple[str, ...],
    consumed_inbox_ref: str | None,
    message: str,
) -> ContinuationExecutionResult:
    next_step = emit_next_typed_step(
        executor_kind="typed_command",
        payload={
            "command": command,
            "task_text": str(task_text or "").strip(),
            "consumed_inbox_ref": str(consumed_inbox_ref or "").strip(),
        },
        evidence_source=NextStepEvidenceSource.GROUNDED_INBOX_ITEM,
        evidence_refs=evidence_refs,
    )
    try:
        next_work_item = continuation_work_item(
            identifier=f"wi_{uuid4().hex}",
            parent=current_work_item,
            next_step=next_step,
            parent_budget=continuation_budget,
        )
    except ContinuationBudgetError as exc:
        return blocked_result(str(exc), reason_code="continuation_budget_exhausted", refs=evidence_refs)
    return ContinuationExecutionResult(
        decision=decide_continue(next_work_item=next_work_item),
        message=message,
        refs=evidence_refs,
    )


__all__ = [
    "INBOX_TYPED_CONTINUATION_INTENTS",
    "continue_with_inbox_sub_task",
    "continue_with_inbox_typed_intent",
    "emit_typed_command_continue",
    "execute_inbox_sub_task",
    "execute_inbox_typed_continuation",
]
