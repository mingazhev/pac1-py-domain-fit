"""Explicit `ServiceLine` domain model for derived revenue aggregation.

`service_line` is not a stored field on `FinanceRecord`. It is a *derived*
grouping dimension: callers ask "how much did service line X bring in
since Y" and the answer is computed by matching line items against an exact canonical name
and summing their `line_eur`. This module makes the derivation explicit so
consumers do not have to reconstruct the grouping contract at every call
site.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .finance_record import FinanceRecord
from .policy import (
    FinanceServiceLineRevenueResolution,
    resolve_service_line_total,
)


@dataclass(frozen=True, slots=True)
class ServiceLine:
    """Derived revenue aggregation dimension for invoice line items.

    A `ServiceLine` is identified by an exact canonical item name. It is explicitly
    derived — it does not shadow or replace stored line items. Callers that
    need the aggregated revenue ask the service line to resolve against a
    record set; callers that need the raw line items read them from the
    records directly.
    """

    item_name: str
    since_date: str

    def aggregate(
        self,
        records: Sequence[FinanceRecord],
    ) -> FinanceServiceLineRevenueResolution | None:
        return resolve_service_line_total(
            records,
            item_name=self.item_name,
            since_date=self.since_date,
        )
