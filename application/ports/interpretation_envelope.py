"""Unified request/result envelope for interpretation ports.

Phase A2 of the north-star boundary cleanup. The two interpretation
ports --- ``ReadStepInterpretationPort`` and ``WorkflowInterpretationPort``
--- are currently bags of 6+6 callable fields with heterogeneous arities
(3, 4, 5 positional arguments). That shape is not a typed contract; it
is a loose capability bundle, which allows silent fallback when a
caller reads ``port.resolve_X`` and the field happens to be ``None``.

This module introduces a typed envelope that every interpretation
request/result can flow through:

- :class:`InterpretationRequest` --- ``kind`` + opaque ``payload`` +
  optional ``evidence`` refs. The ``kind`` is one of the
  ``KIND_*`` string literals below.
- :class:`InterpretationResult` --- optional typed ``plan`` (domain
  specific: a ``FinanceLookupIntent``, a typed command, a
  ``ReadStepInterpretationResult``, a route decision, an anchor ref,
  ...), optional :class:`PublicDecision` for clarify/blocked/fallback
  short-circuits, and ``llm_stage`` for audit.

The envelope does not replace the existing callable fields on the
ports (keeping call sites stable in A2); it sits *alongside* them and
is wired via thin ``dispatch_*`` adapter functions. Once adapters are
the only call-site shape, the raw callable fields can be collapsed in
a later phase.

The ``kind`` constants are intentionally plain strings, not an
``Enum``. Enum membership is not load-bearing here --- the dispatch
adapters route by equality --- and keeping them as module constants
makes the list trivially extensible as new interpretation surfaces
are added without forcing an ``Enum`` import on every call site.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from domain.process.decision import PublicDecision

# --- Read interpretation kinds -------------------------------------------------

KIND_ACCOUNT_LOOKUP = "account_lookup"
KIND_CONTACT_LOOKUP = "contact_lookup"
KIND_QUEUE_STATE_LOOKUP = "queue_state_lookup"
KIND_FINANCE_LOOKUP_INTENT = "finance_lookup_intent"
KIND_FINANCE_ANCHOR_RECORD_REF = "finance_anchor_record_ref"
KIND_FINANCE_LOOKUP_FALLBACK = "finance_lookup_fallback"

# --- Workflow interpretation kinds ---------------------------------------------

KIND_WORKFLOW_TYPED_INTENT = "workflow_typed_intent"
KIND_WORKFLOW_ROUTE_SUBTASK = "workflow_route_subtask"
KIND_WORKFLOW_FINANCE_SUBSET = "workflow_finance_subset"
KIND_WORKFLOW_CAST_IDENTITY = "workflow_cast_identity"
KIND_WORKFLOW_STAMP_AUTHORIZATION = "workflow_stamp_authorization"
KIND_WORKFLOW_ENRICH_TYPED_COMMAND = "workflow_enrich_typed_command"


READ_INTERPRETATION_KINDS: frozenset[str] = frozenset(
    {
        KIND_ACCOUNT_LOOKUP,
        KIND_CONTACT_LOOKUP,
        KIND_QUEUE_STATE_LOOKUP,
        KIND_FINANCE_LOOKUP_INTENT,
        KIND_FINANCE_ANCHOR_RECORD_REF,
        KIND_FINANCE_LOOKUP_FALLBACK,
    }
)


WORKFLOW_INTERPRETATION_KINDS: frozenset[str] = frozenset(
    {
        KIND_WORKFLOW_TYPED_INTENT,
        KIND_WORKFLOW_ROUTE_SUBTASK,
        KIND_WORKFLOW_FINANCE_SUBSET,
        KIND_WORKFLOW_CAST_IDENTITY,
        KIND_WORKFLOW_STAMP_AUTHORIZATION,
        KIND_WORKFLOW_ENRICH_TYPED_COMMAND,
    }
)


@dataclass(frozen=True, slots=True)
class InterpretationRequest:
    """Typed request envelope passed to an interpretation port adapter.

    ``kind`` identifies the interpretation surface and must be one of
    the ``KIND_*`` constants in this module. ``payload`` carries
    kind-specific inputs (task text, candidate records, etc.) and
    ``evidence`` carries grounding refs when the caller already has
    them.
    """

    kind: str
    payload: Mapping[str, object]
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InterpretationResult:
    """Typed result envelope returned by an interpretation port adapter.

    ``plan`` is the kind-specific typed output (e.g. a
    ``FinanceLookupIntent``, a typed command, a
    ``ReadStepInterpretationResult``, an anchor ref string, a
    ``WorkflowSubTaskRoutingResult`` ...). ``decision`` is a ready-made
    :class:`PublicDecision` when the LLM short-circuited (currently
    unused by A2 adapters but reserved for later phases). ``llm_stage``
    is the audit tag attached to the ``PublicDecision`` (e.g.
    ``read_interpretation_account_lookup``,
    ``finance_lookup_fallback``).
    """

    plan: object | None = None
    decision: PublicDecision | None = None
    llm_stage: str = ""
    evidence: tuple[str, ...] = field(default=())


EMPTY_RESULT: InterpretationResult = InterpretationResult()


__all__ = [
    "EMPTY_RESULT",
    "InterpretationRequest",
    "InterpretationResult",
    "KIND_ACCOUNT_LOOKUP",
    "KIND_CONTACT_LOOKUP",
    "KIND_FINANCE_ANCHOR_RECORD_REF",
    "KIND_FINANCE_LOOKUP_FALLBACK",
    "KIND_FINANCE_LOOKUP_INTENT",
    "KIND_QUEUE_STATE_LOOKUP",
    "KIND_WORKFLOW_CAST_IDENTITY",
    "KIND_WORKFLOW_ENRICH_TYPED_COMMAND",
    "KIND_WORKFLOW_FINANCE_SUBSET",
    "KIND_WORKFLOW_ROUTE_SUBTASK",
    "KIND_WORKFLOW_STAMP_AUTHORIZATION",
    "KIND_WORKFLOW_TYPED_INTENT",
    "READ_INTERPRETATION_KINDS",
    "WORKFLOW_INTERPRETATION_KINDS",
]
