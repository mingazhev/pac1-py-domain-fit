from __future__ import annotations

from collections.abc import Mapping, Sequence

from domain.capture import CaptureRecordProjection


def capture_record_from_mapping(
    raw: Mapping[str, object],
) -> CaptureRecordProjection | None:
    captured_on = str(raw.get("captured_on") or "").strip()
    path = str(raw.get("path") or "").strip()
    title = str(raw.get("title") or "").strip()
    body = str(raw.get("body") or "").strip()
    if not captured_on and not path and not title:
        return None
    return CaptureRecordProjection(
        path=path,
        title=title,
        body=body,
        captured_on=captured_on,
    )


def capture_records_from_mappings(
    raw_records: Sequence[Mapping[str, object]],
) -> tuple[CaptureRecordProjection, ...]:
    return tuple(
        record
        for record in (capture_record_from_mapping(raw) for raw in raw_records)
        if record is not None
    )


__all__ = ["capture_record_from_mapping", "capture_records_from_mappings"]
