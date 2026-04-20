"""First-class ``PublicDecision`` envelope for the public machine.

Phase 16A lifts the decision surface out of scattered helpers
(``WorkflowDecision`` per-executor results, ``OUTCOME_*`` string tokens,
``_emit_fallback_capture`` in ``runtime_io``, clarify paths in
``runtime_routing``) into a single typed contract.

The six valid decision kinds come from ``NORTH_STAR.md``:

- ``done``
- ``clarify``
- ``blocked``
- ``unsupported``
- ``continue``
- ``fallback``

Structural invariants encoded here (not as comments):

- ``done`` requires a typed ``TaskOutcome``; no free outcome strings.
- ``clarify`` requires a typed ``ClarificationRequest``; the reason code
  must be non-empty so clarification is auditable.
- ``blocked`` / ``unsupported`` require a non-empty reason code.
- ``continue`` requires a ``WorkItem`` of origin ``CONTINUATION`` with a
  non-exhausted budget and grounded evidence refs.  That is the
  stricter-than-fallback contract stated in ``NORTH_STAR.md``.
- ``fallback`` requires a non-empty reason code but does not carry a
  next work item; the bounded LLM path owns its own scope.

The factories below raise ``DecisionContractError`` on any violation so
the runtime cannot silently emit an ill-shaped decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .task_outcome import ClarificationRequest, TaskOutcome, TaskOutcomeKind
from .work_item import WorkItem, WorkItemOrigin


class DecisionKind(str, Enum):
    """The six valid decisions the public machine may emit."""

    DONE = "done"
    CLARIFY = "clarify"
    BLOCKED = "blocked"
    UNSUPPORTED = "unsupported"
    CONTINUE = "continue"
    FALLBACK = "fallback"


class DecisionContractError(ValueError):
    """Raised when a ``PublicDecision`` would violate its shape invariants."""


@dataclass(frozen=True, slots=True)
class PublicDecision:
    """Single owner of stop / continue / clarify / fallback choices.

    Constructed through the ``decide_*`` factories.  Constructing a
    ``PublicDecision`` directly bypasses invariants; new call sites
    should always go through a factory.
    """

    kind: DecisionKind
    reason_code: str = ""
    outcome: TaskOutcome | None = None
    clarification: ClarificationRequest | None = None
    next_work_item: WorkItem | None = None
    llm_stage: str | None = None
    evidence_refs: tuple[str, ...] = ()

    @property
    def is_terminal(self) -> bool:
        """True when the decision ends the current loop iteration.

        ``continue`` is the only non-terminal kind.  ``fallback`` is
        terminal for the deterministic machine even though the bounded
        LLM path may still run afterward.
        """
        return self.kind is not DecisionKind.CONTINUE


def _require_reason(reason_code: str, *, kind: DecisionKind) -> str:
    value = (reason_code or "").strip()
    if not value:
        raise DecisionContractError(
            f"PublicDecision({kind.value}) requires a non-empty reason_code"
        )
    return value


def _normalize_llm_stage(llm_stage: str | None) -> str | None:
    if llm_stage is None:
        return None
    value = llm_stage.strip()
    return value or None


def decide_done(
    *,
    outcome: TaskOutcome,
    reason_code: str = "",
    llm_stage: str | None = None,
) -> PublicDecision:
    """Emit a ``done`` decision backed by a typed ``TaskOutcome``.

    The outcome kind must not be ``UNKNOWN``; unknown outcomes belong in
    ``decide_fallback`` or ``decide_unsupported`` depending on cause.

    ``llm_stage`` is an optional audit tag identifying a bounded LLM
    path (``mutation_fallback``, ``read_interpretation_<kind>``, ...)
    when the done decision was produced via an LLM-assisted route.  It
    does NOT change the decision kind — mapping to harness outcomes
    still follows ``DecisionKind``.
    """

    if outcome.kind is TaskOutcomeKind.UNKNOWN:
        raise DecisionContractError(
            "PublicDecision(done) requires a classified TaskOutcome "
            "(TaskOutcomeKind.UNKNOWN is not acceptable)"
        )
    resolved_reason = (reason_code or outcome.reason_code or "").strip()
    return PublicDecision(
        kind=DecisionKind.DONE,
        reason_code=resolved_reason,
        outcome=outcome,
        llm_stage=_normalize_llm_stage(llm_stage),
    )


def decide_clarify(
    *,
    clarification: ClarificationRequest,
    llm_stage: str | None = None,
) -> PublicDecision:
    """Emit a ``clarify`` decision backed by a typed clarification."""

    reason = _require_reason(clarification.reason_code, kind=DecisionKind.CLARIFY)
    return PublicDecision(
        kind=DecisionKind.CLARIFY,
        reason_code=reason,
        clarification=clarification,
        llm_stage=_normalize_llm_stage(llm_stage),
    )


def decide_blocked(
    *,
    reason_code: str,
    llm_stage: str | None = None,
) -> PublicDecision:
    """Emit a ``blocked`` decision (security/policy denied continuation)."""

    return PublicDecision(
        kind=DecisionKind.BLOCKED,
        reason_code=_require_reason(reason_code, kind=DecisionKind.BLOCKED),
        llm_stage=_normalize_llm_stage(llm_stage),
    )


def decide_unsupported(
    *,
    reason_code: str,
    llm_stage: str | None = None,
) -> PublicDecision:
    """Emit an ``unsupported`` decision."""

    return PublicDecision(
        kind=DecisionKind.UNSUPPORTED,
        reason_code=_require_reason(reason_code, kind=DecisionKind.UNSUPPORTED),
        llm_stage=_normalize_llm_stage(llm_stage),
    )


def decide_continue(
    *,
    next_work_item: WorkItem,
    reason_code: str = "typed_continuation_emitted",
) -> PublicDecision:
    """Emit a ``continue`` decision carrying the next controlled work item.

    Enforces the stricter-than-fallback contract:

    - ``next_work_item`` must be a ``CONTINUATION`` (not a fresh request).
    - it must carry provenance: ``parent_work_item_id`` non-empty.
    - it must carry grounded evidence: ``evidence_refs`` non-empty.
    - it must still fit its budget: ``is_continuation_ready`` is True.

    Any violation raises ``DecisionContractError`` so the runtime cannot
    downgrade a speculative branch into a fake ``continue``.
    """

    if next_work_item.origin is not WorkItemOrigin.CONTINUATION:
        raise DecisionContractError(
            "PublicDecision(continue) requires a CONTINUATION work item; "
            "fresh REQUEST items must re-enter the loop as new requests"
        )
    if not (next_work_item.parent_work_item_id or "").strip():
        raise DecisionContractError(
            "PublicDecision(continue) requires parent provenance; the "
            "continuation WorkItem has no parent_work_item_id"
        )
    if not next_work_item.evidence_refs or not any(
        (ref or "").strip() for ref in next_work_item.evidence_refs
    ):
        raise DecisionContractError(
            "PublicDecision(continue) requires grounded evidence refs; "
            "refusing to continue on free-form speculation"
        )
    if not next_work_item.is_continuation_ready:
        raise DecisionContractError(
            "PublicDecision(continue) requires an un-exhausted "
            "ContinuationBudget; emit a fallback or blocked decision instead"
        )
    return PublicDecision(
        kind=DecisionKind.CONTINUE,
        reason_code=_require_reason(reason_code, kind=DecisionKind.CONTINUE),
        next_work_item=next_work_item,
    )


def decide_fallback(
    *,
    reason_code: str,
    llm_stage: str,
    evidence_refs: tuple[str, ...] = (),
) -> PublicDecision:
    """Emit a ``fallback`` decision — bounded LLM path did not produce a
    usable typed answer and the deterministic machine has nothing else
    to say.

    **Do not use this to tag successful LLM-assisted paths.** If the
    bounded LLM path produced a usable answer/clarification/block, emit
    the corresponding ``decide_done`` / ``decide_clarify`` /
    ``decide_blocked`` with the optional ``llm_stage`` audit tag.  The
    ``DecisionKind.FALLBACK`` kind maps to ``OUTCOME_ERR_INTERNAL`` in
    the harness — it must stay reserved for *real* fallback cases (LLM
    surrendered, bounded budget exhausted without a typed plan, typed
    shape violation).

    ``llm_stage`` is required so audit can see which bounded LLM path
    hit the wall (``mutation_fallback``, ``finance_lookup_fallback``,
    ``inbox_disclosure``, ...).
    """

    stage = (llm_stage or "").strip()
    if not stage:
        raise DecisionContractError(
            "PublicDecision(fallback) requires a non-empty llm_stage"
        )
    return PublicDecision(
        kind=DecisionKind.FALLBACK,
        reason_code=_require_reason(reason_code, kind=DecisionKind.FALLBACK),
        llm_stage=stage,
        evidence_refs=tuple(ref for ref in evidence_refs if (ref or "").strip()),
    )


__all__ = [
    "DecisionContractError",
    "DecisionKind",
    "PublicDecision",
    "decide_blocked",
    "decide_clarify",
    "decide_continue",
    "decide_done",
    "decide_fallback",
    "decide_unsupported",
]
