from __future__ import annotations

from collections.abc import Sequence

from .exact_matching import (
    finance_record_find_unique_line_item_by_name,
    finance_record_matches_counterparty_name,
)
from .finance_record import FinanceRecord
from .money import Money
from .policy_models import (
    FinanceLineItemTotalCriteria,
    FinanceLineItemTotalResolution,
    FinanceLineItemValueCriteria,
    FinanceLineItemValueResolution,
)
from .selection import (
    infer_counterparty_from_line_item_records,
    nearest_date_cluster,
    resolve_line_item_scoped_amount,
    resolve_line_item_scoped_value,
)


def resolve_line_item_total(
    records: Sequence[FinanceRecord],
    *,
    criteria: FinanceLineItemTotalCriteria,
    anchor_record: FinanceRecord | None = None,
) -> FinanceLineItemTotalResolution | None:
    if not criteria.item_name:
        return None

    matching_records: tuple[FinanceRecord, ...]
    anchor_records: tuple[FinanceRecord, ...] = ()

    if anchor_record is not None:
        counterparty = anchor_record.counterparty
        record_type = anchor_record.record_type
        if not counterparty:
            return None
        matching_records = (anchor_record,)
    elif criteria.counterparty_name:
        matching_records = tuple(
            record
            for record in records
            if finance_record_matches_counterparty_name(record, criteria.counterparty_name)
            and record.matches_record_type(criteria.requested_record_type)
            and finance_record_find_unique_line_item_by_name(record, criteria.item_name)
            is not None
        )
        counterparties = {record.counterparty for record in matching_records if record.counterparty}
        record_types = {record.record_type for record in matching_records}
        if len(counterparties) != 1 or len(record_types) != 1:
            return None
        counterparty = next(iter(counterparties))
        record_type = next(iter(record_types))
    else:
        inferred = infer_counterparty_from_line_item_records(
            records,
            criteria.item_name,
            target_date=criteria.target_date,
            amount_hints=criteria.amount_hints,
        )
        if inferred is None:
            return None
        counterparty, record_type, inferred_paths = inferred
        inferred_paths_set = set(inferred_paths)
        anchor_records = tuple(
            record for record in records if record.path in inferred_paths_set
        )
        matching_records = tuple(
            record
            for record in records
            if record.counterparty.lower() == counterparty.lower()
            and record.record_type is record_type
            and record.matches_record_type(criteria.requested_record_type)
            and finance_record_find_unique_line_item_by_name(record, criteria.item_name)
            is not None
        )

    if not matching_records:
        return None

    scoped_records = matching_records
    if (
        criteria.target_date
        and criteria.counterparty_name
        and anchor_record is None
        and not anchor_records
    ):
        nearest_cluster = nearest_date_cluster(
            matching_records,
            target_date=criteria.target_date,
        )
        if nearest_cluster:
            scoped_records = nearest_cluster

    scoped_match = resolve_line_item_scoped_amount(
        scoped_records,
        criteria.item_name,
        target_date=criteria.target_date,
    )
    if scoped_match is None and anchor_records:
        scoped_match = resolve_line_item_scoped_amount(
            anchor_records,
            criteria.item_name,
            target_date=criteria.target_date,
        )
    if scoped_match is None and scoped_records is not matching_records:
        scoped_match = resolve_line_item_scoped_amount(
            matching_records,
            criteria.item_name,
            target_date=criteria.target_date,
        )
    if scoped_match is None:
        return None
    matched_record, amount = scoped_match
    return FinanceLineItemTotalResolution(
        counterparty=counterparty,
        record_type=record_type,
        amount=amount,
        matched_record=matched_record,
        anchor_records=anchor_records,
    )


def resolve_line_item_value(
    records: Sequence[FinanceRecord],
    *,
    criteria: FinanceLineItemValueCriteria,
    value_fields: Sequence[str],
) -> FinanceLineItemValueResolution | None:
    if not criteria.item_name:
        return None
    matching_records = tuple(
        record
        for record in records
        if record.matches_record_type(criteria.requested_record_type)
        and (
            not criteria.counterparty_name
            or finance_record_matches_counterparty_name(record, criteria.counterparty_name)
        )
        and (
            criteria.date_range is None
            or record.in_date_range(*criteria.date_range)
        )
        and finance_record_find_unique_line_item_by_name(record, criteria.item_name)
        is not None
    )
    if not matching_records:
        return None
    scoped_match = resolve_line_item_scoped_value(
        matching_records,
        criteria.item_name,
        value_fields=value_fields,
        target_date=criteria.target_date,
    )
    if scoped_match is None and criteria.date_range is not None:
        ranked_matches: list[tuple[str, float, str, FinanceRecord, object]] = []
        for record in matching_records:
            line_item = finance_record_find_unique_line_item_by_name(record, criteria.item_name)
            if line_item is None:
                continue
            value = line_item.value_for_fields(value_fields)
            if value is None or not record.date:
                continue
            ranked_matches.append(
                (
                    record.date,
                    float(value),
                    record.path,
                    record,
                    value,
                )
            )
        if ranked_matches:
            ranked_matches.sort(reverse=True)
            _, _, _, matched_record, amount = ranked_matches[0]
            scoped_match = (matched_record, amount)
    if scoped_match is None:
        return None
    matched_record, amount = scoped_match
    return FinanceLineItemValueResolution(
        amount=amount,
        matched_record=matched_record,
    )


__all__ = ["resolve_line_item_total", "resolve_line_item_value"]
