"""Explicit currency policy for finance records.

The finance schema fixes `total_eur`, `unit_eur`, and `line_eur` to euros by
convention and states that convention in Markdown prose. The code layer used
to leave that convention implicit. `CurrencyPolicy` encodes the boundary as
domain data so tests and consumers can assert on it instead of re-deriving
the rule from field names.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CurrencyCode = Literal["EUR"]


@dataclass(frozen=True, slots=True)
class CurrencyPolicy:
    """Records the currency boundary for the finance bounded context.

    The current policy is single-currency EUR because the workspace schema
    declares EUR as the fallback when no currency is specified. Multi-currency
    records are not modelled yet and must be rejected rather than silently
    coerced.
    """

    canonical_currency: CurrencyCode = "EUR"
    accepted_currencies: tuple[str, ...] = field(default_factory=lambda: ("EUR",))

    def is_accepted(self, currency: object) -> bool:
        text = str(currency or "").strip().upper()
        if not text:
            return True
        return text in self.accepted_currencies

    def normalize(self, currency: object) -> CurrencyCode:
        text = str(currency or "").strip().upper()
        if not text or text not in self.accepted_currencies:
            return self.canonical_currency
        return self.canonical_currency


DEFAULT_CURRENCY_POLICY = CurrencyPolicy()
