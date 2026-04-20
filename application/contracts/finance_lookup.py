from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from domain.finance.policy import FinanceAnchorCriteria


FinanceLookupAction = Literal[
    "counterparty_total",
    "service_line_total",
    "record_date",
    "record_total",
    "settlement_status",
    "settlement_reference",
    "line_item_count",
    "line_item_quantity",
    "line_item_price",
    "line_item_total",
]


@dataclass(frozen=True, slots=True)
class FinanceLookupIntent:
    action: FinanceLookupAction
    anchor_criteria: FinanceAnchorCriteria
    requested_record_type: str | None = None
    since_date: str | None = None
    amount_hints: tuple[int | float, ...] = ()
    output_format: str | None = None


def _coerce_output_format(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "iso"}:
        return None
    if normalized in {"dd-mm-yyyy", "mm/dd/yyyy", "month dd, yyyy"}:
        return normalized
    return None


def format_finance_record_date_output(
    task_text: str,
    record_date: str,
    *,
    output_format: str | None = None,
) -> str:
    normalized_date = str(record_date or "").strip()
    try:
        parsed = datetime.strptime(normalized_date, "%Y-%m-%d")
    except ValueError:
        return normalized_date
    normalized_task = _coerce_output_format(output_format) or str(task_text or "").strip().lower()
    if "dd-mm-yyyy" in normalized_task:
        return parsed.strftime("%d-%m-%Y")
    if "mm/dd/yyyy" in normalized_task:
        return parsed.strftime("%m/%d/%Y")
    if "month dd, yyyy" in normalized_task:
        return parsed.strftime("%B %d, %Y")
    match = re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized_date)
    if match is None and output_format is None:
        return normalized_date
    return parsed.strftime("%Y-%m-%d")


__all__ = [
    "FinanceLookupAction",
    "FinanceLookupIntent",
    "format_finance_record_date_output",
]
