from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


Number = int | float


def normalize_number(value: Number) -> Number:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def money_to_number(value: Money | Number | None) -> Number | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return normalize_number(value)
    return value.to_number()


def money_number_from_cents(cents: int) -> Number:
    if cents % 100 == 0:
        return cents // 100
    return cents / 100.0


@dataclass(frozen=True, slots=True)
class Money:
    cents: int

    @classmethod
    def from_number(cls, value: object) -> Money | None:
        if not isinstance(value, int | float):
            return None
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        cents = int((decimal_value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return cls(cents=cents)

    def to_number(self) -> Number:
        return money_number_from_cents(self.cents)


def coerce_money(value: Money | Number | None) -> Money | None:
    if isinstance(value, Money):
        return value
    return Money.from_number(value)
