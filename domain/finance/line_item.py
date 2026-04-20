from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from .money import Money, Number, coerce_money, money_to_number, normalize_number


def _normalize(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    normalized_chars = [char if char.isalnum() else " " for char in text]
    return " ".join("".join(normalized_chars).split())


@dataclass(frozen=True, slots=True)
class LineItem:
    item: str
    quantity: Number | None = None
    unit_eur: Money | Number | None = None
    line_eur: Money | Number | None = None

    def __post_init__(self) -> None:
        quantity = self.quantity
        if isinstance(quantity, int | float):
            object.__setattr__(self, "quantity", normalize_number(quantity))
        object.__setattr__(self, "unit_eur", coerce_money(self.unit_eur))
        object.__setattr__(self, "line_eur", coerce_money(self.line_eur))

    @property
    def effective_price(self) -> Number | None:
        return money_to_number(self.unit_eur) if self.unit_eur is not None else money_to_number(self.line_eur)

    def matches_name(self, item_name: str) -> bool:
        normalized_name = _normalize(item_name)
        if not normalized_name:
            return False
        return normalized_name == _normalize(self.item)

    def value_for_fields(self, fields: Sequence[str]) -> Number | None:
        for field_name in fields:
            normalized_field = field_name.strip().lower()
            if normalized_field in {"qty", "quantity"} and self.quantity is not None:
                return self.quantity
            if normalized_field == "unit_eur":
                value = money_to_number(self.unit_eur)
                if value is not None:
                    return value
                line_total = money_to_number(self.line_eur)
                if (
                    line_total is not None
                    and self.quantity is not None
                    and float(self.quantity) > 0.0
                ):
                    return normalize_number(float(line_total) / float(self.quantity))
            if normalized_field == "line_eur":
                value = money_to_number(self.line_eur)
                if value is not None:
                    return value
        return None

    def numeric_match_score(self, hints: Sequence[Number]) -> int:
        remaining = [float(hint) for hint in hints]
        score = 0
        for candidate in (self.quantity, money_to_number(self.unit_eur), money_to_number(self.line_eur)):
            if candidate is None:
                continue
            candidate_value = float(candidate)
            for index, hint in enumerate(remaining):
                if abs(candidate_value - hint) <= 1e-9:
                    score += 1
                    del remaining[index]
                    break
        return score
