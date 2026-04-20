from __future__ import annotations

import re

from domain.cast.relationship import (
    expand_cast_relationship_aliases,
    normalize_cast_relationship_label,
)


def normalize_relationship_label(value: object) -> str:
    return re.sub(r"[_\-]+", " ", normalize_cast_relationship_label(value)).strip()


def expand_relationship_aliases(value: str) -> tuple[str, ...]:
    return expand_cast_relationship_aliases(value)


__all__ = [
    "expand_relationship_aliases",
    "normalize_relationship_label",
]
