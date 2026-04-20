from __future__ import annotations

from collections.abc import Sequence

from domain.cast import CastEntity, CastIdentityProjection

from .finance_record import FinanceRecord
from .invoice import Invoice
from .bill import Bill
from .record_type import RecordType


def _normalize_entity_link(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _entity_identity_terms(
    entity: CastEntity | CastIdentityProjection,
) -> tuple[str, ...]:
    if isinstance(entity, CastEntity):
        return tuple(
            term for term in entity.canonical_terms if str(term or "").strip()
        )
    return tuple(
        dict.fromkeys(
            term
            for term in (
                entity.entity_id,
                entity.entity_slug,
                entity.title,
                entity.alias,
                entity.primary_contact_email,
                entity.relationship,
                entity.kind,
                *(entity.identity_terms or ()),
                *(entity.alias_terms or ()),
            )
            if str(term or "").strip()
        )
    )


def finance_record_matches_entity(
    record: FinanceRecord,
    entity: CastEntity | CastIdentityProjection,
) -> bool:
    related_entity = _normalize_entity_link(getattr(record, "related_entity", ""))
    if not related_entity:
        return False
    for term in _entity_identity_terms(entity):
        normalized_term = _normalize_entity_link(term)
        if not normalized_term:
            continue
        if related_entity == normalized_term:
            return True
    return False


def select_entity_linked_finance_records(
    records: Sequence[FinanceRecord],
    *,
    entity: CastEntity | CastIdentityProjection,
    record_type: str | RecordType | None = None,
) -> tuple[FinanceRecord, ...]:
    return tuple(
        sorted(
            (
                record
                for record in records
                if record.matches_record_type(record_type)
                and finance_record_matches_entity(record, entity)
            ),
            key=lambda item: (
                str(getattr(item, "date", "") or ""),
                str(getattr(item, "path", "") or ""),
            ),
        )
    )


def select_entity_linked_invoices(
    records: Sequence[Invoice],
    *,
    entity: CastEntity | CastIdentityProjection,
) -> tuple[Invoice, ...]:
    return tuple(
        record
        for record in select_entity_linked_finance_records(
            records,
            entity=entity,
            record_type=RecordType.INVOICE,
        )
        if isinstance(record, Invoice)
    )


def select_entity_linked_bills(
    records: Sequence[Bill],
    *,
    entity: CastEntity | CastIdentityProjection,
) -> tuple[Bill, ...]:
    return tuple(
        record
        for record in select_entity_linked_finance_records(
            records,
            entity=entity,
            record_type=RecordType.BILL,
        )
        if isinstance(record, Bill)
    )


__all__ = [
    "finance_record_matches_entity",
    "select_entity_linked_bills",
    "select_entity_linked_finance_records",
    "select_entity_linked_invoices",
]
