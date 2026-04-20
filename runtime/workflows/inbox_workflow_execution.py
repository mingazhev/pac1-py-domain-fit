"""Inbox workflow loop: the full runtime loop over inbox items.

Consolidates three previously-split modules:

- ``inbox_process_runtime`` — top-level dispatcher invoked by the
  execution engine for an ``InboxProcessNextCommand``.
- ``inbox_reentry_runtime`` — the ``*_via_runtime`` wrappers used by
  the continuation / re-entry path.
- ``inbox_services`` — the shared service binder that assembles the
  ``WorkflowInterpretationPort`` / ``TypedStepExecutionPort`` / finance
  record index for both the dispatcher and the re-entry wrappers.
"""

from __future__ import annotations

from application.context import RuntimeContext
from application.workflows import resolve_inbox_workflow_step
from application.workflows.continuation_common import ContinuationExecutionResult
from application.workflows.typed_reentry import (
    continue_with_inbox_sub_task,
    continue_with_inbox_typed_intent,
    execute_inbox_sub_task,
    execute_inbox_typed_continuation,
)
from application.workflows.workflow_step_execution import (
    continue_with_inbox_workflow_step,
    execute_inbox_workflow_step,
)
from domain.process import WorkItem
from domain.process.continuation import ContinuationBudget
from runtime.workflows.inbox_command_enrichment import (
    build_inbox_classifier,
    build_typed_step_execution_port,
    build_workflow_interpretation_port,
    enrich_inbox_typed_command,
    extract_task_inputs_via_runtime,
    stamp_workflow_authorization,
)
from runtime.io.vm_tools import read_text, write_text
from task_routing import InboxProcessNextCommand, extract_task_inputs_for_decision
from task_routing.finance_prompt_index import build_finance_record_index
from telemetry.trace import emit_runtime_exception, emit_trace


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


# ---------------------------------------------------------------------------
# Service binder (formerly inbox_services.py).


def build_inbox_runtime_services(
    *,
    context: RuntimeContext,
    gateway: object | None,
    model: str | None,
    execute_typed_command_fn=None,
    extract_task_inputs_fn=extract_task_inputs_via_runtime,
    extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision,
    stamp_workflow_authorization_fn=stamp_workflow_authorization,
    enrich_inbox_typed_command_fn=enrich_inbox_typed_command,
) -> tuple[object, object | None, str]:
    workflow_interpretation_port = build_workflow_interpretation_port(
        gateway,
        model,
        extract_task_inputs_fn=extract_task_inputs_fn,
        extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision_fn,
        stamp_workflow_authorization_fn=stamp_workflow_authorization_fn,
        enrich_inbox_typed_command_fn=enrich_inbox_typed_command_fn,
    )
    typed_step_execution_port = (
        build_typed_step_execution_port(execute_typed_command_fn)
        if execute_typed_command_fn is not None
        else None
    )
    finance_record_index = build_finance_record_index(context.finance_records)
    return workflow_interpretation_port, typed_step_execution_port, finance_record_index


# ---------------------------------------------------------------------------
# Re-entry wrappers (formerly inbox_reentry_runtime.py).


def execute_inbox_typed_continuation_via_runtime(
    continuation_intent: str,
    *,
    source_text: str,
    context: RuntimeContext,
    continuation_budget: ContinuationBudget | None,
    vm: object | None,
    gateway: object | None,
    model: str | None,
    inbox_ref: str | None,
    execute_typed_command_fn,
    extract_task_inputs_fn,
    extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision,
    stamp_workflow_authorization_fn,
    enrich_inbox_typed_command_fn,
) -> ContinuationExecutionResult:
    workflow_interpretation_port, typed_step_execution_port, finance_record_index = (
        build_inbox_runtime_services(
            context=context,
            gateway=gateway,
            model=model,
            execute_typed_command_fn=execute_typed_command_fn,
            extract_task_inputs_fn=extract_task_inputs_fn,
            extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision_fn,
            stamp_workflow_authorization_fn=stamp_workflow_authorization_fn,
            enrich_inbox_typed_command_fn=enrich_inbox_typed_command_fn,
        )
    )
    return execute_inbox_typed_continuation(
        continuation_intent,
        source_text=source_text,
        context=context,
        continuation_budget=continuation_budget,
        vm=vm,
        workflow_interpretation_port=workflow_interpretation_port,
        inbox_ref=inbox_ref,
        finance_record_index=finance_record_index,
        typed_step_execution_port=typed_step_execution_port,
    )


def execute_inbox_sub_task_via_runtime(
    sub_task_text: str,
    *,
    context: RuntimeContext,
    continuation_budget: ContinuationBudget | None,
    vm: object | None,
    gateway: object | None,
    model: str | None,
    inbox_ref: str | None,
    execute_typed_command_fn,
    extract_task_inputs_fn,
    extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision,
    stamp_workflow_authorization_fn,
    enrich_inbox_typed_command_fn,
) -> ContinuationExecutionResult:
    workflow_interpretation_port, typed_step_execution_port, finance_record_index = (
        build_inbox_runtime_services(
            context=context,
            gateway=gateway,
            model=model,
            execute_typed_command_fn=execute_typed_command_fn,
            extract_task_inputs_fn=extract_task_inputs_fn,
            extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision_fn,
            stamp_workflow_authorization_fn=stamp_workflow_authorization_fn,
            enrich_inbox_typed_command_fn=enrich_inbox_typed_command_fn,
        )
    )
    return execute_inbox_sub_task(
        sub_task_text,
        context=context,
        continuation_budget=continuation_budget,
        vm=vm,
        workflow_interpretation_port=workflow_interpretation_port,
        inbox_ref=inbox_ref,
        finance_record_index=finance_record_index,
        supported_intents=INBOX_TYPED_CONTINUATION_INTENTS,
        typed_step_execution_port=typed_step_execution_port,
    )


def execute_inbox_workflow_step_via_runtime(
    next_step,
    *,
    task_text: str,
    context: RuntimeContext,
    continuation_budget: ContinuationBudget | None,
    vm: object | None,
    gateway: object | None,
    model: str | None,
    execute_typed_command_fn,
    read_text_fn=read_text,
    write_text_fn=write_text,
) -> ContinuationExecutionResult:
    workflow_interpretation_port, typed_step_execution_port, _ = build_inbox_runtime_services(
        context=context,
        gateway=gateway,
        model=model,
        execute_typed_command_fn=execute_typed_command_fn,
    )
    return execute_inbox_workflow_step(
        next_step,
        task_text=task_text,
        context=context,
        continuation_budget=continuation_budget,
        vm=vm,
        read_text_fn=read_text_fn,
        write_text_fn=write_text_fn,
        workflow_interpretation_port=workflow_interpretation_port,
        typed_step_execution_port=typed_step_execution_port,
    )


def continue_with_inbox_typed_intent_via_runtime(
    continuation_intent: str,
    *,
    source_text: str,
    context: RuntimeContext,
    current_work_item,
    continuation_budget: ContinuationBudget | None,
    gateway: object | None,
    model: str | None,
    inbox_ref: str | None,
    extract_task_inputs_fn,
    extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision,
    stamp_workflow_authorization_fn,
    enrich_inbox_typed_command_fn,
) -> ContinuationExecutionResult:
    workflow_interpretation_port, _, finance_record_index = build_inbox_runtime_services(
        context=context,
        gateway=gateway,
        model=model,
        extract_task_inputs_fn=extract_task_inputs_fn,
        extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision_fn,
        stamp_workflow_authorization_fn=stamp_workflow_authorization_fn,
        enrich_inbox_typed_command_fn=enrich_inbox_typed_command_fn,
    )
    return continue_with_inbox_typed_intent(
        continuation_intent,
        source_text=source_text,
        context=context,
        current_work_item=current_work_item,
        continuation_budget=continuation_budget,
        workflow_interpretation_port=workflow_interpretation_port,
        inbox_ref=inbox_ref,
        finance_record_index=finance_record_index,
    )


def continue_with_inbox_sub_task_via_runtime(
    sub_task_text: str,
    *,
    context: RuntimeContext,
    current_work_item,
    continuation_budget: ContinuationBudget | None,
    gateway: object | None,
    model: str | None,
    inbox_ref: str | None,
    extract_task_inputs_fn,
    extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision,
    stamp_workflow_authorization_fn,
    enrich_inbox_typed_command_fn,
) -> ContinuationExecutionResult:
    workflow_interpretation_port, _, finance_record_index = build_inbox_runtime_services(
        context=context,
        gateway=gateway,
        model=model,
        extract_task_inputs_fn=extract_task_inputs_fn,
        extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision_fn,
        stamp_workflow_authorization_fn=stamp_workflow_authorization_fn,
        enrich_inbox_typed_command_fn=enrich_inbox_typed_command_fn,
    )
    return continue_with_inbox_sub_task(
        sub_task_text,
        context=context,
        current_work_item=current_work_item,
        continuation_budget=continuation_budget,
        workflow_interpretation_port=workflow_interpretation_port,
        inbox_ref=inbox_ref,
        finance_record_index=finance_record_index,
        supported_intents=INBOX_TYPED_CONTINUATION_INTENTS,
    )


def continue_with_inbox_workflow_step_via_runtime(
    next_step,
    *,
    task_text: str,
    context: RuntimeContext,
    current_work_item,
    continuation_budget: ContinuationBudget | None,
    vm: object | None,
    gateway: object | None,
    model: str | None,
    execute_typed_command_fn,
    read_text_fn=read_text,
    write_text_fn=write_text,
) -> ContinuationExecutionResult:
    workflow_interpretation_port, typed_step_execution_port, _ = build_inbox_runtime_services(
        context=context,
        gateway=gateway,
        model=model,
        execute_typed_command_fn=execute_typed_command_fn,
    )
    return continue_with_inbox_workflow_step(
        next_step,
        task_text=task_text,
        context=context,
        current_work_item=current_work_item,
        continuation_budget=continuation_budget,
        vm=vm,
        read_text_fn=read_text_fn,
        write_text_fn=write_text_fn,
        workflow_interpretation_port=workflow_interpretation_port,
        typed_step_execution_port=typed_step_execution_port,
    )


# ---------------------------------------------------------------------------
# Top-level dispatcher (formerly inbox_process_runtime.py).


def execute_inbox_process_next_command_via_runtime(
    command: InboxProcessNextCommand,
    *,
    task_text: str,
    context: RuntimeContext,
    continuation_budget: ContinuationBudget | None,
    current_work_item: WorkItem | None,
    vm: object | None,
    gateway: object | None,
    model: str | None,
    execute_typed_command_fn,
    delete_path_fn,
    build_classifier_fn=build_inbox_classifier,
    resolve_inbox_workflow_step_fn=resolve_inbox_workflow_step,
    extract_task_inputs_fn=extract_task_inputs_via_runtime,
    extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision,
    stamp_workflow_authorization_fn=stamp_workflow_authorization,
    enrich_inbox_typed_command_fn=enrich_inbox_typed_command,
    read_text_fn=read_text,
    write_text_fn=write_text,
):
    classifier = build_classifier_fn(
        gateway,
        model,
        inbox_policy=context.workspace_policies.inbox,
        root_policy=context.workspace_policies.root,
    )
    workflow = resolve_inbox_workflow_step_fn(
        context.inbox_items,
        filename_only=command.filename_only,
        task_text=task_text,
        classify_body=classifier,
        cast_entities=context.cast_entities,
        emit_trace_fn=emit_trace,
    )
    inbox_path = workflow.inbox_item_path
    if workflow.status == "resolved":
        if not command.filename_only and vm is not None and inbox_path:
            try:
                delete_path_fn(vm, inbox_path)
            except Exception as exc:  # noqa: BLE001
                emit_runtime_exception(
                    stage="inbox_process_runtime",
                    operation="delete_consumed_inbox_item",
                    error=exc,
                    extra={"path": inbox_path},
                )
                pass
        return workflow, None
    if workflow.status != "continue":
        return workflow, None
    if str(workflow.continuation_intent or "").strip():
        if current_work_item is not None:
            result = continue_with_inbox_typed_intent_via_runtime(
                str(workflow.continuation_intent or "").strip(),
                source_text=workflow.processed_sub_task_text or "",
                context=context,
                current_work_item=current_work_item,
                continuation_budget=continuation_budget,
                gateway=gateway,
                model=model,
                inbox_ref=inbox_path,
                extract_task_inputs_fn=extract_task_inputs_fn,
                extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision_fn,
                stamp_workflow_authorization_fn=stamp_workflow_authorization_fn,
                enrich_inbox_typed_command_fn=enrich_inbox_typed_command_fn,
            )
        else:
            result = execute_inbox_typed_continuation_via_runtime(
                str(workflow.continuation_intent or "").strip(),
                source_text=workflow.processed_sub_task_text or "",
                context=context,
                continuation_budget=continuation_budget,
                vm=vm,
                gateway=gateway,
                model=model,
                inbox_ref=inbox_path,
                execute_typed_command_fn=execute_typed_command_fn,
                extract_task_inputs_fn=extract_task_inputs_fn,
                extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision_fn,
                stamp_workflow_authorization_fn=stamp_workflow_authorization_fn,
                enrich_inbox_typed_command_fn=enrich_inbox_typed_command_fn,
            )
    elif workflow.processed_sub_task_text:
        if current_work_item is not None:
            result = continue_with_inbox_sub_task_via_runtime(
                workflow.processed_sub_task_text,
                context=context,
                current_work_item=current_work_item,
                continuation_budget=continuation_budget,
                gateway=gateway,
                model=model,
                inbox_ref=inbox_path,
                extract_task_inputs_fn=extract_task_inputs_fn,
                extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision_fn,
                stamp_workflow_authorization_fn=stamp_workflow_authorization_fn,
                enrich_inbox_typed_command_fn=enrich_inbox_typed_command_fn,
            )
        else:
            result = execute_inbox_sub_task_via_runtime(
                workflow.processed_sub_task_text,
                context=context,
                continuation_budget=continuation_budget,
                vm=vm,
                gateway=gateway,
                model=model,
                inbox_ref=inbox_path,
                execute_typed_command_fn=execute_typed_command_fn,
                extract_task_inputs_fn=extract_task_inputs_fn,
                extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision_fn,
                stamp_workflow_authorization_fn=stamp_workflow_authorization_fn,
                enrich_inbox_typed_command_fn=enrich_inbox_typed_command_fn,
            )
    elif workflow.next_step is not None:
        if current_work_item is not None:
            result = continue_with_inbox_workflow_step_via_runtime(
                workflow.next_step,
                task_text=task_text,
                context=context,
                current_work_item=current_work_item,
                continuation_budget=continuation_budget,
                vm=vm,
                gateway=gateway,
                model=model,
                execute_typed_command_fn=execute_typed_command_fn,
                read_text_fn=read_text_fn,
                write_text_fn=write_text_fn,
            )
        else:
            result = execute_inbox_workflow_step_via_runtime(
                workflow.next_step,
                task_text=task_text,
                context=context,
                continuation_budget=continuation_budget,
                vm=vm,
                gateway=gateway,
                model=model,
                execute_typed_command_fn=execute_typed_command_fn,
                read_text_fn=read_text_fn,
                write_text_fn=write_text_fn,
            )
    else:
        result = None

    if (
        result is not None
        and vm is not None
        and inbox_path
        and getattr(result.decision, "kind", None).name == "DONE"
    ):
        try:
            delete_path_fn(vm, inbox_path)
        except Exception as exc:  # noqa: BLE001
            emit_runtime_exception(
                error=exc,
                stage="inbox_workflow_execution",
                operation="delete_processed_inbox_item",
                extra={"path": inbox_path},
            )
    return workflow, result


__all__ = [
    "INBOX_TYPED_CONTINUATION_INTENTS",
    "build_inbox_runtime_services",
    "continue_with_inbox_sub_task_via_runtime",
    "continue_with_inbox_typed_intent_via_runtime",
    "continue_with_inbox_workflow_step_via_runtime",
    "execute_inbox_process_next_command_via_runtime",
    "execute_inbox_sub_task_via_runtime",
    "execute_inbox_typed_continuation_via_runtime",
    "execute_inbox_workflow_step_via_runtime",
]
