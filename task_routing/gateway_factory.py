from __future__ import annotations

from openai import OpenAI

from .gateway import StructuredExtractionGateway
from .llm_port import GatewayBackedLlmPort, LlmPort
from .openai_gateway import OpenAICompatibleStructuredExtractionGateway
from .provider import openai_client_kwargs_from_env, provider_config_for_model


def build_structured_extraction_gateway(
    model: str,
    *,
    client: OpenAI | None = None,
) -> StructuredExtractionGateway:
    config = provider_config_for_model(model)
    if config.transport_name not in {"openai_native", "openai_compatible"}:
        raise ValueError(f"Unsupported LLM transport: {config.transport_name}")
    openai_client = client or OpenAI(**openai_client_kwargs_from_env())
    return OpenAICompatibleStructuredExtractionGateway(
        openai_client,
        capabilities=config.capabilities,
        prompt_profile=config.prompt_profile,
    )


def build_llm_port(
    model: str,
    *,
    client: OpenAI | None = None,
) -> LlmPort:
    gateway = build_structured_extraction_gateway(model, client=client)
    return GatewayBackedLlmPort(gateway, model)


__all__ = ["build_structured_extraction_gateway", "build_llm_port"]
