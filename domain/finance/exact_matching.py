from __future__ import annotations

from .finance_record import FinanceRecord
from .line_item import LineItem


def normalize_finance_identity_text(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    normalized_chars = [char if char.isalnum() else " " for char in text]
    return " ".join("".join(normalized_chars).split())


def matches_finance_identity_text(recorded_value: object, requested_value: object) -> bool:
    requested = normalize_finance_identity_text(requested_value)
    recorded = normalize_finance_identity_text(recorded_value)
    if not requested or not recorded:
        return False
    return requested == recorded


def finance_record_matches_counterparty_name(record: FinanceRecord, counterparty: str) -> bool:
    return matches_finance_identity_text(record.counterparty, counterparty)


def finance_record_find_line_items_by_name(
    record: FinanceRecord,
    item_name: str,
) -> tuple[LineItem, ...]:
    return tuple(item for item in record.line_items if item.matches_name(item_name))


def finance_record_find_unique_line_item_by_name(
    record: FinanceRecord,
    item_name: str,
) -> LineItem | None:
    matches = finance_record_find_line_items_by_name(record, item_name)
    if len(matches) != 1:
        return None
    return matches[0]


def finance_record_resolve_unique_line_item_index_by_name(
    record: FinanceRecord,
    item_name: str,
) -> int | None:
    normalized_name = normalize_finance_identity_text(item_name)
    if not normalized_name:
        return None
    matches = tuple(
        index
        for index, item in enumerate(record.line_items)
        if item.matches_name(normalized_name)
    )
    if len(matches) != 1:
        return None
    return matches[0]


__all__ = [
    "finance_record_find_line_items_by_name",
    "finance_record_find_unique_line_item_by_name",
    "finance_record_matches_counterparty_name",
    "finance_record_resolve_unique_line_item_index_by_name",
    "matches_finance_identity_text",
    "normalize_finance_identity_text",
]
