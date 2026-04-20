from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from application.contracts import FinanceLookupIntent

from .interpretation_envelope import (
    EMPTY_RESULT,
    InterpretationRequest,
    InterpretationResult,
    KIND_ACCOUNT_LOOKUP,
    KIND_CONTACT_LOOKUP,
    KIND_FINANCE_ANCHOR_RECORD_REF,
    KIND_FINANCE_LOOKUP_FALLBACK,
    KIND_FINANCE_LOOKUP_INTENT,
    KIND_QUEUE_STATE_LOOKUP,
)


@dataclass(frozen=True, slots=True)
class ReadStepInterpretationResult:
    status: Literal["done", "clarify", "blocked"]
    message: str
    reason_code: str
    refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReadStepInterpretationPort:
    resolve_account_lookup: Callable[
        [str, str, Sequence[Mapping[str, object]]],
        ReadStepInterpretationResult | None,
    ] | None = None
    resolve_contact_lookup: Callable[
        [str, str, str, Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]],
        ReadStepInterpretationResult | None,
    ] | None = None
    resolve_queue_state_lookup: Callable[
        [str, Sequence[object], Sequence[str]],
        ReadStepInterpretationResult | None,
    ] | None = None
    derive_finance_lookup_intent: Callable[
        [str, Mapping[str, object], str | None, Mapping[str, object] | None],
        FinanceLookupIntent | None,
    ] | None = None
    resolve_finance_anchor_record_ref: Callable[
        [str, Sequence[object]],
        str | None,
    ] | None = None
    plan_finance_lookup_fallback: Callable[
        [str, Sequence[object], str, str],
        ReadStepInterpretationResult | None,
    ] | None = None


# --- Unified dispatch -----------------------------------------------------------

# Audit stage tags emitted by ``dispatch_read_interpretation``. Kept in sync
# with the existing ``llm_stage`` strings so call-site migration is a pure
# shape change, not an audit-surface change.
_STAGE_TAGS: dict[str, str] = {
    KIND_ACCOUNT_LOOKUP: "read_interpretation_account_lookup",
    KIND_CONTACT_LOOKUP: "read_interpretation_contact_lookup",
    KIND_QUEUE_STATE_LOOKUP: "read_interpretation_queue_state_lookup",
    KIND_FINANCE_LOOKUP_INTENT: "finance_lookup_intent",
    KIND_FINANCE_ANCHOR_RECORD_REF: "finance_anchor_record_ref",
    KIND_FINANCE_LOOKUP_FALLBACK: "finance_lookup_fallback",
}


def dispatch_read_interpretation(
    port: ReadStepInterpretationPort | None,
    request: InterpretationRequest,
) -> InterpretationResult:
    """Route a typed :class:`InterpretationRequest` to the legacy callable.

    Returns :data:`EMPTY_RESULT` (``plan=None``, ``decision=None``) when
    the port is absent, the callable for the requested kind is ``None``,
    or the callable itself returns ``None``. That matches the
    pre-existing silent-None semantics --- downstream callers always
    fall back to the deterministic path on a ``None`` plan.
    """

    if port is None:
        return EMPTY_RESULT
    kind = request.kind
    payload = request.payload
    stage = _STAGE_TAGS.get(kind, kind)

    if kind == KIND_ACCOUNT_LOOKUP:
        fn = port.resolve_account_lookup
        if fn is None:
            return EMPTY_RESULT
        plan = fn(
            str(payload.get("query", "") or ""),
            str(payload.get("output_field", "") or ""),
            payload.get("accounts") or (),
        )
        return _wrap(plan, stage)

    if kind == KIND_CONTACT_LOOKUP:
        fn = port.resolve_contact_lookup
        if fn is None:
            return EMPTY_RESULT
        plan = fn(
            str(payload.get("query", "") or ""),
            str(payload.get("relationship_role", "") or ""),
            str(payload.get("output_field", "") or ""),
            payload.get("accounts") or (),
            payload.get("contacts") or (),
        )
        return _wrap(plan, stage)

    if kind == KIND_QUEUE_STATE_LOOKUP:
        fn = port.resolve_queue_state_lookup
        if fn is None:
            return EMPTY_RESULT
        plan = fn(
            str(payload.get("queue_reference", "") or ""),
            payload.get("queue_states") or (),
            payload.get("document_refs") or (),
        )
        return _wrap(plan, stage)

    if kind == KIND_FINANCE_LOOKUP_INTENT:
        fn = port.derive_finance_lookup_intent
        if fn is None:
            return EMPTY_RESULT
        plan = fn(
            str(payload.get("task_text", "") or ""),
            payload.get("extracted_payload") or {},
            payload.get("translated_text"),
            payload.get("context_payload"),
        )
        return _wrap(plan, stage)

    if kind == KIND_FINANCE_ANCHOR_RECORD_REF:
        fn = port.resolve_finance_anchor_record_ref
        if fn is None:
            return EMPTY_RESULT
        plan = fn(
            str(payload.get("task_text", "") or ""),
            payload.get("candidates") or (),
        )
        return _wrap(plan, stage)

    if kind == KIND_FINANCE_LOOKUP_FALLBACK:
        fn = port.plan_finance_lookup_fallback
        if fn is None:
            return EMPTY_RESULT
        plan = fn(
            str(payload.get("task_text", "") or ""),
            payload.get("finance_records") or (),
            str(payload.get("root_policy", "") or ""),
            str(payload.get("finance_policy", "") or ""),
        )
        return _wrap(plan, stage)

    return EMPTY_RESULT


def _wrap(plan: object | None, stage: str) -> InterpretationResult:
    if plan is None:
        return EMPTY_RESULT
    return InterpretationResult(plan=plan, decision=None, llm_stage=stage)


__all__ = [
    "ReadStepInterpretationPort",
    "ReadStepInterpretationResult",
    "dispatch_read_interpretation",
]
