from __future__ import annotations

from collections.abc import Callable, Sequence

from domain.cast import CastEntity
from domain.inbox import InboxItem, envelope_from_inbox_item
from domain.security import detect_injection_patterns, sanitize_security_text
from .inbox_payloads import (
    coerce_finance_document_ingest_request,
    coerce_finance_payment_request,
    coerce_invoice_email_request,
)
from .inbox_policy import apply_inbox_classifier_policy
from .inbox_types import (
    canonical_entity_for_sender,
    FinanceDocumentIngestWorkflowStep,
    FinancePaymentWorkflowStep,
    InboxClassifier,
    InboxClassifierVerdict,
    InboxWorkflowResult,
    InvoiceEmailWorkflowStep,
)
from .inbox_verdicts import result_from_classifier_verdict


def resolve_inbox_workflow_step(
    inbox_items: Sequence[InboxItem],
    *,
    filename_only: bool,
    task_text: str,
    classify_body: InboxClassifier | None = None,
    cast_entities: Sequence[CastEntity] | None = None,
    emit_trace_fn: Callable[..., None] | None = None,
) -> InboxWorkflowResult:
    if not inbox_items:
        return InboxWorkflowResult(
            status="clarify_missing",
            message="No inbox items are loaded in canonical context.",
            grounding_refs=(),
            reason_code="inbox_workflow_queue_empty",
        )

    next_item = _pick_next_item(inbox_items)
    ref = _ref_for(next_item)

    if filename_only:
        return InboxWorkflowResult(
            status="resolved",
            message=next_item.path,
            grounding_refs=(ref,) if ref else (),
            reason_code="inbox_workflow_filename_resolved",
            inbox_item_path=ref,
        )

    body_text = _inbox_body_text(next_item)
    if body_text:
        sanitized = sanitize_security_text(body_text)
        findings = tuple(detect_injection_patterns(sanitized))
        if findings:
            return InboxWorkflowResult(
                status="blocked",
                message=(
                    f"Inbox item {next_item.path} tripped injection preflight "
                    f"on its body content; refused."
                ),
                grounding_refs=(ref,) if ref else (),
                reason_code="inbox_workflow_injection_refused",
                inbox_item_path=ref,
            )

        if classify_body is not None:
            canonical_entity = canonical_entity_for_sender(
                str(next_item.sender or ""), cast_entities
            )
            envelope = envelope_from_inbox_item(
                next_item,
                sender_canonical_entity=canonical_entity,
            )
            verdict = classify_body(sanitized, envelope)
            if verdict is not None:
                policy_result = apply_inbox_classifier_policy(
                    verdict,
                    item=next_item,
                    envelope=envelope,
                    ref=ref,
                    body_text=sanitized,
                )
                if policy_result is not None:
                    return policy_result
                return result_from_classifier_verdict(
                    verdict,
                    next_item,
                    ref,
                    body_text=sanitized,
                )

    return InboxWorkflowResult(
        status="clarify_missing",
        message=(
            f"Inbox item {next_item.path} could not be classified into a "
            "typed continuation."
        ),
        grounding_refs=(ref,) if ref else (),
        reason_code="inbox_workflow_classifier_unresolved",
        inbox_item_path=ref,
    )

def _pick_next_item(items: Sequence[InboxItem]) -> InboxItem:
    def _key(item: InboxItem) -> tuple[str, str]:
        return (str(item.received_at or ""), str(item.path or ""))

    return sorted(items, key=_key)[0]


def _ref_for(item: InboxItem) -> str:
    path = str(item.path or "").strip()
    if not path:
        return ""
    return path if path.startswith("/") else f"/{path}"


def _inbox_body_text(item: InboxItem) -> str:
    pieces = [
        str(item.subject or "").strip(),
        str(item.body or "").strip(),
    ]
    return "\n".join(piece for piece in pieces if piece)


__all__ = [
    "coerce_finance_document_ingest_request",
    "coerce_finance_payment_request",
    "coerce_invoice_email_request",
    "FinanceDocumentIngestWorkflowStep",
    "FinancePaymentWorkflowStep",
    "InboxClassifierVerdict",
    "InvoiceEmailWorkflowStep",
    "InboxWorkflowResult",
    "resolve_inbox_workflow_step",
]
