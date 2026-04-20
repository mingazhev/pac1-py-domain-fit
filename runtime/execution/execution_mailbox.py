"""Inbox continuation and re-entry surface for deterministic execution.

Concentrates three previously-split modules (``deterministic_inbox``,
``deterministic_inbox_support``, ``deterministic_reentry``) into a single
"mailbox" surface. The layering is:

- :func:`execute_typed_command_for_continuation` — the re-entry leg used
  by the execution engine when a ``WorkItem`` of origin ``CONTINUATION``
  arrives.
- ``execute_inbox_*`` — the thin deterministic wrappers that delegate to
  ``runtime.workflows.inbox_workflow_execution`` and repackage the result as a
  :class:`DeterministicExecutionResult`.
- ``*_for_runtime`` — the module-scoped convenience binders used by the
  runtime so orchestrator / tests can mock the ``execute_typed_command``
  callable via module globals.
"""

from __future__ import annotations

from application.context import RuntimeContext
from domain.process import WorkItem, decide_unsupported
from domain.process.continuation import ContinuationBudget
from runtime.execution.execution_results import DeterministicExecutionResult
from runtime.workflows.inbox_command_enrichment import (
    enrich_inbox_typed_command,
    extract_task_inputs_via_runtime,
    stamp_workflow_authorization,
)
from task_routing import extract_task_inputs_for_decision


# ---------------------------------------------------------------------------
# Reentry helper (formerly deterministic_reentry.py).


def execute_typed_command_for_continuation(
    command: object,
    *,
    task_text: str,
    context: RuntimeContext,
    continuation_budget: ContinuationBudget | None,
    current_work_item: WorkItem | None,
    vm: object | None,
    gateway: object | None,
    model: str | None,
    seen_signatures: frozenset[str] | None,
    materialize_typed_step_fn,
    execute_typed_command_fn,
):
    materialized = materialize_typed_step_fn(command)
    from application.workflows.continuation_common import ContinuationExecutionResult

    if materialized is None:
        return ContinuationExecutionResult(
            decision=decide_unsupported(reason_code="continuation_command_missing"),
            message="Continuation work item carried no valid typed command.",
            refs=(),
        )

    result = execute_typed_command_fn(
        materialized,
        task_text=task_text,
        context=context,
        continuation_budget=continuation_budget,
        current_work_item=current_work_item,
        vm=vm,
        gateway=gateway,
        model=model,
        seen_signatures=seen_signatures,
    )
    return ContinuationExecutionResult(
        decision=result.decision,
        message=result.message,
        refs=result.refs,
    )


# ---------------------------------------------------------------------------
# Deterministic inbox wrappers (formerly deterministic_inbox.py).


def execute_inbox_typed_continuation(
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
    extract_task_inputs_for_decision_fn,
    stamp_workflow_authorization_fn,
    enrich_inbox_typed_command_fn,
) -> DeterministicExecutionResult:
    from runtime.workflows.inbox_workflow_execution import execute_inbox_typed_continuation_via_runtime

    result = execute_inbox_typed_continuation_via_runtime(
        continuation_intent,
        source_text=source_text,
        context=context,
        continuation_budget=continuation_budget,
        vm=vm,
        gateway=gateway,
        model=model,
        inbox_ref=inbox_ref,
        execute_typed_command_fn=execute_typed_command_fn,
        extract_task_inputs_fn=extract_task_inputs_fn,
        extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision_fn,
        stamp_workflow_authorization_fn=stamp_workflow_authorization_fn,
        enrich_inbox_typed_command_fn=enrich_inbox_typed_command_fn,
    )
    return DeterministicExecutionResult(
        decision=result.decision,
        message=result.message,
        refs=result.refs,
    )


def execute_inbox_sub_task(
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
    extract_task_inputs_for_decision_fn,
    stamp_workflow_authorization_fn,
    enrich_inbox_typed_command_fn,
) -> DeterministicExecutionResult:
    from runtime.workflows.inbox_workflow_execution import execute_inbox_sub_task_via_runtime

    result = execute_inbox_sub_task_via_runtime(
        sub_task_text,
        context=context,
        continuation_budget=continuation_budget,
        vm=vm,
        gateway=gateway,
        model=model,
        inbox_ref=inbox_ref,
        execute_typed_command_fn=execute_typed_command_fn,
        extract_task_inputs_fn=extract_task_inputs_fn,
        extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision_fn,
        stamp_workflow_authorization_fn=stamp_workflow_authorization_fn,
        enrich_inbox_typed_command_fn=enrich_inbox_typed_command_fn,
    )
    return DeterministicExecutionResult(
        decision=result.decision,
        message=result.message,
        refs=result.refs,
    )


def execute_inbox_continuation(
    next_step,
    *,
    task_text: str,
    context: RuntimeContext,
    continuation_budget: ContinuationBudget | None,
    vm: object | None,
    execute_typed_command_fn,
    read_text_fn,
    write_text_fn,
) -> DeterministicExecutionResult:
    from runtime.workflows.inbox_workflow_execution import execute_inbox_workflow_step_via_runtime

    result = execute_inbox_workflow_step_via_runtime(
        next_step,
        task_text=task_text,
        context=context,
        continuation_budget=continuation_budget,
        vm=vm,
        execute_typed_command_fn=execute_typed_command_fn,
        read_text_fn=read_text_fn,
        write_text_fn=write_text_fn,
    )
    return DeterministicExecutionResult(
        decision=result.decision,
        message=result.message,
        refs=result.refs,
    )


def continue_with_inbox_typed_intent(
    continuation_intent: str,
    *,
    source_text: str,
    context: RuntimeContext,
    current_work_item: WorkItem,
    continuation_budget: ContinuationBudget | None,
    gateway: object | None,
    model: str | None,
    inbox_ref: str | None,
    extract_task_inputs_fn,
    extract_task_inputs_for_decision_fn,
    stamp_workflow_authorization_fn,
    enrich_inbox_typed_command_fn,
) -> DeterministicExecutionResult:
    from runtime.workflows.inbox_workflow_execution import continue_with_inbox_typed_intent_via_runtime

    result = continue_with_inbox_typed_intent_via_runtime(
        continuation_intent,
        source_text=source_text,
        context=context,
        current_work_item=current_work_item,
        continuation_budget=continuation_budget,
        gateway=gateway,
        model=model,
        inbox_ref=inbox_ref,
        extract_task_inputs_fn=extract_task_inputs_fn,
        extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision_fn,
        stamp_workflow_authorization_fn=stamp_workflow_authorization_fn,
        enrich_inbox_typed_command_fn=enrich_inbox_typed_command_fn,
    )
    return DeterministicExecutionResult(
        decision=result.decision,
        message=result.message,
        refs=result.refs,
    )


def continue_with_inbox_sub_task(
    sub_task_text: str,
    *,
    context: RuntimeContext,
    current_work_item: WorkItem,
    continuation_budget: ContinuationBudget | None,
    gateway: object | None,
    model: str | None,
    inbox_ref: str | None,
    extract_task_inputs_fn,
    extract_task_inputs_for_decision_fn,
    stamp_workflow_authorization_fn,
    enrich_inbox_typed_command_fn,
) -> DeterministicExecutionResult:
    from runtime.workflows.inbox_workflow_execution import continue_with_inbox_sub_task_via_runtime

    result = continue_with_inbox_sub_task_via_runtime(
        sub_task_text,
        context=context,
        current_work_item=current_work_item,
        continuation_budget=continuation_budget,
        gateway=gateway,
        model=model,
        inbox_ref=inbox_ref,
        extract_task_inputs_fn=extract_task_inputs_fn,
        extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision_fn,
        stamp_workflow_authorization_fn=stamp_workflow_authorization_fn,
        enrich_inbox_typed_command_fn=enrich_inbox_typed_command_fn,
    )
    return DeterministicExecutionResult(
        decision=result.decision,
        message=result.message,
        refs=result.refs,
    )


def continue_with_inbox_workflow_step(
    next_step,
    *,
    task_text: str,
    context: RuntimeContext,
    current_work_item: WorkItem,
    continuation_budget: ContinuationBudget | None,
    vm: object | None,
    execute_typed_command_fn,
    read_text_fn,
    write_text_fn,
) -> DeterministicExecutionResult:
    from runtime.workflows.inbox_workflow_execution import continue_with_inbox_workflow_step_via_runtime

    result = continue_with_inbox_workflow_step_via_runtime(
        next_step,
        task_text=task_text,
        context=context,
        current_work_item=current_work_item,
        continuation_budget=continuation_budget,
        vm=vm,
        execute_typed_command_fn=execute_typed_command_fn,
        read_text_fn=read_text_fn,
        write_text_fn=write_text_fn,
    )
    return DeterministicExecutionResult(
        decision=result.decision,
        message=result.message,
        refs=result.refs,
    )


# ---------------------------------------------------------------------------
# Runtime-bound convenience wrappers (formerly deterministic_inbox_support.py).


execute_typed_command_fn = None


def execute_typed_command_for_runtime(
    command: object,
    *,
    task_text: str,
    context: RuntimeContext,
    continuation_budget: ContinuationBudget | None,
    current_work_item: WorkItem | None = None,
    vm: object | None,
    gateway: object | None,
    model: str | None,
    seen_signatures: frozenset[str] | None = None,
):
    if execute_typed_command_fn is None:
        raise RuntimeError("execute_typed_command_for_runtime is not bound")
    return execute_typed_command_fn(
        command,
        task_text=task_text,
        context=context,
        continuation_budget=continuation_budget,
        current_work_item=current_work_item,
        vm=vm,
        gateway=gateway,
        model=model,
        seen_signatures=seen_signatures,
    )


def execute_inbox_typed_continuation_for_runtime(
    continuation_intent: str,
    *,
    source_text: str,
    context: RuntimeContext,
    continuation_budget: ContinuationBudget | None,
    vm: object | None,
    gateway: object | None,
    model: str | None,
    inbox_ref: str | None,
    execute_typed_command_fn=None,
) -> DeterministicExecutionResult:
    if execute_typed_command_fn is None:
        execute_typed_command_fn = execute_typed_command_for_runtime
    globals()["execute_typed_command_fn"] = execute_typed_command_fn
    return execute_inbox_typed_continuation(
        continuation_intent,
        source_text=source_text,
        context=context,
        continuation_budget=continuation_budget,
        vm=vm,
        gateway=gateway,
        model=model,
        inbox_ref=inbox_ref,
        execute_typed_command_fn=execute_typed_command_for_runtime,
        extract_task_inputs_fn=extract_task_inputs_via_runtime,
        extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision,
        stamp_workflow_authorization_fn=stamp_workflow_authorization,
        enrich_inbox_typed_command_fn=enrich_inbox_typed_command,
    )


def execute_inbox_sub_task_for_runtime(
    sub_task_text: str,
    *,
    context: RuntimeContext,
    continuation_budget: ContinuationBudget | None,
    vm: object | None,
    gateway: object | None,
    model: str | None,
    inbox_ref: str | None,
    execute_typed_command_fn=None,
) -> DeterministicExecutionResult:
    if execute_typed_command_fn is None:
        execute_typed_command_fn = execute_typed_command_for_runtime
    globals()["execute_typed_command_fn"] = execute_typed_command_fn
    return execute_inbox_sub_task(
        sub_task_text,
        context=context,
        continuation_budget=continuation_budget,
        vm=vm,
        gateway=gateway,
        model=model,
        inbox_ref=inbox_ref,
        execute_typed_command_fn=execute_typed_command_for_runtime,
        extract_task_inputs_fn=extract_task_inputs_via_runtime,
        extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision,
        stamp_workflow_authorization_fn=stamp_workflow_authorization,
        enrich_inbox_typed_command_fn=enrich_inbox_typed_command,
    )


def execute_inbox_continuation_for_runtime(
    next_step,
    *,
    task_text: str,
    context: RuntimeContext,
    continuation_budget: ContinuationBudget | None,
    vm: object | None,
    execute_typed_command_fn=None,
    read_text_fn,
    write_text_fn,
) -> DeterministicExecutionResult:
    if execute_typed_command_fn is None:
        execute_typed_command_fn = execute_typed_command_for_runtime
    globals()["execute_typed_command_fn"] = execute_typed_command_fn
    return execute_inbox_continuation(
        next_step,
        task_text=task_text,
        context=context,
        continuation_budget=continuation_budget,
        vm=vm,
        execute_typed_command_fn=execute_typed_command_for_runtime,
        read_text_fn=read_text_fn,
        write_text_fn=write_text_fn,
    )


def continue_with_inbox_typed_intent_for_runtime(
    continuation_intent: str,
    *,
    source_text: str,
    context: RuntimeContext,
    current_work_item: WorkItem,
    continuation_budget: ContinuationBudget | None,
    gateway: object | None,
    model: str | None,
    inbox_ref: str | None,
) -> DeterministicExecutionResult:
    globals()["execute_typed_command_fn"] = None
    return continue_with_inbox_typed_intent(
        continuation_intent,
        source_text=source_text,
        context=context,
        current_work_item=current_work_item,
        continuation_budget=continuation_budget,
        gateway=gateway,
        model=model,
        inbox_ref=inbox_ref,
        extract_task_inputs_fn=extract_task_inputs_via_runtime,
        extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision,
        stamp_workflow_authorization_fn=stamp_workflow_authorization,
        enrich_inbox_typed_command_fn=enrich_inbox_typed_command,
    )


def continue_with_inbox_sub_task_for_runtime(
    sub_task_text: str,
    *,
    context: RuntimeContext,
    current_work_item: WorkItem,
    continuation_budget: ContinuationBudget | None,
    gateway: object | None,
    model: str | None,
    inbox_ref: str | None,
) -> DeterministicExecutionResult:
    globals()["execute_typed_command_fn"] = None
    return continue_with_inbox_sub_task(
        sub_task_text,
        context=context,
        current_work_item=current_work_item,
        continuation_budget=continuation_budget,
        gateway=gateway,
        model=model,
        inbox_ref=inbox_ref,
        extract_task_inputs_fn=extract_task_inputs_via_runtime,
        extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision,
        stamp_workflow_authorization_fn=stamp_workflow_authorization,
        enrich_inbox_typed_command_fn=enrich_inbox_typed_command,
    )


def continue_with_inbox_workflow_step_for_runtime(
    next_step,
    *,
    task_text: str,
    context: RuntimeContext,
    current_work_item: WorkItem,
    continuation_budget: ContinuationBudget | None,
    vm: object | None,
    execute_typed_command_fn=None,
    read_text_fn,
    write_text_fn,
) -> DeterministicExecutionResult:
    if execute_typed_command_fn is None:
        execute_typed_command_fn = execute_typed_command_for_runtime
    globals()["execute_typed_command_fn"] = execute_typed_command_fn
    return continue_with_inbox_workflow_step(
        next_step,
        task_text=task_text,
        context=context,
        current_work_item=current_work_item,
        continuation_budget=continuation_budget,
        vm=vm,
        execute_typed_command_fn=execute_typed_command_for_runtime,
        read_text_fn=read_text_fn,
        write_text_fn=write_text_fn,
    )


__all__ = [
    "continue_with_inbox_sub_task",
    "continue_with_inbox_sub_task_for_runtime",
    "continue_with_inbox_typed_intent",
    "continue_with_inbox_typed_intent_for_runtime",
    "continue_with_inbox_workflow_step",
    "continue_with_inbox_workflow_step_for_runtime",
    "execute_inbox_continuation",
    "execute_inbox_continuation_for_runtime",
    "execute_inbox_sub_task",
    "execute_inbox_sub_task_for_runtime",
    "execute_inbox_typed_continuation",
    "execute_inbox_typed_continuation_for_runtime",
    "execute_typed_command_for_continuation",
    "execute_typed_command_for_runtime",
    "stamp_workflow_authorization",
]
