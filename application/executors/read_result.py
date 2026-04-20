from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from application.ports import ReadStepInterpretationResult


@dataclass(frozen=True, slots=True)
class ReadStepExecutionResult:
    status: Literal["done", "clarify", "blocked", "unsupported"]
    message: str
    reason_code: str
    refs: tuple[str, ...] = ()
    llm_stage: str | None = None


def from_status_result(
    result,
    *,
    clarify_reason: str,
    done_reason: str,
) -> ReadStepExecutionResult:
    if result is None:
        return ReadStepExecutionResult(
            status="clarify",
            message="Could not resolve the requested record from canonical data.",
            reason_code=clarify_reason,
        )
    if getattr(result, "status", "") == "clarify_missing":
        return ReadStepExecutionResult(
            status="clarify",
            message=result.message,
            reason_code=clarify_reason,
            refs=getattr(result, "grounding_refs", ()),
        )
    return ReadStepExecutionResult(
        status="done",
        message=result.message,
        reason_code=done_reason,
        refs=getattr(result, "grounding_refs", ()),
    )


def from_interpretation_result(
    result: ReadStepInterpretationResult,
    *,
    llm_stage: str,
) -> ReadStepExecutionResult:
    return ReadStepExecutionResult(
        status=result.status,
        message=result.message,
        reason_code=result.reason_code,
        refs=result.refs,
        llm_stage=llm_stage,
    )


def from_lookup_result(
    result,
    *,
    clarify_message: str,
    clarify_reason: str,
    done_reason: str,
) -> ReadStepExecutionResult:
    if result is None:
        return ReadStepExecutionResult(
            status="clarify",
            message=clarify_message,
            reason_code=clarify_reason,
        )
    return ReadStepExecutionResult(
        status="done",
        message=result.message,
        reason_code=done_reason,
        refs=getattr(result, "grounding_refs", ()),
    )


__all__ = [
    "from_interpretation_result",
    "from_lookup_result",
    "from_status_result",
    "ReadStepExecutionResult",
]
