from __future__ import annotations

"""Thin public surface over finance policy modules.

`domain/finance/policy.py` used to bundle anchor selection, counterparty
aggregation, line-item selection, service-line revenue, and generic record
selection in one 500+ line module. The public API stays here; the owning logic
now lives in smaller modules grouped by responsibility.
"""

from .anchor_selection import select_anchor_record, select_unique_record
from .counterparty_total import resolve_counterparty_total
from .line_item_values import resolve_line_item_total, resolve_line_item_value
from .policy_models import (
    FinanceAnchorCriteria,
    FinanceCounterpartyTotalCriteria,
    FinanceCounterpartyTotalResolution,
    FinanceLineItemTotalCriteria,
    FinanceLineItemTotalResolution,
    FinanceLineItemValueCriteria,
    FinanceLineItemValueResolution,
    FinanceRecordQueryCriteria,
    FinanceServiceLineRevenueResolution,
)
from .service_line_total import resolve_service_line_total

__all__ = [
    "FinanceAnchorCriteria",
    "FinanceCounterpartyTotalCriteria",
    "FinanceCounterpartyTotalResolution",
    "FinanceLineItemTotalCriteria",
    "FinanceLineItemTotalResolution",
    "FinanceLineItemValueCriteria",
    "FinanceLineItemValueResolution",
    "FinanceRecordQueryCriteria",
    "FinanceServiceLineRevenueResolution",
    "resolve_counterparty_total",
    "resolve_line_item_total",
    "resolve_line_item_value",
    "resolve_service_line_total",
    "select_anchor_record",
    "select_unique_record",
]
