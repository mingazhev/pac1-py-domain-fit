from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class CaptureRecordProjection:
    path: str
    title: str
    body: str
    captured_on: str


@dataclass(frozen=True, slots=True)
class CaptureDayIndex:
    by_date: dict[str, tuple[CaptureRecordProjection, ...]]


@dataclass(frozen=True, slots=True)
class CaptureDayResolution:
    status: Literal["resolved", "clarify_missing", "clarify_multiple"]
    target_date: str
    record: CaptureRecordProjection | None = None
    candidates: tuple[CaptureRecordProjection, ...] = ()
def build_capture_day_index(
    records: Sequence[CaptureRecordProjection],
) -> CaptureDayIndex:
    if not records:
        return CaptureDayIndex(by_date={})
    by_date: dict[str, list[CaptureRecordProjection]] = defaultdict(list)
    for record in records:
        captured_on = str(record.captured_on or "").strip()
        if not captured_on:
            continue
        by_date[captured_on].append(record)
    return CaptureDayIndex(
        by_date={key: tuple(value) for key, value in by_date.items()}
    )


def resolve_capture_on_date(
    index: CaptureDayIndex,
    *,
    target_date: str,
) -> CaptureDayResolution:
    normalized_date = str(target_date or "").strip()
    if not normalized_date:
        return CaptureDayResolution(
            status="clarify_missing",
            target_date="",
        )
    candidates = tuple(index.by_date.get(normalized_date, ()))
    if not candidates:
        return CaptureDayResolution(
            status="clarify_missing",
            target_date=normalized_date,
        )
    if len(candidates) != 1:
        return CaptureDayResolution(
            status="clarify_multiple",
            target_date=normalized_date,
            candidates=candidates,
        )
    return CaptureDayResolution(
        status="resolved",
        target_date=normalized_date,
        record=candidates[0],
        candidates=candidates,
    )


__all__ = [
    "CaptureDayIndex",
    "CaptureDayResolution",
    "CaptureRecordProjection",
    "build_capture_day_index",
    "resolve_capture_on_date",
]
