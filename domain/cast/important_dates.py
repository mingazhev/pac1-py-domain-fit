from __future__ import annotations

import re
from enum import Enum
from typing import Any


class ImportantDateKind(str, Enum):
    BIRTHDAY = "birthday"
    CREATED_ON = "created_on"
    PROTOTYPE_STARTED = "prototype_started"
    ANNUAL_VET_WINDOW = "annual_vet_window"
    MAINTENANCE_WINDOW = "maintenance_window"
    MILESTONE = "milestone"


def _normalize_important_date_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def parse_important_date_kind(value: Any) -> ImportantDateKind | None:
    normalized = _normalize_important_date_token(value)
    if not normalized:
        return None
    for member in ImportantDateKind:
        if member.value == normalized:
            return member
    return None


def classify_important_date_label(label: Any) -> ImportantDateKind:
    parsed = parse_important_date_kind(label)
    if parsed is not None:
        return parsed
    return ImportantDateKind.MILESTONE


def normalize_important_date_kind(value: Any) -> str:
    parsed = parse_important_date_kind(value)
    if parsed is not None:
        return parsed.value
    normalized = _normalize_important_date_token(value)
    return normalized or ImportantDateKind.MILESTONE.value
