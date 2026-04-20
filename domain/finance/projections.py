from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
import re

from .finance_record import FinanceRecord
from .money import Number, money_to_number
from .record_resolution import (
    FinanceRecordIdentityCriteria,
    finance_record_matches_hint,
    filter_records_by_identity,
    select_unique_record_by_identity,
)
from .settlement import payment_state_text, settlement_channel_text


@dataclass(frozen=True, slots=True)
class FinanceRecordIdentityProjection:
    path: str
    record_type: str
    date: str
    counterparty: str
    reference_number: str
    alias: str
    project: str
    related_entity: str
    total_eur: Number | None
    title: str
    line_item_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FinanceAttachmentProjection:
    path: str
    record_type: str
    reference_number: str
    counterparty: str
    alias: str
    date: str


@dataclass(frozen=True, slots=True)
class FinanceSettlementProjection:
    path: str
    payment_state: str
    settlement_reference: str
    settlement_channel: str
    settlement_date: str
    is_settled: bool


@dataclass(frozen=True, slots=True)
class FinanceDocumentFamilyProjection:
    path: str
    canonical_terms: tuple[str, ...]


def _record_type_text(record: FinanceRecord | Mapping[str, object]) -> str:
    raw = getattr(record, "record_type", None) if not isinstance(record, Mapping) else record.get("record_type")
    return str(getattr(raw, "value", raw) or "").strip()


def _line_item_names(record: FinanceRecord) -> tuple[str, ...]:
    names: list[str] = []
    for item in getattr(record, "line_items", ()) or ():
        name = str(getattr(item, "item", "") or getattr(item, "description", "") or "").strip()
        if name:
            names.append(name)
    return tuple(dict.fromkeys(names))


def _normalize_family_reference(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    normalized = re.sub(r"[^0-9a-z]+", " ", text)
    return re.sub(r"\s+", " ", normalized).strip()


def finance_document_family_projection_from_record(
    record: FinanceRecord,
) -> FinanceDocumentFamilyProjection:
    path = str(record.path or "").strip().replace("\\", "/")
    stem = PurePosixPath(path).stem if path else ""
    terms = tuple(
        dict.fromkeys(
            normalized
            for normalized in (
                _normalize_family_reference(record.title),
                _normalize_family_reference(record.alias),
                _normalize_family_reference(record.reference_number),
                _normalize_family_reference(stem),
            )
            if normalized and normalized not in {"invoice", "bill"}
        )
    )
    return FinanceDocumentFamilyProjection(
        path=path,
        canonical_terms=terms,
    )


def finance_record_identity_projection_from_record(
    record: FinanceRecord,
) -> FinanceRecordIdentityProjection:
    return FinanceRecordIdentityProjection(
        path=str(record.path or "").strip(),
        record_type=_record_type_text(record),
        date=str(record.date or "").strip(),
        counterparty=str(record.counterparty or "").strip(),
        reference_number=str(record.reference_number or "").strip(),
        alias=str(record.alias or "").strip(),
        project=str(record.project or "").strip(),
        related_entity=str(record.related_entity or "").strip(),
        total_eur=money_to_number(record.total_eur),
        title=str(record.title or "").strip(),
        line_item_names=_line_item_names(record),
    )


def finance_attachment_projection_from_record(
    record: FinanceRecord,
) -> FinanceAttachmentProjection:
    identity = finance_record_identity_projection_from_record(record)
    return FinanceAttachmentProjection(
        path=identity.path,
        record_type=identity.record_type,
        reference_number=identity.reference_number,
        counterparty=identity.counterparty,
        alias=identity.alias,
        date=identity.date,
    )


def finance_settlement_projection_from_record(
    record: FinanceRecord | Mapping[str, object],
) -> FinanceSettlementProjection:
    path = str(
        getattr(record, "path", "") if not isinstance(record, Mapping) else record.get("path")
        or ""
    ).strip()
    payment_state = payment_state_text(
        getattr(record, "payment_state", "")
        if not isinstance(record, Mapping)
        else record.get("payment_state")
    )
    settlement_reference = str(
        getattr(record, "settlement_reference", "")
        if not isinstance(record, Mapping)
        else record.get("settlement_reference")
        or ""
    ).strip()
    settlement_channel = settlement_channel_text(
        getattr(record, "settlement_channel", "")
        if not isinstance(record, Mapping)
        else record.get("settlement_channel")
    )
    settlement_date = str(
        getattr(record, "settlement_date", "")
        if not isinstance(record, Mapping)
        else record.get("settlement_date")
        or ""
    ).strip()
    is_settled = payment_state.lower() in {"paid", "settled"} or bool(
        settlement_reference or settlement_date
    )
    return FinanceSettlementProjection(
        path=path,
        payment_state=payment_state,
        settlement_reference=settlement_reference,
        settlement_channel=settlement_channel,
        settlement_date=settlement_date,
        is_settled=is_settled,
    )


def resolve_finance_record_identity(
    records: Sequence[FinanceRecord],
    *,
    criteria: FinanceRecordIdentityCriteria,
) -> FinanceRecordIdentityProjection | None:
    record = select_unique_record_by_identity(records, criteria=criteria)
    if record is None:
        return None
    return finance_record_identity_projection_from_record(record)


def select_finance_records(
    records: Sequence[FinanceRecord],
    *,
    criteria: FinanceRecordIdentityCriteria,
) -> tuple[FinanceRecordIdentityProjection, ...]:
    matches = filter_records_by_identity(records, criteria=criteria)
    return tuple(
        finance_record_identity_projection_from_record(record) for record in matches
    )


def resolve_finance_attachment(
    records: Sequence[FinanceRecord],
    *,
    criteria: FinanceRecordIdentityCriteria,
    record_hint: str = "",
) -> str | None:
    hint = str(record_hint or "").strip()
    if hint:
        matches = filter_records_by_identity(records, criteria=criteria)
        record = _select_record_by_hint(matches, hint)
        if record is None:
            record = _select_record_by_relaxed_hint(
                records,
                criteria=criteria,
                hint=hint,
            )
        if record is not None:
            path = str(record.path or "").strip()
            return path or None
    record = select_unique_record_by_identity(records, criteria=criteria)
    if record is None:
        return None
    path = str(record.path or "").strip()
    return path or None


def _select_record_by_hint(
    records: Sequence[FinanceRecord],
    hint: str,
) -> FinanceRecord | None:
    if not str(hint or "").strip():
        return None
    matched = [
        record
        for record in records
        if finance_record_matches_hint(record, hint)
    ]
    if len(matched) != 1:
        return None
    return matched[0]


def _select_record_by_relaxed_hint(
    records: Sequence[FinanceRecord],
    *,
    criteria: FinanceRecordIdentityCriteria,
    hint: str,
) -> FinanceRecord | None:
    relaxed_criteria = FinanceRecordIdentityCriteria(
        record_type=criteria.record_type,
        counterparty=criteria.counterparty,
        project=criteria.project,
        related_entity=criteria.related_entity,
    )
    relaxed_matches = filter_records_by_identity(records, criteria=relaxed_criteria)
    if not relaxed_matches:
        return None
    return _select_record_by_hint(relaxed_matches, hint)

def resolve_finance_settlement_state(
    records: Sequence[FinanceRecord],
    *,
    criteria: FinanceRecordIdentityCriteria,
) -> FinanceSettlementProjection | None:
    record = select_unique_record_by_identity(records, criteria=criteria)
    if record is None:
        return None
    return finance_settlement_projection_from_record(record)


__all__ = [
    "FinanceAttachmentProjection",
    "FinanceDocumentFamilyProjection",
    "FinanceRecordIdentityProjection",
    "FinanceSettlementProjection",
    "finance_attachment_projection_from_record",
    "finance_document_family_projection_from_record",
    "finance_record_identity_projection_from_record",
    "finance_settlement_projection_from_record",
    "resolve_finance_attachment",
    "resolve_finance_record_identity",
    "resolve_finance_settlement_state",
    "select_finance_records",
]
