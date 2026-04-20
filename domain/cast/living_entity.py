from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .cast_entity import CastEntity


def next_birthday_occurrence(
    birthday: str, reference_date: datetime
) -> datetime | None:
    """Strictly-future next-birthday occurrence.

    A birthday that falls on ``reference_date.date()`` itself is
    considered already-past for the purpose of "next upcoming":
    when the answer needs to advance a person-of-the-day question,
    today's birthday is the current one, not the next one.
    """

    try:
        parsed = datetime.strptime(birthday, "%Y-%m-%d")
    except ValueError:
        return None
    for year in range(reference_date.year, reference_date.year + 9):
        try:
            occurrence = parsed.replace(year=year)
        except ValueError:
            continue
        if occurrence.date() > reference_date.date():
            return occurrence
    return None


@dataclass(frozen=True, slots=True)
class LivingCastEntity(CastEntity):
    birthday: str | None = None

    def has_birthday(self) -> bool:
        return bool(self.birthday)

    def supports_birthday_tracking(self) -> bool:
        return True

    def next_birthday_after(self, reference_date: datetime) -> datetime | None:
        if not self.birthday:
            return None
        return next_birthday_occurrence(self.birthday, reference_date)
