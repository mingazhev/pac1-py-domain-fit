from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .continuation import ContinuationBudget, SubcommandDependency


@dataclass(frozen=True, slots=True)
class TypedPlanStep:
    command: Any
    task_text: str
    evidence_refs: tuple[str, ...] = ()
    dependency_bindings: tuple[SubcommandDependency, ...] = ()


@dataclass(frozen=True, slots=True)
class TypedStepPlan:
    steps: tuple[TypedPlanStep, ...]
    continuation_budget: ContinuationBudget | None = None
    shared_evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    @property
    def subcommand_kinds(self) -> tuple[str, ...]:
        kinds: list[str] = []
        for step in self.steps:
            kind = str(getattr(step.command, "kind", "") or "").strip()
            if not kind:
                kind = type(step.command).__name__
            kinds.append(kind)
        return tuple(kinds)


__all__ = [
    "TypedPlanStep",
    "TypedStepPlan",
]
