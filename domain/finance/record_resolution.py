from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .exact_matching import (
    finance_record_matches_counterparty_name,
    matches_finance_identity_text,
    normalize_finance_identity_text,
)

from .finance_record import FinanceRecord, RecordType
from .money import Number, money_to_number


def finance_record_identity_terms(record: FinanceRecord) -> tuple[str, ...]:
    path = str(getattr(record, "path", "") or "").strip().replace("\\", "/")
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0] if path else ""
    pieces = [
        str(getattr(record, "title", "") or "").strip(),
        str(getattr(record, "reference_number", "") or "").strip(),
        str(getattr(record, "alias", "") or "").strip(),
        stem,
        *stem.split("__"),
    ]
    normalized: list[str] = []
    for piece in pieces:
        token = normalize_finance_identity_text(piece)
        if token:
            normalized.append(token)
    return tuple(dict.fromkeys(normalized))


def finance_record_matches_hint(record: FinanceRecord, hint: str) -> bool:
    normalized_hint = normalize_finance_identity_text(hint)
    if not normalized_hint:
        return False
    for term in finance_record_identity_terms(record):
        if _is_generic_identity_term(term):
            continue
        if term == normalized_hint:
            return True
    return False


def _is_generic_identity_term(term: str) -> bool:
    return term in {"", "invoice", "bill"}


@dataclass(frozen=True, slots=True)
class FinanceRecordIdentityCriteria:
    record_type: str | RecordType | None = None
    counterparty: str = ""
    reference_number: str = ""
    alias: str = ""
    project: str = ""
    related_entity: str = ""
    date: str = ""
    amount_eur: Number | None = None

    def has_identity(self) -> bool:
        return any(
            (
                str(self.counterparty or "").strip(),
                str(self.reference_number or "").strip(),
                str(self.alias or "").strip(),
                str(self.project or "").strip(),
                str(self.related_entity or "").strip(),
                str(self.date or "").strip(),
                self.amount_eur is not None,
            )
        )


def filter_records_by_identity(
    records: Sequence[FinanceRecord],
    *,
    criteria: FinanceRecordIdentityCriteria,
) -> tuple[FinanceRecord, ...]:
    if not criteria.has_identity():
        return ()
    return tuple(record for record in records if record_matches_identity(record, criteria))


def select_unique_record_by_identity(
    records: Sequence[FinanceRecord],
    *,
    criteria: FinanceRecordIdentityCriteria,
) -> FinanceRecord | None:
    matches = filter_records_by_identity(records, criteria=criteria)
    if len(matches) != 1:
        return None
    return matches[0]


def record_matches_identity(
    record: FinanceRecord,
    criteria: FinanceRecordIdentityCriteria,
) -> bool:
    if not _matches_record_type(record, criteria.record_type):
        return False
    if criteria.counterparty and not _matches_counterparty(record, criteria.counterparty):
        return False
    if criteria.reference_number and not matches_finance_identity_text(
        getattr(record, "reference_number", ""),
        criteria.reference_number,
    ):
        return False
    if criteria.alias and not matches_finance_identity_text(getattr(record, "alias", ""), criteria.alias):
        return False
    if criteria.project and not matches_finance_identity_text(getattr(record, "project", ""), criteria.project):
        return False
    if criteria.related_entity and not matches_finance_identity_text(
        getattr(record, "related_entity", ""),
        criteria.related_entity,
    ):
        return False
    if criteria.date and str(getattr(record, "date", "") or "").strip() != str(criteria.date or "").strip():
        return False
    if criteria.amount_eur is not None:
        record_amount = money_to_number(getattr(record, "total_eur", None))
        if record_amount is None or float(record_amount) != float(criteria.amount_eur):
            return False
    return True


def _matches_record_type(record: FinanceRecord, record_type: str | RecordType | None) -> bool:
    normalized = str(record_type or "").strip().lower()
    if normalized in {"", "any"}:
        return True
    if hasattr(record, "matches_record_type"):
        return bool(record.matches_record_type(record_type))
    if record_type is None:
        return True
    parsed = (
        record_type
        if isinstance(record_type, RecordType)
        else RecordType.parse(record_type)
    )
    if parsed is None:
        return True
    raw_record_type = getattr(record, "record_type", None)
    candidate = (
        raw_record_type
        if isinstance(raw_record_type, RecordType)
        else RecordType.parse(raw_record_type)
    )
    return candidate is parsed


def _matches_counterparty(record: FinanceRecord, counterparty: str) -> bool:
    return finance_record_matches_counterparty_name(record, counterparty)


__all__ = [
    "FinanceRecordIdentityCriteria",
    "finance_record_identity_terms",
    "finance_record_matches_hint",
    "filter_records_by_identity",
    "record_matches_identity",
    "select_unique_record_by_identity",
]
