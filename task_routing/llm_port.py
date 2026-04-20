"""Typed facade over ``StructuredExtractionGateway``.

Today every LLM call-site duplicates the same pattern: call
``gateway.extract(...)``, emit an ``emit_llm_trace`` for the same
``(role, stage, model, response_format, result)`` tuple, then gate
on ``status is RESOLVED`` and ``isinstance(parsed, response_format)``.
The four semantically distinct intents — ``classify``, ``extract_typed``,
``select_from_set``, ``plan`` — all funnel through that same pattern.

``LlmPort`` names the intent at the call-site (method name) and owns the
trace + status + isinstance boilerplate. It's a thin adapter over the
existing gateway; no transport logic lives here.
"""
from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from telemetry.trace import emit_llm_trace

from .gateway import (
    ReasoningEffort,
    StructuredExtractionGateway,
    StructuredExtractionResult,
    StructuredExtractionStatus,
)


T = TypeVar("T", bound=BaseModel)


class LlmPort(Protocol):
    def classify(
        self,
        *,
        stage: str,
        response_format: type[T],
        messages: list[dict[str, Any]],
        max_completion_tokens: int,
        role: str = "core",
        reasoning_effort: ReasoningEffort | None = None,
        intent: str | None = None,
        trace_context_extra: dict[str, Any] | None = None,
    ) -> T | None: ...

    def extract_typed(
        self,
        *,
        stage: str,
        response_format: type[T],
        messages: list[dict[str, Any]],
        max_completion_tokens: int,
        role: str = "core",
        reasoning_effort: ReasoningEffort | None = None,
        intent: str | None = None,
        trace_context_extra: dict[str, Any] | None = None,
    ) -> T | None: ...

    def select_from_set(
        self,
        *,
        stage: str,
        response_format: type[T],
        messages: list[dict[str, Any]],
        max_completion_tokens: int,
        role: str = "core",
        reasoning_effort: ReasoningEffort | None = None,
        intent: str | None = None,
        trace_context_extra: dict[str, Any] | None = None,
    ) -> T | None: ...

    def plan(
        self,
        *,
        stage: str,
        response_format: type[T],
        messages: list[dict[str, Any]],
        max_completion_tokens: int,
        role: str = "core",
        reasoning_effort: ReasoningEffort | None = None,
        intent: str | None = None,
        trace_context_extra: dict[str, Any] | None = None,
    ) -> T | None: ...

    # Escape hatch: callers needing custom trace/retry semantics use this.
    def run_raw(
        self,
        *,
        stage: str,
        response_format: type[T],
        messages: list[dict[str, Any]],
        max_completion_tokens: int,
        role: str,
        reasoning_effort: ReasoningEffort | None = None,
        trace_context_extra: dict[str, Any] | None = None,
    ) -> StructuredExtractionResult[T]: ...


class GatewayBackedLlmPort:
    """``LlmPort`` implementation backed by a ``StructuredExtractionGateway``.

    The four typed methods are semantic aliases over a single private
    helper; they exist so call-sites name their intent.
    """

    def __init__(
        self,
        gateway: StructuredExtractionGateway,
        model: str,
    ) -> None:
        self._gateway = gateway
        self._model = model

    @property
    def gateway(self) -> StructuredExtractionGateway:
        return self._gateway

    @property
    def model(self) -> str:
        return self._model

    def classify(
        self,
        *,
        stage: str,
        response_format: type[T],
        messages: list[dict[str, Any]],
        max_completion_tokens: int,
        role: str = "core",
        reasoning_effort: ReasoningEffort | None = None,
        intent: str | None = None,
        trace_context_extra: dict[str, Any] | None = None,
    ) -> T | None:
        return self._run_typed(
            stage=stage,
            response_format=response_format,
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            role=role,
            reasoning_effort=reasoning_effort,
            intent=intent,
            trace_context_extra=trace_context_extra,
        )

    def extract_typed(
        self,
        *,
        stage: str,
        response_format: type[T],
        messages: list[dict[str, Any]],
        max_completion_tokens: int,
        role: str = "core",
        reasoning_effort: ReasoningEffort | None = None,
        intent: str | None = None,
        trace_context_extra: dict[str, Any] | None = None,
    ) -> T | None:
        return self._run_typed(
            stage=stage,
            response_format=response_format,
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            role=role,
            reasoning_effort=reasoning_effort,
            intent=intent,
            trace_context_extra=trace_context_extra,
        )

    def select_from_set(
        self,
        *,
        stage: str,
        response_format: type[T],
        messages: list[dict[str, Any]],
        max_completion_tokens: int,
        role: str = "core",
        reasoning_effort: ReasoningEffort | None = None,
        intent: str | None = None,
        trace_context_extra: dict[str, Any] | None = None,
    ) -> T | None:
        return self._run_typed(
            stage=stage,
            response_format=response_format,
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            role=role,
            reasoning_effort=reasoning_effort,
            intent=intent,
            trace_context_extra=trace_context_extra,
        )

    def plan(
        self,
        *,
        stage: str,
        response_format: type[T],
        messages: list[dict[str, Any]],
        max_completion_tokens: int,
        role: str = "core",
        reasoning_effort: ReasoningEffort | None = None,
        intent: str | None = None,
        trace_context_extra: dict[str, Any] | None = None,
    ) -> T | None:
        return self._run_typed(
            stage=stage,
            response_format=response_format,
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            role=role,
            reasoning_effort=reasoning_effort,
            intent=intent,
            trace_context_extra=trace_context_extra,
        )

    def run_raw(
        self,
        *,
        stage: str,
        response_format: type[T],
        messages: list[dict[str, Any]],
        max_completion_tokens: int,
        role: str,
        reasoning_effort: ReasoningEffort | None = None,
        trace_context_extra: dict[str, Any] | None = None,
    ) -> StructuredExtractionResult[T]:
        """Passthrough for call-sites that must inspect the raw status.

        The inbox-classifier retries the extract on non-RESOLVED status
        with a higher token budget, so it needs the full result. All
        other call-sites should use the typed methods above.
        """
        return self._extract(
            stage=stage,
            response_format=response_format,
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            role=role,
            reasoning_effort=reasoning_effort,
            trace_context_extra=trace_context_extra,
        )

    def _run_typed(
        self,
        *,
        stage: str,
        response_format: type[T],
        messages: list[dict[str, Any]],
        max_completion_tokens: int,
        role: str,
        reasoning_effort: ReasoningEffort | None,
        intent: str | None,
        trace_context_extra: dict[str, Any] | None,
    ) -> T | None:
        extraction = self._extract(
            stage=stage,
            response_format=response_format,
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            role=role,
            reasoning_effort=reasoning_effort,
            trace_context_extra=trace_context_extra,
        )
        emit_llm_trace(
            role=role,
            stage=stage,
            model=self._model,
            response_format=response_format,
            result=extraction,
            intent=intent,
        )
        if extraction.status is not StructuredExtractionStatus.RESOLVED:
            return None
        parsed = extraction.parsed
        if not isinstance(parsed, response_format):
            return None
        return parsed

    def _extract(
        self,
        *,
        stage: str,
        response_format: type[T],
        messages: list[dict[str, Any]],
        max_completion_tokens: int,
        role: str,
        reasoning_effort: ReasoningEffort | None,
        trace_context_extra: dict[str, Any] | None,
    ) -> StructuredExtractionResult[T]:
        trace_context: dict[str, Any] = {"role": role, "stage": stage}
        if trace_context_extra:
            trace_context.update(
                {k: v for k, v in trace_context_extra.items() if v is not None}
            )
        return self._gateway.extract(
            model=self._model,
            response_format=response_format,
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            reasoning_effort=reasoning_effort,
            trace_context=trace_context,
        )


__all__ = ["LlmPort", "GatewayBackedLlmPort"]
