from __future__ import annotations

from collections.abc import Sequence

from .exact_matching import finance_record_matches_counterparty_name
from .finance_record import FinanceRecord
from .money import money_number_from_cents
from .policy_models import (
    FinanceCounterpartyTotalCriteria,
    FinanceCounterpartyTotalResolution,
)
from .selection import (
    infer_counterparty_from_line_item_records,
    resolve_line_item_scoped_amount,
)


def resolve_counterparty_total(
    records: Sequence[FinanceRecord],
    *,
    criteria: FinanceCounterpartyTotalCriteria,
    anchor_record: FinanceRecord | None = None,
) -> FinanceCounterpartyTotalResolution | None:
    matching_records: tuple[FinanceRecord, ...]
    anchor_records: tuple[FinanceRecord, ...] = ()

    if anchor_record is not None:
        counterparty = anchor_record.counterparty
        record_type = anchor_record.record_type
        if not counterparty:
            return None
        matching_records = tuple(
            record
            for record in records
            if record.counterparty.lower() == counterparty.lower()
            and record.record_type is record_type
            and record.has_total()
        )
    else:
        if criteria.counterparty_name:
            candidate_records = tuple(
                record
                for record in records
                if finance_record_matches_counterparty_name(
                    record, criteria.counterparty_name
                )
                and record.matches_record_type(criteria.requested_record_type)
                and record.has_total()
            )
            counterparties = {record.counterparty for record in candidate_records}
            record_types = {record.record_type for record in candidate_records}
            if len(counterparties) != 1 or len(record_types) != 1:
                return None
            counterparty = next(iter(counterparties))
            record_type = next(iter(record_types))
            matching_records = candidate_records
        else:
            if not criteria.item_name:
                return None
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
                and record.has_total()
            )

    if not matching_records:
        return None

    if criteria.line_item_scope:
        if not criteria.item_name:
            return None
        scoped_records = matching_records
        if anchor_record is not None:
            scoped_records = (anchor_record,)
        elif anchor_records:
            scoped_records = anchor_records
        elif criteria.target_date:
            exact_dated = tuple(
                record for record in matching_records if record.date == criteria.target_date
            )
            if exact_dated:
                scoped_records = exact_dated
        scoped_match = resolve_line_item_scoped_amount(
            scoped_records,
            criteria.item_name,
            target_date=criteria.target_date,
        )
        if scoped_match is None and scoped_records != matching_records:
            scoped_match = resolve_line_item_scoped_amount(
                matching_records,
                criteria.item_name,
                target_date=criteria.target_date,
            )
        if scoped_match is None:
            return None
        matched_record, amount = scoped_match
        return FinanceCounterpartyTotalResolution(
            counterparty=counterparty,
            record_type=record_type,
            amount=amount,
            matched_records=(matched_record,),
            line_item_scope=True,
        )

    total_cents = sum(
        record.total_eur.cents
        for record in matching_records
        if record.total_eur is not None
    )
    normalized_total = money_number_from_cents(total_cents)
    return FinanceCounterpartyTotalResolution(
        counterparty=counterparty,
        record_type=record_type,
        amount=normalized_total,
        matched_records=matching_records,
        anchor_records=anchor_records,
        line_item_scope=False,
    )


__all__ = ["resolve_counterparty_total"]
