from __future__ import annotations

from collections.abc import Sequence

from .finance_record import FinanceRecord, RecordType
from .money import Money, money_number_from_cents
from .policy_models import FinanceServiceLineRevenueResolution
from .exact_matching import finance_record_find_line_items_by_name


def resolve_service_line_total(
    records: Sequence[FinanceRecord],
    *,
    item_name: str,
    since_date: str,
) -> FinanceServiceLineRevenueResolution | None:
    if not item_name or not since_date:
        return None

    matched_records: list[FinanceRecord] = []
    total_cents = 0
    for record in records:
        if record.record_type is not RecordType.INVOICE:
            continue
        if not record.date or record.date < since_date:
            continue
        line_items = finance_record_find_line_items_by_name(record, item_name)
        if not line_items:
            continue
        record_total_cents = 0
        matched_amount = False
        for line_item in line_items:
            amount = (
                line_item.line_eur if line_item.line_eur is not None else line_item.unit_eur
            )
            if amount is None:
                continue
            if isinstance(amount, Money):
                record_total_cents += amount.cents
            else:
                money_value = Money.from_number(amount)
                if money_value is None:
                    continue
                record_total_cents += money_value.cents
            matched_amount = True
        if not matched_amount:
            continue
        total_cents += record_total_cents
        matched_records.append(record)

    if not matched_records:
        return None
    normalized_total = money_number_from_cents(total_cents)
    return FinanceServiceLineRevenueResolution(
        amount=normalized_total,
        matched_records=tuple(matched_records),
    )


__all__ = ["resolve_service_line_total"]
