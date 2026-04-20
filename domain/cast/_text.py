from __future__ import annotations

import re
from collections.abc import Sequence


def normalize_cast_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def join_unique_text(parts: Sequence[str]) -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        normalized = str(part or "").strip()
        if not normalized:
            continue
        key = normalize_cast_text(normalized)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(normalized)
    return " ".join(ordered)
