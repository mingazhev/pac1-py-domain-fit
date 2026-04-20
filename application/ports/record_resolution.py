from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class RecordResolutionResult:
    status: Literal["resolved", "clarify_multiple", "clarify_none"]
    candidate: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class RecordResolutionPort:
    resolve_account_candidate: Callable[
        [Sequence[Mapping[str, Any]], str, Sequence[str]],
        RecordResolutionResult,
    ] | None = None
    resolve_contact_candidate: Callable[
        [Sequence[Mapping[str, Any]], str, Sequence[str]],
        RecordResolutionResult,
    ] | None = None


__all__ = ["RecordResolutionPort", "RecordResolutionResult"]
