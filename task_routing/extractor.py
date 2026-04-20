from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from domain.process import resolve_instruction_language
from domain.workspace import WorkspacePolicies

from .disclosure import disclose_route_decision
from .gateway import StructuredExtractionGateway
from .llm_port import GatewayBackedLlmPort
from .model import (
    TaskIntent,
    TaskRouteDecision,
    TypedTaskRequest as TypedStep,
    TypedTaskRequest,
)
from .prompts import (
    build_extraction_prompt,
    request_model_for_decision,
)


@dataclass(frozen=True, slots=True)
class RoutedTaskInputs:
    decision: TaskRouteDecision
    routed_request: TypedTaskRequest | None = None
    typed_command: TypedStep | None = None
    typed_request_source: str | None = None
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    effective_task_text: str = ""

    @property
    def translated_text(self) -> str | None:
        if self.routed_request is not None and self.routed_request.translated_text:
            return self.routed_request.translated_text
        translated = str(self.extracted_fields.get("translated_text") or "").strip()
        return translated or None


def extract_task_inputs(
    gateway: StructuredExtractionGateway,
    model: str,
    task_text: str,
    *,
    supported_intents: Collection[TaskIntent] | None = None,
    workspace_policies: WorkspacePolicies | None = None,
    finance_record_index: str = "",
) -> RoutedTaskInputs:
    decision = disclose_route_decision(
        gateway,
        model,
        task_text,
        current_decision=TaskRouteDecision(),
    )
    return extract_task_inputs_for_decision(
        gateway,
        model,
        task_text,
        decision=decision,
        supported_intents=supported_intents,
        workspace_policies=workspace_policies,
        finance_record_index=finance_record_index,
    )


def extract_task_inputs_for_decision(
    gateway: StructuredExtractionGateway,
    model: str,
    task_text: str,
    *,
    decision: TaskRouteDecision,
    supported_intents: Collection[TaskIntent] | None = None,
    workspace_policies: WorkspacePolicies | None = None,
    finance_record_index: str = "",
    user_content: str | None = None,
) -> RoutedTaskInputs:
    if supported_intents is not None and decision.intent not in supported_intents:
        return RoutedTaskInputs(
            decision=decision,
            effective_task_text=task_text,
        )
    routed_request = extract_typed_request_for_decision(
        gateway,
        model,
        task_text,
        decision,
        workspace_policies,
        finance_record_index,
        user_content=user_content,
    )
    typed_request_source = "structured" if routed_request is not None else None
    typed_command = routed_request
    extracted_fields: dict[str, Any] = {}
    translated_text = (
        str(routed_request.translated_text).strip()
        if routed_request is not None
        and str(routed_request.translated_text or "").strip()
        else str(extracted_fields.get("translated_text") or "").strip()
    )
    language_decision = resolve_instruction_language(
        task_text,
        translated_text=translated_text,
    )
    return RoutedTaskInputs(
        decision=decision,
        routed_request=routed_request,
        typed_command=typed_command,
        typed_request_source=typed_request_source,
        extracted_fields=extracted_fields,
        effective_task_text=language_decision.effective_text,
    )


def extract_typed_request_for_decision(
    gateway: StructuredExtractionGateway,
    model: str,
    task_text: str,
    decision: TaskRouteDecision,
    workspace_policies: WorkspacePolicies | None,
    finance_record_index: str,
    *,
    user_content: str | None = None,
) -> TypedTaskRequest | None:
    request_model = request_model_for_decision(decision)
    if request_model is None:
        return None
    content = str(user_content or task_text)
    llm_port = GatewayBackedLlmPort(gateway, model)
    return llm_port.extract_typed(
        stage="typed_extraction",
        response_format=request_model,
        messages=[
            {
                "role": "system",
                "content": build_extraction_prompt(
                    decision,
                    workspace_policies=workspace_policies,
                    finance_record_index=finance_record_index,
                ),
            },
            {"role": "user", "content": content},
        ],
        max_completion_tokens=512,
        intent=str(decision.intent.value),
        trace_context_extra={"intent": str(decision.intent.value)},
    )
__all__ = [
    "RoutedTaskInputs",
    "extract_task_inputs",
    "extract_task_inputs_for_decision",
    "extract_typed_request_for_decision",
]
