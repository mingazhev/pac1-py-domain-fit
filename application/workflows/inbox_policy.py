from __future__ import annotations

import re

from domain.inbox import InboxItem, InboxMessageEnvelope

from application.contracts import InvoiceBundleRequest
from .inbox_payloads import coerce_invoice_email_request
from .inbox_types import InboxClassifierVerdict, InboxWorkflowResult


def apply_inbox_classifier_policy(
    verdict: InboxClassifierVerdict,
    *,
    item: InboxItem,
    envelope: InboxMessageEnvelope | None,
    ref: str,
    body_text: str = "",
) -> InboxWorkflowResult | None:
    mixed_project_result = _clarify_mixed_project_lookup_and_delete(
        verdict,
        ref=ref,
        item=item,
        body_text=body_text,
    )
    if mixed_project_result is not None:
        return mixed_project_result
    if verdict.decision != "process_as_invoice_email":
        return None
    request = coerce_invoice_email_request(verdict.invoice_email_request)
    if request is None or envelope is None:
        return None
    grounding = (ref,) if ref else ()
    if isinstance(request, InvoiceBundleRequest):
        if not envelope.self_addressed:
            return InboxWorkflowResult(
                status="blocked",
                message=(
                    "Invoice bundle workflow is only allowed for self-addressed "
                    "internal inbox notes."
                ),
                grounding_refs=grounding,
                reason_code="invoice_email_bundle_external_sender_blocked",
                inbox_item_path=ref,
            )
        return None
    if not envelope.self_addressed and not envelope.sender_is_canonical:
        return InboxWorkflowResult(
            status="blocked",
            message=(
                f"Inbox item {item.path} is not allowed to trigger invoice resend "
                "because the sender is not a canonical trusted contact."
            ),
            grounding_refs=grounding,
            reason_code="invoice_email_sender_not_canonical",
            inbox_item_path=ref,
        )
    return None


_MIXED_PROJECT_DELETE_VERBS = (
    "delete",
    "remove",
    "archive",
)
_MIXED_PROJECT_QUERY_MARKERS = (
    "project",
    "start date",
    "started",
    "which started",
    "started earlier",
    "started first",
    "compare",
    "earlier",
    "first",
)


def _clarify_mixed_project_lookup_and_delete(
    verdict: InboxClassifierVerdict,
    *,
    ref: str,
    item: InboxItem,
    body_text: str,
) -> InboxWorkflowResult | None:
    if verdict.decision != "process_as_task":
        return None
    if str(verdict.continuation_intent or "").strip() != "project_query":
        return None
    normalized = _normalize_policy_text(
        str(verdict.sub_task_text or "").strip() or body_text
    )
    if not normalized:
        return None
    if not any(f" {verb} " in normalized for verb in _MIXED_PROJECT_DELETE_VERBS):
        return None
    if not any(marker in normalized for marker in _MIXED_PROJECT_QUERY_MARKERS):
        return None
    grounding = (ref,) if ref else ()
    return InboxWorkflowResult(
        status="clarify_missing",
        message=(
            f"Inbox item {item.path} mixes project lookup with a destructive "
            "follow-up and needs clarification before execution."
        ),
        grounding_refs=grounding,
        reason_code="inbox_workflow_mixed_project_lookup_requires_clarification",
        inbox_item_path=ref,
    )


def _normalize_policy_text(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", str(value or "").strip()).lower()
    return f" {collapsed} " if collapsed else ""


__all__ = ["apply_inbox_classifier_policy"]
