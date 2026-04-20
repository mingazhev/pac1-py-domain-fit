from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel


PromptMessage = dict[str, Any]

LLM_PROVIDER_ENV = "PAC1_LLM_PROVIDER"
LLM_TRANSPORT_ENV = "PAC1_LLM_TRANSPORT"
LLM_BASE_URL_ENV = "PAC1_LLM_BASE_URL"
LLM_API_KEY_ENV = "PAC1_LLM_API_KEY"
LLM_SUPPORTS_STRUCTURED_OUTPUTS_ENV = "PAC1_LLM_SUPPORTS_STRUCTURED_OUTPUTS"
LLM_SUPPORTS_REASONING_ENV = "PAC1_LLM_SUPPORTS_REASONING_EFFORT"
LLM_PROMPT_PROFILE_ENV = "PAC1_LLM_PROMPT_PROFILE"


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    supports_structured_outputs: bool = True
    supports_reasoning_effort: bool = True


@dataclass(frozen=True, slots=True)
class PromptPreparation:
    messages: list[PromptMessage]
    profile_name: str


class PromptProfile(Protocol):
    def prepare_extraction(
        self,
        *,
        messages: list[PromptMessage],
        response_format: type[BaseModel],
        capabilities: ProviderCapabilities,
        trace_context: Mapping[str, Any] | None = None,
    ) -> PromptPreparation:
        ...


class NativePromptProfile:
    name = "native"

    def prepare_extraction(
        self,
        *,
        messages: list[PromptMessage],
        response_format: type[BaseModel],
        capabilities: ProviderCapabilities,
        trace_context: Mapping[str, Any] | None = None,
    ) -> PromptPreparation:
        return PromptPreparation(
            messages=[dict(message) for message in messages],
            profile_name=self.name,
        )


class JsonSchemaPromptProfile:
    name = "json_schema"

    def prepare_extraction(
        self,
        *,
        messages: list[PromptMessage],
        response_format: type[BaseModel],
        capabilities: ProviderCapabilities,
        trace_context: Mapping[str, Any] | None = None,
    ) -> PromptPreparation:
        schema_json = json.dumps(
            response_format.model_json_schema(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        instructions = (
            "Return ONLY one valid JSON object that matches the target schema exactly. "
            "Do not wrap the JSON in markdown fences. Do not add commentary.\n\n"
            f"Target JSON schema:\n{schema_json}"
        )
        prepared = [dict(message) for message in messages]
        if prepared and str(prepared[0].get("role") or "") == "system":
            prepared[0] = {
                **prepared[0],
                "content": f"{prepared[0].get('content', '')}\n\n{instructions}".strip(),
            }
        else:
            prepared.insert(0, {"role": "system", "content": instructions})
        return PromptPreparation(messages=prepared, profile_name=self.name)


@dataclass(frozen=True, slots=True)
class LLMProviderConfig:
    provider_name: str
    transport_name: str
    capabilities: ProviderCapabilities
    prompt_profile: PromptProfile


def provider_config_for_model(model: str) -> LLMProviderConfig:
    provider_name = _env_value(LLM_PROVIDER_ENV) or "openai"
    transport_name = resolve_transport_name(provider_name)
    supports_structured_outputs = _resolve_bool_override(
        LLM_SUPPORTS_STRUCTURED_OUTPUTS_ENV,
        default=(transport_name == "openai_native"),
    )
    supports_reasoning_effort = _resolve_bool_override(
        LLM_SUPPORTS_REASONING_ENV,
        default=(transport_name == "openai_native" and _model_looks_like_gpt5(model)),
    )
    capabilities = ProviderCapabilities(
        supports_structured_outputs=supports_structured_outputs,
        supports_reasoning_effort=supports_reasoning_effort,
    )
    profile_name = _env_value(LLM_PROMPT_PROFILE_ENV) or default_prompt_profile_name(
        provider_name=provider_name,
        model=model,
        capabilities=capabilities,
    )
    return LLMProviderConfig(
        provider_name=provider_name,
        transport_name=transport_name,
        capabilities=capabilities,
        prompt_profile=prompt_profile_for_name(profile_name),
    )


def resolve_transport_name(provider_name: str) -> str:
    explicit = _env_value(LLM_TRANSPORT_ENV).lower()
    if explicit:
        if explicit in {"openai_native", "openai_compatible"}:
            return explicit
        raise ValueError(f"Unsupported LLM transport: {explicit}")
    normalized = str(provider_name or "").strip().lower()
    if normalized in {"openai", ""}:
        return "openai_native"
    if normalized in {"openai_compatible"}:
        return "openai_compatible"
    if _env_value(LLM_BASE_URL_ENV):
        return "openai_compatible"
    raise ValueError(
        "Unsupported LLM provider. Set PAC1_LLM_PROVIDER=openai, "
        "or set PAC1_LLM_TRANSPORT=openai_compatible for an OpenAI-compatible backend."
    )


def default_prompt_profile_name(
    *,
    provider_name: str,
    model: str,
    capabilities: ProviderCapabilities,
) -> str:
    del provider_name, model
    return "native" if capabilities.supports_structured_outputs else "json_schema"


def prompt_profile_for_name(name: str) -> PromptProfile:
    normalized = str(name or "").strip().lower()
    if normalized in {"", "native", "structured", "provider_native"}:
        return NativePromptProfile()
    if normalized in {"json", "json_schema", "json-only", "json_only"}:
        return JsonSchemaPromptProfile()
    raise ValueError(f"Unsupported prompt profile: {name}")


def openai_client_kwargs_from_env() -> dict[str, str]:
    kwargs: dict[str, str] = {}
    base_url = _env_value(LLM_BASE_URL_ENV)
    api_key = _env_value(LLM_API_KEY_ENV)
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key
    return kwargs


def _env_value(name: str) -> str:
    return os.environ.get(name, "").strip()


def _resolve_bool_override(name: str, *, default: bool) -> bool:
    raw = _env_value(name).lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _model_looks_like_gpt5(model: str) -> bool:
    normalized = str(model or "").lower()
    return "gpt-5" in normalized or "gpt5" in normalized


__all__ = [
    "JsonSchemaPromptProfile",
    "LLMProviderConfig",
    "NativePromptProfile",
    "PromptMessage",
    "PromptPreparation",
    "PromptProfile",
    "ProviderCapabilities",
    "default_prompt_profile_name",
    "openai_client_kwargs_from_env",
    "prompt_profile_for_name",
    "provider_config_for_model",
    "resolve_transport_name",
]
