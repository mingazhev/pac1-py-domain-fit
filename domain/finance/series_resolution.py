"""Series grouping and party reconciliation helpers.

`FinanceRecordSeries`, `DocumentOccurrenceKey`, and `PartyReference` are
typed identities defined in `identity.py`. This module is the live wiring
from a `FinanceRecord` to those identities so selection paths can ask for
typed answers instead of re-parsing strings on every call.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from .finance_record import FinanceRecord
from .identity import (
    DocumentOccurrenceKey,
    FinanceRecordSeries,
    PartyReference,
    Vendor,
)
from .record_type import RecordType


def _record_type_literal(record_type: RecordType) -> Literal["invoice", "bill"]:
    if record_type is RecordType.INVOICE:
        return "invoice"
    return "bill"


def document_occurrence_key(record: FinanceRecord) -> DocumentOccurrenceKey | None:
    """Build a `DocumentOccurrenceKey` for this finance record.

    Records without a reference number cannot be part of a series keyed by
    number; the caller receives `None` instead of a fabricated key.
    """

    reference = record.reference_number.strip()
    counterparty = record.counterparty.strip()
    if not reference or not counterparty:
        return None
    return DocumentOccurrenceKey(
        reference_number=reference,
        counterparty=counterparty,
        record_type=_record_type_literal(record.record_type),
        occurrence_date=record.date,
    )


def group_records_into_series(
    records: Sequence[FinanceRecord],
) -> tuple[FinanceRecordSeries, ...]:
    """Group records into `FinanceRecordSeries` keyed by reference+counterparty+type.

    Records with the same `reference_number` under the same counterparty and
    record type form a series. Records missing a reference or counterparty
    are skipped — they cannot participate in keyed series identity honestly.
    """

    grouped: dict[tuple[str, str, Literal["invoice", "bill"]], list[DocumentOccurrenceKey]] = {}
    for record in records:
        key = document_occurrence_key(record)
        if key is None:
            continue
        group_id = (
            key.reference_number,
            key.counterparty.strip().lower(),
            key.record_type,
        )
        grouped.setdefault(group_id, []).append(key)

    series_list: list[FinanceRecordSeries] = []
    for (reference, counterparty_norm, record_type), occurrence_keys in sorted(grouped.items()):
        if len(occurrence_keys) < 2:
            continue
        canonical_counterparty = occurrence_keys[0].counterparty
        series_list.append(
            FinanceRecordSeries(
                series_id=f"series/{record_type}/{counterparty_norm}/{reference}",
                counterparty=canonical_counterparty,
                record_type=record_type,
                occurrence_keys=tuple(
                    sorted(occurrence_keys, key=lambda k: (k.occurrence_date, k.reference_number))
                ),
            )
        )
    return tuple(series_list)


def reconcile_party_from_record(
    record: FinanceRecord,
    *,
    canonical_entity_by_name: Mapping[str, str] | None = None,
) -> PartyReference:
    """Return a `PartyReference` for the record's counterparty.

    If a name -> canonical id map is supplied and the record's counterparty is
    in it, the match is marked `exact` with source `cast`. Otherwise the
    reference is `unresolved` and the raw display name is preserved verbatim.
    """

    display_name = record.counterparty.strip()
    if not display_name:
        return PartyReference(display_name="")
    if canonical_entity_by_name:
        canonical_id = canonical_entity_by_name.get(display_name.lower())
        if canonical_id:
            return PartyReference(
                display_name=display_name,
                canonical_entity_id=canonical_id,
                match_confidence="exact",
                source="cast",
            )
    return PartyReference(display_name=display_name)


def find_vendor_for_record(
    record: FinanceRecord,
    vendors: Sequence[Vendor],
) -> Vendor | None:
    """Find the vendor whose canonical name or aliases match this record's counterparty."""

    counterparty = record.counterparty.strip()
    if not counterparty:
        return None
    for vendor in vendors:
        if vendor.matches_name(counterparty):
            return vendor
    return None
