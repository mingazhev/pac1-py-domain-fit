"""Mutation result/decision mapping + LLM fallback planner.

Consolidates the former ``runtime.mutation_results`` and
``runtime.mutation_fallbacks`` modules.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from application.context import RuntimeContext
from application.mutations import MutationStepResult
from domain.process import (
    ClarificationRequest,
    PublicDecision,
    decide_blocked,
    decide_clarify,
    decide_done,
    decide_unsupported,
)
from domain.workspace import WorkspacePolicies
from runtime.io.mutation_persistence import vm_merge_frontmatter
from task_routing import (
    FinanceMutationCommand,
    OutboxDraftCommand,
    ProjectMutationCommand,
    QueueMutationCommand,
    TypedStep,
)
from task_routing.outcome_classifier import classify_task_outcome
from telemetry.trace import emit_runtime_exception


# ---------------------------------------------------------------------------
# Fallback planner (formerly runtime.mutation_fallbacks)
# ---------------------------------------------------------------------------


class MutationFallbackResult:
    def __init__(
        self,
        *,
        decision: PublicDecision,
        message: str,
        refs: tuple[str, ...],
        normalized_path: str | None = None,
        frontmatter_updates: dict[str, object] | None = None,
    ) -> None:
        self.decision = decision
        self.message = message
        self.refs = refs
        self.normalized_path = normalized_path
        self.frontmatter_updates = frontmatter_updates or {}


def run_mutation_fallback(
    command: TypedStep,
    *,
    task_text: str,
    gateway: Any,
    model: str | None,
    vm: Any,
    context: RuntimeContext | None = None,
) -> MutationFallbackResult | None:
    if gateway is None or not model:
        return None
    from task_routing.mutation_fallback import plan_mutation_fallback

    root_policy = ""
    lane_policy = ""
    lane_label = ""
    if context is not None:
        root_policy = context.workspace_policies.root
        lane_policy, lane_label = lane_policy_for_command(
            command, context.workspace_policies
        )

    plan = plan_mutation_fallback(
        gateway,
        model,
        task_text=task_text,
        command_summary=command_summary(command),
        existing_record_text=existing_record_text(vm, command),
        root_policy_text=root_policy,
        lane_policy_text=lane_policy,
        lane_label=lane_label,
    )
    if plan is None:
        return None
    if plan.decision == "refuse":
        return MutationFallbackResult(
            decision=decide_blocked(
                reason_code="mutation_fallback_refused",
                llm_stage="mutation_fallback",
            ),
            message=plan.reason or "LLM fallback refused the mutation on safety grounds.",
            refs=(),
        )
    if plan.decision == "clarify" or not plan.target_path:
        return MutationFallbackResult(
            decision=decide_clarify(
                clarification=ClarificationRequest(
                    reason_code="mutation_fallback_clarify",
                    message=plan.reason or "LLM fallback could not determine the mutation.",
                ),
                llm_stage="mutation_fallback",
            ),
            message=plan.reason or "Mutation needs clarification.",
            refs=(),
        )
    path = plan.target_path.strip()
    if not path:
        return None
    normalized_path = path if path.startswith("/") else f"/{path}"
    updates = {
        key: str(value) if not isinstance(value, (int, float, bool)) else value
        for key, value in (plan.frontmatter_updates or {}).items()
        if isinstance(key, str) and key.strip()
    }
    return MutationFallbackResult(
        decision=decide_done(
            outcome=classify_task_outcome(
                "OUTCOME_OK", reason_code="mutation_fallback_resolved"
            ),
            reason_code="mutation_fallback_resolved",
            llm_stage="mutation_fallback",
        ),
        message=normalized_path,
        refs=(normalized_path,),
        normalized_path=normalized_path,
        frontmatter_updates=updates,
    )


def lane_policy_for_command(
    command: TypedStep,
    policies: WorkspacePolicies,
) -> tuple[str, str]:
    if isinstance(command, FinanceMutationCommand):
        return policies.finance, "Finance"
    if isinstance(command, OutboxDraftCommand):
        return policies.outbox, "Outbox"
    if isinstance(command, ProjectMutationCommand):
        return policies.projects or policies.work, "Projects"
    if isinstance(command, QueueMutationCommand):
        return policies.system, "System"
    return "", ""


def command_summary(command: TypedStep) -> str:
    parts = [f"type={type(command).__name__}"]
    for field in fields(command):
        value = getattr(command, field.name)
        if value in (None, "", (), []):
            continue
        if isinstance(value, (list, tuple)):
            rendered = ", ".join(str(v) for v in value)
        else:
            rendered = str(value)
        parts.append(f"{field.name}={rendered[:200]}")
    return " | ".join(parts)


def existing_record_text(vm: Any, command: TypedStep) -> str | None:
    from runtime.io.vm_tools import read_text

    candidate_path = None
    for attribute in ("record_path", "anchor_record_ref"):
        value = getattr(command, attribute, None)
        if value and str(value).strip():
            candidate_path = str(value).strip()
            break
    if not candidate_path or vm is None:
        return None
    normalized = candidate_path if candidate_path.startswith("/") else f"/{candidate_path}"
    try:
        return read_text(vm, normalized)
    except Exception as exc:  # noqa: BLE001
        emit_runtime_exception(
            stage="mutation_fallbacks",
            operation="read_existing_record_text",
            error=exc,
            extra={"path": normalized},
        )
        return None


# ---------------------------------------------------------------------------
# Result mapping (formerly runtime.mutation_results)
# ---------------------------------------------------------------------------


class MutationExecutionResult:
    def __init__(
        self,
        *,
        decision: PublicDecision,
        message: str,
        refs: tuple[str, ...] = (),
    ) -> None:
        self.decision = decision
        self.message = message
        self.refs = refs


def map_mutation_result(result: MutationStepResult) -> MutationExecutionResult:
    if result.status == "resolved":
        outcome = classify_task_outcome(
            "OUTCOME_OK", reason_code=result.reason_code
        )
        return MutationExecutionResult(
            decision=decide_done(outcome=outcome, reason_code=result.reason_code),
            message=result.message,
            refs=result.grounding_refs,
        )
    if result.status == "blocked":
        return MutationExecutionResult(
            decision=decide_blocked(reason_code=result.reason_code),
            message=result.message,
            refs=result.grounding_refs,
        )
    if result.status == "unsupported":
        return MutationExecutionResult(
            decision=decide_unsupported(reason_code=result.reason_code),
            message=result.message,
            refs=result.grounding_refs,
        )
    return MutationExecutionResult(
        decision=decide_clarify(
            clarification=ClarificationRequest(
                reason_code=result.reason_code,
                message=result.message,
            )
        ),
        message=result.message,
        refs=result.grounding_refs,
    )


def map_fallback_result(
    fallback: MutationFallbackResult,
    *,
    vm: Any,
    context: RuntimeContext | None,
) -> MutationExecutionResult:
    if vm is not None and fallback.normalized_path and fallback.frontmatter_updates:
        vm_merge_frontmatter(
            vm,
            fallback.normalized_path,
            {
                str(k): (str(v) if not isinstance(v, (int, float, bool)) else v)
                for k, v in fallback.frontmatter_updates.items()
            },
            layout=(context.workspace_layout if context is not None else None),
        )
    return MutationExecutionResult(
        decision=fallback.decision,
        message=fallback.message,
        refs=fallback.refs,
    )


def unsupported_mutation(reason_code: str) -> MutationExecutionResult:
    return MutationExecutionResult(
        decision=decide_unsupported(reason_code=reason_code),
        message="That mutation variant is not wired into the pipeline.",
    )


__all__ = [
    "MutationExecutionResult",
    "MutationFallbackResult",
    "command_summary",
    "existing_record_text",
    "lane_policy_for_command",
    "map_fallback_result",
    "map_mutation_result",
    "run_mutation_fallback",
    "unsupported_mutation",
]
