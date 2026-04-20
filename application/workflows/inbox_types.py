from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from application.contracts import (
    FinanceDocumentIngestRequest,
    FinancePaymentRequest,
    InvoiceBundleRequest,
    InvoiceResendRequest,
)
from domain.cast import CastEntity
from domain.inbox import InboxMessageEnvelope


InboxClassifier = Callable[
    [str, InboxMessageEnvelope | None],
    "InboxClassifierVerdict | None",
]


@dataclass(frozen=True, slots=True)
class InvoiceEmailWorkflowStep:
    request: InvoiceResendRequest | InvoiceBundleRequest
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class FinancePaymentWorkflowStep:
    request: FinancePaymentRequest
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class FinanceDocumentIngestWorkflowStep:
    request: FinanceDocumentIngestRequest
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class InboxClassifierVerdict:
    """Typed carrier used when the LLM classifier runs against a body."""

    decision: Literal[
        "process_as_task",
        "process_as_invoice_email",
        "process_as_finance_payment",
        "process_as_finance_document_ingest",
        "refuse_security",
        "refuse_out_of_scope",
        "clarify",
        "no_actionable_step",
    ]
    reason: str = ""
    sub_task_text: str | None = None
    continuation_intent: str | None = None
    invoice_email_request: (
        InvoiceResendRequest | InvoiceBundleRequest | Mapping[str, object] | None
    ) = None
    finance_payment_request: FinancePaymentRequest | Mapping[str, object] | None = None
    finance_document_ingest_request: (
        FinanceDocumentIngestRequest | Mapping[str, object] | None
    ) = None


@dataclass(frozen=True, slots=True)
class InboxWorkflowResult:
    status: Literal["resolved", "clarify_missing", "blocked", "continue"]
    message: str
    grounding_refs: tuple[str, ...]
    reason_code: str
    next_step: (
        InvoiceEmailWorkflowStep
        | FinancePaymentWorkflowStep
        | FinanceDocumentIngestWorkflowStep
        | None
    ) = None
    inbox_item_path: str | None = None
    processed_sub_task_text: str | None = None
    continuation_intent: str | None = None


def canonical_entity_for_sender(
    sender: str,
    cast_entities: list[CastEntity] | tuple[CastEntity, ...] | None,
) -> str | None:
    from domain.cast import resolve_sender_canonical_entity

    if not cast_entities:
        return None
    projection = resolve_sender_canonical_entity(cast_entities, sender)
    if projection is None:
        return None
    return (
        str(projection.title or "").strip()
        or str(projection.entity_slug or "").strip()
        or str(projection.entity_id or "").strip()
        or None
    )


__all__ = [
    "canonical_entity_for_sender",
    "FinanceDocumentIngestWorkflowStep",
    "FinancePaymentWorkflowStep",
    "InboxClassifier",
    "InboxClassifierVerdict",
    "InboxWorkflowResult",
    "InvoiceEmailWorkflowStep",
]
