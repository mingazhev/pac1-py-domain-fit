from __future__ import annotations

from collections.abc import Sequence
import re

from domain.finance import FinanceRecord, finance_document_family_projection_from_record


def normalize_finance_document_family_reference(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    normalized = re.sub(r"[^0-9a-z]+", " ", text)
    return re.sub(r"\s+", " ", normalized).strip()


def finance_document_family_references(record: FinanceRecord) -> tuple[str, ...]:
    projection = finance_document_family_projection_from_record(record)
    return tuple(
        term
        for term in projection.canonical_terms
        if normalize_finance_document_family_reference(term)
    )


def finance_document_matches_family_reference(
    record: FinanceRecord,
    family_reference: str,
) -> bool:
    normalized_reference = normalize_finance_document_family_reference(
        family_reference
    )
    if not normalized_reference:
        return False
    return normalized_reference in finance_document_family_references(record)


def select_finance_documents_by_family_reference(
    records: Sequence[FinanceRecord],
    *,
    family_reference: str,
) -> tuple[FinanceRecord, ...]:
    normalized_reference = normalize_finance_document_family_reference(
        family_reference
    )
    if not normalized_reference:
        return tuple(records)
    return tuple(
        record
        for record in records
        if finance_document_matches_family_reference(record, normalized_reference)
    )


__all__ = [
    "finance_document_family_references",
    "finance_document_matches_family_reference",
    "normalize_finance_document_family_reference",
    "select_finance_documents_by_family_reference",
]
