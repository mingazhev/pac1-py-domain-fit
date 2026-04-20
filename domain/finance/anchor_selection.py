from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import PurePosixPath

from .exact_matching import (
    finance_record_find_unique_line_item_by_name,
    finance_record_matches_counterparty_name,
)
from .finance_record import FinanceRecord
from .policy_models import FinanceAnchorCriteria, FinanceRecordQueryCriteria


def _normalize(value: object) -> str:
    return str(value or "").strip().lower()


def select_anchor_record(
    records: Sequence[FinanceRecord],
    *,
    criteria: FinanceAnchorCriteria,
) -> FinanceRecord | None:
    normalized_path_reference = _normalize(criteria.path_reference_text)
    if normalized_path_reference:
        for record in records:
            record_path = record.path.strip()
            if not record_path:
                continue
            lowered_path = record_path.lstrip("/").lower()
            if lowered_path and lowered_path in normalized_path_reference:
                return record
            filename = PurePosixPath(record_path).name.lower()
            if filename and filename in normalized_path_reference:
                return record

    candidates: list[FinanceRecord] = []
    for record in records:
        if (
            criteria.item_name
            and finance_record_find_unique_line_item_by_name(record, criteria.item_name)
            is None
        ):
            continue
        if (
            criteria.counterparty_name
            and not finance_record_matches_counterparty_name(
                record, criteria.counterparty_name
            )
        ):
            continue
        if (
            criteria.reference_number
            and str(record.reference_number or "").strip().lower()
            != criteria.reference_number.strip().lower()
        ):
            continue
        if (
            criteria.alias
            and str(record.alias or "").strip().lower() != criteria.alias.strip().lower()
        ):
            continue
        if (
            criteria.project
            and str(record.project or "").strip().lower()
            != criteria.project.strip().lower()
        ):
            continue
        if (
            criteria.related_entity
            and str(record.related_entity or "").strip().lower()
            != criteria.related_entity.strip().lower()
        ):
            continue
        if criteria.date_range is not None and not record.in_date_range(
            *criteria.date_range
        ):
            continue
        if criteria.target_date and record.date != criteria.target_date:
            continue
        candidates.append(record)
    if len(candidates) == 1:
        return candidates[0]

    if not candidates and criteria.target_date:
        relaxed: list[FinanceRecord] = []
        for record in records:
            if (
                criteria.item_name
                and finance_record_find_unique_line_item_by_name(record, criteria.item_name)
                is None
            ):
                continue
            if (
                criteria.counterparty_name
                and not finance_record_matches_counterparty_name(
                    record, criteria.counterparty_name
                )
            ):
                continue
            if (
                criteria.reference_number
                and str(record.reference_number or "").strip().lower()
                != criteria.reference_number.strip().lower()
            ):
                continue
            if (
                criteria.alias
                and str(record.alias or "").strip().lower()
                != criteria.alias.strip().lower()
            ):
                continue
            if (
                criteria.project
                and str(record.project or "").strip().lower()
                != criteria.project.strip().lower()
            ):
                continue
            if (
                criteria.related_entity
                and str(record.related_entity or "").strip().lower()
                != criteria.related_entity.strip().lower()
            ):
                continue
            if not record.date:
                continue
            relaxed.append(record)
        if relaxed:
            ranked: list[tuple[str, str, FinanceRecord]] = []
            for record in relaxed:
                try:
                    datetime.strptime(record.date, "%Y-%m-%d").date()
                except ValueError:
                    continue
                ranked.append((record.date, record.path, record))
            if ranked:
                ranked.sort(reverse=True)
                top_date = ranked[0][0]
                if sum(1 for date, _, _ in ranked if date == top_date) > 1:
                    return None
                return ranked[0][2]
            return max(relaxed, key=lambda item: (item.date, item.path))
    return None


def select_unique_record(
    records: Sequence[FinanceRecord],
    *,
    criteria: FinanceRecordQueryCriteria,
) -> FinanceRecord | None:
    candidates = tuple(
        record
        for record in records
        if record.matches_record_type(criteria.requested_record_type)
        and (
            not criteria.counterparty_name
            or finance_record_matches_counterparty_name(record, criteria.counterparty_name)
        )
        and (criteria.date_range is None or record.in_date_range(*criteria.date_range))
    )
    if len(candidates) != 1:
        return None
    return candidates[0]


__all__ = ["select_anchor_record", "select_unique_record"]
