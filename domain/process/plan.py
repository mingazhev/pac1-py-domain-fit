"""First-class ``Plan`` envelope for the public machine.

Phase 19 of ``NORTH_STAR_PLAN.MD`` lifts interpretation output into a
typed envelope so the second edge of the public machine,
``WorkItem -> Plan``, is held by types.

``NORTH_STAR_GROUNDING.md`` is explicit that interpretation must emit
exactly one of:

- ``ATOMIC_COMMAND``: a single typed deterministic command.
- ``TYPED_PLAN``: a multi-step plan with ordered subcommands, dependency
  bindings, evidence refs, and a remaining continuation budget.
- ``IMMEDIATE_DECISION``: a short-circuit ``PublicDecision`` (e.g.
  ``clarify``, ``blocked``, ``unsupported``) when interpretation can
  itself decide the outcome without execution.

Until this type existed, those three paths were ad hoc returns from
``task_routing/`` internals, so a multi-step plan, an atomic command, and
an immediate decision were all just "whatever interpretation happened to
return".  The ``Plan`` envelope makes the choice explicit and provides
exactly one named seam for emission.

Structural invariants enforced by the factories:

- exactly one variant payload is set; the other two stay ``None``.
- ``ATOMIC_COMMAND`` requires a non-``None`` command payload.
- ``TYPED_PLAN`` requires a multi-step plan with at least two ordered
  subcommand kinds (a one-step "plan" must use the atomic envelope).
- ``TYPED_PLAN`` requires either a positive-budget remaining continuation
  budget *or* no budget at all (a budget at zero is exhausted and must
  flow as a ``fallback`` decision, not as a typed plan).
- ``IMMEDIATE_DECISION`` requires a typed ``PublicDecision``.

The factories raise :class:`PlanContractError` on any violation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .decision import PublicDecision


class PlanKind(str, Enum):
    """The three valid envelope variants interpretation may emit."""

    ATOMIC_COMMAND = "atomic_command"
    TYPED_PLAN = "typed_plan"
    IMMEDIATE_DECISION = "immediate_decision"


class PlanContractError(ValueError):
    """Raised when a ``Plan`` would violate its envelope invariants."""


@dataclass(frozen=True, slots=True)
class Plan:
    """Public-machine envelope for interpretation output.

    Constructed via :func:`plan_atomic`, :func:`plan_typed`, or
    :func:`plan_immediate`.  ``__post_init__`` enforces exactly one
    variant payload so direct construction cannot yield an ill-shaped
    envelope.

    ``atomic_command`` payload is a ``DeterministicExecutionPlan`` (kept
    as ``Any`` here to avoid a domain -> ``task_routing`` import cycle;
    runtime conversion happens in the single named seam in
    ``task_routing/chain.py``).

    ``typed_plan`` payload is a ``TaskDecompositionPlan`` (same reason).

    ``immediate_decision`` payload is a fully typed ``PublicDecision``.
    """

    kind: PlanKind
    atomic_command: Any = None
    typed_plan: Any = None
    immediate_decision: PublicDecision | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PlanKind):
            raise PlanContractError(
                "Plan.kind must be a PlanKind enum value; "
                f"got {type(self.kind).__name__}"
            )
        populated = {
            PlanKind.ATOMIC_COMMAND: self.atomic_command,
            PlanKind.TYPED_PLAN: self.typed_plan,
            PlanKind.IMMEDIATE_DECISION: self.immediate_decision,
        }
        for variant_kind, payload in populated.items():
            if payload is None:
                continue
            if variant_kind is not self.kind:
                raise PlanContractError(
                    f"Plan(kind={self.kind.value}) must not carry "
                    f"{variant_kind.value} payload"
                )
        if populated[self.kind] is None:
            raise PlanContractError(
                f"Plan(kind={self.kind.value}) must carry a non-None "
                f"{self.kind.value} payload"
            )
        if (
            self.kind is PlanKind.IMMEDIATE_DECISION
            and not isinstance(self.immediate_decision, PublicDecision)
        ):
            raise PlanContractError(
                "Plan.immediate_decision must be a PublicDecision; "
                f"got {type(self.immediate_decision).__name__}"
            )

    @property
    def is_immediate(self) -> bool:
        return self.kind is PlanKind.IMMEDIATE_DECISION

    @property
    def is_atomic(self) -> bool:
        return self.kind is PlanKind.ATOMIC_COMMAND

    @property
    def is_typed_plan(self) -> bool:
        return self.kind is PlanKind.TYPED_PLAN


def plan_atomic(*, command: Any) -> Plan:
    """Wrap a single typed deterministic command as a ``Plan``."""

    if command is None:
        raise PlanContractError(
            "Plan(ATOMIC_COMMAND) requires a non-None command payload"
        )
    return Plan(kind=PlanKind.ATOMIC_COMMAND, atomic_command=command)


def plan_typed(*, typed_plan: Any) -> Plan:
    """Wrap a multi-step typed decomposition plan as a ``Plan``.

    Enforces the structural minimum:

    - ``subcommand_kinds`` exists and contains at least two entries (a
      single-step plan must use ``plan_atomic`` instead).
    - if a ``continuation_budget`` is set, it must not already be
      exhausted: an exhausted budget must flow as a ``fallback``
      decision, not as a typed plan.
    """

    if typed_plan is None:
        raise PlanContractError(
            "Plan(TYPED_PLAN) requires a non-None typed plan payload"
        )
    subcommand_kinds = getattr(typed_plan, "subcommand_kinds", None)
    if subcommand_kinds is None:
        raise PlanContractError(
            "Plan(TYPED_PLAN) payload must expose subcommand_kinds"
        )
    if len(subcommand_kinds) < 2:
        raise PlanContractError(
            "Plan(TYPED_PLAN) requires at least two ordered subcommands; "
            "single-step plans must use plan_atomic instead"
        )
    budget = getattr(typed_plan, "continuation_budget", None)
    if budget is not None and getattr(budget, "exhausted", False):
        raise PlanContractError(
            "Plan(TYPED_PLAN) cannot wrap a typed plan whose continuation "
            "budget is already exhausted; emit a fallback decision instead"
        )
    return Plan(kind=PlanKind.TYPED_PLAN, typed_plan=typed_plan)


def plan_immediate(*, decision: PublicDecision) -> Plan:
    """Wrap an interpretation short-circuit ``PublicDecision`` as a ``Plan``."""

    if not isinstance(decision, PublicDecision):
        raise PlanContractError(
            "Plan(IMMEDIATE_DECISION) requires a typed PublicDecision; "
            f"got {type(decision).__name__}"
        )
    return Plan(kind=PlanKind.IMMEDIATE_DECISION, immediate_decision=decision)


__all__ = [
    "Plan",
    "PlanContractError",
    "PlanKind",
    "plan_atomic",
    "plan_immediate",
    "plan_typed",
]
