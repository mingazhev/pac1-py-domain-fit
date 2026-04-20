from __future__ import annotations

from typing import TYPE_CHECKING

from application.queries import (
    resolve_account_lookup_query,
    resolve_contact_lookup_query,
    resolve_queue_state_lookup_query,
)
from application.ports import (
    RecordResolutionPort,
    QueryResolutionPort,
    ReadStepInterpretationPort,
)
from .finance_read_step import execute_finance_lookup_step
from .query_read_step import execute_non_finance_read_step
from .read_result import ReadStepExecutionResult

if TYPE_CHECKING:
    from application.context import RuntimeContext

def execute_read_step(
    command,
    *,
    task_text: str,
    context: RuntimeContext,
    record_resolution_port: RecordResolutionPort | None = None,
    query_resolution_port: QueryResolutionPort | None = None,
    interpretation_port: ReadStepInterpretationPort | None = None,
) -> ReadStepExecutionResult | None:
    kind = _command_kind(command)
    if kind == "finance_lookup":
        return execute_finance_lookup_step(
            command,
            task_text=task_text,
            context=context,
            interpretation_port=interpretation_port,
        )
    return execute_non_finance_read_step(
        command,
        kind=kind,
        task_text=task_text,
        context=context,
        record_resolution_port=record_resolution_port,
        query_resolution_port=query_resolution_port,
        interpretation_port=interpretation_port,
    )


def _command_kind(command: object) -> str:
    return str(getattr(command, "kind", "") or "").strip()


__all__ = [
    "ReadStepExecutionResult",
    "execute_read_step",
]
