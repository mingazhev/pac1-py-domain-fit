from __future__ import annotations

from dataclasses import dataclass

from domain.process import (
    ClarificationRequest,
    PublicDecision,
    TaskOutcome,
    TaskOutcomeKind,
    decide_blocked,
    decide_clarify,
    decide_done,
)
from domain.process.continuation import ContinuationBudget, default_continuation_budget

_DONE_REASON_KIND_BY_EXACT_CODE: dict[str, TaskOutcomeKind] = {
    "deterministic_resolution_succeeded": TaskOutcomeKind.FACTUAL_ANSWER,
    "report_generated": TaskOutcomeKind.REPORT_GENERATED,
}

_DONE_REASON_PREFIX_KIND: tuple[tuple[str, TaskOutcomeKind], ...] = (
    ("delegation_", TaskOutcomeKind.DELEGATION_CREATED),
    ("read_only_", TaskOutcomeKind.QUERY_ANSWERED),
)


def _classify_ok_outcome(reason_code: str) -> TaskOutcome:
    """Local mirror of the ``OUTCOME_OK`` branch of ``task_routing.outcome_classifier``.

    The application layer is forbidden from importing ``task_routing`` (see
    ``tests/test_application_layer_boundaries.py``). ``done_result`` always
    feeds ``OUTCOME_OK`` into the classifier, so we inline the reason-code →
    kind mapping here rather than introduce a cross-layer dependency. Keeps
    behaviour identical to ``classify_task_outcome("OUTCOME_OK", reason_code=...)``.
    """

    normalized_reason = str(reason_code or "").strip().lower()
    kind = _DONE_REASON_KIND_BY_EXACT_CODE.get(normalized_reason)
    if kind is None and normalized_reason.endswith("_completed"):
        kind = TaskOutcomeKind.MUTATION_COMPLETED
    if kind is None:
        for prefix, candidate_kind in _DONE_REASON_PREFIX_KIND:
            if normalized_reason.startswith(prefix):
                kind = candidate_kind
                break
    if kind is None:
        kind = TaskOutcomeKind.QUERY_ANSWERED
    return TaskOutcome(
        kind=kind,
        outcome_name="OUTCOME_OK",
        reason_code=reason_code,
    )

if False:  # pragma: no cover
    from application.context import RuntimeContext
    from application.ports import WorkflowInterpretationPort


@dataclass(frozen=True, slots=True)
class ContinuationExecutionResult:
    decision: PublicDecision
    message: str
    refs: tuple[str, ...] = ()


def continuation_budget_or_default(
    continuation_budget: ContinuationBudget | None,
) -> ContinuationBudget:
    return continuation_budget or default_continuation_budget()


def stamp_workflow_authorization(
    workflow_interpretation_port,
    command: object,
) -> object:
    from application.ports import (
        InterpretationRequest,
        KIND_WORKFLOW_STAMP_AUTHORIZATION,
        dispatch_workflow_interpretation,
    )

    envelope = dispatch_workflow_interpretation(
        workflow_interpretation_port,
        InterpretationRequest(
            kind=KIND_WORKFLOW_STAMP_AUTHORIZATION,
            payload={"command": command},
        ),
    )
    return envelope.plan if envelope.plan is not None else command


def enrich_inbox_typed_command(
    workflow_interpretation_port,
    command: object,
    *,
    source_text: str,
) -> object:
    from application.ports import (
        InterpretationRequest,
        KIND_WORKFLOW_ENRICH_TYPED_COMMAND,
        dispatch_workflow_interpretation,
    )

    envelope = dispatch_workflow_interpretation(
        workflow_interpretation_port,
        InterpretationRequest(
            kind=KIND_WORKFLOW_ENRICH_TYPED_COMMAND,
            payload={"command": command, "task_text": source_text},
        ),
    )
    return envelope.plan if envelope.plan is not None else command


def inbox_prompt_content(
    inbox_ref: str | None,
    *,
    context,
    source_text: str,
) -> str:
    item = find_inbox_item_by_ref(context.inbox_items, inbox_ref)
    if item is None:
        return source_text
    from domain.inbox import envelope_from_inbox_item
    from domain.cast import resolve_sender_canonical_entity

    canonical = resolve_sender_canonical_entity(context.cast_entities, item.sender)
    canonical_entity = canonical.title if canonical is not None else ""
    envelope = envelope_from_inbox_item(
        item,
        sender_canonical_entity=canonical_entity,
    )
    envelope_context = envelope.as_prompt_context()
    if not envelope_context:
        return source_text
    return f"{envelope_context}\n\n{source_text}".strip()


def find_inbox_item_by_ref(inbox_items, inbox_ref: str | None):
    normalized_ref = str(inbox_ref or "").strip()
    if not normalized_ref:
        return None
    for item in inbox_items:
        candidate = str(getattr(item, "path", "") or "").strip()
        if candidate == normalized_ref or f"/{candidate.lstrip('/')}" == normalized_ref:
            return item
    return None


def clarify_result(
    message: str,
    *,
    reason_code: str,
    refs: tuple[str, ...] = (),
) -> ContinuationExecutionResult:
    return ContinuationExecutionResult(
        decision=decide_clarify(
            clarification=ClarificationRequest(
                reason_code=reason_code,
                message=message,
            )
        ),
        message=message,
        refs=refs,
    )


def blocked_result(
    message: str,
    *,
    reason_code: str,
    refs: tuple[str, ...] = (),
) -> ContinuationExecutionResult:
    return ContinuationExecutionResult(
        decision=decide_blocked(reason_code=reason_code),
        message=message,
        refs=refs,
    )


def done_result(
    message: str,
    *,
    reason_code: str,
    refs: tuple[str, ...] = (),
) -> ContinuationExecutionResult:
    return ContinuationExecutionResult(
        decision=decide_done(
            outcome=_classify_ok_outcome(reason_code),
            reason_code=reason_code,
        ),
        message=message,
        refs=refs,
    )


__all__ = [
    "ContinuationExecutionResult",
    "blocked_result",
    "clarify_result",
    "continuation_budget_or_default",
    "done_result",
    "enrich_inbox_typed_command",
    "find_inbox_item_by_ref",
    "inbox_prompt_content",
    "stamp_workflow_authorization",
]
