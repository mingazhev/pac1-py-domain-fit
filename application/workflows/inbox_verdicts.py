from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass

from domain.inbox import InboxItem

from .inbox_payloads import (
    coerce_finance_document_ingest_request,
    coerce_finance_payment_request,
    coerce_invoice_email_request,
)
from .inbox_types import (
    FinanceDocumentIngestWorkflowStep,
    FinancePaymentWorkflowStep,
    InboxClassifierVerdict,
    InboxWorkflowResult,
    InvoiceEmailWorkflowStep,
)


def workflow_payload(value: object) -> dict[str, object]:
    if is_dataclass(value):
        return {
            key: current
            for key, current in asdict(value).items()
            if current not in (None, "", ())
        }
    if hasattr(value, "__dict__"):
        return {
            key: current
            for key, current in vars(value).items()
            if current not in (None, "", ())
        }
    return {}


def result_from_classifier_verdict(
    verdict: InboxClassifierVerdict,
    item: InboxItem,
    ref: str,
    *,
    body_text: str,
) -> InboxWorkflowResult:
    grounding = (ref,) if ref else ()
    if verdict.decision == "refuse_security":
        return InboxWorkflowResult(
            status="blocked",
            message=(
                f"Inbox item {item.path} classified as security-refuse: "
                f"{verdict.reason or 'refused by typed classifier'}."
            ),
            grounding_refs=grounding,
            reason_code="inbox_workflow_security_refused",
            inbox_item_path=ref,
        )
    if verdict.decision == "refuse_out_of_scope":
        return InboxWorkflowResult(
            status="clarify_missing",
            message=(
                f"Inbox item {item.path} needs clarification because it is currently "
                f"outside the supported inbox execution scope: "
                f"{verdict.reason or 'no typed handler'}."
            ),
            grounding_refs=grounding,
            reason_code="inbox_workflow_requires_clarification",
            inbox_item_path=ref,
        )
    if verdict.decision == "clarify":
        return InboxWorkflowResult(
            status="clarify_missing",
            message=(
                f"Inbox item {item.path} needs clarification: "
                f"{verdict.reason or 'ambiguous body'}."
            ),
            grounding_refs=grounding,
            reason_code="inbox_workflow_requires_clarification",
            inbox_item_path=ref,
        )
    if verdict.decision == "process_as_task":
        continuation_intent = str(verdict.continuation_intent or "").strip() or None
        sub_text = str(verdict.sub_task_text or "").strip()
        if continuation_intent:
            return InboxWorkflowResult(
                status="continue",
                message=(
                    f"Inbox item {item.path} emitted a typed continuation "
                    f"intent ({continuation_intent}) for deterministic extraction."
                ),
                grounding_refs=grounding,
                reason_code="inbox_workflow_emitted_typed_intent",
                inbox_item_path=ref,
                processed_sub_task_text=sub_text or body_text,
                continuation_intent=continuation_intent,
            )
        if not sub_text:
            return InboxWorkflowResult(
                status="clarify_missing",
                message=(
                    f"Inbox item {item.path} classified as processable but "
                    "carried no sub_task_text."
                ),
                grounding_refs=grounding,
                reason_code="inbox_workflow_sub_task_missing",
                inbox_item_path=ref,
            )
        return InboxWorkflowResult(
            status="continue",
            message=(
                f"Inbox item {item.path} emitted a typed continuation "
                "sub-task for the orchestrator to re-interpret."
            ),
            grounding_refs=grounding,
            reason_code="inbox_workflow_emitted_sub_task",
            inbox_item_path=ref,
            processed_sub_task_text=sub_text,
        )
    if verdict.decision == "process_as_invoice_email":
        request = coerce_invoice_email_request(verdict.invoice_email_request)
        if request is None:
            return InboxWorkflowResult(
                status="clarify_missing",
                message=(
                    f"Inbox item {item.path} classified as invoice email "
                    "workflow but carried no typed payload."
                ),
                grounding_refs=grounding,
                reason_code="inbox_workflow_invoice_email_missing",
                inbox_item_path=ref,
            )
        return InboxWorkflowResult(
            status="continue",
            message=(
                f"Inbox item {item.path} emitted a typed invoice email "
                "workflow for deterministic execution."
            ),
            grounding_refs=grounding,
            reason_code="inbox_workflow_emitted_invoice_email",
            next_step=InvoiceEmailWorkflowStep(request=request, evidence_ref=ref),
            inbox_item_path=ref,
        )
    if verdict.decision == "process_as_finance_payment":
        request = coerce_finance_payment_request(verdict.finance_payment_request)
        if request is None:
            return InboxWorkflowResult(
                status="clarify_missing",
                message=(
                    f"Inbox item {item.path} classified as finance payment "
                    "workflow but carried no typed payload."
                ),
                grounding_refs=grounding,
                reason_code="inbox_workflow_finance_payment_missing",
                inbox_item_path=ref,
            )
        return InboxWorkflowResult(
            status="continue",
            message=(
                f"Inbox item {item.path} emitted a typed finance payment "
                "workflow for deterministic execution."
            ),
            grounding_refs=grounding,
            reason_code="inbox_workflow_emitted_finance_payment",
            next_step=FinancePaymentWorkflowStep(request=request, evidence_ref=ref),
            inbox_item_path=ref,
        )
    if verdict.decision == "process_as_finance_document_ingest":
        request = coerce_finance_document_ingest_request(
            verdict.finance_document_ingest_request
        )
        if request is None:
            return InboxWorkflowResult(
                status="clarify_missing",
                message=(
                    f"Inbox item {item.path} classified as finance document "
                    "ingest workflow but carried no typed payload."
                ),
                grounding_refs=grounding,
                reason_code="inbox_workflow_finance_document_ingest_missing",
                inbox_item_path=ref,
            )
        return InboxWorkflowResult(
            status="continue",
            message=(
                f"Inbox item {item.path} emitted a typed finance document "
                "ingest workflow for deterministic execution."
            ),
            grounding_refs=grounding,
            reason_code="inbox_workflow_emitted_finance_document_ingest",
            next_step=FinanceDocumentIngestWorkflowStep(request=request, evidence_ref=ref),
            inbox_item_path=ref,
        )
    return InboxWorkflowResult(
        status="resolved",
        message=(
            f"Processed inbox item {item.path}: "
            f"{verdict.reason or 'no actionable step'}; cleared from queue."
        ),
        grounding_refs=grounding,
        reason_code="inbox_workflow_no_actionable_step",
        inbox_item_path=ref,
    )


__all__ = ["result_from_classifier_verdict", "workflow_payload"]
