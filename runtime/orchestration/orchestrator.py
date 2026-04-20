"""Runtime orchestrator — the public machine loop.

The four public concepts named in ``NORTH_STAR.md`` are:

- ``Request``      — the external ask
- ``WorkItem``     — the controlled unit entering or re-entering the loop
- ``Plan``         — interpretation of a WorkItem (immediate decision,
                     typed multi-step plan, or single atomic command)
- ``Decision``     — stop/continue choice the machine emits

The loop in this module follows the seven steps from NORTH_STAR:

    1. Request -> WorkItem
    2. preflight and policy gate
    3. interpret the WorkItem into a Plan (or an immediate Decision)
    4. execute one deterministic step
    5. postcheck
    6. choose a Decision (done / clarify / blocked / unsupported / continue /
       fallback)
    7. if Decision == continue, emit the next controlled WorkItem and loop

Valid decisions (see ``domain.process.decision``):
``done``, ``clarify``, ``blocked``, ``unsupported``, ``continue``, ``fallback``.
``continue`` is stricter than ``fallback`` — it requires a typed,
evidence-backed, provenance-linked next WorkItem that is still inside budget.
"""

from __future__ import annotations

from uuid import uuid4

try:
    from bitgn.vm.pcm_connect import PcmRuntimeClientSync
except ModuleNotFoundError:  # pragma: no cover - local test fallback only
    class PcmRuntimeClientSync:  # type: ignore[override]
        def __init__(self, *_args, **_kwargs) -> None:
            raise ModuleNotFoundError("bitgn SDK is not installed")

from domain.process import Plan, TypedStepPlan, RequestSource, WorkItem, decide_unsupported, new_request, new_request_work_item
from domain.security import sanitize_security_text
from runtime.context.context_assembly import (
    load_runtime_context,
    load_workspace_policies,
    needed_kinds_for_command,
)
from runtime.execution.execution_engine import execute_typed_command
from runtime.execution.execution_results import DeterministicExecutionResult
from runtime.orchestration.request_authorization import stamp_request_authorization
from runtime.orchestration.request_planning import (
    SUPPORTED_INTENTS,
    consume_inbox_evidence_if_needed,
    message_for_immediate_decision,
    plan_for_continuation_work_item,
    plan_for_request_work_item,
)
from runtime.execution.step_materialization import materialize_typed_step
from runtime.execution.typed_plan_runtime import execute_typed_plan
from runtime.io.vm_tools import delete_path, emit_terminal_public_decision
from task_routing import (
    StructuredExtractionGateway,
    build_structured_extraction_gateway,
    extract_task_inputs,
)


def run_agent(model: str, harness_url: str, task_text: str) -> None:
    vm = PcmRuntimeClientSync(harness_url)
    gateway = build_structured_extraction_gateway(model)

    # === STEP 1: Request -> WorkItem ===
    sanitized_task = sanitize_security_text(task_text)
    request = new_request(
        identifier=f"req_{uuid4().hex}",
        task_text=sanitized_task,
        source=RequestSource.HARNESS,
    )
    current_work_item = new_request_work_item(request=request)

    # === STEP 2: preflight / policy gate (workspace policies) ===
    workspace_policies = load_workspace_policies(vm)

    while True:
        # === STEP 3: Plan (typed plan, atomic command, or immediate Decision) ===
        plan, effective_task_text = _plan_for_work_item(
            current_work_item,
            gateway=gateway,
            model=model,
            workspace_policies=workspace_policies,
        )

        # --- Plan branch: immediate Decision (skip to STEP 6) ---
        if plan.is_immediate:
            decision = plan.immediate_decision
            assert decision is not None
            emit_terminal_public_decision(
                vm,
                decision,
                message=message_for_immediate_decision(decision),
                refs=current_work_item.evidence_refs,
            )
            return

        # --- Plan branch: typed multi-step plan ---
        if plan.is_typed_plan:
            typed_plan = plan.typed_plan
            if not isinstance(typed_plan, TypedStepPlan):
                emit_terminal_public_decision(
                    vm,
                    decide_unsupported(reason_code="typed_plan_payload_invalid"),
                    message="The public machine produced an invalid typed plan payload.",
                    refs=current_work_item.evidence_refs,
                )
                return
            # === STEP 4-5: Execute + postcheck ===
            typed_plan_result = execute_typed_plan(
                typed_plan,
                current_work_item=current_work_item,
                vm=vm,
                gateway=gateway,
                model=model,
                load_runtime_context_fn=load_runtime_context,
                execute_typed_command_fn=execute_typed_command,
                materialize_typed_step_fn=materialize_typed_step,
            )
            # === STEP 6-7: Decision + (maybe) continue ===
            next_work_item = _finalize_step_result(
                vm=vm,
                current_work_item=current_work_item,
                result=typed_plan_result,
            )
            if next_work_item is None:
                return
            current_work_item = next_work_item
            continue

        # --- Plan branch: single atomic command ---
        command = plan.atomic_command
        if command is None:
            decision = decide_unsupported(reason_code="plan_without_atomic_command")
            emit_terminal_public_decision(
                vm,
                decision,
                message="The public machine produced no executable atomic command.",
                refs=current_work_item.evidence_refs,
            )
            return
        # === STEP 4-5: Execute + postcheck ===
        needed_kinds = needed_kinds_for_command(command)
        context = load_runtime_context(vm, needed_kinds=needed_kinds)
        result = execute_typed_command(
            command,
            task_text=effective_task_text,
            context=context,
            continuation_budget=current_work_item.budget,
            current_work_item=current_work_item,
            vm=vm,
            gateway=gateway,
            model=model,
        )
        # === STEP 6-7: Decision + (maybe) continue ===
        next_work_item = _finalize_step_result(
            vm=vm,
            current_work_item=current_work_item,
            result=result,
        )
        if next_work_item is None:
            return
        current_work_item = next_work_item


def _finalize_step_result(
    *,
    vm,
    current_work_item: WorkItem,
    result: DeterministicExecutionResult,
) -> WorkItem | None:
    """STEP 6-7: act on the Decision produced by one executed step.

    Returns the next controlled ``WorkItem`` when the Decision is
    ``continue`` (so the caller loops back to STEP 3), or ``None`` when
    the Decision is terminal (so the caller returns).

    Terminal decisions also trigger inbox-evidence cleanup and emit the
    public terminal decision to the harness.
    """
    if result.decision.next_work_item is not None:
        return result.decision.next_work_item
    consume_inbox_evidence_if_needed(
        vm,
        current_work_item=current_work_item,
        decision=result.decision,
        delete_path_fn=delete_path,
    )
    emit_terminal_public_decision(
        vm,
        result.decision,
        message=result.message,
        refs=result.refs,
    )
    return None


def _plan_for_work_item(
    work_item: WorkItem,
    *,
    gateway: StructuredExtractionGateway,
    model: str,
    workspace_policies,
) -> tuple[Plan, str]:
    """STEP 3 of the public machine loop: interpret a ``WorkItem`` into a ``Plan``.

    A fresh ``REQUEST`` work item goes through request interpretation
    (task extraction, policy stamping, immediate-decision shortcuts); a
    ``CONTINUATION`` work item materialises the typed next step from its
    ``continuation_source`` without re-running request interpretation.
    """
    if work_item.origin.value == "request":
        return plan_for_request_work_item(
            work_item,
            gateway=gateway,
            model=model,
            workspace_policies=workspace_policies,
            request_source=RequestSource.HARNESS,
            extract_task_inputs_fn=extract_task_inputs,
            stamp_request_authorization_fn=stamp_request_authorization,
        )
    return plan_for_continuation_work_item(
        work_item,
        materialize_typed_step_fn=materialize_typed_step,
    )

_needed_kinds_for_command = needed_kinds_for_command
