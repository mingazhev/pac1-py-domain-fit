from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from application.contracts import (
    FinanceLookupIntent,
    format_finance_record_date_output,
)
from domain.finance import (
    FinanceCounterpartyTotalCriteria,
    FinanceRecord,
    FinanceRecordIdentityCriteria,
    FinanceLineItemValueCriteria,
    FinanceRecordQueryCriteria,
    FinanceLineItemTotalCriteria,
    RecordType,
    resolve_counterparty_total,
    resolve_finance_record_identity,
    resolve_finance_settlement_state,
    resolve_line_item_value,
    resolve_line_item_total,
    resolve_service_line_total,
    select_anchor_record,
    select_unique_record,
    select_unique_record_by_identity,
)
from domain.finance.settlement import payment_state_text


def _format_numeric_value(value: int | float) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _sorted_repo_paths(paths: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({path for path in paths if str(path or "").strip()}, key=str.lower))


@dataclass(frozen=True, slots=True)
class FinanceLookupQueryResult:
    message: str
    summary: str
    grounding_refs: tuple[str, ...]


def resolve_finance_lookup_query(
    records: Sequence[FinanceRecord],
    *,
    intent: FinanceLookupIntent,
    task_text: str,
) -> FinanceLookupQueryResult | None:
    action = intent.action

    if action == "counterparty_total":
        typed_anchor = (
            select_anchor_record(records, criteria=intent.anchor_criteria)
            if _should_use_anchor_record(intent)
            else None
        )
        resolved_total = resolve_counterparty_total(
            records,
            criteria=FinanceCounterpartyTotalCriteria(
                item_name=intent.anchor_criteria.item_name,
                counterparty_name=intent.anchor_criteria.counterparty_name,
                requested_record_type=intent.requested_record_type,
                target_date=intent.anchor_criteria.target_date,
                amount_hints=intent.amount_hints,
            ),
            anchor_record=typed_anchor,
        )
        if resolved_total is None:
            return None
        counterparty = resolved_total.counterparty
        answer = _format_numeric_value(resolved_total.amount)
        refs = _sorted_repo_paths(
            [
                *[record.path for record in resolved_total.matched_records if record.path],
                *[record.path for record in resolved_total.anchor_records if record.path],
            ]
        )
        summary = f"resolved total paid to {counterparty} deterministically"
        return FinanceLookupQueryResult(
            message=answer,
            summary=summary,
            grounding_refs=refs,
        )

    if action == "line_item_total":
        typed_anchor = (
            select_anchor_record(records, criteria=intent.anchor_criteria)
            if _should_use_anchor_record(intent)
            else None
        )
        resolved_total = resolve_line_item_total(
            records,
            criteria=FinanceLineItemTotalCriteria(
                item_name=intent.anchor_criteria.item_name,
                counterparty_name=intent.anchor_criteria.counterparty_name,
                requested_record_type=intent.requested_record_type,
                target_date=intent.anchor_criteria.target_date,
                amount_hints=intent.amount_hints,
            ),
            anchor_record=typed_anchor,
        )
        if resolved_total is None:
            return None
        return FinanceLookupQueryResult(
            message=_format_numeric_value(resolved_total.amount),
            summary=(
                f"resolved line-item total for {intent.anchor_criteria.item_name} "
                f"from {resolved_total.counterparty} deterministically"
            ),
            grounding_refs=(resolved_total.matched_record.path,),
        )

    if action == "service_line_total":
        item_name = intent.anchor_criteria.item_name
        since_date = intent.since_date
        if not item_name or not since_date:
            return None
        resolved_total = resolve_service_line_total(
            records,
            item_name=item_name,
            since_date=since_date,
        )
        if resolved_total is None:
            return None
        return FinanceLookupQueryResult(
            message=_format_numeric_value(resolved_total.amount),
            summary=f"resolved service-line revenue for {item_name} since {since_date} deterministically",
            grounding_refs=_sorted_repo_paths([record.path for record in resolved_total.matched_records if record.path]),
        )

    if action == "record_date":
        if intent.anchor_criteria.date_range is None or not intent.anchor_criteria.counterparty_name:
            return None
        selected_record = select_unique_record(
            records,
            criteria=FinanceRecordQueryCriteria(
                counterparty_name=intent.anchor_criteria.counterparty_name,
                requested_record_type=intent.requested_record_type,
                date_range=intent.anchor_criteria.date_range,
            ),
        )
        if selected_record is None:
            return None
        return FinanceLookupQueryResult(
            message=format_finance_record_date_output(
                task_text,
                selected_record.date,
                output_format=intent.output_format,
            ),
            summary=f"resolved finance record date for {selected_record.counterparty} deterministically",
            grounding_refs=(selected_record.path,),
        )

    if action == "record_total":
        selected_record = _select_unique_finance_record(records, intent=intent)
        if selected_record is None or selected_record.total_eur is None:
            return None
        amount = _format_numeric_value(selected_record.total_eur.to_number())
        return FinanceLookupQueryResult(
            message=amount,
            summary=f"resolved finance record total for {selected_record.counterparty} deterministically",
            grounding_refs=(selected_record.path,),
        )

    if action == "settlement_status":
        settlement = resolve_finance_settlement_state(
            records,
            criteria=_identity_criteria_from_intent(intent),
        )
        if settlement is None:
            return None
        status = payment_state_text(settlement.payment_state).strip() or (
            "settled" if settlement.is_settled else "unsettled"
        )
        return FinanceLookupQueryResult(
            message=status,
            summary="resolved finance settlement status deterministically",
            grounding_refs=(settlement.path,),
        )

    if action == "settlement_reference":
        settlement = resolve_finance_settlement_state(
            records,
            criteria=_identity_criteria_from_intent(intent),
        )
        if settlement is None or not settlement.settlement_reference.strip():
            return None
        return FinanceLookupQueryResult(
            message=settlement.settlement_reference.strip(),
            summary="resolved finance settlement reference deterministically",
            grounding_refs=(settlement.path,),
        )

    if action == "line_item_count":
        if intent.anchor_criteria.date_range is None or not intent.anchor_criteria.counterparty_name:
            return None
        selected_record = select_unique_record(
            records,
            criteria=FinanceRecordQueryCriteria(
                counterparty_name=intent.anchor_criteria.counterparty_name,
                requested_record_type=intent.requested_record_type,
                date_range=intent.anchor_criteria.date_range,
            ),
        )
        if selected_record is None:
            return None
        return FinanceLookupQueryResult(
            message=_format_numeric_value(len(selected_record.line_items)),
            summary=(
                f"resolved finance line count for {intent.requested_record_type or 'record'} from "
                f"{selected_record.counterparty} deterministically"
            ),
            grounding_refs=(selected_record.path,),
        )

    item_name = intent.anchor_criteria.item_name
    if (
        not item_name
        or intent.anchor_criteria.date_range is None
        or not intent.anchor_criteria.counterparty_name
    ):
        return None
    resolved_value = resolve_line_item_value(
        records,
        criteria=FinanceLineItemValueCriteria(
            item_name=item_name,
            counterparty_name=intent.anchor_criteria.counterparty_name,
            requested_record_type=intent.requested_record_type or RecordType.BILL,
            target_date=intent.anchor_criteria.target_date,
            date_range=intent.anchor_criteria.date_range,
        ),
        value_fields=("qty", "quantity")
        if action == "line_item_quantity"
        else ("unit_eur", "line_eur"),
    )
    if resolved_value is None:
        return None
    if action == "line_item_quantity":
        summary = f"resolved line-item quantity for {item_name} deterministically"
    else:
        summary = f"resolved line-item price for {item_name} deterministically"
    return FinanceLookupQueryResult(
        message=_format_numeric_value(resolved_value.amount),
        summary=summary,
        grounding_refs=(resolved_value.matched_record.path,),
    )


def _identity_criteria_from_intent(
    intent: FinanceLookupIntent,
) -> FinanceRecordIdentityCriteria:
    return FinanceRecordIdentityCriteria(
        record_type=intent.requested_record_type,
        counterparty=intent.anchor_criteria.counterparty_name,
        reference_number=intent.anchor_criteria.reference_number,
        alias=intent.anchor_criteria.alias,
        project=intent.anchor_criteria.project,
        related_entity=intent.anchor_criteria.related_entity,
        date=intent.anchor_criteria.target_date or "",
    )


def _select_unique_finance_record(
    records: Sequence[FinanceRecord],
    *,
    intent: FinanceLookupIntent,
) -> FinanceRecord | None:
    identity_criteria = _identity_criteria_from_intent(intent)
    if identity_criteria.has_identity():
        selected = select_unique_record_by_identity(records, criteria=identity_criteria)
        if selected is not None:
            return selected
        if (
            intent.anchor_criteria.counterparty_name
            and intent.anchor_criteria.date_range is not None
        ):
            return select_unique_record(
                records,
                criteria=FinanceRecordQueryCriteria(
                    counterparty_name=intent.anchor_criteria.counterparty_name,
                    requested_record_type=intent.requested_record_type,
                    date_range=intent.anchor_criteria.date_range,
                ),
            )
        return None
    if intent.anchor_criteria.date_range is None or not intent.anchor_criteria.counterparty_name:
        return None
    return select_unique_record(
        records,
        criteria=FinanceRecordQueryCriteria(
            counterparty_name=intent.anchor_criteria.counterparty_name,
            requested_record_type=intent.requested_record_type,
            date_range=intent.anchor_criteria.date_range,
        ),
    )


def _should_use_anchor_record(intent: FinanceLookupIntent) -> bool:
    criteria = intent.anchor_criteria
    return any(
        (
            criteria.path_reference_text,
            criteria.reference_number,
            criteria.alias,
            criteria.project,
            criteria.related_entity,
        )
    )
