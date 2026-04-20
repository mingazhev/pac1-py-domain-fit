from __future__ import annotations

from dataclasses import dataclass

from .deletion_audit import DeletionAudit
from .task_outcome import TaskOutcomeKind
from .wipe_request import WipeRequest


class DomainEvent:
    @property
    def event_type(self) -> str:
        raise NotImplementedError

    def as_payload(self) -> dict[str, object]:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class QueueBatchQueuedEvent(DomainEvent):
    workflow_name: str
    batch_timestamp: str
    target: str
    queued_paths: tuple[str, ...]

    @property
    def event_type(self) -> str:
        return "queue_batch_queued"

    def as_payload(self) -> dict[str, object]:
        return {
            "workflow_name": self.workflow_name,
            "batch_timestamp": self.batch_timestamp,
            "target": self.target,
            "queued_paths": self.queued_paths,
        }


@dataclass(frozen=True, slots=True)
class WorkflowClarificationEvent(DomainEvent):
    workflow_name: str
    reason_code: str
    requested_by_path: str = ""

    @property
    def event_type(self) -> str:
        return "workflow_clarification_requested"

    def as_payload(self) -> dict[str, object]:
        return {
            "workflow_name": self.workflow_name,
            "reason_code": self.reason_code,
            "requested_by_path": self.requested_by_path,
        }


@dataclass(frozen=True, slots=True)
class DeletionAuditRecordedEvent(DomainEvent):
    audit: DeletionAudit

    @property
    def event_type(self) -> str:
        return "deletion_audit_recorded"

    def as_payload(self) -> dict[str, object]:
        return {"audit": self.audit.as_payload()}


@dataclass(frozen=True, slots=True)
class WipeRequestedEvent(DomainEvent):
    request: WipeRequest

    @property
    def event_type(self) -> str:
        return "wipe_requested"

    def as_payload(self) -> dict[str, object]:
        return {"request": self.request.as_payload()}


@dataclass(frozen=True, slots=True)
class OutcomeGateDecidedEvent(DomainEvent):
    """Records a fail-closed outcome-gate decision.

    Emitted when ``assert_outcome_for_mutability`` or
    ``gate_side_effects_against_outcome`` denies an outcome; keeps the
    decision observable for audit without re-deriving it from logs.
    """

    outcome_kind: TaskOutcomeKind
    gate_name: str
    reason_code: str
    allowed: bool = False

    @property
    def event_type(self) -> str:
        return "outcome_gate_decided"

    def as_payload(self) -> dict[str, object]:
        return {
            "outcome_kind": self.outcome_kind.value,
            "gate_name": self.gate_name,
            "reason_code": self.reason_code,
            "allowed": self.allowed,
        }


@dataclass(frozen=True, slots=True)
class SecurityRefusalDecidedEvent(DomainEvent):
    """Surfaces a typed security refusal as an observable domain event."""

    refusal_kind: str
    reason_code: str
    gate: str = ""

    @property
    def event_type(self) -> str:
        return "security_refusal_decided"

    def as_payload(self) -> dict[str, object]:
        return {
            "refusal_kind": self.refusal_kind,
            "reason_code": self.reason_code,
            "gate": self.gate,
        }
