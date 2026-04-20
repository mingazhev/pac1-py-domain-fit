from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from application.temporal import resolve_relative_lookup_base_time
from domain.capture import CaptureRecordProjection, build_capture_day_index, resolve_capture_on_date
from temporal_controls import (
    compute_relative_date,
    extract_relative_date_phrase,
)


@dataclass(frozen=True, slots=True)
class CaptureLookupQueryResult:
    status: Literal["resolved", "clarify_missing", "clarify_multiple"]
    message: str
    grounding_refs: tuple[str, ...]


_OUTPUT_MAP: dict[str, str] = {
    "title": "title",
    "filename": "path",
    "context_note": "body",
    "date": "captured_on",
}


def resolve_capture_lookup_query(
    capture_records: Sequence[CaptureRecordProjection],
    *,
    relative_date_phrase: str,
    output_field: str,
    context_payload: Mapping[str, Any] | None,
) -> CaptureLookupQueryResult | None:
    phrase = str(relative_date_phrase or "").strip()
    if not phrase:
        return None
    base_time = resolve_relative_lookup_base_time(context_payload)
    if base_time is None:
        return None
    if not capture_records:
        return CaptureLookupQueryResult(
            status="clarify_missing",
            message="No capture notes are loaded in canonical context.",
            grounding_refs=(),
        )
    date_phrase = extract_relative_date_phrase(phrase)
    if not date_phrase:
        return None
    target_date = compute_relative_date(base_time, date_phrase)
    resolution = resolve_capture_on_date(
        build_capture_day_index(capture_records),
        target_date=target_date,
    )
    target_field = _OUTPUT_MAP.get(output_field, "title")
    if resolution.status == "resolved" and resolution.record is not None:
        record = resolution.record
        value = str(getattr(record, target_field, "") or "").strip()
        if not value and target_field == "path":
            value = str(getattr(record, "path", "") or "").strip()
        grounding = _refs(record)
        return CaptureLookupQueryResult(
            status="resolved",
            message=value,
            grounding_refs=grounding,
        )
    if resolution.status == "clarify_multiple":
        candidate_paths = tuple(
            _normalize_path(getattr(record, "path", ""))
            for record in resolution.candidates
            if str(getattr(record, "path", "") or "").strip()
        )
        return CaptureLookupQueryResult(
            status="clarify_multiple",
            message=(
                f"Multiple capture notes match {resolution.target_date}; "
                "clarify which one."
            ),
            grounding_refs=candidate_paths,
        )
    return CaptureLookupQueryResult(
        status="clarify_missing",
        message=(
            f"No capture note was recorded on {resolution.target_date}."
        ),
        grounding_refs=(),
    )


def _refs(record: Mapping[str, Any] | object) -> tuple[str, ...]:
    path = _normalize_path(
        getattr(record, "path", None) if not isinstance(record, Mapping) else record.get("path")
    )
    return (path,) if path else ()


def _normalize_path(path: object) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        return ""
    if not text.startswith("/"):
        text = f"/{text}"
    while "//" in text:
        text = text.replace("//", "/")
    return text.rstrip("/") or "/"


__all__ = ["CaptureLookupQueryResult", "resolve_capture_lookup_query"]
