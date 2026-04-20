from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from typing import Any, Callable

from openai import OpenAI
from pydantic import BaseModel

from telemetry.trace import emit_prompt_trace, stable_trace_id

from .gateway import ReasoningEffort
from .gateway import StructuredExtractionResult, StructuredExtractionStatus
from .provider import NativePromptProfile, PromptProfile, ProviderCapabilities


StructuredParseFn = Callable[..., tuple[Any, int]]
TextParseFn = Callable[..., tuple[str, int]]
STRUCTURED_RETRY_LIMIT = 3
USE_RESPONSES_API_ENV = "PAC1_USE_RESPONSES_API"
TRACE_PROMPTS_ENV = "PAC1_TRACE_PROMPTS"
RATE_LIMIT_RETRY_ATTEMPTS_ENV = "PAC1_LLM_RATE_LIMIT_MAX_ATTEMPTS"
RATE_LIMIT_INITIAL_DELAY_MS_ENV = "PAC1_LLM_RATE_LIMIT_INITIAL_DELAY_MS"
RATE_LIMIT_MAX_DELAY_MS_ENV = "PAC1_LLM_RATE_LIMIT_MAX_DELAY_MS"


class StructuredResponseError(RuntimeError):
    pass


def _rate_limit_retry_attempts() -> int:
    raw = str(os.environ.get(RATE_LIMIT_RETRY_ATTEMPTS_ENV, "") or "").strip()
    try:
        value = int(raw) if raw else 6
    except ValueError:
        value = 6
    return max(1, value)


def _rate_limit_initial_delay_seconds() -> float:
    raw = str(os.environ.get(RATE_LIMIT_INITIAL_DELAY_MS_ENV, "") or "").strip()
    try:
        value_ms = int(raw) if raw else 1000
    except ValueError:
        value_ms = 1000
    return max(0.0, value_ms / 1000.0)


def _rate_limit_max_delay_seconds() -> float:
    raw = str(os.environ.get(RATE_LIMIT_MAX_DELAY_MS_ENV, "") or "").strip()
    try:
        value_ms = int(raw) if raw else 30000
    except ValueError:
        value_ms = 30000
    return max(0.0, value_ms / 1000.0)


def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True
    body = str(exc).lower()
    return "rate limit" in body or "too many requests" in body or "status code: 429" in body


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after is None:
        return None
    try:
        return max(0.0, float(str(retry_after).strip()))
    except ValueError:
        return None


def _rate_limit_backoff_seconds(attempt_index: int, exc: Exception) -> float:
    hinted = _retry_after_seconds(exc)
    initial = _rate_limit_initial_delay_seconds()
    maximum = _rate_limit_max_delay_seconds()
    exponential = initial * (2 ** attempt_index)
    delay = hinted if hinted is not None else exponential
    return min(maximum, max(0.0, delay))


def _use_responses_api(model: str) -> bool:
    env_flag = os.environ.get(USE_RESPONSES_API_ENV, "").strip().lower()
    if env_flag in {"1", "true", "yes"}:
        return True
    if env_flag in {"0", "false", "no"}:
        return False
    return "gpt-5" in model or "gpt5" in model


def _messages_to_responses_input(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    instructions = ""
    input_items: list[dict[str, Any]] = []
    for msg in messages:
        role = str(msg.get("role") or "user")
        content = msg.get("content", "")
        if role == "system":
            instructions = (
                f"{instructions}\n{content}".strip() if instructions else str(content)
            )
            continue
        if role == "tool":
            input_items.append({"role": "user", "content": content})
            continue
        input_items.append({"role": role, "content": content})
    return instructions, input_items


def parse_structured_chat_completion(
    client: OpenAI,
    *,
    model: str,
    response_format: type[BaseModel],
    messages: list[dict[str, Any]],
    max_completion_tokens: int,
    reasoning_effort: ReasoningEffort | None = None,
) -> tuple[BaseModel, int]:
    last_exc: Exception | None = None
    max_attempts = max(STRUCTURED_RETRY_LIMIT, _rate_limit_retry_attempts())
    for attempt in range(max_attempts):
        try:
            if _use_responses_api(model):
                instructions, input_items = _messages_to_responses_input(messages)
                response_kwargs: dict[str, Any] = {
                    "model": model,
                    "text_format": response_format,
                    "instructions": instructions,
                    "input": input_items,
                    "max_output_tokens": max_completion_tokens,
                }
                if reasoning_effort is not None:
                    response_kwargs["reasoning"] = {"effort": reasoning_effort}
                started = time.time()
                response = client.responses.parse(**response_kwargs)
                elapsed_ms = int((time.time() - started) * 1000)
                parsed = getattr(response, "output_parsed", None)
                if parsed is None:
                    raise StructuredResponseError(
                        f"{response_format.__name__} responses API did not return parsed output."
                    )
                return parsed, elapsed_ms

            started = time.time()
            response = client.beta.chat.completions.parse(
                model=model,
                response_format=response_format,
                messages=messages,
                max_completion_tokens=max_completion_tokens,
            )
            elapsed_ms = int((time.time() - started) * 1000)
            choices = getattr(response, "choices", None)
            if not choices:
                raise StructuredResponseError(
                    f"{response_format.__name__} response contained no choices."
                )
            message = getattr(choices[0], "message", None)
            if message is None:
                raise StructuredResponseError(
                    f"{response_format.__name__} response contained no message."
                )
            parsed = getattr(message, "parsed", None)
            if parsed is None:
                raise StructuredResponseError(
                    f"{response_format.__name__} response did not contain a structured payload."
                )
            return parsed, elapsed_ms
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_rate_limit_error(exc) and attempt + 1 < max_attempts:
                time.sleep(_rate_limit_backoff_seconds(attempt, exc))
                continue

    if last_exc is not None and _is_rate_limit_error(last_exc):
        raise StructuredResponseError(
            f"{response_format.__name__} request rate_limited after {max_attempts} attempts: "
            f"{type(last_exc).__name__}: {last_exc}"
        ) from last_exc
    raise StructuredResponseError(
        f"{response_format.__name__} request failed after {max_attempts} attempts: "
        f"{type(last_exc).__name__}: {last_exc}"
    ) from last_exc


def parse_text_completion(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_completion_tokens: int,
    reasoning_effort: ReasoningEffort | None = None,
) -> tuple[str, int]:
    last_exc: Exception | None = None
    max_attempts = max(STRUCTURED_RETRY_LIMIT, _rate_limit_retry_attempts())
    for attempt in range(max_attempts):
        try:
            if _use_responses_api(model):
                instructions, input_items = _messages_to_responses_input(messages)
                response_kwargs: dict[str, Any] = {
                    "model": model,
                    "instructions": instructions,
                    "input": input_items,
                    "max_output_tokens": max_completion_tokens,
                }
                if reasoning_effort is not None:
                    response_kwargs["reasoning"] = {"effort": reasoning_effort}
                started = time.time()
                response = client.responses.create(**response_kwargs)
                elapsed_ms = int((time.time() - started) * 1000)
                text = str(getattr(response, "output_text", "") or "").strip()
                if not text:
                    raise StructuredResponseError("Text response did not contain output_text.")
                return text, elapsed_ms

            started = time.time()
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=max_completion_tokens,
            )
            elapsed_ms = int((time.time() - started) * 1000)
            choices = getattr(response, "choices", None)
            if not choices:
                raise StructuredResponseError("Text response contained no choices.")
            message = getattr(choices[0], "message", None)
            if message is None:
                raise StructuredResponseError("Text response contained no message.")
            content = _coerce_text_message_content(getattr(message, "content", ""))
            if not content:
                raise StructuredResponseError("Text response contained empty content.")
            return content, elapsed_ms
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_rate_limit_error(exc) and attempt + 1 < max_attempts:
                time.sleep(_rate_limit_backoff_seconds(attempt, exc))
                continue
    if last_exc is not None and _is_rate_limit_error(last_exc):
        raise StructuredResponseError(
            f"text completion request rate_limited after {max_attempts} attempts: "
            f"{type(last_exc).__name__}: {last_exc}"
        ) from last_exc
    raise StructuredResponseError(
        f"text completion request failed after {max_attempts} attempts: "
        f"{type(last_exc).__name__}: {last_exc}"
    ) from last_exc


class OpenAICompatibleStructuredExtractionGateway:
    def __init__(
        self,
        client: OpenAI,
        *,
        parse_fn: StructuredParseFn = parse_structured_chat_completion,
        text_parse_fn: TextParseFn = parse_text_completion,
        capabilities: ProviderCapabilities | None = None,
        prompt_profile: PromptProfile | None = None,
    ) -> None:
        self._client = client
        self._parse_fn = parse_fn
        self._text_parse_fn = text_parse_fn
        self._capabilities = capabilities or ProviderCapabilities()
        self._prompt_profile = prompt_profile or NativePromptProfile()

    def extract(
        self,
        *,
        model: str,
        response_format: type[BaseModel],
        messages: list[dict[str, Any]],
        max_completion_tokens: int,
        reasoning_effort: ReasoningEffort | None = None,
        trace_context: Mapping[str, Any] | None = None,
    ) -> StructuredExtractionResult[BaseModel]:
        prepared = self._prompt_profile.prepare_extraction(
            messages=messages,
            response_format=response_format,
            capabilities=self._capabilities,
            trace_context=trace_context,
        )
        effective_messages = prepared.messages
        effective_reasoning = (
            reasoning_effort if self._capabilities.supports_reasoning_effort else None
        )
        api_mode = _api_mode(
            model,
            supports_structured_outputs=self._capabilities.supports_structured_outputs,
        )
        trace_id = _prompt_trace_id(
            model=model,
            response_format=response_format,
            messages=effective_messages,
            max_completion_tokens=max_completion_tokens,
            reasoning_effort=effective_reasoning,
            trace_context=trace_context,
            api_mode=api_mode,
            profile_name=prepared.profile_name,
            capabilities=self._capabilities,
        )
        _maybe_emit_prompt_trace(
            trace_id=trace_id,
            model=model,
            response_format=response_format,
            messages=effective_messages,
            max_completion_tokens=max_completion_tokens,
            reasoning_effort=effective_reasoning,
            trace_context=trace_context,
            api_mode=api_mode,
            profile_name=prepared.profile_name,
            capabilities=self._capabilities,
        )
        try:
            if self._capabilities.supports_structured_outputs:
                parsed, elapsed_ms = self._parse_fn(
                    self._client,
                    model=model,
                    response_format=response_format,
                    messages=effective_messages,
                    max_completion_tokens=max_completion_tokens,
                    reasoning_effort=effective_reasoning,
                )
            else:
                text, elapsed_ms = self._text_parse_fn(
                    self._client,
                    model=model,
                    messages=effective_messages,
                    max_completion_tokens=max_completion_tokens,
                    reasoning_effort=effective_reasoning,
                )
                parsed = _parse_json_payload(text, response_format)
        except StructuredResponseError as exc:
            return StructuredExtractionResult(
                status=_classify_structured_error(exc),
                error=str(exc),
                trace_id=trace_id,
            )
        except Exception as exc:  # noqa: BLE001
            return StructuredExtractionResult(
                status=StructuredExtractionStatus.PROVIDER_ERROR,
                error=f"{type(exc).__name__}: {exc}",
                trace_id=trace_id,
            )
        if parsed is None:
            return StructuredExtractionResult(
                status=StructuredExtractionStatus.EMPTY_RESULT,
                trace_id=trace_id,
            )
        if not isinstance(parsed, response_format):
            return StructuredExtractionResult(
                status=StructuredExtractionStatus.SCHEMA_VALIDATION_FAILED,
                error=(
                    f"Structured payload type mismatch: expected {response_format.__name__}, "
                    f"got {type(parsed).__name__}"
                ),
                trace_id=trace_id,
            )
        return StructuredExtractionResult(
            status=StructuredExtractionStatus.RESOLVED,
            parsed=parsed,
            elapsed_ms=elapsed_ms,
            trace_id=trace_id,
        )


def _trace_prompts_enabled() -> bool:
    raw = os.environ.get(TRACE_PROMPTS_ENV, "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def _prompt_trace_id(
    *,
    model: str,
    response_format: type[BaseModel],
    messages: list[dict[str, Any]],
    max_completion_tokens: int,
    reasoning_effort: ReasoningEffort | None,
    trace_context: Mapping[str, Any] | None,
    api_mode: str,
    profile_name: str,
    capabilities: ProviderCapabilities,
) -> str:
    return stable_trace_id(
        {
            "model": model,
            "schema": getattr(response_format, "__name__", str(response_format)),
            "messages": messages,
            "max_completion_tokens": max_completion_tokens,
            "reasoning_effort": reasoning_effort,
            "trace_context": dict(trace_context or {}),
            "api_mode": api_mode,
            "prompt_profile": profile_name,
            "supports_structured_outputs": capabilities.supports_structured_outputs,
            "supports_reasoning_effort": capabilities.supports_reasoning_effort,
        }
    )


def _maybe_emit_prompt_trace(
    *,
    trace_id: str,
    model: str,
    response_format: type[BaseModel],
    messages: list[dict[str, Any]],
    max_completion_tokens: int,
    reasoning_effort: ReasoningEffort | None,
    trace_context: Mapping[str, Any] | None,
    api_mode: str,
    profile_name: str,
    capabilities: ProviderCapabilities,
) -> None:
    if not _trace_prompts_enabled():
        return
    context = dict(trace_context or {})
    emit_prompt_trace(
        trace_id=trace_id,
        role=str(context.pop("role", "") or "unknown"),
        stage=str(context.pop("stage", "") or "unknown"),
        model=model,
        response_format=response_format,
        messages=messages,
        max_completion_tokens=max_completion_tokens,
        reasoning_effort=reasoning_effort,
        api_mode=api_mode,
        extra={
            **context,
            "prompt_profile": profile_name,
            "supports_structured_outputs": capabilities.supports_structured_outputs,
            "supports_reasoning_effort": capabilities.supports_reasoning_effort,
        },
    )


def _api_mode(model: str, *, supports_structured_outputs: bool) -> str:
    base = "responses" if _use_responses_api(model) else "chat_completions"
    suffix = "structured" if supports_structured_outputs else "text_json"
    return f"{base}_{suffix}"


def _parse_json_payload(
    text: str,
    response_format: type[BaseModel],
) -> BaseModel:
    candidate = _normalize_json_payload(text)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise StructuredResponseError(
            f"{response_format.__name__} response did not contain valid JSON: {exc}"
        ) from exc
    try:
        return response_format.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        raise StructuredResponseError(
            f"{response_format.__name__} JSON failed schema validation: {exc}"
        ) from exc


def _normalize_json_payload(text: str) -> str:
    value = str(text or "").strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    first = value.find("{")
    last = value.rfind("}")
    if first != -1 and last != -1 and first < last:
        return value[first : last + 1]
    return value


def _coerce_text_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("content") or "").strip()
                if text:
                    chunks.append(text)
                continue
            text = str(item or "").strip()
            if text:
                chunks.append(text)
        return "\n".join(chunks).strip()
    return str(content or "").strip()


def _classify_structured_error(exc: StructuredResponseError) -> StructuredExtractionStatus:
    message = str(exc).lower()
    if "rate_limited" in message:
        return StructuredExtractionStatus.PROVIDER_ERROR
    if any(marker in message for marker in _EMPTY_RESULT_MARKERS):
        return StructuredExtractionStatus.EMPTY_RESULT
    if any(marker in message for marker in _SCHEMA_VALIDATION_MARKERS):
        return StructuredExtractionStatus.SCHEMA_VALIDATION_FAILED
    return StructuredExtractionStatus.SCHEMA_VALIDATION_FAILED


_EMPTY_RESULT_MARKERS = (
    "response contained no choices",
    "response contained no message",
    "did not return parsed output",
    "did not contain output_text",
    "contained empty content",
)

_SCHEMA_VALIDATION_MARKERS = (
    "did not contain a structured payload",
)


OpenAIStructuredExtractionGateway = OpenAICompatibleStructuredExtractionGateway
