from __future__ import annotations

from collections.abc import Callable

from domain.process.continuation import ContinuationBudget, ContinuationBudgetError

from .continuation_common import (
    ContinuationExecutionResult,
    blocked_result,
    clarify_result,
    continuation_budget_or_default,
    done_result,
    find_inbox_item_by_ref,
    stamp_workflow_authorization,
)
from .inbox_execution import (
    plan_finance_document_ingest_workflow_step,
    plan_finance_payment_workflow_step,
    plan_invoice_email_workflow_step,
)
from .inbox_workflow import (
    FinanceDocumentIngestWorkflowStep,
    FinancePaymentWorkflowStep,
    InvoiceEmailWorkflowStep,
)
from .typed_reentry import emit_typed_command_continue


def continue_with_inbox_workflow_step(
    next_step: InvoiceEmailWorkflowStep | FinancePaymentWorkflowStep | FinanceDocumentIngestWorkflowStep,
    *,
    task_text: str,
    context,
    current_work_item,
    continuation_budget: ContinuationBudget | None,
    vm: object | None = None,
    read_text_fn: Callable[[object, str], str],
    write_text_fn: Callable[[object, str, str], None],
    workflow_interpretation_port,
    typed_step_execution_port,
) -> ContinuationExecutionResult:
    budget = continuation_budget_or_default(continuation_budget)
    if budget.exhausted:
        return blocked_result(
            "Inbox workflow refused to emit a next step: continuation budget is exhausted.",
            reason_code="continuation_budget_exhausted",
            refs=(next_step.evidence_ref,) if next_step.evidence_ref else (),
        )
    if isinstance(next_step, InvoiceEmailWorkflowStep):
        plan = plan_invoice_email_workflow_step(
            next_step,
            inbox_item=find_inbox_item_by_ref(context.inbox_items, next_step.evidence_ref),
            finance_records=context.finance_records,
            cast_entities=context.cast_entities,
            available_channels=tuple(
                ref
                for ref in context.document_refs
                if context.workspace_layout.is_outbox_channel_path(ref)
            ),
            workflow_interpretation_port=workflow_interpretation_port,
        )
        if plan.status == "clarify_missing" or plan.command is None:
            return clarify_result(plan.message, reason_code=plan.reason_code, refs=plan.grounding_refs)
        if plan.status == "blocked":
            return blocked_result(plan.message, reason_code=plan.reason_code, refs=plan.grounding_refs)
        return emit_typed_command_continue(
            current_work_item=current_work_item,
            continuation_budget=budget,
            command=stamp_workflow_authorization(
                workflow_interpretation_port,
                plan.command,
            ),
            task_text=task_text,
            evidence_refs=plan.grounding_refs,
            consumed_inbox_ref=next_step.evidence_ref,
            message=plan.message,
        )
    if isinstance(next_step, FinancePaymentWorkflowStep):
        plan = plan_finance_payment_workflow_step(
            next_step,
            finance_records=context.finance_records,
        )
        if plan.status == "clarify_missing" or plan.command is None:
            return clarify_result(plan.message, reason_code=plan.reason_code, refs=plan.grounding_refs)
        if plan.status == "blocked":
            return blocked_result(plan.message, reason_code=plan.reason_code, refs=plan.grounding_refs)
        return emit_typed_command_continue(
            current_work_item=current_work_item,
            continuation_budget=budget,
            command=stamp_workflow_authorization(
                workflow_interpretation_port,
                plan.command,
            ),
            task_text=task_text,
            evidence_refs=plan.grounding_refs,
            consumed_inbox_ref=next_step.evidence_ref,
            message=plan.message,
        )
    return execute_finance_document_ingest_workflow_step(
        next_step,
        task_text=task_text,
        context=context,
        continuation_budget=budget,
        vm=vm,
        read_text_fn=read_text_fn,
        write_text_fn=write_text_fn,
        workflow_interpretation_port=workflow_interpretation_port,
    )


def execute_inbox_workflow_step(
    next_step: InvoiceEmailWorkflowStep | FinancePaymentWorkflowStep | FinanceDocumentIngestWorkflowStep,
    *,
    task_text: str,
    context,
    continuation_budget: ContinuationBudget | None,
    vm: object | None = None,
    read_text_fn: Callable[[object, str], str],
    write_text_fn: Callable[[object, str, str], None],
    workflow_interpretation_port,
    typed_step_execution_port,
) -> ContinuationExecutionResult:
    budget = continuation_budget_or_default(continuation_budget)
    if budget.exhausted:
        return blocked_result(
            "Inbox workflow refused to emit a next step: continuation budget is exhausted.",
            reason_code="continuation_budget_exhausted",
            refs=(next_step.evidence_ref,) if next_step.evidence_ref else (),
        )
    if isinstance(next_step, InvoiceEmailWorkflowStep):
        plan = plan_invoice_email_workflow_step(
            next_step,
            inbox_item=find_inbox_item_by_ref(context.inbox_items, next_step.evidence_ref),
            finance_records=context.finance_records,
            cast_entities=context.cast_entities,
            available_channels=tuple(
                ref
                for ref in context.document_refs
                if context.workspace_layout.is_outbox_channel_path(ref)
            ),
            workflow_interpretation_port=workflow_interpretation_port,
        )
        if plan.status == "clarify_missing" or plan.command is None:
            return clarify_result(plan.message, reason_code=plan.reason_code, refs=plan.grounding_refs)
        if plan.status == "blocked":
            return blocked_result(plan.message, reason_code=plan.reason_code, refs=plan.grounding_refs)
        try:
            descended = budget.descend().consume(1)
        except ContinuationBudgetError as exc:
            return blocked_result(
                str(exc),
                reason_code="continuation_budget_exhausted",
                refs=plan.grounding_refs,
            )
        return typed_step_execution_port.execute(
            stamp_workflow_authorization(
                workflow_interpretation_port,
                plan.command,
            ),
            task_text,
            context,
            descended,
            vm,
        )
    if isinstance(next_step, FinancePaymentWorkflowStep):
        plan = plan_finance_payment_workflow_step(
            next_step,
            finance_records=context.finance_records,
        )
        if plan.status == "clarify_missing" or plan.command is None:
            return clarify_result(plan.message, reason_code=plan.reason_code, refs=plan.grounding_refs)
        if plan.status == "blocked":
            return blocked_result(plan.message, reason_code=plan.reason_code, refs=plan.grounding_refs)
        try:
            descended = budget.descend().consume(1)
        except ContinuationBudgetError as exc:
            return blocked_result(
                str(exc),
                reason_code="continuation_budget_exhausted",
                refs=plan.grounding_refs,
            )
        return typed_step_execution_port.execute(
            stamp_workflow_authorization(
                workflow_interpretation_port,
                plan.command,
            ),
            task_text,
            context,
            descended,
            vm,
        )
    return execute_finance_document_ingest_workflow_step(
        next_step,
        task_text=task_text,
        context=context,
        continuation_budget=budget,
        vm=vm,
        read_text_fn=read_text_fn,
        write_text_fn=write_text_fn,
        workflow_interpretation_port=workflow_interpretation_port,
    )


def execute_finance_document_ingest_workflow_step(
    next_step: FinanceDocumentIngestWorkflowStep,
    *,
    task_text: str,
    context,
    continuation_budget: ContinuationBudget,
    vm: object | None = None,
    read_text_fn: Callable[[object, str], str],
    write_text_fn: Callable[[object, str, str], None],
    workflow_interpretation_port=None,
) -> ContinuationExecutionResult:
    _ = task_text, continuation_budget
    if vm is None:
        return blocked_result(
            "Finance document ingest requires a writable runtime VM.",
            reason_code="finance_document_ingest_vm_missing",
            refs=(next_step.evidence_ref,) if next_step.evidence_ref else (),
        )
    plan = plan_finance_document_ingest_workflow_step(
        next_step,
        finance_records=context.finance_records,
        cast_entities=context.cast_entities,
        read_note=lambda path: read_text_fn(vm, path),
        workflow_interpretation_port=workflow_interpretation_port,
    )
    if plan.status != "resolved":
        return clarify_result(plan.message, reason_code=plan.reason_code, refs=plan.grounding_refs)
    for write in plan.writes:
        try:
            write_text_fn(vm, write.path, write.content)
        except Exception:  # noqa: BLE001
            return blocked_result(
                f"Finance document ingest could not write {write.path}.",
                reason_code="finance_document_ingest_write_failed",
                refs=plan.grounding_refs,
            )
    return done_result(plan.message, reason_code=plan.reason_code, refs=plan.grounding_refs)


__all__ = [
    "continue_with_inbox_workflow_step",
    "execute_finance_document_ingest_workflow_step",
    "execute_inbox_workflow_step",
]
