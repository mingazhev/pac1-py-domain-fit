from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.context import RuntimeContext
    from application.workflows.continuation_common import ContinuationExecutionResult
    from domain.process.continuation import ContinuationBudget


@dataclass(frozen=True, slots=True)
class TypedStepExecutionPort:
    execute: Callable[
        [object, str, "RuntimeContext", "ContinuationBudget | None", object | None],
        "ContinuationExecutionResult",
    ]


__all__ = ["TypedStepExecutionPort"]
