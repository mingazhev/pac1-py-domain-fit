from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from numbers import Real
from typing import Any

DEFAULT_CONTAINER_KEYS: tuple[str, ...] = ("records", "accounts", "contacts", "items", "rows")
DEFAULT_SEARCH_FIELDS: tuple[str, ...] = (
    "display_name",
    "legal_name",
    "full_name",
    "account_manager",
    "account_manager_id",
    "primary_contact",
    "primary_contact_id",
    "title",
    "industry",
    "country",
    "region",
    "city",
    "description",
    "notes",
    "compliance_flags",
    "email",
)
DEFAULT_TEXT_OUTPUT_FIELDS: tuple[str, ...] = ("name", "display_name", "legal_name", "full_name", "title", "email")
DEFAULT_NUMERIC_FIELD_HINTS: tuple[str, ...] = (
    "amount",
    "balance",
    "count",
    "price",
    "quantity",
    "qty",
    "rate",
    "revenue",
    "score",
    "sum",
    "total",
    "value",
)

Record = Mapping[str, Any]
RecordPredicate = Callable[[Record], bool]


def records_from_payload(
    payload: Any,
    *,
    container_keys: Sequence[str] = DEFAULT_CONTAINER_KEYS,
) -> list[Record]:
    if payload is None:
        return []

    if isinstance(payload, Mapping):
        extracted = _extract_records_from_mapping(payload, container_keys=container_keys)
        if extracted is not None:
            return extracted
        return [payload]

    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [item for item in payload if isinstance(item, Mapping)]

    return []


def filter_records(
    payload: Any,
    *,
    predicate: RecordPredicate | None = None,
    query: str | None = None,
    fields: Sequence[str] | None = None,
) -> list[Record]:
    records = records_from_payload(payload)
    if predicate is None and not query:
        return list(records)

    selected: list[Record] = []
    for record in records:
        if predicate is not None and not predicate(record):
            continue
        if query and not record_matches_query(record, query, fields=fields):
            continue
        selected.append(record)
    return selected


def count_records(
    payload: Any,
    *,
    predicate: RecordPredicate | None = None,
    query: str | None = None,
    fields: Sequence[str] | None = None,
) -> int:
    return len(filter_records(payload, predicate=predicate, query=query, fields=fields))


def list_field_values(
    payload: Any,
    field: str,
    *,
    predicate: RecordPredicate | None = None,
    query: str | None = None,
    fields: Sequence[str] | None = None,
) -> list[str]:
    selected = filter_records(payload, predicate=predicate, query=query, fields=fields)
    values = [str(record[field]).strip() for record in selected if field in record and str(record[field]).strip()]
    return sorted(values, key=lambda item: item.lower())


def sum_numeric_field(
    payload: Any,
    field: str,
    *,
    predicate: RecordPredicate | None = None,
    query: str | None = None,
    fields: Sequence[str] | None = None,
) -> int | float:
    selected = filter_records(payload, predicate=predicate, query=query, fields=fields)
    total: Real = 0
    for record in selected:
        if field not in record:
            continue
        value = _coerce_number(record[field], field=field)
        total += value
    if isinstance(total, float) and total.is_integer():
        return int(total)
    return total


def infer_text_field(
    payload: Any,
    *,
    preferred_fields: Sequence[str] = DEFAULT_TEXT_OUTPUT_FIELDS,
) -> str | None:
    records = records_from_payload(payload)
    if not records:
        return None

    for field in preferred_fields:
        if any(field in record and str(record[field]).strip() for record in records):
            return field

    for record in records:
        for field, value in record.items():
            if _is_non_empty_text(value):
                return field
    return None


def infer_numeric_field(
    payload: Any,
    *,
    query: str | None = None,
    preferred_fields: Sequence[str] = DEFAULT_NUMERIC_FIELD_HINTS,
) -> str | None:
    records = records_from_payload(payload)
    if not records:
        return None

    numeric_fields: list[str] = []
    for record in records:
        for field, value in record.items():
            if field in numeric_fields:
                continue
            if _is_numeric_candidate(value):
                numeric_fields.append(field)

    if not numeric_fields:
        return None

    if query:
        query_tokens = set(_tokenize(query))
        for hint in preferred_fields:
            if hint in query_tokens:
                for field in numeric_fields:
                    if hint in field.lower():
                        return field

    if len(numeric_fields) == 1:
        return numeric_fields[0]

    return None


def record_matches_query(record: Record, query: str, *, fields: Sequence[str] | None = None) -> bool:
    tokens = _tokenize(query)
    if not tokens:
        return True
    haystack_tokens = set(_tokenize(_record_search_text(record, fields=fields)))
    return all(token in haystack_tokens for token in tokens)


def build_query_predicate(query: str, *, fields: Sequence[str] | None = None) -> RecordPredicate:
    def _predicate(record: Record) -> bool:
        return record_matches_query(record, query, fields=fields)

    return _predicate


def _extract_records_from_mapping(
    payload: Mapping[str, Any],
    *,
    container_keys: Sequence[str],
) -> list[Record] | None:
    for key in container_keys:
        value = payload.get(key)
        extracted = _coerce_record_list(value)
        if extracted is not None:
            return extracted

    for value in payload.values():
        extracted = _coerce_record_list(value)
        if extracted is not None:
            return extracted

    if _looks_like_record(payload):
        return None
    return []


def _coerce_record_list(value: Any) -> list[Record] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    records = [item for item in value if isinstance(item, Mapping)]
    if records and len(records) == len(value):
        return records
    return None


def _looks_like_record(payload: Mapping[str, Any]) -> bool:
    scalar_count = 0
    for value in payload.values():
        if isinstance(value, Mapping):
            continue
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            continue
        scalar_count += 1
    return scalar_count > 0


def _record_search_text(record: Mapping[str, Any], *, fields: Sequence[str] | None = None) -> str:
    if fields is None:
        parts = [_stringify(value) for value in record.values()]
    else:
        parts = [_stringify(record[field]) for field in fields if field in record]
    return " ".join(part for part in parts if part)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Mapping):
        parts = [_stringify(item) for item in value.values()]
        return " ".join(part for part in parts if part)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        parts = [_stringify(item) for item in value]
        return " ".join(part for part in parts if part)
    return str(value).strip()


def _tokenize(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", text.lower()))


def _coerce_number(value: Any, *, field: str) -> int | float:
    if isinstance(value, bool):
        raise TypeError(f"field {field!r} must be numeric, not bool")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, Real):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise TypeError(f"field {field!r} must be numeric")
        if re.fullmatch(r"[+-]?\d+", stripped):
            return int(stripped)
        return float(stripped)
    raise TypeError(f"field {field!r} must be numeric")


def _is_non_empty_text(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return False


def _is_numeric_candidate(value: Any) -> bool:
    try:
        _coerce_number(value, field="candidate")
    except Exception:  # noqa: BLE001
        return False
    return not isinstance(value, bool)
