from __future__ import annotations

from dataclasses import dataclass

from .finance_record import FinanceRecord, RecordType
from .money import Number


@dataclass(frozen=True, slots=True)
class FinanceAnchorCriteria:
    path_reference_text: str = ""
    item_name: str = ""
    counterparty_name: str = ""
    reference_number: str = ""
    alias: str = ""
    project: str = ""
    related_entity: str = ""
    date_range: tuple[str, str] | None = None
    target_date: str | None = None


@dataclass(frozen=True, slots=True)
class FinanceCounterpartyTotalCriteria:
    item_name: str = ""
    counterparty_name: str = ""
    requested_record_type: str | RecordType | None = None
    target_date: str | None = None
    line_item_scope: bool = False
    amount_hints: tuple[Number, ...] = ()


@dataclass(frozen=True, slots=True)
class FinanceCounterpartyTotalResolution:
    counterparty: str
    record_type: RecordType
    amount: Number
    matched_records: tuple[FinanceRecord, ...]
    anchor_records: tuple[FinanceRecord, ...] = ()
    line_item_scope: bool = False


@dataclass(frozen=True, slots=True)
class FinanceLineItemTotalCriteria:
    item_name: str = ""
    counterparty_name: str = ""
    requested_record_type: str | RecordType | None = None
    target_date: str | None = None
    amount_hints: tuple[Number, ...] = ()


@dataclass(frozen=True, slots=True)
class FinanceLineItemTotalResolution:
    counterparty: str
    record_type: RecordType
    amount: Number
    matched_record: FinanceRecord
    anchor_records: tuple[FinanceRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class FinanceLineItemValueCriteria:
    item_name: str = ""
    counterparty_name: str = ""
    requested_record_type: str | RecordType | None = None
    target_date: str | None = None
    date_range: tuple[str, str] | None = None


@dataclass(frozen=True, slots=True)
class FinanceLineItemValueResolution:
    amount: Number
    matched_record: FinanceRecord


@dataclass(frozen=True, slots=True)
class FinanceRecordQueryCriteria:
    counterparty_name: str = ""
    requested_record_type: str | RecordType | None = None
    date_range: tuple[str, str] | None = None


@dataclass(frozen=True, slots=True)
class FinanceServiceLineRevenueResolution:
    amount: Number
    matched_records: tuple[FinanceRecord, ...]


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
]
