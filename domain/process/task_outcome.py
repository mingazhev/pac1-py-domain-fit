from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TaskOutcomeKind(str, Enum):
    FACTUAL_ANSWER = "factual_answer"
    QUERY_ANSWERED = "query_answered"
    REPORT_GENERATED = "report_generated"
    DELEGATION_CREATED = "delegation_created"
    MUTATION_COMPLETED = "mutation_completed"
    CLARIFICATION_REQUESTED = "clarification_requested"
    SECURITY_VIOLATION = "security_violation"
    INTERNAL_ERROR = "internal_error"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TaskOutcome:
    kind: TaskOutcomeKind
    outcome_name: str
    reason_code: str = ""


@dataclass(frozen=True, slots=True)
class ClarificationRequest:
    reason_code: str
    message: str = ""

    @property
    def kind(self) -> TaskOutcomeKind:
        return TaskOutcomeKind.CLARIFICATION_REQUESTED


@dataclass(frozen=True, slots=True)
class SecurityViolationEvent:
    reason_code: str
    message: str = ""
    gate: str = ""

    @property
    def kind(self) -> TaskOutcomeKind:
        return TaskOutcomeKind.SECURITY_VIOLATION
