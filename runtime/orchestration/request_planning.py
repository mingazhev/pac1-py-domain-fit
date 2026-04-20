from __future__ import annotations

from collections.abc import Callable

from domain.process import (
    ClarificationRequest,
    Plan,
    WorkItem,
    decide_blocked,
    decide_clarify,
    decide_unsupported,
    plan_atomic,
    plan_immediate,
)
from domain.security import (
    detect_injection_patterns,
    refusal_for_injection_in_task_instruction,
)
from runtime.orchestration.request_authorization import classify_request_source
from task_routing import TaskIntent
from telemetry.trace import emit_runtime_exception


SUPPORTED_INTENTS = {
    TaskIntent.ACCOUNT_LOOKUP,
    TaskIntent.CONTACT_LOOKUP,
    TaskIntent.CAPTURE_LOOKUP,
    TaskIntent.PROJECT_QUERY,
    TaskIntent.PROJECT_MUTATION,
    TaskIntent.ENTITY_QUERY,
    TaskIntent.MESSAGE_QUERY,
    TaskIntent.FINANCE_LOOKUP,
    TaskIntent.FINANCE_MUTATION,
    TaskIntent.INBOX_PROCESS_NEXT,
    TaskIntent.INBOX_WORKFLOW,
    TaskIntent.QUEUE_STATE_LOOKUP,
    TaskIntent.QUEUE_MUTATION,
    TaskIntent.OUTBOX_DRAFT,
}


def plan_for_request_work_item(
    work_item: WorkItem,
    *,
    gateway,
    model: str,
    workspace_policies,
    request_source,
    extract_task_inputs_fn: Callable[..., object],
    stamp_request_authorization_fn: Callable[..., object],
) -> tuple[Plan, str]:
    # NORTH_STAR: security starts BEFORE full semantic understanding.
    # Both gates below must run strictly before ``extract_task_inputs_fn``,
    # which is the first LLM call that reads raw ``work_item.goal``.
    authz_context = classify_request_source(request_source)
    if not authz_context.trusted:
        reason = authz_context.reason_code or "unauthorized_source"
        return (
            plan_immediate(decision=decide_blocked(reason_code=reason, llm_stage=None)),
            "The request was rejected before interpretation: source not authorized.",
        )
    injection_findings = tuple(detect_injection_patterns(work_item.goal))
    if injection_findings:
        refusal = refusal_for_injection_in_task_instruction(injection_findings)
        return (
            plan_immediate(decision=decide_blocked(reason_code=refusal.reason)),
            refusal.summary,
        )
    routed = extract_task_inputs_fn(
        gateway,
        model,
        work_item.goal,
        supported_intents=SUPPORTED_INTENTS,
        workspace_policies=workspace_policies,
    )
    if routed.decision.intent is TaskIntent.UNKNOWN:
        return (
            plan_immediate(
                decision=decide_clarify(
                    clarification=ClarificationRequest(
                        reason_code="route_unknown",
                        message="The request could not be classified into a supported typed task family.",
                    )
                )
            ),
            "The request needs clarification before deterministic execution.",
        )
    if routed.decision.intent not in SUPPORTED_INTENTS:
        return (
            plan_immediate(decision=decide_unsupported(reason_code="unsupported_clean_family")),
            "That task family is intentionally outside the first clean PAC1 cut.",
        )
    if routed.typed_command is None:
        return (
            plan_immediate(
                decision=decide_clarify(
                    clarification=ClarificationRequest(
                        reason_code="typed_request_missing",
                        message="The request matched a supported family but did not yield a valid typed payload.",
                    )
                )
            ),
            "The request needs clarification because structured extraction did not produce a valid typed payload.",
        )
    stamped = stamp_request_authorization_fn(
        routed.typed_command,
        source=request_source,
    )
    return plan_atomic(command=stamped), (routed.effective_task_text or work_item.goal)


def plan_for_continuation_work_item(
    work_item: WorkItem,
    *,
    materialize_typed_step_fn: Callable[[object], object | None],
) -> tuple[Plan, str]:
    source = work_item.continuation_source
    if source is None or source.executor_kind != "typed_command":
        return (
            plan_immediate(decision=decide_unsupported(reason_code="continuation_kind_not_wired")),
            "Continuation work item has no executable typed command payload.",
        )
    command = materialize_typed_step_fn(source.payload.get("command"))
    if command is None:
        return (
            plan_immediate(decision=decide_unsupported(reason_code="continuation_command_missing")),
            "Continuation work item carried no valid typed command.",
        )
    task_text = str(source.payload.get("task_text") or "").strip() or work_item.goal
    return plan_atomic(command=command), task_text


def message_for_immediate_decision(decision) -> str:
    if decision.kind.value == "blocked":
        return "The request was blocked by deterministic preflight."
    if decision.kind.value == "clarify":
        return (
            decision.clarification.message
            if decision.clarification is not None
            else "The request needs clarification before deterministic execution."
        )
    if decision.kind.value == "unsupported":
        return "That task family is intentionally outside the first clean PAC1 cut."
    return "The public machine produced an immediate terminal decision."


def consume_inbox_evidence_if_needed(
    vm,
    *,
    current_work_item: WorkItem,
    decision,
    delete_path_fn: Callable[[object, str], None],
) -> None:
    if decision.kind.value != "done":
        return
    source = current_work_item.continuation_source
    if source is None:
        return
    consumed_ref = str(source.payload.get("consumed_inbox_ref") or "").strip()
    if not consumed_ref:
        return
    try:
        delete_path_fn(vm, consumed_ref)
    except Exception as exc:  # noqa: BLE001
        emit_runtime_exception(
            stage="request_planning",
            operation="delete_consumed_inbox_ref",
            error=exc,
            extra={"path": consumed_ref},
        )
        return


__all__ = [
    "SUPPORTED_INTENTS",
    "consume_inbox_evidence_if_needed",
    "message_for_immediate_decision",
    "plan_for_continuation_work_item",
    "plan_for_request_work_item",
]
