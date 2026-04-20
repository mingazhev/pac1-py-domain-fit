from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from .exact_matching import finance_record_find_unique_line_item_by_name
from .finance_record import FinanceRecord
from .line_item import LineItem
from .money import Number, money_to_number, normalize_number
from .record_type import RecordType


def infer_counterparty_from_line_item_records(
    records: Sequence[FinanceRecord],
    item_name: str,
    *,
    target_date: str | None = None,
    amount_hints: Sequence[Number] = (),
) -> tuple[str, RecordType, tuple[str, ...]] | None:
    matched_records = [
        record
        for record in records
        if finance_record_find_unique_line_item_by_name(record, item_name) is not None
    ]
    if not matched_records:
        return None
    if target_date:
        exact_dated = [record for record in matched_records if record.date == target_date]
        if exact_dated:
            matched_records = exact_dated
    if amount_hints:
        ranked_matches: list[tuple[int, str, str, FinanceRecord]] = []
        for record in matched_records:
            line_item = finance_record_find_unique_line_item_by_name(record, item_name)
            if line_item is None:
                continue
            ranked_matches.append(
                (
                    line_item.numeric_match_score(amount_hints),
                    record.date,
                    record.path,
                    record,
                )
            )
        if ranked_matches:
            ranked_matches.sort(
                key=lambda item: (item[0], item[1], item[2]),
                reverse=True,
            )
            best_numeric_score = ranked_matches[0][0]
            best_records = [
                item[3]
                for item in ranked_matches
                if item[0] == best_numeric_score
            ]
            if best_numeric_score > 0 and len(best_records) == 1 and best_records[0].counterparty:
                best = best_records[0]
                refs = (best.path,) if best.path else ()
                return best.counterparty, best.record_type, refs
            if best_numeric_score > 0:
                grouped_records: dict[tuple[str, RecordType], list[FinanceRecord]] = {}
                for record in best_records:
                    if not record.counterparty:
                        continue
                    grouped_records.setdefault((record.counterparty, record.record_type), []).append(record)
                if len(grouped_records) == 1:
                    (counterparty, record_type), group = next(iter(grouped_records.items()))
                    refs = tuple(sorted({record.path for record in group if record.path}))
                    return counterparty, record_type, refs
    counterparties = {record.counterparty for record in matched_records if record.counterparty}
    record_types = {record.record_type for record in matched_records}
    if len(counterparties) != 1 or len(record_types) != 1:
        return None
    refs = tuple(sorted({record.path for record in matched_records if record.path}))
    return next(iter(counterparties)), next(iter(record_types)), refs


def resolve_line_item_scoped_amount(
    records: Sequence[FinanceRecord],
    item_name: str,
    *,
    target_date: str | None = None,
) -> tuple[FinanceRecord, Number] | None:
    matches: list[tuple[FinanceRecord, Number, int]] = []
    for record in records:
        line_item = finance_record_find_unique_line_item_by_name(record, item_name)
        if line_item is None:
            continue
        amount = _line_item_total_amount(record, line_item)
        if amount is None:
            continue
        matches.append((record, amount, 1))
    return _resolve_best_record_match(matches, target_date=target_date)


def resolve_line_item_scoped_value(
    records: Sequence[FinanceRecord],
    item_name: str,
    *,
    value_fields: Sequence[str],
    target_date: str | None = None,
) -> tuple[FinanceRecord, Number] | None:
    matches: list[tuple[FinanceRecord, Number, int]] = []
    for record in records:
        line_item = finance_record_find_unique_line_item_by_name(record, item_name)
        if line_item is None:
            continue
        value = line_item.value_for_fields(value_fields)
        if value is None:
            continue
        matches.append((record, value, 1))
    return _resolve_best_record_match(matches, target_date=target_date)


def nearest_date_cluster(
    records: Sequence[FinanceRecord],
    *,
    target_date: str,
) -> tuple[FinanceRecord, ...]:
    try:
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        return ()
    ranked: list[tuple[int, str, FinanceRecord]] = []
    for record in records:
        if not record.date:
            continue
        try:
            record_date = datetime.strptime(record.date, "%Y-%m-%d").date()
        except ValueError:
            continue
        ranked.append((abs((record_date - target).days), record.date, record))
    if not ranked:
        return ()
    ranked.sort(key=lambda item: (item[0], item[1]))
    best_distance, best_date, _ = ranked[0]
    return tuple(
        record
        for distance, date, record in ranked
        if distance == best_distance and date == best_date
    )


def _resolve_best_record_match(
    matches: Sequence[tuple[FinanceRecord, Number, int]],
    *,
    target_date: str | None,
) -> tuple[FinanceRecord, Number] | None:
    if len(matches) == 1:
        record, value, _ = matches[0]
        return (record, value)
    if not matches or not target_date:
        return None
    exact_matches = [match for match in matches if match[0].date == target_date]
    if len(exact_matches) == 1:
        record, value, _ = exact_matches[0]
        return (record, value)
    if len(exact_matches) > 1:
        return None

    ranked: list[tuple[int, str, FinanceRecord, Number]] = []
    for record, value, match_score in matches:
        del match_score
        if not record.date:
            continue
        try:
            record_date = datetime.fromisoformat(record.date).date()
            target = datetime.fromisoformat(target_date).date()
        except ValueError:
            continue
        ranked.append((abs((record_date - target).days), record.date, record, value))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]))
    best_distance = ranked[0][0]
    nearest = [item for item in ranked if item[0] == best_distance]
    if len(nearest) != 1:
        return None
    _, _, record, value = nearest[0]
    return record, value


def _line_item_total_amount(record: FinanceRecord, line_item: LineItem) -> Number | None:
    unit = money_to_number(line_item.unit_eur)
    quantity = line_item.quantity
    derived_total: Number | None = None
    if unit is not None and quantity is not None:
        derived_total = normalize_number(float(unit) * float(quantity))
    if line_item.line_eur is not None:
        value = money_to_number(line_item.line_eur)
        if value is not None:
            record_total = money_to_number(record.total_eur)
            if record_total is not None and derived_total is not None and abs(float(derived_total) - float(value)) > 1e-9:
                if abs(float(record_total) - float(value)) <= 1e-9:
                    return value
                if abs(float(record_total) - float(derived_total)) <= 1e-9:
                    return derived_total
            if (
                derived_total is not None
                and unit is not None
                and quantity is not None
                and float(quantity) > 1.0
                and abs(float(value) - float(unit)) <= 1e-9
                and abs(float(derived_total) - float(value)) > 1e-9
            ):
                return derived_total
            return value
    if derived_total is not None:
        return derived_total
    return unit


__all__ = [
    "infer_counterparty_from_line_item_records",
    "nearest_date_cluster",
    "resolve_line_item_scoped_amount",
    "resolve_line_item_scoped_value",
]
