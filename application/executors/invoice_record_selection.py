from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from domain.cast import CastEntity, CastIdentityProjection
from domain.finance import (
    FinanceRecord,
    Invoice,
    finance_record_matches_hint,
    finance_record_matches_entity,
    select_entity_linked_invoices,
)
from domain.finance.exact_matching import finance_record_matches_counterparty_name


InvoiceAttachmentOrder = Literal["reverse_chronological", "chronological"]
InvoiceBundleSelectionMode = Literal["oldest", "latest"]


def _normalize_invoice_date(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    iso_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso_match is not None:
        return text
    day_first_match = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", text)
    if day_first_match is not None:
        day, month, year = day_first_match.groups()
        return f"{year}-{month}-{day}"
    return text


def _alternate_ambiguous_iso_date(value: object) -> str:
    text = str(value or "").strip()
    iso_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso_match is None:
        return ""
    year, month, day = iso_match.groups()
    if month == day:
        return ""
    try:
        month_number = int(month)
        day_number = int(day)
    except ValueError:
        return ""
    if not (1 <= month_number <= 12 and 1 <= day_number <= 12):
        return ""
    return f"{year}-{day}-{month}"


def invoice_record_matches_entity(
    record: Invoice,
    entity: CastEntity | CastIdentityProjection,
) -> bool:
    return finance_record_matches_entity(record, entity)


def select_invoice_resend_record(
    records: Sequence[Invoice],
    *,
    mode: Literal["dated", "latest"],
    counterparty: str,
    target_date: str = "",
    record_hint: str = "",
    select_invoice_record_subset=None,
) -> Invoice | None:
    requested_date = _normalize_invoice_date(target_date)
    matches: list[FinanceRecord] = []
    for record in records:
        if counterparty and not finance_record_matches_counterparty_name(record, counterparty):
            continue
        if mode == "dated" and requested_date and _normalize_invoice_date(record.date) != requested_date:
            continue
        matches.append(record)

    if not matches and mode == "dated":
        alternate_date = _alternate_ambiguous_iso_date(target_date)
        if alternate_date:
            for record in records:
                if counterparty and not finance_record_matches_counterparty_name(record, counterparty):
                    continue
                if _normalize_invoice_date(record.date) != alternate_date:
                    continue
                matches.append(record)

    if not matches:
        return None
    if str(record_hint or "").strip():
        hinted = tuple(
            record for record in matches if finance_record_matches_hint(record, record_hint)
        )
        if len(hinted) == 1:
            return hinted[0]
        if select_invoice_record_subset is not None:
            picked = select_invoice_record_subset(record_hint, hinted or tuple(matches))
            selected = tuple(
                (hinted or tuple(matches))[index]
                for index in picked
                if isinstance(index, int)
                and 0 <= index < len(hinted or tuple(matches))
            )
            if len(selected) == 1:
                return selected[0]
        return None
    if mode == "dated":
        return sorted(matches, key=lambda item: item.path)[0]
    return max(matches, key=lambda item: (item.date, item.path))


def select_invoice_bundle_records(
    records: Sequence[Invoice],
    linked_entity: CastEntity | CastIdentityProjection,
    *,
    count: int,
    selection_mode: InvoiceBundleSelectionMode = "latest",
    attachment_order: InvoiceAttachmentOrder = "reverse_chronological",
) -> tuple[Invoice, ...]:
    matches = [
        record for record in select_entity_linked_invoices(records, entity=linked_entity)
    ]
    if not matches:
        return ()
    ordered = sorted(matches, key=lambda item: (item.date, item.path))
    if selection_mode == "latest":
        selected = tuple(reversed(ordered[-count:]))
    else:
        selected = tuple(ordered[:count])
    return order_invoice_records_for_reply(
        selected,
        attachment_order=attachment_order,
    )


def order_invoice_records_for_reply(
    records: Sequence[Invoice],
    *,
    request_text: str = "",
    attachment_order: InvoiceAttachmentOrder | None = None,
) -> tuple[Invoice, ...]:
    _ = request_text
    resolved_order = attachment_order or "reverse_chronological"
    reverse = resolved_order == "reverse_chronological"
    return tuple(sorted(records, key=lambda item: (item.date, item.path), reverse=reverse))


__all__ = [
    "InvoiceAttachmentOrder",
    "InvoiceBundleSelectionMode",
    "invoice_record_matches_entity",
    "order_invoice_records_for_reply",
    "select_invoice_bundle_records",
    "select_invoice_resend_record",
]
