from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


InvoiceAttachmentOrder = Literal["reverse_chronological", "chronological"]
InvoiceBundleSelectionMode = Literal["oldest", "latest"]


@dataclass(frozen=True, slots=True)
class InvoiceResendRequest:
    mode: Literal["dated", "latest"]
    counterparty: str
    target_date: str = ""
    record_hint: str = ""


@dataclass(frozen=True, slots=True)
class InvoiceBundleRequest:
    count: int
    target_query: str
    selection_mode: InvoiceBundleSelectionMode = "latest"
    attachment_order: InvoiceAttachmentOrder = "reverse_chronological"


@dataclass(frozen=True, slots=True)
class FinancePaymentRequest:
    action: Literal["mark_paid", "settle_payment"]
    record_type: Literal["invoice", "bill", "any"] = "any"
    counterparty: str = ""
    target_date: str = ""
    amount_eur: float | None = None
    reference_number: str = ""
    alias: str = ""
    project: str = ""
    related_entity: str = ""
    settlement_reference: str = ""
    settlement_channel: Literal[
        "bank_transfer",
        "card",
        "cash",
        "manual_attestation",
        "",
    ] = ""
    settlement_date: str = ""


@dataclass(frozen=True, slots=True)
class FinanceDocumentIngestRequest:
    target_paths: tuple[str, ...] = ()
    record_type: Literal["invoice", "bill", "any"] = "any"
    entity_query: str = ""
    target_scope: Literal["single", "all_matches"] = "single"
    family_reference: str = ""


__all__ = [
    "FinanceDocumentIngestRequest",
    "FinancePaymentRequest",
    "InvoiceAttachmentOrder",
    "InvoiceBundleRequest",
    "InvoiceBundleSelectionMode",
    "InvoiceResendRequest",
]
