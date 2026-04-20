"""Multi-file write transaction surface.

Capture, distill, thread, and memory writes often happen as a single logical
action across multiple files. If any step fails after earlier steps have
already committed, the remaining work cannot be silently abandoned: either
the earlier writes must be rolled back, or the partial commit must be
surfaced so the caller can decide.

This module provides a typed envelope that records planned steps and their
outcomes, plus a fail-closed gate that rejects partial commits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MultiFileStepStatus(str, Enum):
    PENDING = "pending"
    COMMITTED = "committed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MultiFileWriteStep:
    path: str
    kind: str
    status: MultiFileStepStatus = MultiFileStepStatus.PENDING


@dataclass(frozen=True, slots=True)
class MultiFileWriteTransaction:
    transaction_id: str
    steps: tuple[MultiFileWriteStep, ...] = field(default_factory=tuple)

    @property
    def committed_steps(self) -> tuple[MultiFileWriteStep, ...]:
        return tuple(step for step in self.steps if step.status is MultiFileStepStatus.COMMITTED)

    @property
    def failed_steps(self) -> tuple[MultiFileWriteStep, ...]:
        return tuple(step for step in self.steps if step.status is MultiFileStepStatus.FAILED)

    @property
    def pending_steps(self) -> tuple[MultiFileWriteStep, ...]:
        return tuple(step for step in self.steps if step.status is MultiFileStepStatus.PENDING)

    def with_step_status(
        self, path: str, status: MultiFileStepStatus
    ) -> "MultiFileWriteTransaction":
        updated = tuple(
            MultiFileWriteStep(path=step.path, kind=step.kind, status=status)
            if step.path == path
            else step
            for step in self.steps
        )
        return MultiFileWriteTransaction(transaction_id=self.transaction_id, steps=updated)


@dataclass(frozen=True, slots=True)
class TransactionGateDecision:
    allowed: bool
    rollback_required: bool
    reason_code: str = ""
    failed_paths: tuple[str, ...] = ()
    committed_paths: tuple[str, ...] = ()


def gate_multi_file_transaction(
    transaction: MultiFileWriteTransaction,
) -> TransactionGateDecision:
    """Decide the outcome of a multi-file transaction.

    - All steps committed: allowed, no rollback.
    - No steps attempted or all still pending: allowed only if no steps have
      failed; pending-only transactions are treated as not-yet-started.
    - Any step failed while others committed: rollback required with
      ``partial_multi_file_commit``.
    - Any step failed with no commits: rollback not required but the
      transaction is refused with ``multi_file_transaction_failed``.
    """
    failed = transaction.failed_steps
    committed = transaction.committed_steps
    failed_paths = tuple(step.path for step in failed)
    committed_paths = tuple(step.path for step in committed)

    if failed and committed:
        return TransactionGateDecision(
            allowed=False,
            rollback_required=True,
            reason_code="partial_multi_file_commit",
            failed_paths=failed_paths,
            committed_paths=committed_paths,
        )
    if failed:
        return TransactionGateDecision(
            allowed=False,
            rollback_required=False,
            reason_code="multi_file_transaction_failed",
            failed_paths=failed_paths,
            committed_paths=committed_paths,
        )
    return TransactionGateDecision(
        allowed=True,
        rollback_required=False,
        committed_paths=committed_paths,
    )


__all__ = [
    "MultiFileStepStatus",
    "MultiFileWriteStep",
    "MultiFileWriteTransaction",
    "TransactionGateDecision",
    "gate_multi_file_transaction",
]
