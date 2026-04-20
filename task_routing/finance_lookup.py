from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from application.contracts import (
    FinanceLookupAction,
    FinanceLookupIntent,
    format_finance_record_date_output,
)
from application.temporal import resolve_relative_lookup_base_time
from domain.finance import Number
from domain.finance.policy import FinanceAnchorCriteria
from temporal_controls import compute_relative_date


def _coerce_output_format(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "iso"}:
        return None
    if normalized in {"dd-mm-yyyy", "mm/dd/yyyy", "month dd, yyyy"}:
        return normalized
    return None


def _coerce_record_type(value: object) -> str | None:
    normalized = _clean_text(value).lower()
    if normalized in {"", "any"}:
        return None
    if normalized in {"bill", "invoice"}:
        return normalized
    return normalized or None


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _extract_amount_hints(extracted: Mapping[str, object] | None) -> tuple[Number, ...]:
    if not extracted:
        return ()
    raw_values = extracted.get("amount_hints")
    if not isinstance(raw_values, tuple | list):
        return ()
    return tuple(value for value in raw_values if isinstance(value, int | float))


def _normalize_spaces(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _merged_amount_hints(
    existing: tuple[Number, ...],
    derived: tuple[Number, ...],
) -> tuple[Number, ...]:
    merged: list[Number] = []
    for value in (*existing, *derived):
        if value not in merged:
            merged.append(value)
    return tuple(merged)


def _resolve_target_date(
    extracted: Mapping[str, object],
    *,
    context_payload: Mapping[str, object] | None,
    current_time: datetime | None = None,
) -> str | None:
    explicit_date = _clean_text(extracted.get("target_date"))
    if explicit_date:
        return explicit_date
    relative_days_ago = extracted.get("relative_days_ago")
    if not isinstance(relative_days_ago, int | float):
        return None
    base_time = resolve_relative_lookup_base_time(
        context_payload,
        current_time=current_time,
    )
    if base_time is None:
        return None
    return compute_relative_date(base_time, f"{int(relative_days_ago)} days ago")


def _resolve_date_range(
    extracted: Mapping[str, object],
) -> tuple[str, str] | None:
    start = _clean_text(extracted.get("date_range_start"))
    end = _clean_text(extracted.get("date_range_end"))
    if not start or not end:
        return None
    return (start, end)


def _resolve_since_date(extracted: Mapping[str, object]) -> str | None:
    since_date = _clean_text(extracted.get("since_date"))
    if since_date:
        return since_date
    date_range_start = _clean_text(extracted.get("date_range_start"))
    return date_range_start or None


def _derive_record_type_override(
    requested_record_type: str | None,
    *,
    action: str,
    task_text: str,
    counterparty_name: str,
) -> str | None:
    del action, task_text, counterparty_name
    if requested_record_type is not None:
        return requested_record_type
    return None

def resolve_finance_lookup_intent(
    task_text: str,
    *,
    extracted: Mapping[str, object] | None = None,
    translated_text: str | None = None,
    context_payload: Mapping[str, object] | None = None,
    current_time: datetime | None = None,
) -> FinanceLookupIntent | None:
    payload = extracted or {}
    action = _clean_text(payload.get("action"))
    since_date = _resolve_since_date(payload)
    if not action:
        return None
    date_range = _resolve_date_range(payload)
    item_name = _clean_text(payload.get("item_name"))
    amount_hints = _extract_amount_hints(payload)

    anchor_ref = _clean_text(payload.get("anchor_record_ref"))
    counterparty_name = _clean_text(payload.get("counterparty"))
    reference_number = _clean_text(payload.get("reference_number"))
    alias = _clean_text(payload.get("alias"))
    project = _clean_text(payload.get("project"))
    related_entity = _clean_text(payload.get("related_entity"))
    requested_record_type = _derive_record_type_override(
        _coerce_record_type(payload.get("record_type")),
        action=action,
        task_text=task_text,
        counterparty_name=counterparty_name,
    )
    return FinanceLookupIntent(
        action=action,
        anchor_criteria=FinanceAnchorCriteria(
            path_reference_text=anchor_ref,
            item_name=item_name,
            counterparty_name=counterparty_name,
            reference_number=reference_number,
            alias=alias,
            project=project,
            related_entity=related_entity,
            date_range=date_range,
            target_date=_resolve_target_date(
                payload,
                context_payload=context_payload,
                current_time=current_time,
            ),
        ),
        requested_record_type=requested_record_type,
        since_date=since_date,
        amount_hints=amount_hints,
        output_format=_coerce_output_format(payload.get("output_format")),
    )


__all__ = [
    "FinanceLookupIntent",
    "FinanceLookupAction",
    "format_finance_record_date_output",
    "resolve_finance_lookup_intent",
]
