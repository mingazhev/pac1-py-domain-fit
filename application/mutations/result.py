from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class MutationStepResult:
    status: Literal["resolved", "clarify_missing", "blocked", "unsupported"]
    message: str
    grounding_refs: tuple[str, ...]
    reason_code: str


__all__ = ["MutationStepResult"]
