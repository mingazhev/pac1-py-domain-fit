from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel


ParsedModelT = TypeVar("ParsedModelT", bound=BaseModel)
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]


class StructuredExtractionStatus(str, Enum):
    RESOLVED = "resolved"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    PROVIDER_ERROR = "provider_error"
    EMPTY_RESULT = "empty_result"


@dataclass(frozen=True, slots=True)
class StructuredExtractionResult(Generic[ParsedModelT]):
    status: StructuredExtractionStatus
    parsed: ParsedModelT | None = None
    elapsed_ms: int | None = None
    error: str | None = None
    trace_id: str | None = None


class StructuredExtractionGateway(Protocol):
    def extract(
        self,
        *,
        model: str,
        response_format: type[ParsedModelT],
        messages: list[dict[str, Any]],
        max_completion_tokens: int,
        reasoning_effort: ReasoningEffort | None = None,
        trace_context: Mapping[str, Any] | None = None,
    ) -> StructuredExtractionResult[ParsedModelT]:
        ...
