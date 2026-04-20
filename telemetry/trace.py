from __future__ import annotations

import hashlib
import json
from typing import Any

TRACE_PREFIX = "PAC1_TRACE_JSON:"


def emit_trace(event_type: str, **payload: Any) -> None:
    body = {
        "type": str(event_type or "").strip() or "trace",
        **{key: value for key, value in payload.items() if value is not None},
    }
    print(f"{TRACE_PREFIX} {json.dumps(body, ensure_ascii=False, sort_keys=True)}")


def stable_trace_id(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:16]


def emit_prompt_trace(
    *,
    trace_id: str,
    role: str,
    stage: str,
    model: str,
    response_format: type[Any],
    messages: list[dict[str, Any]],
    max_completion_tokens: int,
    reasoning_effort: str | None = None,
    api_mode: str,
    extra: dict[str, Any] | None = None,
) -> None:
    system_parts = [
        str(message.get("content") or "")
        for message in messages
        if str(message.get("role") or "") == "system"
    ]
    payload: dict[str, Any] = {
        "trace_id": trace_id,
        "role": role,
        "stage": stage,
        "model": model,
        "schema": getattr(response_format, "__name__", str(response_format)),
        "api_mode": api_mode,
        "max_completion_tokens": max_completion_tokens,
        "reasoning_effort": reasoning_effort,
        "message_count": len(messages),
        "prompt_sha1": stable_trace_id(messages),
        "system_prompt_sha1": stable_trace_id(system_parts) if system_parts else None,
        "messages": messages,
    }
    if extra:
        payload.update({key: value for key, value in extra.items() if value is not None})
    emit_trace("prompt_trace_input", **payload)


def emit_llm_trace(
    *,
    role: str,
    stage: str,
    model: str,
    response_format: type[Any],
    result: Any,
    intent: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "role": role,
        "stage": stage,
        "model": model,
        "schema": getattr(response_format, "__name__", str(response_format)),
        "status": getattr(getattr(result, "status", None), "value", None)
        or str(getattr(result, "status", "") or ""),
        "elapsed_ms": getattr(result, "elapsed_ms", None),
        "intent": intent,
        "error": getattr(result, "error", None),
        "trace_id": getattr(result, "trace_id", None),
    }
    if extra:
        payload.update({key: value for key, value in extra.items() if value is not None})
    emit_trace("llm_trace", **payload)


def emit_runtime_exception(
    *,
    stage: str,
    operation: str,
    error: Exception,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "stage": stage,
        "operation": operation,
        "error_type": type(error).__name__,
        "error": str(error),
    }
    if extra:
        payload.update({key: value for key, value in extra.items() if value is not None})
    emit_trace("runtime_exception", **payload)


__all__ = [
    "TRACE_PREFIX",
    "emit_trace",
    "emit_prompt_trace",
    "emit_llm_trace",
    "emit_runtime_exception",
    "stable_trace_id",
]
