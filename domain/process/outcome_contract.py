"""Typed contracts that bind outcome kinds to route mutability and side effects.

Phase 3 promotes outcome selection from a loose string-driven convention into
explicit, auditable contracts:

- ``RouteMutabilityTier`` mirrors the application-level intent mutability
  hierarchy inside the domain so process-layer code can enforce it without
  importing from routing seams.
- ``assert_outcome_for_mutability`` rejects mutation-bearing outcomes
  (``MUTATION_COMPLETED`` / ``DELEGATION_CREATED``) on read-only routes. This
  is the primary stop-gap against read-only questions drifting into
  unauthorized writes.
- ``SideEffectProfile`` carries observed write counts; the gate verifies that
  the outcome kind matches the observed effects (e.g. a ``FACTUAL_ANSWER``
  cannot have written to the outbox; a ``MUTATION_COMPLETED`` must have
  produced at least one side effect).

The module stays pure domain: it imports only from ``task_outcome`` and does
not depend on routing, application, or runtime modules.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .task_outcome import TaskOutcomeKind


class RouteMutabilityTier(str, Enum):
    """Mutability tier assigned to a route or command before execution."""

    READ_ONLY = "read_only"
    INTERNAL_MUTATION = "internal_mutation"
    EXTERNAL_MUTATION = "external_mutation"


_MUTATION_OUTCOMES: frozenset[TaskOutcomeKind] = frozenset(
    {TaskOutcomeKind.MUTATION_COMPLETED, TaskOutcomeKind.DELEGATION_CREATED}
)

_READ_ONLY_OUTCOMES: frozenset[TaskOutcomeKind] = frozenset(
    {
        TaskOutcomeKind.FACTUAL_ANSWER,
        TaskOutcomeKind.QUERY_ANSWERED,
        TaskOutcomeKind.REPORT_GENERATED,
    }
)

_DENIAL_OUTCOMES: frozenset[TaskOutcomeKind] = frozenset(
    {
        TaskOutcomeKind.CLARIFICATION_REQUESTED,
        TaskOutcomeKind.UNSUPPORTED,
        TaskOutcomeKind.SECURITY_VIOLATION,
    }
)


@dataclass(frozen=True, slots=True)
class OutcomeMutabilityDecision:
    allowed: bool
    outcome_kind: TaskOutcomeKind
    mutability: RouteMutabilityTier
    reason_code: str = ""


def mutability_admits_outcome_kind(
    mutability: RouteMutabilityTier,
    outcome_kind: TaskOutcomeKind,
) -> bool:
    if outcome_kind is TaskOutcomeKind.UNKNOWN:
        return False
    if (
        outcome_kind in _MUTATION_OUTCOMES
        and mutability is RouteMutabilityTier.READ_ONLY
    ):
        return False
    return True


def assert_outcome_for_mutability(
    outcome_kind: TaskOutcomeKind,
    mutability: RouteMutabilityTier,
) -> OutcomeMutabilityDecision:
    if mutability_admits_outcome_kind(mutability, outcome_kind):
        return OutcomeMutabilityDecision(
            allowed=True,
            outcome_kind=outcome_kind,
            mutability=mutability,
        )
    if outcome_kind in _MUTATION_OUTCOMES:
        return OutcomeMutabilityDecision(
            allowed=False,
            outcome_kind=outcome_kind,
            mutability=mutability,
            reason_code="read_only_route_attempted_mutation",
        )
    return OutcomeMutabilityDecision(
        allowed=False,
        outcome_kind=outcome_kind,
        mutability=mutability,
        reason_code="outcome_not_admitted_by_mutability",
    )


@dataclass(frozen=True, slots=True)
class SideEffectProfile:
    outbox_messages_written: int = 0
    inbox_items_deleted: int = 0
    canonical_records_written: int = 0
    external_dispatches: int = 0

    @property
    def has_any_side_effects(self) -> bool:
        return (
            self.outbox_messages_written > 0
            or self.inbox_items_deleted > 0
            or self.canonical_records_written > 0
            or self.external_dispatches > 0
        )

    @property
    def has_external_dispatch(self) -> bool:
        return self.external_dispatches > 0 or self.outbox_messages_written > 0


@dataclass(frozen=True, slots=True)
class SideEffectGateDecision:
    allowed: bool
    outcome_kind: TaskOutcomeKind
    profile: SideEffectProfile
    reason_code: str = ""


def gate_side_effects_against_outcome(
    outcome_kind: TaskOutcomeKind,
    profile: SideEffectProfile,
    *,
    mutability: RouteMutabilityTier | None = None,
) -> SideEffectGateDecision:
    """Return a decision that states whether observed side effects are legal.

    The gate is fail-closed:

    - Read-only outcomes must not have emitted side effects.
    - ``MUTATION_COMPLETED`` must have emitted at least one side effect.
    - Denial outcomes (clarification / unsupported / security) must not have
      emitted side effects either; a denied request still touching state is a
      postcondition breach.
    - If ``mutability`` is provided, a read-only route may not dispatch
      external content regardless of outcome wording.
    """
    if (
        outcome_kind in _READ_ONLY_OUTCOMES
        and profile.has_any_side_effects
    ):
        return SideEffectGateDecision(
            allowed=False,
            outcome_kind=outcome_kind,
            profile=profile,
            reason_code="read_only_outcome_emitted_side_effects",
        )
    if (
        outcome_kind is TaskOutcomeKind.MUTATION_COMPLETED
        and not profile.has_any_side_effects
    ):
        return SideEffectGateDecision(
            allowed=False,
            outcome_kind=outcome_kind,
            profile=profile,
            reason_code="mutation_outcome_without_side_effects",
        )
    if (
        outcome_kind in _DENIAL_OUTCOMES
        and profile.has_any_side_effects
    ):
        return SideEffectGateDecision(
            allowed=False,
            outcome_kind=outcome_kind,
            profile=profile,
            reason_code="denied_outcome_emitted_side_effects",
        )
    if (
        mutability is RouteMutabilityTier.READ_ONLY
        and profile.has_external_dispatch
    ):
        return SideEffectGateDecision(
            allowed=False,
            outcome_kind=outcome_kind,
            profile=profile,
            reason_code="read_only_route_external_dispatch",
        )
    return SideEffectGateDecision(
        allowed=True,
        outcome_kind=outcome_kind,
        profile=profile,
    )


__all__ = [
    "OutcomeMutabilityDecision",
    "RouteMutabilityTier",
    "SideEffectGateDecision",
    "SideEffectProfile",
    "assert_outcome_for_mutability",
    "gate_side_effects_against_outcome",
    "mutability_admits_outcome_kind",
]
