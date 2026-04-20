from __future__ import annotations

import re

from pydantic import BaseModel

from .gateway import StructuredExtractionGateway
from .llm_port import GatewayBackedLlmPort
from .model import RouteConfidence, TaskDomain, TaskIntent, TaskRouteDecision
from .prompt_registry import PROMPTS
from .reasoning import reasoning_effort_for_stage


class IntentDisclosure(BaseModel):
    intent: TaskIntent = TaskIntent.UNKNOWN


def disclose_route_decision(
    gateway: StructuredExtractionGateway,
    model: str,
    task_text: str,
    *,
    current_decision: TaskRouteDecision,
) -> TaskRouteDecision:
    if not _should_disclose(current_decision, task_text):
        return current_decision
    llm_port = GatewayBackedLlmPort(gateway, model)
    parsed = llm_port.classify(
        stage="route_disclosure",
        response_format=IntentDisclosure,
        messages=[
            {"role": "system", "content": PROMPTS["route_disclosure"]},
            {"role": "user", "content": task_text},
        ],
        max_completion_tokens=256,
        reasoning_effort=reasoning_effort_for_stage("route_disclosure"),
    )
    if parsed is None:
        return current_decision
    intent = parsed.intent
    if intent is TaskIntent.UNKNOWN:
        return current_decision
    return TaskRouteDecision(
        domain=_domain_for_intent(intent),
        intent=intent,
        confidence=RouteConfidence.MEDIUM,
    )


def _should_disclose(decision: TaskRouteDecision, task_text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(task_text or "").strip()).lower()
    if not normalized:
        return False
    if decision.intent is TaskIntent.UNKNOWN:
        return True
    return decision.confidence is RouteConfidence.LOW or not decision.supports_typed_extraction


def _domain_for_intent(intent: TaskIntent) -> TaskDomain:
    if intent is TaskIntent.CAPTURE_LOOKUP:
        return TaskDomain.CAPTURE
    if intent in {
        TaskIntent.ACCOUNT_LOOKUP,
        TaskIntent.CONTACT_LOOKUP,
    }:
        return TaskDomain.ACCOUNTS
    if intent is TaskIntent.PROJECT_QUERY:
        return TaskDomain.PROJECTS
    if intent is TaskIntent.ENTITY_QUERY:
        return TaskDomain.ENTITIES
    if intent is TaskIntent.MESSAGE_QUERY:
        return TaskDomain.MESSAGES
    if intent is TaskIntent.OUTBOUND_EMAIL_LOOKUP:
        return TaskDomain.OUTBOX
    if intent in {TaskIntent.FINANCE_LOOKUP, TaskIntent.FINANCE_MUTATION}:
        return TaskDomain.FINANCE
    if intent is TaskIntent.PROJECT_MUTATION:
        return TaskDomain.PROJECTS
    if intent in {TaskIntent.QUEUE_MUTATION, TaskIntent.QUEUE_STATE_LOOKUP}:
        return TaskDomain.PROCESS
    if intent in {
        TaskIntent.INBOX_PROCESS_NEXT,
        TaskIntent.INBOX_EMAIL_LOOKUP,
        TaskIntent.INBOX_WORKFLOW,
    }:
        return TaskDomain.INBOX
    if intent in {
        TaskIntent.FOLLOW_UP_SEND,
        TaskIntent.FOLLOW_UP_RESCHEDULE,
    }:
        return TaskDomain.FOLLOW_UP
    return TaskDomain.UNKNOWN
