from __future__ import annotations

from collections.abc import Mapping

from application.contracts import (
    FinanceDocumentIngestRequest,
    FinancePaymentRequest,
    InvoiceBundleRequest,
    InvoiceResendRequest,
)


def coerce_invoice_email_request(
    payload: InvoiceResendRequest | InvoiceBundleRequest | Mapping[str, object] | object | None,
) -> InvoiceResendRequest | InvoiceBundleRequest | None:
    if isinstance(payload, (InvoiceResendRequest, InvoiceBundleRequest)):
        return payload
    if payload is None:
        return None
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(exclude_none=True)
    if not isinstance(payload, Mapping):
        return None
    workflow_kind = str(payload.get("workflow_kind") or "").strip()
    if workflow_kind == "invoice_resend":
        mode = str(payload.get("mode") or "").strip()
        counterparty = str(payload.get("counterparty") or "").strip()
        target_date = str(payload.get("target_date") or "").strip()
        record_hint = str(payload.get("record_hint") or "").strip()
        if mode not in {"dated", "latest"} or not counterparty:
            return None
        if mode == "dated" and not target_date:
            return None
        return InvoiceResendRequest(
            mode=mode,
            counterparty=counterparty,
            target_date=target_date,
            record_hint=record_hint,
        )
    if workflow_kind != "invoice_bundle":
        return None
    target_query = str(payload.get("target_query") or "").strip()
    selection_mode = str(payload.get("selection_mode") or "").strip()
    attachment_order = str(payload.get("attachment_order") or "").strip()
    try:
        count = int(payload.get("count"))
    except (TypeError, ValueError):
        return None
    if count <= 0 or not target_query:
        return None
    if selection_mode not in {"oldest", "latest"}:
        selection_mode = "latest"
    if attachment_order not in {"reverse_chronological", "chronological"}:
        attachment_order = "reverse_chronological"
    return InvoiceBundleRequest(
        count=count,
        target_query=target_query,
        selection_mode=selection_mode,
        attachment_order=attachment_order,
    )


def coerce_finance_payment_request(
    payload: FinancePaymentRequest | Mapping[str, object] | object | None,
) -> FinancePaymentRequest | None:
    if isinstance(payload, FinancePaymentRequest):
        return payload
    if payload is None:
        return None
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(exclude_none=True)
    if not isinstance(payload, Mapping):
        return None
    action = str(payload.get("action") or "").strip()
    if action not in {"mark_paid", "settle_payment"}:
        return None
    record_type = str(payload.get("record_type") or "any").strip()
    if record_type not in {"invoice", "bill", "any"}:
        record_type = "any"
    channel = str(payload.get("settlement_channel") or "").strip()
    if channel not in {"bank_transfer", "card", "cash", "manual_attestation", ""}:
        channel = ""
    amount = payload.get("amount_eur")
    if not isinstance(amount, int | float):
        amount = None
    request = FinancePaymentRequest(
        action=action,
        record_type=record_type,  # type: ignore[arg-type]
        counterparty=str(payload.get("counterparty") or "").strip(),
        target_date=str(payload.get("target_date") or "").strip(),
        amount_eur=float(amount) if isinstance(amount, int | float) else None,
        reference_number=str(payload.get("reference_number") or "").strip(),
        alias=str(payload.get("alias") or "").strip(),
        project=str(payload.get("project") or "").strip(),
        related_entity=str(payload.get("related_entity") or "").strip(),
        settlement_reference=str(payload.get("settlement_reference") or "").strip(),
        settlement_channel=channel,  # type: ignore[arg-type]
        settlement_date=str(payload.get("settlement_date") or "").strip(),
    )
    if not any(
        str(value or "").strip()
        for value in (
            request.counterparty,
            request.target_date,
            request.reference_number,
            request.alias,
            request.project,
            request.related_entity,
        )
    ):
        return None
    return request


def coerce_finance_document_ingest_request(
    payload: FinanceDocumentIngestRequest | Mapping[str, object] | object | None,
) -> FinanceDocumentIngestRequest | None:
    if isinstance(payload, FinanceDocumentIngestRequest):
        return payload
    if payload is None:
        return None
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(exclude_none=True)
    if not isinstance(payload, Mapping):
        return None
    raw_paths = payload.get("target_paths") or ()
    if isinstance(raw_paths, str):
        raw_paths = (raw_paths,)
    if not isinstance(raw_paths, tuple | list):
        raw_paths = ()
    target_paths = tuple(
        normalized
        for path in raw_paths
        if (normalized := _normalize_explicit_finance_target_path(path))
    )
    record_type = str(payload.get("record_type") or "any").strip()
    if record_type not in {"invoice", "bill", "any"}:
        record_type = "any"
    entity_query = str(payload.get("entity_query") or "").strip()
    target_scope = str(payload.get("target_scope") or "single").strip()
    family_reference = str(payload.get("family_reference") or "").strip()
    if target_scope not in {"single", "all_matches"}:
        target_scope = "single"
    if not target_paths and not entity_query:
        return None
    return FinanceDocumentIngestRequest(
        target_paths=target_paths,
        record_type=record_type,  # type: ignore[arg-type]
        entity_query=entity_query,
        target_scope=target_scope,  # type: ignore[arg-type]
        family_reference=family_reference,
    )


def _normalize_explicit_finance_target_path(value: object) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text or text == "/":
        return ""
    if not text.startswith("/"):
        text = f"/{text}"
    leaf = text.rsplit("/", 1)[-1].strip()
    if not leaf or "." not in leaf:
        return ""
    if not leaf.lower().endswith(".md"):
        return ""
    return text


__all__ = [
    "coerce_finance_document_ingest_request",
    "coerce_finance_payment_request",
    "coerce_invoice_email_request",
]
