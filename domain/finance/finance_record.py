from __future__ import annotations

from dataclasses import dataclass

from .currency import DEFAULT_CURRENCY_POLICY, CurrencyCode, CurrencyPolicy
from .line_item import LineItem
from .money import Money, Number, coerce_money
from .record_type import RecordType
from .references import EntityReference, ProjectReference, ReferenceNumber
from .settlement import PaymentState, SettlementChannel


@dataclass(frozen=True, slots=True)
class FinanceRecord:
    path: str
    record_type: RecordType
    date: str
    counterparty: str
    total_eur: Money | Number | None = None
    related_entity: str = ""
    project: str = ""
    reference_number: str = ""
    alias: str = ""
    title: str = ""
    line_items: tuple[LineItem, ...] = ()
    payment_state: PaymentState | str | None = None
    settlement_reference: str = ""
    settlement_channel: SettlementChannel | str | None = None
    settlement_date: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "total_eur", coerce_money(self.total_eur))
        object.__setattr__(self, "payment_state", PaymentState.parse(self.payment_state))
        object.__setattr__(
            self,
            "settlement_channel",
            SettlementChannel.parse(self.settlement_channel),
        )

    def matches_record_type(self, record_type: str | RecordType | None) -> bool:
        if record_type is None:
            return True
        normalized = str(record_type or "").strip().lower()
        if normalized in {"", "any"}:
            return True
        parsed = (
            record_type
            if isinstance(record_type, RecordType)
            else RecordType.parse(record_type)
        )
        return parsed is not None and self.record_type is parsed

    def has_total(self) -> bool:
        return self.total_eur is not None

    def in_date_range(self, start_date: str, end_date: str) -> bool:
        return bool(self.date) and start_date <= self.date <= end_date

    def typed_reference_number(self) -> ReferenceNumber | None:
        if self.record_type is RecordType.INVOICE:
            return ReferenceNumber.for_invoice(self.reference_number)
        return ReferenceNumber.for_bill(self.reference_number)

    def typed_entity_reference(self) -> EntityReference | None:
        return EntityReference.from_raw(self.related_entity)

    def typed_project_reference(self) -> ProjectReference | None:
        return ProjectReference.from_raw(self.project)

    def currency_code(self, policy: CurrencyPolicy = DEFAULT_CURRENCY_POLICY) -> CurrencyCode:
        return policy.canonical_currency
