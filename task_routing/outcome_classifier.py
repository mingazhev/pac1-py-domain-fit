"""Mapping from runtime outcome codes to typed process outcomes.

The runtime and VM boundary still surface ``outcome_name`` / ``reason_code``
as strings. This module is the single conversion point into the typed
``TaskOutcome`` contract owned by ``domain.process``.
"""

from __future__ import annotations

from domain.process.task_outcome import TaskOutcome, TaskOutcomeKind
from domain.security.refusal import SecurityRefusalKind


_DONE_REASON_KIND_BY_EXACT_CODE: dict[str, TaskOutcomeKind] = {
    "deterministic_resolution_succeeded": TaskOutcomeKind.FACTUAL_ANSWER,
    "report_generated": TaskOutcomeKind.REPORT_GENERATED,
}

_DONE_REASON_PREFIX_KIND: tuple[tuple[str, TaskOutcomeKind], ...] = (
    ("delegation_", TaskOutcomeKind.DELEGATION_CREATED),
    ("read_only_", TaskOutcomeKind.QUERY_ANSWERED),
)


def classify_task_outcome(
    outcome_name: str,
    *,
    reason_code: str = "",
) -> TaskOutcome:
    normalized_outcome = str(outcome_name or "").strip()
    normalized_reason = str(reason_code or "").strip().lower()

    if normalized_outcome == "OUTCOME_NONE_CLARIFICATION":
        return TaskOutcome(
            kind=TaskOutcomeKind.CLARIFICATION_REQUESTED,
            outcome_name=normalized_outcome,
            reason_code=reason_code,
        )
    if normalized_outcome == "OUTCOME_DENIED_SECURITY":
        return TaskOutcome(
            kind=TaskOutcomeKind.SECURITY_VIOLATION,
            outcome_name=normalized_outcome,
            reason_code=reason_code,
        )
    if normalized_outcome == "OUTCOME_NONE_UNSUPPORTED":
        return TaskOutcome(
            kind=TaskOutcomeKind.UNSUPPORTED,
            outcome_name=normalized_outcome,
            reason_code=reason_code,
        )
    if normalized_outcome.startswith("OUTCOME_ERR"):
        return TaskOutcome(
            kind=TaskOutcomeKind.INTERNAL_ERROR,
            outcome_name=normalized_outcome,
            reason_code=reason_code,
        )
    if normalized_outcome != "OUTCOME_OK":
        return TaskOutcome(
            kind=TaskOutcomeKind.UNKNOWN,
            outcome_name=normalized_outcome,
            reason_code=reason_code,
        )
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
        outcome_name=normalized_outcome,
        reason_code=reason_code,
    )


def security_refusal_reason_code(kind: SecurityRefusalKind) -> str:
    """Return the canonical reason code for a typed security refusal."""
    return f"security_refusal_{kind.value}"
