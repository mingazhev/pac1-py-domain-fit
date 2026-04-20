"""Controlled-continuation primitives for the public machine.

These types are pure domain concepts:

- ``ContinuationBudget`` bounds recursive continuation of a controlled
  work item so an agent loop cannot spiral into unbounded planner work.
- ``NextTypedStep`` + ``NextStepEvidenceSource`` express a continuation
  as a typed next subcommand grounded in explicit workspace evidence.
- ``SubcommandDependency`` + ``DependencyBindingKind`` wire output of
  one typed step into the input of a later one.

Phase 16A moves these primitives from ``task_routing.decomposition`` into
the domain layer so ``domain.process.work_item`` can depend on them
without crossing the application/routing boundary.  ``task_routing``
re-exports them for existing call sites, so nothing outside this package
needs to change its import path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DependencyBindingKind(str, Enum):
    """How a later subcommand consumes an earlier subcommand's output."""

    EQUAL = "equal"
    INCLUDES = "includes"
    GUARD = "guard"


class NextStepEvidenceSource(str, Enum):
    """Allowed evidence categories for emitting a next typed step.

    USER_REQUEST
        The continuation is grounded in the original user request text.

    WORKSPACE_RECORD
        The continuation is grounded in a canonical workspace record
        (cast, project, finance note, accounts file, etc.).

    GROUNDED_INBOX_ITEM
        The continuation is grounded in the body of a trusted inbox
        item that has already passed preflight gating.

    Free-form model speculation is intentionally absent.  Attempts to
    build a next typed step without one of these sources must raise
    ``NextStepEvidenceError``.
    """

    USER_REQUEST = "user_request"
    WORKSPACE_RECORD = "workspace_record"
    GROUNDED_INBOX_ITEM = "grounded_inbox_item"


class NextStepEvidenceError(ValueError):
    """Raised when a next typed step is built without grounded evidence."""


class DependencyBindingError(ValueError):
    """Raised when a typed dependency binding is structurally invalid."""


class ContinuationBudgetError(ValueError):
    """Raised when a continuation budget is exhausted or mis-shaped."""


DEFAULT_CONTINUATION_MAX_DEPTH = 2
DEFAULT_CONTINUATION_MAX_STEPS = 2


@dataclass(frozen=True, slots=True)
class SubcommandDependency:
    """Typed binding: subcommand at ``source_step_index`` feeds a later step.

    ``source_field`` names the field in the source subcommand's result
    payload; ``target_field`` names the field in the consuming
    subcommand's request payload that must be populated from it.

    Dependencies may only point backward (lower step index).  Forward
    bindings are rejected at validation time.
    """

    source_step_index: int
    source_field: str
    target_field: str
    kind: DependencyBindingKind = DependencyBindingKind.EQUAL


def validate_subcommand_dependency(
    dependency: SubcommandDependency,
    *,
    plan_length: int,
    target_step_index: int,
) -> None:
    """Raise ``DependencyBindingError`` if the binding is not structurally valid.

    Rules:
    - ``source_step_index`` must be >= 0 and < plan_length.
    - ``source_step_index`` must be strictly less than ``target_step_index``
      (dependencies point backward only).
    - ``source_field`` and ``target_field`` must both be non-empty after strip.
    """

    if dependency.source_step_index < 0:
        raise DependencyBindingError(
            "SubcommandDependency.source_step_index must be non-negative"
        )
    if dependency.source_step_index >= plan_length:
        raise DependencyBindingError(
            "SubcommandDependency.source_step_index is out of range for plan"
        )
    if dependency.source_step_index >= target_step_index:
        raise DependencyBindingError(
            "SubcommandDependency must bind from a strictly earlier step"
        )
    if not dependency.source_field or not dependency.source_field.strip():
        raise DependencyBindingError(
            "SubcommandDependency.source_field must be non-empty"
        )
    if not dependency.target_field or not dependency.target_field.strip():
        raise DependencyBindingError(
            "SubcommandDependency.target_field must be non-empty"
        )


@dataclass(frozen=True, slots=True)
class ContinuationBudget:
    """Recursion budget for controlled continuation.

    ``max_depth``
        Maximum parent-chain length allowed for continuation.  A work
        item with ``current_depth >= max_depth`` cannot spawn another
        continuation.

    ``max_steps``
        Total allowed subcommand count across the continuation chain.

    ``current_depth``
        How many parents this work item already sits under.

    ``remaining_steps``
        Subcommand budget remaining for the continuation chain.
    """

    max_depth: int
    max_steps: int
    current_depth: int = 0
    remaining_steps: int = 0

    @staticmethod
    def initial(max_depth: int, max_steps: int) -> "ContinuationBudget":
        if max_depth < 0:
            raise ContinuationBudgetError("max_depth must be non-negative")
        if max_steps <= 0:
            raise ContinuationBudgetError("max_steps must be positive")
        return ContinuationBudget(
            max_depth=max_depth,
            max_steps=max_steps,
            current_depth=0,
            remaining_steps=max_steps,
        )

    @property
    def exhausted(self) -> bool:
        return self.remaining_steps <= 0 or self.current_depth >= self.max_depth

    def consume(self, steps: int = 1) -> "ContinuationBudget":
        if steps < 0:
            raise ContinuationBudgetError("consume(steps) must be non-negative")
        return ContinuationBudget(
            max_depth=self.max_depth,
            max_steps=self.max_steps,
            current_depth=self.current_depth,
            remaining_steps=max(0, self.remaining_steps - steps),
        )

    def descend(self) -> "ContinuationBudget":
        if self.current_depth + 1 > self.max_depth:
            raise ContinuationBudgetError(
                "ContinuationBudget.descend would exceed max_depth"
            )
        return ContinuationBudget(
            max_depth=self.max_depth,
            max_steps=self.max_steps,
            current_depth=self.current_depth + 1,
            remaining_steps=self.remaining_steps,
        )


def default_continuation_budget() -> "ContinuationBudget":
    """Single source of truth for controlled continuation defaults.

    The default must leave a freshly emitted continuation executable.
    ``(1, 1)`` is structurally wrong for the public machine because the child
    becomes exhausted immediately after ``descend().consume(1)`` and therefore
    cannot legally flow through ``decide_continue``.
    """

    return ContinuationBudget.initial(
        max_depth=DEFAULT_CONTINUATION_MAX_DEPTH,
        max_steps=DEFAULT_CONTINUATION_MAX_STEPS,
    )


@dataclass(frozen=True, slots=True)
class NextTypedStep:
    """Explicit continuation: one more typed subcommand with grounded evidence.

    ``executor_kind``
        ``DeterministicExecutorKind.value`` for the continuation step.

    ``payload``
        Command payload for the continuation subcommand.

    ``evidence_source``
        Which grounded category justifies the continuation.

    ``evidence_refs``
        Concrete refs (workspace paths, inbox item ids, etc.) that back
        the continuation.  Must be non-empty.  This is the structural
        guard against free-form model speculation becoming a new step.

    ``dependency_bindings``
        Optional typed bindings that let this continuation consume the
        output of earlier steps in the parent plan.
    """

    executor_kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    evidence_source: NextStepEvidenceSource = NextStepEvidenceSource.USER_REQUEST
    evidence_refs: tuple[str, ...] = ()
    dependency_bindings: tuple[SubcommandDependency, ...] = ()


def emit_next_typed_step(
    *,
    executor_kind: str,
    payload: dict[str, Any] | None,
    evidence_source: NextStepEvidenceSource | str,
    evidence_refs: tuple[str, ...] | list[str] | None,
    dependency_bindings: tuple[SubcommandDependency, ...] | None = None,
) -> NextTypedStep:
    """Build a ``NextTypedStep`` while enforcing the evidence contract.

    Rejects (via ``NextStepEvidenceError``):
    - empty executor_kind
    - evidence_source that is not in ``NextStepEvidenceSource``
    - empty evidence_refs (the structural guard against free-form
      continuation)
    """

    executor = (executor_kind or "").strip()
    if not executor:
        raise NextStepEvidenceError(
            "NextTypedStep.executor_kind must be a non-empty string"
        )

    if isinstance(evidence_source, NextStepEvidenceSource):
        source = evidence_source
    else:
        source_value = (evidence_source or "").strip()
        try:
            source = NextStepEvidenceSource(source_value)
        except ValueError as exc:
            raise NextStepEvidenceError(
                "NextTypedStep.evidence_source must be one of "
                f"{[s.value for s in NextStepEvidenceSource]}"
            ) from exc

    refs = tuple(
        str(ref).strip() for ref in (evidence_refs or ()) if str(ref or "").strip()
    )
    if not refs:
        raise NextStepEvidenceError(
            "NextTypedStep requires at least one grounded evidence ref. "
            "Free-form model speculation is not a valid continuation source."
        )

    return NextTypedStep(
        executor_kind=executor,
        payload=dict(payload or {}),
        evidence_source=source,
        evidence_refs=refs,
        dependency_bindings=tuple(dependency_bindings or ()),
    )


__all__ = [
    "ContinuationBudget",
    "ContinuationBudgetError",
    "DEFAULT_CONTINUATION_MAX_DEPTH",
    "DEFAULT_CONTINUATION_MAX_STEPS",
    "DependencyBindingError",
    "DependencyBindingKind",
    "NextStepEvidenceError",
    "NextStepEvidenceSource",
    "NextTypedStep",
    "SubcommandDependency",
    "default_continuation_budget",
    "emit_next_typed_step",
    "validate_subcommand_dependency",
]
