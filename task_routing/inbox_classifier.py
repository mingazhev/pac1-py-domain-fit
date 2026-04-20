from __future__ import annotations

import hashlib
import os
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from domain.inbox import InboxMessageEnvelope
from telemetry.trace import emit_llm_trace, emit_trace

from .gateway import StructuredExtractionGateway, StructuredExtractionResult, StructuredExtractionStatus
from .llm_port import GatewayBackedLlmPort, LlmPort
from .prompt_registry import PROMPTS
from .reasoning import reasoning_effort_for_stage


PAC1_TRACE_INBOX_CLASSIFIER_ENV = "PAC1_TRACE_INBOX_CLASSIFIER"
_TRACE_DISABLED = {"0", "false", "no", "off"}
_BODY_TRACE_LIMIT = 4000


class InboxItemDecision(BaseModel):
    """Typed classification of a single inbox item's body.

    The deterministic inbox workflow calls this classifier when a raw
    inbox item lands in the queue. The LLM interprets the body; the
    runtime owns the terminal decision off the typed verdict.
    """

    decision: Literal[
        "process_as_task",
        "process_as_invoice_email",
        "process_as_finance_payment",
        "process_as_finance_document_ingest",
        "refuse_security",
        "refuse_out_of_scope",
        "clarify",
        "no_actionable_step",
    ] = "no_actionable_step"

    reason: str = Field(
        default="",
        description=(
            "One short sentence describing why this decision was chosen. "
            "Factual, not hedging."
        ),
    )

    sub_task_text: str | None = Field(
        default=None,
        description=(
            "When decision=process_as_task, the clean English task "
            "instruction extracted from the inbox body, rewritten as a "
            "direct user request; empty for all other decisions."
        ),
    )
    continuation_intent: Literal[
        "account_lookup",
        "contact_lookup",
        "capture_lookup",
        "project_query",
        "entity_query",
        "message_query",
        "finance_lookup",
        "finance_mutation",
        "outbound_email_lookup",
        "outbox_draft",
        "queue_mutation",
        "queue_state_lookup",
    ] | None = Field(
        default=None,
        description=(
            "When decision=process_as_task, select the single supported "
            "typed continuation family that should execute this inbox item. "
            "Leave null for all non-process decisions."
        ),
    )
    invoice_email_request: "InvoiceEmailWorkflowRequest | None" = Field(
        default=None,
        description=(
            "When decision=process_as_invoice_email, the typed invoice-email "
            "workflow payload. Leave null for all other decisions."
        ),
    )
    finance_payment_request: "FinancePaymentWorkflowRequest | None" = Field(
        default=None,
        description=(
            "When decision=process_as_finance_payment, the typed finance-payment "
            "workflow payload. Leave null for all other decisions."
        ),
    )
    finance_document_ingest_request: "FinanceDocumentIngestWorkflowRequest | None" = Field(
        default=None,
        description=(
            "When decision=process_as_finance_document_ingest, the typed finance "
            "document-ingest payload. Leave null for all other decisions."
        ),
    )

    @model_validator(mode="after")
    def _continuation_contract(self) -> "InboxItemDecision":
        if self.decision == "process_as_invoice_email":
            if self.invoice_email_request is None:
                raise ValueError(
                    "process_as_invoice_email requires invoice_email_request"
                )
            if self.continuation_intent is not None:
                raise ValueError(
                    "continuation_intent is not valid for process_as_invoice_email"
                )
            cleaned_sub_task = str(self.sub_task_text or "").strip()
            if cleaned_sub_task:
                raise ValueError(
                    "sub_task_text is not valid for process_as_invoice_email"
                )
            if self.finance_payment_request is not None or self.finance_document_ingest_request is not None:
                raise ValueError(
                    "finance workflow requests are not valid for process_as_invoice_email"
                )
            return self
        if self.decision == "process_as_finance_payment":
            if self.finance_payment_request is None:
                raise ValueError(
                    "process_as_finance_payment requires finance_payment_request"
                )
            if (
                self.continuation_intent is not None
                or self.invoice_email_request is not None
                or self.finance_document_ingest_request is not None
                or str(self.sub_task_text or "").strip()
            ):
                raise ValueError(
                    "process_as_finance_payment only accepts finance_payment_request"
                )
            return self
        if self.decision == "process_as_finance_document_ingest":
            if self.finance_document_ingest_request is None:
                raise ValueError(
                    "process_as_finance_document_ingest requires finance_document_ingest_request"
                )
            if (
                self.continuation_intent is not None
                or self.invoice_email_request is not None
                or self.finance_payment_request is not None
                or str(self.sub_task_text or "").strip()
            ):
                raise ValueError(
                    "process_as_finance_document_ingest only accepts finance_document_ingest_request"
                )
            return self
        if self.decision == "process_as_task":
            if self.continuation_intent is None and not (self.sub_task_text or "").strip():
                raise ValueError(
                    "process_as_task requires continuation_intent or sub_task_text"
                )
            if (
                self.invoice_email_request is not None
                or self.finance_payment_request is not None
                or self.finance_document_ingest_request is not None
            ):
                raise ValueError(
                    "workflow requests are only valid for their matching workflow decision"
                )
            return self
        if (
            self.invoice_email_request is not None
            or self.finance_payment_request is not None
            or self.finance_document_ingest_request is not None
        ):
            raise ValueError(
                "workflow requests are only valid for their matching workflow decision"
            )
        if self.continuation_intent is not None:
            raise ValueError(
                "continuation_intent is only valid when decision=process_as_task"
            )
        if self.sub_task_text is not None:
            cleaned = str(self.sub_task_text or "").strip()
            if cleaned:
                raise ValueError(
                    "sub_task_text is only valid when decision=process_as_task"
                )
        return self


class InvoiceEmailWorkflowRequest(BaseModel):
    workflow_kind: Literal["invoice_resend", "invoice_bundle"]
    mode: Literal["dated", "latest"] | None = None
    counterparty: str | None = None
    target_date: str | None = None
    record_hint: str | None = None
    count: int | None = None
    target_query: str | None = None
    selection_mode: Literal["oldest", "latest"] = "latest"
    attachment_order: Literal["reverse_chronological", "chronological"] = (
        "reverse_chronological"
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_cross_shape_fields(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        workflow_kind = str(payload.get("workflow_kind") or "").strip()
        if workflow_kind == "invoice_bundle":
            for key in ("mode", "counterparty", "target_date", "record_hint"):
                payload[key] = None
            return payload
        if workflow_kind == "invoice_resend":
            for key in ("count", "target_query"):
                payload[key] = None
            return payload
        return payload

    @model_validator(mode="after")
    def _workflow_contract(self) -> "InvoiceEmailWorkflowRequest":
        if self.workflow_kind == "invoice_resend":
            if self.mode is None:
                raise ValueError("invoice_resend requires mode")
            if not str(self.counterparty or "").strip():
                raise ValueError("invoice_resend requires counterparty")
            if self.mode == "dated" and not str(self.target_date or "").strip():
                raise ValueError("dated invoice_resend requires target_date")
            if self.count is not None or self.target_query is not None:
                raise ValueError(
                    "invoice_resend does not accept count or target_query"
                )
            return self
        if not self.count or self.count <= 0:
            raise ValueError("invoice_bundle requires positive count")
        if not str(self.target_query or "").strip():
            raise ValueError("invoice_bundle requires target_query")
        if (
            self.mode is not None
            or self.counterparty is not None
            or self.target_date is not None
            or self.record_hint is not None
        ):
            raise ValueError(
                "invoice_bundle does not accept mode/counterparty/target_date/record_hint"
            )
        return self


class FinancePaymentWorkflowRequest(BaseModel):
    action: Literal["mark_paid", "settle_payment"] = "settle_payment"
    record_type: Literal["invoice", "bill", "any"] = "any"
    counterparty: str | None = None
    target_date: str | None = None
    amount_eur: float | None = None
    reference_number: str | None = None
    alias: str | None = None
    project: str | None = None
    related_entity: str | None = None
    settlement_reference: str | None = None
    settlement_channel: Literal[
        "bank_transfer",
        "card",
        "cash",
        "manual_attestation",
    ] | None = None
    settlement_date: str | None = None

    @model_validator(mode="after")
    def _contract(self) -> "FinancePaymentWorkflowRequest":
        if not any(
            str(value or "").strip()
            for value in (
                self.counterparty,
                self.target_date,
                self.reference_number,
                self.alias,
                self.project,
                self.related_entity,
            )
        ):
            raise ValueError(
                "finance payment workflow requires at least one target identity field"
            )
        return self


class FinanceDocumentIngestWorkflowRequest(BaseModel):
    target_paths: tuple[str, ...] = ()
    record_type: Literal["invoice", "bill", "any"] = "any"
    entity_query: str | None = None
    target_scope: Literal["single", "all_matches"] = "single"
    family_reference: str | None = None

    @model_validator(mode="after")
    def _contract(self) -> "FinanceDocumentIngestWorkflowRequest":
        if not self.target_paths and not str(self.entity_query or "").strip():
            raise ValueError(
                "finance document ingest workflow requires target_paths or entity_query"
            )
        return self


def classify_inbox_item(
    gateway: StructuredExtractionGateway,
    model: str,
    *,
    body_text: str,
    envelope: InboxMessageEnvelope | None = None,
    inbox_policy_text: str = "",
    root_policy_text: str = "",
    max_completion_tokens: int = 384,
) -> InboxItemDecision | None:
    text = str(body_text or "").strip()
    if not text:
        return None
    envelope_context = (
        envelope.as_prompt_context() if envelope is not None else ""
    )
    user_content = (
        f"{envelope_context}\n\n{text}" if envelope_context else text
    )
    system_prompt = PROMPTS["inbox_classifier"]
    policy_segments: list[str] = []
    root = str(root_policy_text or "").strip()
    if root:
        policy_segments.append(
            "Root workspace policy (AGENTS.MD at repo root):\n" + root
        )
    policy = str(inbox_policy_text or "").strip()
    if policy:
        policy_segments.append(
            "Inbox folder policy (AGENTS.MD inside the inbox lane — OVERRIDES "
            "the root policy on any conflict):\n" + policy
        )
    if policy_segments:
        system_prompt = system_prompt + "\n\n" + "\n\n".join(policy_segments)
    reasoning_effort = reasoning_effort_for_stage("workflow_classifier")
    _emit_inbox_classifier_input_trace(
        body_text=text,
        envelope=envelope,
        system_prompt=system_prompt,
        inbox_policy_text=policy,
        root_policy_text=root,
        max_completion_tokens=max_completion_tokens,
        reasoning_effort=reasoning_effort,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    llm_port = GatewayBackedLlmPort(gateway, model)
    extraction = _extract_inbox_decision(
        llm_port,
        messages=messages,
        max_completion_tokens=max_completion_tokens,
        reasoning_effort=reasoning_effort,
    )
    emit_llm_trace(
        role="workflow_classifier",
        stage="inbox_classifier",
        model=model,
        response_format=InboxItemDecision,
        result=extraction,
    )
    if extraction.status is not StructuredExtractionStatus.RESOLVED:
        _emit_inbox_classifier_output_trace(extraction)
        return None
    parsed = extraction.parsed
    if not isinstance(parsed, InboxItemDecision):
        _emit_inbox_classifier_output_trace(extraction)
        return None
    _emit_inbox_classifier_output_trace(extraction)
    return parsed


def _extract_inbox_decision(
    llm_port: LlmPort,
    *,
    messages: list[dict[str, str]],
    max_completion_tokens: int,
    reasoning_effort: str | None,
) -> StructuredExtractionResult[InboxItemDecision]:
    extraction = llm_port.run_raw(
        stage="inbox_classifier",
        role="workflow_classifier",
        response_format=InboxItemDecision,
        messages=messages,
        max_completion_tokens=max_completion_tokens,
        reasoning_effort=reasoning_effort,
    )
    if extraction.status is StructuredExtractionStatus.RESOLVED:
        return extraction
    retry_tokens = max(max_completion_tokens, 512)
    if retry_tokens == max_completion_tokens:
        return extraction
    return llm_port.run_raw(
        stage="inbox_classifier",
        role="workflow_classifier",
        response_format=InboxItemDecision,
        messages=messages,
        max_completion_tokens=retry_tokens,
        reasoning_effort=reasoning_effort,
        trace_context_extra={"retry": True},
    )


def _trace_inbox_classifier_enabled() -> bool:
    raw = os.environ.get(PAC1_TRACE_INBOX_CLASSIFIER_ENV, "").strip().lower()
    return raw not in _TRACE_DISABLED


def _emit_inbox_classifier_input_trace(
    *,
    body_text: str,
    envelope: InboxMessageEnvelope | None,
    system_prompt: str,
    inbox_policy_text: str,
    root_policy_text: str,
    max_completion_tokens: int,
    reasoning_effort: str | None,
) -> None:
    if not _trace_inbox_classifier_enabled():
        return
    emit_trace(
        "inbox_classifier_input",
        stage="inbox_classifier",
        body_text=_truncate_trace_text(body_text),
        envelope=_envelope_trace_payload(envelope),
        prompt_sha1=_prompt_sha1(system_prompt),
        root_policy_chars=len(str(root_policy_text or "")),
        inbox_policy_chars=len(str(inbox_policy_text or "")),
        max_completion_tokens=max_completion_tokens,
        reasoning_effort=reasoning_effort,
    )


def _emit_inbox_classifier_output_trace(
    extraction: StructuredExtractionResult[InboxItemDecision],
) -> None:
    if not _trace_inbox_classifier_enabled():
        return
    parsed = extraction.parsed
    emit_trace(
        "inbox_classifier_output",
        stage="inbox_classifier",
        status=getattr(getattr(extraction, "status", None), "value", None)
        or str(getattr(extraction, "status", "") or ""),
        error=getattr(extraction, "error", None),
        elapsed_ms=getattr(extraction, "elapsed_ms", None),
        decision=(
            parsed.model_dump(mode="json", exclude_none=True)
            if isinstance(parsed, InboxItemDecision)
            else None
        ),
    )


def _envelope_trace_payload(
    envelope: InboxMessageEnvelope | None,
) -> dict[str, object] | None:
    if envelope is None:
        return None
    return {
        "sender": envelope.sender,
        "to": list(envelope.to),
        "subject": envelope.subject,
        "channel": envelope.channel,
        "sender_canonical_entity": envelope.sender_canonical_entity,
        "self_addressed": envelope.self_addressed,
        "sender_is_canonical": envelope.sender_is_canonical,
    }


def _prompt_sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _truncate_trace_text(text: str) -> str:
    value = str(text or "").strip()
    if len(value) <= _BODY_TRACE_LIMIT:
        return value
    return value[: _BODY_TRACE_LIMIT - 1].rstrip() + "…"


__all__ = [
    "InboxItemDecision",
    "FinanceDocumentIngestWorkflowRequest",
    "FinancePaymentWorkflowRequest",
    "InvoiceEmailWorkflowRequest",
    "classify_inbox_item",
]
