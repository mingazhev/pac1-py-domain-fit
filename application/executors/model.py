from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from domain.process.decision import PublicDecision


@dataclass(slots=True)
class WorkflowExecutorInput:
    """Clean workflow executor input envelope."""

    vm: Any
    log: list[dict[str, str]]
    contract: Any
    observed_secret_values: set[str]
    typed_command: Any | None = None


class WorkflowDecision(str, Enum):
    """Execution-internal decision classification."""

    RESOLVED = "resolved"
    DECLINED = "declined"
    BLOCKED = "blocked"
    CLARIFY = "clarify"


@dataclass(frozen=True, slots=True)
class WorkflowExecutorResult:
    """Result returned by a workflow executor."""

    handled: bool
    decision: WorkflowDecision | None = None
    reason_code: str | None = None
    public_decision: PublicDecision | None = None

    def __post_init__(self) -> None:
        if self.decision is None:
            fallback = (
                WorkflowDecision.RESOLVED if self.handled else WorkflowDecision.DECLINED
            )
            object.__setattr__(self, "decision", fallback)

    @classmethod
    def resolved(
        cls,
        reason_code: str | None = None,
        *,
        public_decision: PublicDecision | None = None,
    ) -> "WorkflowExecutorResult":
        return cls(
            handled=True,
            decision=WorkflowDecision.RESOLVED,
            reason_code=reason_code,
            public_decision=public_decision,
        )

    @classmethod
    def declined(
        cls,
        reason_code: str | None = None,
        *,
        public_decision: PublicDecision | None = None,
    ) -> "WorkflowExecutorResult":
        return cls(
            handled=False,
            decision=WorkflowDecision.DECLINED,
            reason_code=reason_code,
            public_decision=public_decision,
        )

    @classmethod
    def blocked(
        cls,
        reason_code: str | None = None,
        *,
        public_decision: PublicDecision | None = None,
    ) -> "WorkflowExecutorResult":
        return cls(
            handled=True,
            decision=WorkflowDecision.BLOCKED,
            reason_code=reason_code,
            public_decision=public_decision,
        )

    @classmethod
    def clarify(
        cls,
        reason_code: str | None = None,
        *,
        public_decision: PublicDecision | None = None,
    ) -> "WorkflowExecutorResult":
        return cls(
            handled=True,
            decision=WorkflowDecision.CLARIFY,
            reason_code=reason_code,
            public_decision=public_decision,
        )
