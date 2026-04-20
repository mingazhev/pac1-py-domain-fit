from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .interpretation_envelope import (
    EMPTY_RESULT,
    InterpretationRequest,
    InterpretationResult,
    KIND_WORKFLOW_CAST_IDENTITY,
    KIND_WORKFLOW_ENRICH_TYPED_COMMAND,
    KIND_WORKFLOW_FINANCE_SUBSET,
    KIND_WORKFLOW_ROUTE_SUBTASK,
    KIND_WORKFLOW_STAMP_AUTHORIZATION,
    KIND_WORKFLOW_TYPED_INTENT,
)


@dataclass(frozen=True, slots=True)
class WorkflowTypedIntentExtractionResult:
    typed_command: object | None = None
    effective_task_text: str = ""


@dataclass(frozen=True, slots=True)
class WorkflowSubTaskRoutingResult:
    intent: str = ""
    typed_command: object | None = None
    effective_task_text: str = ""


@dataclass(frozen=True, slots=True)
class WorkflowInterpretationPort:
    extract_for_typed_intent: Callable[
        [str, str, frozenset[str], object, str, str],
        WorkflowTypedIntentExtractionResult,
    ] | None = None
    route_sub_task: Callable[
        [str, frozenset[str], object, str],
        WorkflowSubTaskRoutingResult,
    ] | None = None
    select_finance_record_subset: Callable[[str, Sequence[object]], tuple[int, ...]] | None = None
    resolve_cast_identity_subset: Callable[[str, Sequence[object]], object | None] | None = None
    stamp_workflow_authorization: Callable[[object], object] | None = None
    enrich_inbox_typed_command: Callable[[object, str], object] | None = None


# --- Unified dispatch -----------------------------------------------------------

_STAGE_TAGS: dict[str, str] = {
    KIND_WORKFLOW_TYPED_INTENT: "workflow_extract_typed_intent",
    KIND_WORKFLOW_ROUTE_SUBTASK: "workflow_route_sub_task",
    KIND_WORKFLOW_FINANCE_SUBSET: "workflow_select_finance_record_subset",
    KIND_WORKFLOW_CAST_IDENTITY: "workflow_resolve_cast_identity_subset",
    KIND_WORKFLOW_STAMP_AUTHORIZATION: "workflow_stamp_authorization",
    KIND_WORKFLOW_ENRICH_TYPED_COMMAND: "workflow_enrich_typed_command",
}


def dispatch_workflow_interpretation(
    port: WorkflowInterpretationPort | None,
    request: InterpretationRequest,
) -> InterpretationResult:
    """Route a typed :class:`InterpretationRequest` to the legacy callable.

    Mirrors :func:`application.ports.read_interpretation.dispatch_read_interpretation`:
    a ``None`` port, a ``None`` callable field, or a ``None`` callable
    return value all collapse to :data:`EMPTY_RESULT` so callers can
    uniformly fall back to the deterministic path.
    """

    if port is None:
        return EMPTY_RESULT
    kind = request.kind
    payload = request.payload
    stage = _STAGE_TAGS.get(kind, kind)

    if kind == KIND_WORKFLOW_TYPED_INTENT:
        fn = port.extract_for_typed_intent
        if fn is None:
            return EMPTY_RESULT
        plan = fn(
            str(payload.get("source_text", "") or ""),
            str(payload.get("continuation_intent", "") or ""),
            payload.get("supported_intents") or frozenset(),
            payload.get("workspace_policies"),
            str(payload.get("finance_record_index", "") or ""),
            str(payload.get("user_content", "") or ""),
        )
        return _wrap(plan, stage)

    if kind == KIND_WORKFLOW_ROUTE_SUBTASK:
        fn = port.route_sub_task
        if fn is None:
            return EMPTY_RESULT
        plan = fn(
            str(payload.get("sub_task_text", "") or ""),
            payload.get("supported_intents") or frozenset(),
            payload.get("workspace_policies"),
            str(payload.get("finance_record_index", "") or ""),
        )
        return _wrap(plan, stage)

    if kind == KIND_WORKFLOW_FINANCE_SUBSET:
        fn = port.select_finance_record_subset
        if fn is None:
            return EMPTY_RESULT
        plan = fn(
            str(payload.get("instruction", "") or ""),
            payload.get("records") or (),
        )
        return _wrap(plan, stage)

    if kind == KIND_WORKFLOW_CAST_IDENTITY:
        fn = port.resolve_cast_identity_subset
        if fn is None:
            return EMPTY_RESULT
        plan = fn(
            str(payload.get("instruction", "") or ""),
            payload.get("entities") or (),
        )
        return _wrap(plan, stage)

    if kind == KIND_WORKFLOW_STAMP_AUTHORIZATION:
        fn = port.stamp_workflow_authorization
        if fn is None:
            return EMPTY_RESULT
        plan = fn(payload.get("command"))
        return _wrap(plan, stage)

    if kind == KIND_WORKFLOW_ENRICH_TYPED_COMMAND:
        fn = port.enrich_inbox_typed_command
        if fn is None:
            return EMPTY_RESULT
        plan = fn(
            payload.get("command"),
            str(payload.get("task_text", "") or ""),
        )
        return _wrap(plan, stage)

    return EMPTY_RESULT


def _wrap(plan: object | None, stage: str) -> InterpretationResult:
    if plan is None:
        return EMPTY_RESULT
    return InterpretationResult(plan=plan, decision=None, llm_stage=stage)


__all__ = [
    "WorkflowInterpretationPort",
    "WorkflowSubTaskRoutingResult",
    "WorkflowTypedIntentExtractionResult",
    "dispatch_workflow_interpretation",
]
