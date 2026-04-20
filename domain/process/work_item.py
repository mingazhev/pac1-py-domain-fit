"""First-class ``WorkItem`` contract for the public machine.

Phase 16A promotes ``Request -> WorkItem -> Plan -> Decision`` from prose in
``NORTH_STAR.md`` and ``docs/RUNTIME_PIPELINE.md`` into real types.

A ``WorkItem`` is the controlled unit that enters or re-enters the runtime
loop.  Two origins are valid:

- ``REQUEST``: a fresh external ask.  Carries no parent, depth zero, no
  continuation budget, and may start with empty evidence refs.
- ``CONTINUATION``: a typed next step derived from a completed parent work
  item.  Must carry a parent id, non-zero depth, non-empty evidence refs
  (the structural guard against free-form model speculation becoming a
  new work item), and an un-exhausted ``ContinuationBudget``.

The continuation shape reuses the building blocks already owned by
``task_routing.decomposition`` (``NextTypedStep``, ``ContinuationBudget``,
``SubcommandDependency``).  This module does not re-implement them; it
lifts them into a domain-layer public contract so runtime helpers can
reason about work items without importing routing internals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .continuation import (
    ContinuationBudget,
    ContinuationBudgetError,
    NextTypedStep,
    SubcommandDependency,
)
from .request import Request


class WorkItemOrigin(str, Enum):
    """Why a work item exists.

    REQUEST
        The item was derived directly from the original external ask.
        Depth is zero, no parent, no budget required.

    CONTINUATION
        The item was emitted as a typed next step from a previous work
        item's ``Decision``.  Depth is strictly positive, must carry
        parent provenance, and must stay inside its ``ContinuationBudget``.
    """

    REQUEST = "request"
    CONTINUATION = "continuation"


class WorkItemContractError(ValueError):
    """Raised when a ``WorkItem`` violates its origin invariants."""


@dataclass(frozen=True, slots=True)
class WorkItem:
    """Controlled unit entering or re-entering the public-machine loop.

    ``identifier``
        Stable id for trace/provenance joining.

    ``origin``
        ``REQUEST`` for fresh asks; ``CONTINUATION`` for typed next steps.

    ``goal``
        Human-readable intent text.  For a ``REQUEST`` this is the raw
        task text; for a ``CONTINUATION`` it is the executor kind of the
        emitted next step (or an equivalent typed summary).

    ``evidence_refs``
        Grounded refs (workspace paths, inbox ids, etc.) that back the
        item.  Must be non-empty for continuations.  May be empty for
        a fresh request since evidence is gathered during interpretation.

    ``parent_work_item_id``
        Provenance link to the parent work item.  Must be non-empty for
        continuations and ``None`` for fresh requests.

    ``depth``
        Number of parents this item sits under.  Zero for requests,
        strictly positive for continuations.

    ``budget``
        Remaining recursion budget.  Required for continuations; absent
        for requests (which start a fresh chain on demand).

    ``dependency_bindings``
        Typed bindings consumed by the eventual plan.  Defaults empty.

    ``continuation_source``
        The typed ``NextTypedStep`` that produced this work item, if any.
        Preserved so the plan interpreter can re-consume the evidence
        contract and dependency wiring.
    """

    identifier: str
    origin: WorkItemOrigin
    goal: str
    evidence_refs: tuple[str, ...] = ()
    parent_work_item_id: str | None = None
    depth: int = 0
    budget: ContinuationBudget | None = None
    dependency_bindings: tuple[SubcommandDependency, ...] = field(default_factory=tuple)
    continuation_source: NextTypedStep | None = None

    @property
    def is_continuation(self) -> bool:
        return self.origin is WorkItemOrigin.CONTINUATION

    @property
    def is_continuation_ready(self) -> bool:
        """True when a continuation work item can still enter execution.

        Fresh requests always return True.  Continuations require a
        non-exhausted budget.
        """
        if self.origin is WorkItemOrigin.REQUEST:
            return True
        if self.budget is None:
            return False
        return not self.budget.exhausted


def _validate_identifier(identifier: str, *, field_name: str) -> str:
    value = (identifier or "").strip()
    if not value:
        raise WorkItemContractError(f"WorkItem.{field_name} must be non-empty")
    return value


def new_request_work_item(
    *,
    request: Request,
    evidence_refs: tuple[str, ...] | list[str] | None = None,
) -> WorkItem:
    """Build a fresh ``REQUEST`` work item from a typed ``Request``.

    Phase 18 (``NORTH_STAR_PLAN.MD``) makes ``Request`` the first node of
    the public machine: ``Request -> WorkItem -> Plan -> Decision``.  The
    REQUEST factory accepts only a typed ``Request`` so the first edge
    is held by the type system, not by convention.

    ``evidence_refs`` defaults to the request's own ``envelope_refs`` (so
    an inbox pickup's envelope provenance propagates into the initial
    work item).  Callers with a better-scoped refs set can override.
    """

    if not isinstance(request, Request):
        raise WorkItemContractError(
            "new_request_work_item requires a typed Request instance; "
            f"got {type(request).__name__}"
        )
    ident = _validate_identifier(request.identifier, field_name="identifier")
    goal = (request.task_text or "").strip()
    if not goal:
        raise WorkItemContractError(
            "WorkItem(origin=REQUEST) must carry a non-empty goal/task_text"
        )
    caller_refs = tuple(
        str(ref).strip()
        for ref in (evidence_refs or ())
        if str(ref or "").strip()
    )
    refs = caller_refs if caller_refs else tuple(request.envelope_refs)
    return WorkItem(
        identifier=ident,
        origin=WorkItemOrigin.REQUEST,
        goal=goal,
        evidence_refs=refs,
        parent_work_item_id=None,
        depth=0,
        budget=None,
        dependency_bindings=(),
        continuation_source=None,
    )


def continuation_work_item(
    *,
    identifier: str,
    parent: WorkItem,
    next_step: NextTypedStep,
    parent_budget: ContinuationBudget,
) -> WorkItem:
    """Build a ``CONTINUATION`` work item from a parent and a typed next step.

    Invariants enforced structurally (not via comment):

    - the parent budget must not be exhausted; descent+consume is
      performed here so the child carries the correctly decremented
      ``ContinuationBudget``.
    - when the parent is itself a ``CONTINUATION``, the caller-supplied
      ``parent_budget`` must match ``parent.budget`` exactly; a forged
      or fresh budget cannot revive an existing continuation chain past
      its depth/step limits.
    - the next step carries at least one grounded evidence ref after
      stripping whitespace (``emit_next_typed_step`` already enforces
      this upstream; we re-check here so a malformed ``NextTypedStep``
      cannot slip through a different construction path).
    - the resulting work item has a non-empty parent id and depth > 0.

    Raises:
        WorkItemContractError: when the parent/next_step shape is invalid.
        ContinuationBudgetError: when the parent budget is already
            exhausted.  Callers must branch to a ``fallback`` or
            ``blocked`` decision in that case.
    """

    ident = _validate_identifier(identifier, field_name="identifier")
    parent_identifier = (parent.identifier or "").strip()
    if not parent_identifier:
        raise WorkItemContractError(
            "Continuation WorkItem requires a parent with a non-empty identifier"
        )
    grounded_refs = tuple(
        str(ref).strip()
        for ref in (next_step.evidence_refs or ())
        if str(ref or "").strip()
    )
    if not grounded_refs:
        raise WorkItemContractError(
            "Continuation WorkItem requires a NextTypedStep with grounded "
            "evidence refs; refusing to continue on free-form speculation"
        )
    if parent.origin is WorkItemOrigin.CONTINUATION and parent_budget != parent.budget:
        raise WorkItemContractError(
            "Continuation WorkItem cannot be built with a parent_budget "
            "that does not match the parent's own ContinuationBudget; "
            "refusing to revive an existing continuation chain with a "
            "forged budget"
        )
    if parent_budget.exhausted:
        raise ContinuationBudgetError(
            "Cannot build continuation WorkItem: parent ContinuationBudget exhausted"
        )

    descended = parent_budget.descend().consume(1)
    goal = (next_step.executor_kind or "").strip() or "continuation_step"
    return WorkItem(
        identifier=ident,
        origin=WorkItemOrigin.CONTINUATION,
        goal=goal,
        evidence_refs=grounded_refs,
        parent_work_item_id=parent_identifier,
        depth=parent.depth + 1,
        budget=descended,
        dependency_bindings=tuple(next_step.dependency_bindings),
        continuation_source=next_step,
    )


__all__ = [
    "WorkItem",
    "WorkItemContractError",
    "WorkItemOrigin",
    "continuation_work_item",
    "new_request_work_item",
]
