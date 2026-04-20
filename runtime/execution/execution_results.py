from __future__ import annotations

from dataclasses import dataclass

from domain.process import (
    ClarificationRequest,
    PublicDecision,
    decide_blocked,
    decide_clarify,
    decide_done,
    decide_unsupported,
)
from task_routing.outcome_classifier import classify_task_outcome


@dataclass(frozen=True, slots=True)
class DeterministicExecutionResult:
    decision: PublicDecision
    message: str
    refs: tuple[str, ...] = ()


def from_read_execution_result(result) -> DeterministicExecutionResult:
    llm_stage = getattr(result, "llm_stage", None) or None
    if result.status == "done":
        return done(
            result.message, result.refs, result.reason_code, llm_stage=llm_stage
        )
    if result.status == "clarify":
        return clarify(
            result.message,
            reason_code=result.reason_code,
            refs=result.refs,
            llm_stage=llm_stage,
        )
    if result.status == "blocked":
        return DeterministicExecutionResult(
            decision=decide_blocked(
                reason_code=result.reason_code, llm_stage=llm_stage
            ),
            message=result.message,
            refs=result.refs,
        )
    return DeterministicExecutionResult(
        decision=decide_unsupported(
            reason_code=result.reason_code, llm_stage=llm_stage
        ),
        message=result.message,
        refs=result.refs,
    )


def done(
    message: str,
    refs: tuple[str, ...],
    reason_code: str,
    *,
    llm_stage: str | None = None,
) -> DeterministicExecutionResult:
    outcome = classify_task_outcome("OUTCOME_OK", reason_code=reason_code)
    return DeterministicExecutionResult(
        decision=decide_done(
            outcome=outcome, reason_code=reason_code, llm_stage=llm_stage
        ),
        message=message,
        refs=refs,
    )


def clarify(
    message: str,
    *,
    reason_code: str,
    refs: tuple[str, ...] = (),
    llm_stage: str | None = None,
) -> DeterministicExecutionResult:
    return DeterministicExecutionResult(
        decision=decide_clarify(
            clarification=ClarificationRequest(
                reason_code=reason_code,
                message=message,
            ),
            llm_stage=llm_stage,
        ),
        message=message,
        refs=refs,
    )


__all__ = [
    "DeterministicExecutionResult",
    "clarify",
    "done",
    "from_read_execution_result",
]
