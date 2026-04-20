from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from formats.frontmatter import parse_frontmatter
from formats.json_payloads import parse_json_object

OUTCOME_RESOLVED = "resolved"
OUTCOME_CLARIFY_MISSING = "clarify_missing"
OUTCOME_CLARIFY_MULTIPLE = "clarify_multiple"

_RELATIVE_PHRASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\byesterday\b", re.IGNORECASE),
    re.compile(r"\btomorrow\b", re.IGNORECASE),
    re.compile(r"\bin\s+(?P<amount>\d+)\s+(?P<unit>day|days|week|weeks)\b", re.IGNORECASE),
    re.compile(r"\b(?P<amount>\d+)\s+(?P<unit>day|days|week|weeks)\s+ago\b", re.IGNORECASE),
    re.compile(r"\b(?P<amount>\d+)\s+(?P<unit>day|days|week|weeks)\s+before\b", re.IGNORECASE),
    re.compile(r"\b(?P<amount>\d+)\s+(?P<unit>day|days|week|weeks)\s+from\s+now\b", re.IGNORECASE),
    re.compile(r"\b(?P<amount>\d+)\s+(?P<unit>day|days|week|weeks)\s+after\b", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class RuntimeContextStamp:
    time_iso: str
    unix_time: int | None
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class TemporalResolution:
    status: str
    target_date: str
    record: Mapping[str, Any] | None = None
    candidates: tuple[Mapping[str, Any], ...] = ()


def parse_runtime_context_timestamp(value: Mapping[str, Any] | str | int | float | datetime) -> datetime:
    if isinstance(value, datetime):
        return _normalize_datetime(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        return _parse_datetime(value)
    if isinstance(value, Mapping):
        for key in ("time", "timestamp", "datetime"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                try:
                    return _parse_datetime(raw)
                except ValueError:
                    continue
        for key in ("unixTime", "unix_time", "timestamp_unix"):
            raw = value.get(key)
            if isinstance(raw, (int, float)):
                return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        raise ValueError("runtime context did not contain a parseable timestamp")
    raise TypeError(f"unsupported timestamp value type: {type(value).__name__}")


def load_runtime_context_stamp(path: Path) -> RuntimeContextStamp:
    payload = parse_json_object(path.read_text(encoding="utf-8"))
    timestamp = parse_runtime_context_timestamp(payload)
    unix_time = payload.get("unixTime")
    if not isinstance(unix_time, (int, float)):
        unix_time = payload.get("unix_time")
    normalized_unix = int(unix_time) if isinstance(unix_time, (int, float)) else None
    time_iso = str(payload.get("time") or payload.get("timestamp") or timestamp.isoformat().replace("+00:00", "Z"))
    return RuntimeContextStamp(time_iso=time_iso, unix_time=normalized_unix, timestamp=timestamp)


def extract_relative_date_phrase(task_text: str) -> str | None:
    for pattern in _RELATIVE_PHRASE_PATTERNS:
        match = pattern.search(task_text)
        if not match:
            continue
        if pattern.pattern == r"\byesterday\b":
            return "yesterday"
        if pattern.pattern == r"\btomorrow\b":
            return "tomorrow"
        amount = match.groupdict().get("amount")
        unit = match.groupdict().get("unit")
        if amount is None or unit is None:
            continue
        if pattern.pattern.endswith(r"\s+from\s+now\b") or pattern.pattern.endswith(r"\s+after\b") or pattern.pattern.startswith(r"\bin\s+"):
            return f"in {amount} {unit}"
        return f"{amount} {unit} ago"
    return None


def compute_relative_date(base_time: Mapping[str, Any] | str | int | float | datetime, phrase: str) -> str:
    base = parse_runtime_context_timestamp(base_time)
    normalized_phrase = phrase.strip().lower()
    if normalized_phrase == "yesterday":
        delta = timedelta(days=-1)
    elif normalized_phrase == "tomorrow":
        delta = timedelta(days=1)
    else:
        match = re.fullmatch(
            r"(?:in\s+)?(?P<amount>\d+)\s+(?P<unit>day|days|week|weeks)(?:\s+(?P<suffix>ago|before|from now|after))?",
            normalized_phrase,
        )
        if not match:
            raise ValueError(f"unsupported relative date phrase: {phrase}")
        amount = int(match.group("amount"))
        unit = match.group("unit")
        suffix = match.group("suffix")
        if unit.startswith("week"):
            amount *= 7
        if suffix in {"ago", "before"}:
            amount *= -1
        elif suffix in {"from now", "after", None} and not normalized_phrase.startswith("in "):
            if suffix is None:
                raise ValueError(f"unsupported relative date phrase: {phrase}")
        delta = timedelta(days=amount)
    return (base + delta).date().isoformat()


def parse_markdown_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    try:
        return parse_frontmatter(text)
    except ValueError:
        return {}, text


def collect_workspace_articles(workspace_root: Path, *, date_field: str = "captured_on") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(workspace_root.rglob("*.md")):
        frontmatter, body = parse_markdown_frontmatter(path)
        if date_field not in frontmatter:
            continue
        record = {
            "path": str(path.relative_to(workspace_root)),
            "title": frontmatter.get("title", path.stem),
            date_field: frontmatter[date_field],
            "frontmatter": frontmatter,
            "body": body,
        }
        records.append(record)
    return records


def resolve_records_by_date(
    records: Sequence[Mapping[str, Any]],
    *,
    target_date: str,
    date_field: str = "captured_on",
) -> TemporalResolution:
    matches = tuple(
        record
        for record in records
        if str(record.get(date_field, "")) == target_date
    )
    if len(matches) == 1:
        return TemporalResolution(status=OUTCOME_RESOLVED, target_date=target_date, record=matches[0], candidates=matches)
    if len(matches) > 1:
        return TemporalResolution(
            status=OUTCOME_CLARIFY_MULTIPLE,
            target_date=target_date,
            candidates=_sorted_candidates(matches, date_field=date_field),
        )
    return TemporalResolution(status=OUTCOME_CLARIFY_MISSING, target_date=target_date)


def resolve_records_by_phrase(
    records: Sequence[Mapping[str, Any]],
    *,
    base_time: Mapping[str, Any] | str | int | float | datetime,
    phrase: str,
    date_field: str = "captured_on",
) -> TemporalResolution:
    target_date = compute_relative_date(base_time, phrase)
    return resolve_records_by_date(records, target_date=target_date, date_field=date_field)


def resolve_workspace_articles_by_phrase(
    workspace_root: Path,
    *,
    base_time: Mapping[str, Any] | str | int | float | datetime,
    phrase: str,
    date_field: str = "captured_on",
) -> TemporalResolution:
    records = collect_workspace_articles(workspace_root, date_field=date_field)
    return resolve_records_by_phrase(records, base_time=base_time, phrase=phrase, date_field=date_field)
def _sorted_candidates(records: Sequence[Mapping[str, Any]], *, date_field: str) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        sorted(
            records,
            key=lambda record: (
                str(record.get("path", "")),
                str(record.get(date_field, "")),
                str(record.get("title", "")),
            ),
        )
    )


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return _normalize_datetime(parsed)
