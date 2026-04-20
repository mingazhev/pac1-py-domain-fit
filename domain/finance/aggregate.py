from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .finance_record import FinanceRecord
from .line_item import LineItem
from .money import Number, money_to_number, normalize_number
from .settlement import (
    PaymentState,
    SettlementChannel,
    payment_state_text,
    settlement_channel_text,
)


@dataclass(frozen=True, slots=True)
class FinanceRecordDraft:
    path: str
    title: str
    record_type: object
    date: str
    counterparty: str
    total_eur: Number | None
    related_entity: str = ""
    project: str = ""
    reference_number: str = ""
    alias: str = ""
    line_items: tuple[LineItem, ...] = ()
    payment_state: PaymentState | str | None = None
    settlement_reference: str = ""
    settlement_channel: SettlementChannel | str | None = None
    settlement_date: str = ""

    @classmethod
    def from_record(cls, record: FinanceRecord) -> FinanceRecordDraft:
        return cls(
            path=str(record.path or "").strip(),
            title=str(record.title or "").strip(),
            record_type=record.record_type,
            date=str(record.date or "").strip(),
            counterparty=str(record.counterparty or "").strip(),
            total_eur=money_to_number(record.total_eur),
            related_entity=str(record.related_entity or "").strip(),
            project=str(record.project or "").strip(),
            reference_number=str(record.reference_number or "").strip(),
            alias=str(record.alias or "").strip(),
            line_items=tuple(record.line_items or ()),
            payment_state=record.payment_state,
            settlement_reference=str(record.settlement_reference or "").strip(),
            settlement_channel=record.settlement_channel,
            settlement_date=str(record.settlement_date or "").strip(),
        )

    def to_record(self) -> FinanceRecord:
        return FinanceRecord(
            path=self.path,
            record_type=self.record_type,
            date=self.date,
            counterparty=self.counterparty,
            total_eur=self.total_eur,
            related_entity=self.related_entity,
            project=self.project,
            reference_number=self.reference_number,
            alias=self.alias,
            title=self.title,
            line_items=self.line_items,
            payment_state=self.payment_state,
            settlement_reference=self.settlement_reference,
            settlement_channel=self.settlement_channel,
            settlement_date=self.settlement_date,
        )


@dataclass(frozen=True, slots=True)
class FinanceAggregateError(Exception):
    reason_code: str
    message: str
    status: str = "clarify_missing"

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class FinanceRecordAggregate:
    draft: FinanceRecordDraft

    @classmethod
    def from_record(cls, record: FinanceRecord) -> FinanceRecordAggregate:
        aggregate = cls(draft=FinanceRecordDraft.from_record(record))
        aggregate._validate()
        return aggregate

    def to_record(self) -> FinanceRecord:
        self._validate()
        return self.draft.to_record()

    def replace_line_items(
        self,
        line_items: Sequence[LineItem],
    ) -> FinanceRecordAggregate:
        normalized_items = tuple(_validated_line_item(item) for item in line_items)
        total_eur = _line_items_total(normalized_items)
        return self._replace(
            line_items=normalized_items,
            total_eur=total_eur,
        )

    def add_line_item(
        self,
        *,
        item: str,
        quantity: Number | None = None,
        unit_eur: Number | None = None,
    ) -> FinanceRecordAggregate:
        line_item = _validated_line_item(
            LineItem(
                item=str(item or "").strip(),
                quantity=1 if quantity is None else quantity,
                unit_eur=unit_eur,
            )
        )
        return self.replace_line_items((*self.draft.line_items, line_item))

    def remove_line_item_at(self, *, index: int) -> FinanceRecordAggregate:
        if not self.draft.line_items:
            raise FinanceAggregateError(
                reason_code="finance_mutation_line_items_missing",
                message="The canonical finance record has no line items to remove.",
            )
        if index < 0 or index >= len(self.draft.line_items):
            raise FinanceAggregateError(
                reason_code="finance_mutation_line_item_not_found",
                message=f"No line item exists at index {index}.",
            )
        remaining = tuple(
            item
            for item_index, item in enumerate(self.draft.line_items)
            if item_index != index
        )
        return self._replace(line_items=remaining, total_eur=_line_items_total(remaining))

    def adjust_total(self, amount: Number | None) -> FinanceRecordAggregate:
        if amount is None:
            raise FinanceAggregateError(
                reason_code="finance_mutation_amount_missing",
                message="adjust_amount requires an explicit amount.",
            )
        normalized = normalize_number(float(amount))
        if float(normalized) < 0:
            raise FinanceAggregateError(
                reason_code="finance_mutation_amount_invalid",
                message="Finance totals cannot be negative.",
            )
        if self.draft.line_items:
            raise FinanceAggregateError(
                reason_code="finance_mutation_total_conflicts_with_lines",
                message=(
                    "Cannot adjust total directly while canonical line items exist; "
                    "change the line items or replace them instead."
                ),
                status="blocked",
            )
        return self._replace(total_eur=normalized)

    def update_date(self, date: str | None) -> FinanceRecordAggregate:
        normalized = str(date or "").strip()
        if not normalized:
            raise FinanceAggregateError(
                reason_code="finance_mutation_date_missing",
                message="Finance record updates require a non-empty ISO date.",
            )
        return self._replace(date=normalized)

    def attach_settlement_evidence(
        self,
        *,
        settlement_reference: str | None = None,
        settlement_channel: str | None = None,
        settlement_date: str | None = None,
    ) -> FinanceRecordAggregate:
        reference = str(settlement_reference or "").strip()
        channel = SettlementChannel.parse(settlement_channel)
        date = str(settlement_date or "").strip()
        if channel and not reference:
            raise FinanceAggregateError(
                reason_code="finance_mutation_settlement_evidence_missing",
                message=(
                    "settlement_channel is set but settlement_reference is missing; "
                    "settlement evidence is incomplete."
                ),
                status="blocked",
            )
        return self._replace(
            settlement_reference=reference or self.draft.settlement_reference,
            settlement_channel=channel or self.draft.settlement_channel,
            settlement_date=date or self.draft.settlement_date,
        )

    def mark_settled(
        self,
        *,
        settlement_reference: str | None = None,
        settlement_channel: str | None = None,
        settlement_date: str | None = None,
    ) -> FinanceRecordAggregate:
        with_evidence = self.attach_settlement_evidence(
            settlement_reference=settlement_reference,
            settlement_channel=settlement_channel,
            settlement_date=settlement_date,
        )
        return with_evidence._replace(payment_state=PaymentState.SETTLED)

    def _replace(self, **updates) -> FinanceRecordAggregate:
        payload = {
            "path": self.draft.path,
            "title": self.draft.title,
            "record_type": self.draft.record_type,
            "date": self.draft.date,
            "counterparty": self.draft.counterparty,
            "total_eur": self.draft.total_eur,
            "related_entity": self.draft.related_entity,
            "project": self.draft.project,
            "reference_number": self.draft.reference_number,
            "alias": self.draft.alias,
            "line_items": self.draft.line_items,
            "payment_state": self.draft.payment_state,
            "settlement_reference": self.draft.settlement_reference,
            "settlement_channel": self.draft.settlement_channel,
            "settlement_date": self.draft.settlement_date,
        }
        payload.update(updates)
        aggregate = FinanceRecordAggregate(draft=FinanceRecordDraft(**payload))
        aggregate._validate()
        return aggregate

    def _validate(self) -> None:
        if not str(self.draft.path or "").strip():
            raise FinanceAggregateError(
                reason_code="finance_mutation_target_unresolved",
                message="Finance aggregate requires a canonical record path.",
            )
        if not str(self.draft.counterparty or "").strip():
            raise FinanceAggregateError(
                reason_code="finance_mutation_counterparty_missing",
                message="Finance aggregate requires a canonical counterparty.",
            )
        if not str(self.draft.date or "").strip():
            raise FinanceAggregateError(
                reason_code="finance_mutation_date_missing",
                message="Finance aggregate requires a canonical ISO date.",
            )
        for item in self.draft.line_items:
            _validated_line_item(item)
        if self.draft.line_items:
            expected_total = _line_items_total(self.draft.line_items)
            recorded_total = self.draft.total_eur
            if recorded_total is None or float(recorded_total) != float(expected_total):
                raise FinanceAggregateError(
                    reason_code="finance_mutation_total_conflicts_with_lines",
                    message="Finance total must equal the sum of canonical line items.",
                    status="blocked",
                )
        if self.draft.settlement_channel and not self.draft.settlement_reference:
            raise FinanceAggregateError(
                reason_code="finance_mutation_settlement_evidence_missing",
                message=(
                    "settlement_channel is set but settlement_reference is missing; "
                    "settlement evidence is incomplete."
                ),
                status="blocked",
            )
        self._validate_settlement_metadata()

    def _validate_settlement_metadata(self) -> None:
        state_text = payment_state_text(self.draft.payment_state)
        channel_text = settlement_channel_text(self.draft.settlement_channel)
        if state_text and PaymentState.parse(state_text) is None:
            raise FinanceAggregateError(
                reason_code="finance_mutation_payment_state_invalid",
                message=f"Unknown payment_state {state_text!r}.",
                status="blocked",
            )
        if channel_text and SettlementChannel.parse(channel_text) is None:
            raise FinanceAggregateError(
                reason_code="finance_mutation_settlement_channel_invalid",
                message=f"Unknown settlement_channel {channel_text!r}.",
                status="blocked",
            )


def _validated_line_item(item: LineItem) -> LineItem:
    name = str(item.item or "").strip()
    if not name:
        raise FinanceAggregateError(
            reason_code="finance_mutation_line_item_missing",
            message="Line items require a non-empty item name.",
        )
    quantity = item.quantity
    if quantity is None or float(quantity) <= 0:
        raise FinanceAggregateError(
            reason_code="finance_mutation_quantity_invalid",
            message="Line item quantity must be greater than zero.",
        )
    unit_eur = money_to_number(item.unit_eur)
    if unit_eur is None or float(unit_eur) < 0:
        raise FinanceAggregateError(
            reason_code="finance_mutation_unit_price_invalid",
            message="Line item unit price must be zero or greater.",
        )
    line_total = money_to_number(item.line_eur)
    if line_total is not None and float(line_total) < 0:
        raise FinanceAggregateError(
            reason_code="finance_mutation_line_total_invalid",
            message="Line item total must be zero or greater.",
        )
    return LineItem(item=name, quantity=quantity, unit_eur=unit_eur)


def _line_items_total(line_items: Sequence[LineItem]) -> Number:
    if not line_items:
        return 0
    total = 0.0
    for item in line_items:
        quantity = float(item.quantity or 0)
        unit = float(money_to_number(item.unit_eur) or 0)
        total += quantity * unit
    return normalize_number(total)


def _canonical_line_item_name(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    normalized_chars = [char if char.isalnum() else " " for char in text]
    return re.sub(r"\s+", " ", "".join(normalized_chars)).strip()


__all__ = [
    "FinanceAggregateError",
    "FinanceRecordAggregate",
    "FinanceRecordDraft",
]
