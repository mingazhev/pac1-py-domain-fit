from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from domain.process import AuthorizationStamp
from domain.finance import (
    FinanceAggregateError,
    FinanceRecord,
    FinanceRecordAggregate,
    FinanceRecordIdentityCriteria,
    finance_record_resolve_unique_line_item_index_by_name,
    PaymentAuthorization,
    SettlementEvidence,
    SettlementChannel,
    evaluate_payment_gate,
    resolve_finance_record_identity,
)

from .finance_markdown import (
    extract_finance_leading_text,
    extract_finance_notes,
    extract_finance_preserved_sections,
    render_finance_markdown,
)
from .result import MutationStepResult


@dataclass(frozen=True, slots=True)
class FinanceRecordWritePlan:
    result: MutationStepResult
    frontmatter_updates: dict[str, str] | None = None
    rendered_content: str | None = None


def resolve_finance_update_record(
    finance_records: Sequence[FinanceRecord],
    *,
    action: str = "update_bill",
    record_type: str | None = None,
    record_path: str | None,
    anchor_record_ref: str | None,
    reference_number: str | None,
    counterparty: str | None,
    alias: str | None,
    project: str | None,
    related_entity: str | None,
    authorization_kind: str | None,
    authorized_by: str | None,
    settlement_reference: str | None,
    settlement_channel: str | None,
    settlement_date: str | None = None,
    amount: float | None = None,
    date: str | None = None,
    notes: str | None = None,
    item_name: str | None = None,
    line_item_index: int | None = None,
    quantity: float | None = None,
    unit_price: float | None = None,
    existing_record_text: str | None = None,
    resolved_record: FinanceRecord | None = None,
) -> FinanceRecordWritePlan:
    resolved = resolved_record or resolve_finance_target_record(
        finance_records,
        action=action,
        record_type=record_type,
        record_path=record_path,
        anchor_record_ref=anchor_record_ref,
        reference_number=reference_number,
        counterparty=counterparty,
        alias=alias,
        project=project,
        related_entity=related_entity,
        date=date,
        amount=amount,
    )
    if resolved is None:
        return FinanceRecordWritePlan(
            result=MutationStepResult(
                status="clarify_missing",
                message=(
                    "Could not resolve a unique canonical finance record for "
                    "the requested update."
                ),
                grounding_refs=_target_refs(record_path, anchor_record_ref),
                reason_code="finance_mutation_target_unresolved",
            )
        )

    normalized_path = _normalize_path(resolved.path)
    gate_plan = _evaluate_payment_gate_for_update(
        action=action,
        record_path=normalized_path,
        authorization_kind=authorization_kind,
        authorized_by=authorized_by,
        settlement_reference=settlement_reference,
        settlement_channel=settlement_channel,
        settlement_date=settlement_date,
    )
    if gate_plan is not None:
        return gate_plan

    if action in {
        "update_bill",
        "update_invoice",
        "add_line_item",
        "remove_line_item",
        "adjust_amount",
        "mark_paid",
        "settle_payment",
    }:
        return _resolve_aggregate_write_plan(
            resolved,
            action=action,
            amount=amount,
            item_name=item_name,
            line_item_index=line_item_index,
            quantity=quantity,
            unit_price=unit_price,
            settlement_reference=settlement_reference,
            settlement_channel=settlement_channel,
            settlement_date=settlement_date,
            date=date,
            notes=notes,
            existing_record_text=existing_record_text,
        )
    return FinanceRecordWritePlan(
        result=MutationStepResult(
            status="unsupported",
            message=f"Finance update action {action!r} is not supported.",
            grounding_refs=(normalized_path,),
            reason_code="finance_mutation_variant_unsupported",
        )
    )


def resolve_finance_update_bill(
    finance_records: Sequence[FinanceRecord],
    **kwargs,
) -> FinanceRecordWritePlan:
    return resolve_finance_update_record(finance_records, **kwargs)


def resolve_finance_target_record(
    finance_records: Sequence[FinanceRecord],
    *,
    action: str,
    record_type: str | None,
    record_path: str | None,
    anchor_record_ref: str | None,
    reference_number: str | None,
    counterparty: str | None,
    alias: str | None,
    project: str | None,
    related_entity: str | None,
    date: str | None,
    amount: float | None,
) -> FinanceRecord | None:
    return _resolve_target_record(
        finance_records,
        action=action,
        record_type=record_type,
        record_path=record_path,
        anchor_record_ref=anchor_record_ref,
        reference_number=reference_number,
        counterparty=counterparty,
        alias=alias,
        project=project,
        related_entity=related_entity,
        date=date,
        amount=amount,
    )


def _resolve_aggregate_write_plan(
    record: FinanceRecord,
    *,
    action: str,
    amount: float | None,
    date: str | None,
    item_name: str | None,
    line_item_index: int | None,
    quantity: float | None,
    unit_price: float | None,
    settlement_reference: str | None,
    settlement_channel: str | None,
    settlement_date: str | None,
    notes: str | None,
    existing_record_text: str | None,
) -> FinanceRecordWritePlan:
    try:
        aggregate = FinanceRecordAggregate.from_record(record)
        if action in {"update_bill", "update_invoice"}:
            if date and date.strip():
                aggregate = aggregate.update_date(date)
            if amount is not None:
                aggregate = aggregate.adjust_total(amount)
            if any(
                str(value or "").strip()
                for value in (
                    settlement_reference,
                    settlement_channel,
                    settlement_date,
                )
            ):
                aggregate = aggregate.attach_settlement_evidence(
                    settlement_reference=settlement_reference,
                    settlement_channel=settlement_channel,
                    settlement_date=settlement_date,
                )
        elif action == "add_line_item":
            aggregate = aggregate.add_line_item(
                item=str(item_name or "").strip(),
                quantity=quantity,
                unit_eur=unit_price,
            )
        elif action == "remove_line_item":
            resolved_line_item_index = line_item_index
            if resolved_line_item_index is None:
                resolved_line_item_index = finance_record_resolve_unique_line_item_index_by_name(
                    record,
                    str(item_name or "").strip(),
                )
                if resolved_line_item_index is None:
                    phrase = str(item_name or "").strip()
                    raise FinanceAggregateError(
                        reason_code="finance_mutation_line_item_not_found",
                        message=(
                            f"No unique canonical line item named {phrase!r} exists on the finance record; "
                            "remove by explicit index instead."
                        ),
                    )
            aggregate = aggregate.remove_line_item_at(index=resolved_line_item_index)
        elif action == "adjust_amount":
            aggregate = aggregate.adjust_total(amount)
        elif action in {"mark_paid", "settle_payment"}:
            aggregate = aggregate.mark_settled(
                settlement_reference=settlement_reference,
                settlement_channel=settlement_channel,
                settlement_date=settlement_date,
            )
        else:
            raise FinanceAggregateError(
                reason_code="finance_mutation_variant_unsupported",
                message=f"Aggregate path does not support action={action}.",
                status="unsupported",
            )
    except FinanceAggregateError as exc:
        return FinanceRecordWritePlan(
            result=MutationStepResult(
                status=exc.status,  # type: ignore[arg-type]
                message=exc.message,
                grounding_refs=(_normalize_path(record.path),),
                reason_code=exc.reason_code,
            )
        )

    effective_notes = (
        notes.strip()
        if notes and notes.strip()
        else extract_finance_notes(existing_record_text)
    )
    rendered = render_finance_markdown(
        aggregate,
        notes=effective_notes,
        leading_text=extract_finance_leading_text(existing_record_text),
        preserved_sections=extract_finance_preserved_sections(existing_record_text),
    )
    normalized_path = _normalize_path(record.path)
    reason_code = {
        "update_bill": "finance_mutation_resolved",
        "update_invoice": "finance_mutation_resolved",
        "add_line_item": "finance_add_line_item_resolved",
        "remove_line_item": "finance_remove_line_item_resolved",
        "adjust_amount": "finance_adjust_amount_resolved",
        "mark_paid": "finance_mark_paid_resolved",
        "settle_payment": "finance_settle_payment_resolved",
    }[action]
    return FinanceRecordWritePlan(
        result=MutationStepResult(
            status="resolved",
            message=normalized_path,
            grounding_refs=(normalized_path,),
            reason_code=reason_code,
        ),
        rendered_content=rendered,
    )


def _evaluate_payment_gate_for_update(
    *,
    action: str,
    record_path: str,
    authorization_kind: str | None,
    authorized_by: str | None,
    settlement_reference: str | None,
    settlement_channel: str | None,
    settlement_date: str | None,
) -> FinanceRecordWritePlan | None:
    settlement_present = any(
        str(value or "").strip()
        for value in (settlement_reference, settlement_channel, settlement_date)
    )
    gate_action = action
    if action in {"update_bill", "update_invoice"} and settlement_present:
        gate_action = "settle_payment"
    if gate_action not in {"mark_paid", "settle_payment"}:
        if settlement_channel and not (settlement_reference or "").strip():
            return FinanceRecordWritePlan(
                result=MutationStepResult(
                    status="blocked",
                    message=(
                        "settlement_channel is set but settlement_reference is "
                        "missing; settlement evidence is incomplete."
                    ),
                    grounding_refs=(record_path,),
                    reason_code="finance_mutation_settlement_evidence_missing",
                )
            )
        return None

    authorization = _payment_authorization(
        record_path=record_path,
        authorization_kind=authorization_kind,
        authorized_by=authorized_by,
    )
    settlement_evidence = _settlement_evidence(
        record_path=record_path,
        settlement_reference=settlement_reference,
        settlement_channel=settlement_channel,
        settlement_date=settlement_date,
        authorized_by=authorized_by,
    )
    decision = evaluate_payment_gate(
        gate_action,
        authorization=authorization,
        settlement_evidence=settlement_evidence,
    )
    if decision.is_approved():
        return None
    reason_code = {
        "payment_authorization_missing": "finance_mutation_payment_authorization_missing",
        "settlement_evidence_missing": "finance_mutation_settlement_evidence_missing",
    }.get(decision.reason, decision.reason or "finance_mutation_payment_gate_blocked")
    status = (
        "clarify_missing"
        if decision.reason == "settlement_evidence_missing"
        else "blocked"
    )
    message = {
        "payment_authorization_missing": (
            "Finance payment mutation requires typed payment authorization."
        ),
        "settlement_evidence_missing": (
            "Finance payment mutation requires settlement evidence before it can mark the record paid."
        ),
    }.get(
        decision.reason,
        f"Finance payment mutation failed its authorization gate: {decision.reason}.",
    )
    return FinanceRecordWritePlan(
        result=MutationStepResult(
            status=status,
            message=message,
            grounding_refs=(record_path,),
            reason_code=reason_code,
        )
    )


def _payment_authorization(
    *,
    record_path: str,
    authorization_kind: str | None,
    authorized_by: str | None,
) -> PaymentAuthorization | None:
    stamp = AuthorizationStamp.from_fields(authorization_kind, authorized_by)
    if stamp is None:
        return None
    return PaymentAuthorization(
        record_path=record_path,
        authorized_by=stamp.authorized_by,
        authorization_kind=stamp.kind.value,
        gate_result="approved",
        requires_settlement_evidence=True,
    )


def _settlement_evidence(
    *,
    record_path: str,
    settlement_reference: str | None,
    settlement_channel: str | None,
    settlement_date: str | None,
    authorized_by: str | None,
) -> SettlementEvidence | None:
    reference = str(settlement_reference or "").strip()
    channel = SettlementChannel.parse(settlement_channel)
    settled_date = str(settlement_date or "").strip()
    if not (reference and channel and settled_date):
        return None
    return SettlementEvidence(
        record_path=record_path,
        settled_date=settled_date,
        confirmation_reference=reference,
        channel=channel,
        attested_by=str(authorized_by or "").strip(),
    )


def _resolve_target_record(
    finance_records: Sequence[FinanceRecord],
    *,
    action: str,
    record_type: str | None,
    record_path: str | None,
    anchor_record_ref: str | None,
    reference_number: str | None,
    counterparty: str | None,
    alias: str | None,
    project: str | None,
    related_entity: str | None,
    date: str | None,
    amount: float | None,
) -> FinanceRecord | None:
    target_path = (record_path or anchor_record_ref or "").strip()
    if target_path:
        return _find_record_by_path(finance_records, _normalize_path(target_path))
    criteria = FinanceRecordIdentityCriteria(
        record_type=_action_record_type(action, record_type),
        counterparty=str(counterparty or "").strip(),
        reference_number=str(reference_number or "").strip(),
        alias=str(alias or "").strip(),
        project=str(project or "").strip(),
        related_entity=str(related_entity or "").strip(),
        date=str(date or "").strip(),
        amount_eur=amount,
    )
    identity = resolve_finance_record_identity(finance_records, criteria=criteria)
    if identity is None:
        return None
    return _find_record_by_path(finance_records, _normalize_path(identity.path))


def _action_record_type(action: str, record_type: str | None) -> str | None:
    normalized = str(record_type or "").strip().lower()
    if normalized in {"invoice", "bill"}:
        return normalized
    if action == "update_invoice":
        return "invoice"
    if action == "update_bill":
        return "bill"
    return None


def _find_record_by_path(
    records: Sequence[FinanceRecord], path: str
) -> FinanceRecord | None:
    for record in records:
        record_path = str(getattr(record, "path", "") or "").strip()
        normalized = record_path if record_path.startswith("/") else f"/{record_path}"
        if normalized == path:
            return record
    return None


def _normalize_path(path: str) -> str:
    normalized = str(path or "").strip()
    if not normalized:
        return ""
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _target_refs(
    record_path: str | None,
    anchor_record_ref: str | None,
) -> tuple[str, ...]:
    refs: list[str] = []
    for candidate in (record_path, anchor_record_ref):
        normalized = _normalize_path(str(candidate or "").strip())
        if normalized:
            refs.append(normalized)
    return tuple(dict.fromkeys(refs))


__all__ = [
    "FinanceRecordWritePlan",
    "resolve_finance_target_record",
    "resolve_finance_update_bill",
    "resolve_finance_update_record",
]
