from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone


def _parse_runtime_context_datetime(payload: Mapping[str, object]) -> datetime | None:
    for key in ("time", "timestamp", "datetime"):
        raw_value = payload.get(key)
        if not raw_value:
            continue
        text = str(raw_value).strip()
        if not text:
            continue
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    for key in ("unixTime", "unix_time"):
        raw_value = payload.get(key)
        if raw_value in (None, ""):
            continue
        try:
            stamp = int(raw_value)
        except (TypeError, ValueError):
            continue
        return datetime.fromtimestamp(stamp, timezone.utc)
    return None


def resolve_relative_lookup_base_time(
    context_payload: Mapping[str, object] | None,
    *,
    current_time: datetime | None = None,
) -> datetime | Mapping[str, object] | None:
    """Authoritative "now" for the current VM request.

    The VM context payload carries the scenario time — for benchmark
    runs this can be days, weeks, or months behind wall-clock time
    and is exactly the answer the harness expects us to reason from.
    There is no staleness fallback: if the payload parses, we use
    it. ``current_time`` is accepted for test override only. When
    the payload does not carry a parseable time at all, we return
    the raw payload so downstream callers can decide.
    """

    if context_payload is None:
        return None
    parsed_context = _parse_runtime_context_datetime(context_payload)
    if parsed_context is not None:
        return parsed_context
    if current_time is not None:
        effective_now = current_time
        if effective_now.tzinfo is None:
            effective_now = effective_now.replace(tzinfo=timezone.utc)
        else:
            effective_now = effective_now.astimezone(timezone.utc)
        return effective_now
    return context_payload
