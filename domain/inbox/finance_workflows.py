from __future__ import annotations
from collections.abc import Sequence
from typing import Literal

from domain.cast import CastEntity, CastIdentityProjection
from domain.finance import (
    FinanceRecord,
    RecordType,
    finance_record_matches_entity,
    select_entity_linked_bills,
    select_entity_linked_finance_records,
    select_entity_linked_invoices,
)


def select_finance_documents_for_entity(
    records: Sequence[FinanceRecord],
    *,
    entity: CastEntity | CastIdentityProjection,
    record_type: Literal["invoice", "bill", "any"] = "any",
) -> tuple[FinanceRecord, ...]:
    normalized_type = str(record_type or "any").strip().lower()
    if normalized_type == "invoice":
        return tuple(
            select_entity_linked_invoices(
                tuple(record for record in records if record.matches_record_type(RecordType.INVOICE)),
                entity=entity,
            )
        )
    if normalized_type == "bill":
        return tuple(
            select_entity_linked_bills(
                tuple(record for record in records if record.matches_record_type(RecordType.BILL)),
                entity=entity,
            )
        )
    return tuple(
        select_entity_linked_finance_records(
            records,
            entity=entity,
            record_type=None,
        )
    )


__all__ = [
    "finance_record_matches_entity",
    "select_finance_documents_for_entity",
]
