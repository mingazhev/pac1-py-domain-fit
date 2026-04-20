from __future__ import annotations
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from application.ports import QueryResolutionPort
from domain.cast import CastEntity, resolve_aggregate_birthday_answer


_SCALAR_PROPERTIES = {
    "title",
    "entity_id",
    "entity_slug",
    "primary_contact_email",
    "kind",
    "relationship",
    "birthday",
    "created_on",
}

_LIST_PROPERTIES = {
    "alias",
    "milestones",
    "important_dates",
    "alias_terms",
    "identity_terms",
}

_MONTH_NAMES = {
    "01": "January",
    "02": "February",
    "03": "March",
    "04": "April",
    "05": "May",
    "06": "June",
    "07": "July",
    "08": "August",
    "09": "September",
    "10": "October",
    "11": "November",
    "12": "December",
}


@dataclass(frozen=True, slots=True)
class EntityQueryResult:
    status: Literal["resolved", "clarify_missing"]
    message: str
    grounding_refs: tuple[str, ...]


def resolve_entity_query(
    cast_records: Sequence[Mapping[str, Any]],
    cast_entities: Sequence[CastEntity],
    *,
    variant: str,
    property: str,
    aggregate: str | None,
    aggregate_filter: str,
    entity_reference: str,
    self_reference: bool,
    output_format: str,
    fallback_text: str,
    cast_refs: Sequence[str],
    resolution_port: QueryResolutionPort | None,
    reference_date: datetime | None = None,
) -> EntityQueryResult | None:
    rows = [dict(record) for record in cast_records]
    if not rows:
        return None
    normalized_reference = _normalize_entity_reference(entity_reference)
    normalized_fallback_text = fallback_text or normalized_reference

    if variant == "aggregate_property" and aggregate == "next_upcoming_birthday":
        return _resolve_aggregate_birthday(
            cast_entities,
            reference_date=reference_date,
            aggregate_filter=aggregate_filter,
            cast_refs=cast_refs,
        )

    if variant == "aggregate_property":
        return None

    if resolution_port is None or resolution_port.resolve_entity_candidate is None:
        return None
    candidate = resolution_port.resolve_entity_candidate(
        rows,
        normalized_reference,
        normalized_fallback_text,
        bool(self_reference),
    )
    if candidate is None:
        return None

    title = str(candidate.get("title") or "the requested entity").strip()
    grounding_refs = _grounding_refs(candidate, cast_refs)

    if property in _SCALAR_PROPERTIES:
        return _scalar_property_result(
            candidate,
            property=property,
            title=title,
            output_format=output_format,
            grounding_refs=grounding_refs,
        )

    if property in _LIST_PROPERTIES:
        return _list_property_result(
            candidate,
            property=property,
            title=title,
            output_format=output_format,
            grounding_refs=grounding_refs,
        )

    return None


def _normalize_entity_reference(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _scalar_property_result(
    candidate: Mapping[str, Any],
    *,
    property: str,
    title: str,
    output_format: str,
    grounding_refs: tuple[str, ...],
) -> EntityQueryResult:
    raw = candidate.get(property)
    value = str(raw or "").strip()
    if not value:
        return EntityQueryResult(
            status="clarify_missing",
            message=f"No {property} is recorded for {title} in the canonical entity file.",
            grounding_refs=grounding_refs,
        )
    if property in {"birthday", "created_on"}:
        value = _format_date(value, output_format)
    return EntityQueryResult(
        status="resolved",
        message=value,
        grounding_refs=grounding_refs,
    )


def _list_property_result(
    candidate: Mapping[str, Any],
    *,
    property: str,
    title: str,
    output_format: str,
    grounding_refs: tuple[str, ...],
) -> EntityQueryResult:
    if property in {"milestones", "important_dates"}:
        entries = _resolve_important_dates(candidate)
        if property == "milestones":
            entries = tuple(
                entry for entry in entries if entry[2] not in {"birthday", "created_on"}
            )
        if not entries:
            return EntityQueryResult(
                status="clarify_missing",
                message=f"No {property} are recorded for {title} in the canonical entity file.",
                grounding_refs=grounding_refs,
            )
        lines = [
            f"{label}: {_format_date(occurred_on, output_format)}"
            for label, occurred_on, _kind in entries
        ]
        return EntityQueryResult(
            status="resolved",
            message="\n".join(lines),
            grounding_refs=grounding_refs,
        )

    raw = candidate.get(property)
    if not raw:
        return EntityQueryResult(
            status="clarify_missing",
            message=f"No {property} are recorded for {title} in the canonical entity file.",
            grounding_refs=grounding_refs,
        )
    values = _coerce_str_list(raw)
    if not values:
        return EntityQueryResult(
            status="clarify_missing",
            message=f"No {property} are recorded for {title} in the canonical entity file.",
            grounding_refs=grounding_refs,
        )
    return EntityQueryResult(
        status="resolved",
        message="\n".join(values),
        grounding_refs=grounding_refs,
    )


def _resolve_aggregate_birthday(
    cast_entities: Sequence[CastEntity],
    *,
    reference_date: datetime | None,
    aggregate_filter: str,
    cast_refs: Sequence[str],
) -> EntityQueryResult | None:
    if reference_date is None:
        return None
    aggregate_answer = resolve_aggregate_birthday_answer(
        cast_entities,
        reference_date,
        prefer_people_only=str(aggregate_filter or "any").strip().lower()
        == "people_only",
    )
    if aggregate_answer is None:
        return None
    message, birthday_refs = aggregate_answer
    grounding_refs = tuple(
        dict.fromkeys(
            _normalize_repo_path(ref)
            for ref in (birthday_refs or cast_refs)
            if str(ref or "").strip()
        )
    )
    return EntityQueryResult(
        status="resolved",
        message=message,
        grounding_refs=grounding_refs,
    )


def _resolve_important_dates(
    candidate: Mapping[str, Any],
) -> tuple[tuple[str, str, str], ...]:
    entries = list(_coerce_named_dates(candidate.get("important_dates")))
    entries.extend(_coerce_named_dates(candidate.get("milestones")))
    birthday = str(candidate.get("birthday") or "").strip()
    created_on = str(candidate.get("created_on") or "").strip()
    if birthday:
        entries.append(("birthday", birthday, "birthday"))
    if created_on:
        entries.append(("created_on", created_on, "created_on"))
    return tuple(dict.fromkeys(entries))


def _coerce_named_dates(value: object) -> tuple[tuple[str, str, str], ...]:
    milestones: list[tuple[str, str, str]] = []
    if isinstance(value, Sequence) and not isinstance(value, str):
        for item in value:
            if not isinstance(item, Mapping):
                continue
            label = str(item.get("label") or item.get("name") or "").strip()
            occurred_on = str(item.get("occurred_on") or item.get("date") or "").strip()
            kind = str(item.get("kind") or "").strip() or "milestone"
            if label and occurred_on:
                milestones.append((label, occurred_on, kind))
    return tuple(milestones)


def _coerce_str_list(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, Sequence):
        return tuple(str(item).strip() for item in value if str(item or "").strip())
    return ()


def _format_date(value: str, output_format: str) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(value or "").strip())
    if match is None:
        return str(value or "").strip()
    year, month, day = match.groups()
    if output_format == "dd-mm-yyyy":
        return f"{day}-{month}-{year}"
    if output_format == "mm/dd/yyyy":
        return f"{month}/{day}/{year}"
    if output_format == "month dd, yyyy":
        return f"{_MONTH_NAMES[month]} {day}, {year}"
    return f"{year}-{month}-{day}"


def _grounding_refs(
    candidate: Mapping[str, Any], cast_refs: Sequence[str]
) -> tuple[str, ...]:
    resolved = _normalize_repo_path(candidate.get("path") or "")
    if resolved not in {"", "/"}:
        return (resolved,)
    return tuple(
        dict.fromkeys(
            _normalize_repo_path(ref) for ref in cast_refs if str(ref or "").strip()
        )
    )


def _normalize_repo_path(path: object) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text.startswith("/"):
        text = f"/{text}"
    text = re.sub(r"/+", "/", text)
    return text.rstrip("/") or "/"


__all__ = ["EntityQueryResult", "resolve_entity_query"]
