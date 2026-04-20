from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from .cast_entity import CastEntity


def resolve_aggregate_birthday_answer(
    entities: Sequence[CastEntity],
    reference_date: datetime,
    *,
    prefer_people_only: bool = False,
) -> tuple[str, tuple[str, ...]] | None:
    ranked: list[tuple[datetime, str, str]] = []
    for entity in entities:
        path = str(entity.path or "").strip()
        normalized_path = f"/{path}".replace("//", "/")
        if not entity.title or normalized_path in {"", "/"}:
            continue
        if not entity.supports_birthday_tracking() or not entity.has_birthday():
            continue
        if prefer_people_only and not entity.is_person():
            continue
        occurrence = entity.next_birthday_after(reference_date)
        if occurrence is None:
            continue
        ranked.append((occurrence, entity.title, normalized_path))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1].lower(), item[2]))
    soonest = ranked[0][0].date()
    selected = [
        (title, path)
        for occurrence, title, path in ranked
        if occurrence.date() == soonest
    ]
    selected.sort(key=lambda item: item[0].lower())
    return "\n".join(title for title, _ in selected), tuple(
        path for _, path in selected
    )


__all__ = ["resolve_aggregate_birthday_answer"]
