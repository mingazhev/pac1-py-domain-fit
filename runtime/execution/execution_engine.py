"""Synchronous deterministic execution facade.

Entry point for the runtime's "execute one step" layer:

- :func:`execute_typed_command` — public entry point used by the
  orchestrator. Wires deterministic dependencies (step contract lookup,
  mutation pipeline, read executor, inbox pipeline, etc.) into the
  dispatch core.
- :func:`execute_typed_command_via_runtime` — dispatch core. All
  collaborators come through kwargs so the wiring stays explicit.
- :func:`step_signature` / :func:`try_vm_delete` — small support
  helpers co-located with the engine so the deterministic surface is
  one module, not three.
"""

from __future__ import annotations

from dataclasses import asdict

from application.context import RuntimeContext
from application.executors import execute_read_step
from application.workflows import resolve_inbox_workflow_step
from domain.process import WorkItem, decide_blocked, decide_unsupported
from domain.process.continuation import ContinuationBudget
from runtime.execution.execution_mailbox import stamp_workflow_authorization
from runtime.execution.execution_mailbox import execute_typed_command_for_continuation
from runtime.execution.execution_results import (
    DeterministicExecutionResult,
    clarify as _clarify,
    done as _done,
    from_read_execution_result as _from_read_execution_result,
)
from runtime.workflows.inbox_command_enrichment import (
    build_inbox_classifier,
    enrich_inbox_typed_command,
    extract_task_inputs_via_runtime,
)
from runtime.workflows.inbox_workflow_execution import execute_inbox_process_next_command_via_runtime
from runtime.execution.mutation_execution import execute_mutation_step
from runtime.ports.runtime_ports import build_runtime_ports
from runtime.execution.step_materialization import materialize_typed_step
from runtime.io.vm_tools import delete_path, read_text, write_text
from task_routing import (
    InboxProcessNextCommand,
    StepSideEffectClass,
    TypedStep,
    UnregisteredStepError,
    contract_for_command,
    extract_task_inputs_for_decision,
)
from telemetry.trace import emit_runtime_exception


# ---------------------------------------------------------------------------
# Support helpers (co-located — both are one-liners exercised by the engine).


def step_signature(command: object) -> str:
    try:
        payload = asdict(command)
    except TypeError:
        payload = {"repr": repr(command)}
    payload.pop("translated_text", None)
    return f"{type(command).__name__}:{sorted(payload.items())}"


def try_vm_delete(delete_path_fn, vm: object, path: str) -> None:
    try:
        delete_path_fn(vm, path)
    except Exception as exc:  # noqa: BLE001
        emit_runtime_exception(
            stage="deterministic",
            operation="delete_path",
            error=exc,
            extra={"path": path},
        )


# ---------------------------------------------------------------------------
# Dispatch core.


def execute_typed_command_via_runtime(
    command: TypedStep,
    *,
    task_text: str,
    context: RuntimeContext,
    continuation_budget: ContinuationBudget | None,
    current_work_item: WorkItem | None,
    vm: object | None,
    gateway: object | None,
    model: str | None,
    seen_signatures: frozenset[str] | None,
    contract_for_command_fn,
    step_signature_fn,
    build_runtime_ports_fn,
    execute_mutation_step_fn,
    execute_read_step_fn,
    execute_inbox_process_next_command_via_runtime_fn,
    execute_typed_command_fn,
    try_vm_delete_fn,
    build_inbox_classifier_fn,
    resolve_inbox_workflow_step_fn,
    extract_task_inputs_fn,
    extract_task_inputs_for_decision_fn,
    stamp_workflow_authorization_fn,
    enrich_inbox_typed_command_fn,
    read_text_fn,
    write_text_fn,
):
    try:
        contract = contract_for_command_fn(command)
    except UnregisteredStepError:
        return DeterministicExecutionResult(
            decision=decide_unsupported(reason_code="unregistered_step_type"),
            message="That step type has no declared StepContract.",
        )

    signature = step_signature_fn(command)
    if seen_signatures is None:
        seen_signatures = frozenset()
    if signature in seen_signatures:
        return DeterministicExecutionResult(
            decision=decide_blocked(reason_code="loop_detected"),
            message=(
                "Same typed step was emitted twice within this run; "
                "refusing to re-execute to break the loop."
            ),
        )
    seen_signatures = seen_signatures | {signature}

    ports = build_runtime_ports_fn(
        context=context,
        gateway=gateway,
        model=model,
    )
    query_resolution_port = ports.query_resolution
    read_interpretation_port = ports.read_interpretation
    record_resolution_port = ports.record_resolution

    if contract.side_effect_class is StepSideEffectClass.MUTATE:
        mutation = execute_mutation_step_fn(
            command,
            task_text=task_text,
            context=context,
            query_resolution_port=query_resolution_port,
            vm=vm,
            gateway=gateway,
            model=model,
        )
        return DeterministicExecutionResult(
            decision=mutation.decision,
            message=mutation.message,
            refs=mutation.refs,
        )

    if contract.side_effect_class is StepSideEffectClass.WORKFLOW:
        if isinstance(command, InboxProcessNextCommand):
            workflow, continuation_result = execute_inbox_process_next_command_via_runtime_fn(
                command,
                task_text=task_text,
                context=context,
                continuation_budget=continuation_budget,
                current_work_item=current_work_item,
                vm=vm,
                gateway=gateway,
                model=model,
                execute_typed_command_fn=execute_typed_command_fn,
                delete_path_fn=lambda active_vm, path: try_vm_delete_fn(active_vm, path),
                build_classifier_fn=build_inbox_classifier_fn,
                resolve_inbox_workflow_step_fn=resolve_inbox_workflow_step_fn,
                extract_task_inputs_fn=extract_task_inputs_fn,
                extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision_fn,
                stamp_workflow_authorization_fn=stamp_workflow_authorization_fn,
                enrich_inbox_typed_command_fn=enrich_inbox_typed_command_fn,
                read_text_fn=read_text_fn,
                write_text_fn=write_text_fn,
            )
            if workflow.status == "resolved":
                return _done(
                    workflow.message,
                    workflow.grounding_refs,
                    workflow.reason_code,
                )
            if workflow.status == "blocked":
                return DeterministicExecutionResult(
                    decision=decide_blocked(reason_code=workflow.reason_code),
                    message=workflow.message,
                    refs=workflow.grounding_refs,
                )
            if workflow.status == "continue" and continuation_result is not None:
                return DeterministicExecutionResult(
                    decision=continuation_result.decision,
                    message=continuation_result.message,
                    refs=continuation_result.refs,
                )
            return _clarify(
                workflow.message,
                reason_code=workflow.reason_code,
                refs=workflow.grounding_refs,
            )
        return DeterministicExecutionResult(
            decision=decide_unsupported(reason_code="workflow_pipeline_not_wired"),
            message="That workflow step family is not yet wired.",
        )

    read_result = execute_read_step_fn(
        command,
        task_text=task_text,
        context=context,
        record_resolution_port=record_resolution_port,
        query_resolution_port=query_resolution_port,
        interpretation_port=read_interpretation_port,
    )
    if read_result is not None:
        return _from_read_execution_result(read_result)

    return DeterministicExecutionResult(
        decision=decide_unsupported(reason_code="unsupported_clean_family"),
        message="That task family is intentionally outside the first clean PAC1 cut.",
    )


# ---------------------------------------------------------------------------
# Public entry point.


def execute_typed_command(
    command: TypedStep,
    *,
    task_text: str,
    context: RuntimeContext,
    continuation_budget: ContinuationBudget | None = None,
    current_work_item: WorkItem | None = None,
    vm: object | None = None,
    gateway: object | None = None,
    model: str | None = None,
    seen_signatures: frozenset[str] | None = None,
) -> DeterministicExecutionResult:
    # Collaborators are referenced as free names so Python resolves each
    # through the module on every call — this is what makes
    # ``patch("runtime.execution.execution_engine._build_inbox_classifier")`` take
    # effect in tests.
    return execute_typed_command_via_runtime(
        command,
        task_text=task_text,
        context=context,
        continuation_budget=continuation_budget,
        current_work_item=current_work_item,
        vm=vm,
        gateway=gateway,
        model=model,
        seen_signatures=seen_signatures,
        contract_for_command_fn=contract_for_command,
        step_signature_fn=_step_signature,
        build_runtime_ports_fn=build_runtime_ports,
        execute_mutation_step_fn=execute_mutation_step,
        execute_read_step_fn=execute_read_step,
        execute_inbox_process_next_command_via_runtime_fn=execute_inbox_process_next_command_via_runtime,
        execute_typed_command_fn=_execute_typed_command_via_runtime,
        try_vm_delete_fn=_try_vm_delete,
        build_inbox_classifier_fn=_build_inbox_classifier,
        resolve_inbox_workflow_step_fn=resolve_inbox_workflow_step,
        extract_task_inputs_fn=_extract_task_inputs_via_runtime,
        extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision,
        stamp_workflow_authorization_fn=_stamp_workflow_authorization,
        enrich_inbox_typed_command_fn=_enrich_inbox_typed_command,
        read_text_fn=read_text,
        write_text_fn=write_text,
    )


def _execute_typed_command_via_runtime(
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
):
    return execute_typed_command_for_continuation(
        command,
        task_text=task_text,
        context=context,
        continuation_budget=continuation_budget,
        current_work_item=current_work_item,
        vm=vm,
        gateway=gateway,
        model=model,
        seen_signatures=seen_signatures,
        materialize_typed_step_fn=materialize_typed_step,
        execute_typed_command_fn=execute_typed_command,
    )


def _try_vm_delete(vm: object, path: str) -> None:
    return try_vm_delete(delete_path, vm, path)


def _step_signature(command: TypedStep) -> str:
    return step_signature(command)


# Module-level aliases preserve the private-call-surface the orchestrator
# and tests historically patched. Keeping these names stable means that
# migrating from ``runtime.deterministic`` to ``runtime.execution.execution_engine``
# is a single path rename, not a contract change.
_build_inbox_classifier = build_inbox_classifier
_extract_task_inputs_via_runtime = extract_task_inputs_via_runtime
_stamp_workflow_authorization = stamp_workflow_authorization
_enrich_inbox_typed_command = enrich_inbox_typed_command


__all__ = [
    "DeterministicExecutionResult",
    "execute_typed_command",
    "execute_typed_command_via_runtime",
    "step_signature",
    "try_vm_delete",
]
