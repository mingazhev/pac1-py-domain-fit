from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from application.contracts import FinanceMutationAction, FinancePaymentRequest
from application.mutations import resolve_finance_target_record
from domain.finance import (
    FinanceRecord,
    PaymentAuthorization,
    SettlementEvidence,
    SettlementChannel,
    evaluate_payment_gate,
)


@dataclass(frozen=True, slots=True)
class FinancePaymentWorkflowPlan:
    status: str
    message: str
    reason_code: str
    grounding_refs: tuple[str, ...] = ()
    command: object | None = None


def resolve_finance_payment_workflow(
    *,
    request: FinancePaymentRequest,
    finance_records: Sequence[FinanceRecord],
) -> FinancePaymentWorkflowPlan:
    record = resolve_finance_target_record(
        finance_records,
        action=request.action,
        record_type=request.record_type,
        record_path=None,
        anchor_record_ref=None,
        reference_number=request.reference_number,
        counterparty=request.counterparty,
        alias=request.alias,
        project=request.project,
        related_entity=request.related_entity,
        date=request.target_date,
        amount=request.amount_eur,
    )
    if record is None:
        return FinancePaymentWorkflowPlan(
            status="clarify_missing",
            message=(
                "Finance payment workflow could not resolve a unique canonical "
                "bill or invoice to act on."
            ),
            reason_code="finance_payment_target_unresolved",
        )
    record_path = str(record.path or "").strip()
    authorization = PaymentAuthorization(
        record_path=record_path,
        authorized_by="inbox_workflow",
        authorization_kind="workflow_policy",
        gate_result="approved",
        requires_settlement_evidence=True,
    )
    evidence = _settlement_evidence_for_request(request, record_path=record_path)
    gate = evaluate_payment_gate(
        request.action,
        authorization=authorization,
        settlement_evidence=evidence,
    )
    if gate.is_blocked():
        if gate.reason == "settlement_evidence_missing":
            return FinancePaymentWorkflowPlan(
                status="clarify_missing",
                message=(
                    "Finance payment workflow identified the canonical record, "
                    "but settlement evidence is missing. Clarify the payment "
                    "confirmation reference or attestation before marking it paid."
                ),
                reason_code="finance_payment_requires_settlement_evidence",
                grounding_refs=(record_path,),
            )
        return FinancePaymentWorkflowPlan(
            status="blocked",
            message=(
                "Finance payment workflow failed its authorization gate: "
                f"{gate.reason}."
            ),
            reason_code=gate.reason or "finance_payment_gate_blocked",
            grounding_refs=(record_path,),
        )
    command = FinanceMutationAction(
        action=request.action,
        record_path=record_path,
        record_type=request.record_type,
        counterparty=request.counterparty or str(record.counterparty or "").strip() or None,
        reference_number=request.reference_number or str(record.reference_number or "").strip() or None,
        alias=request.alias or str(record.alias or "").strip() or None,
        project=request.project or str(record.project or "").strip() or None,
        related_entity=request.related_entity or str(record.related_entity or "").strip() or None,
        date=request.target_date or None,
        amount=request.amount_eur,
        settlement_reference=request.settlement_reference or None,
        settlement_channel=request.settlement_channel or None,
        settlement_date=request.settlement_date or None,
    )
    return FinancePaymentWorkflowPlan(
        status="resolved",
        message="Prepared deterministic finance payment workflow mutation.",
        reason_code="finance_payment_workflow_resolved",
        grounding_refs=(record_path,),
        command=command,
    )


def _settlement_evidence_for_request(
    request: FinancePaymentRequest,
    *,
    record_path: str,
) -> SettlementEvidence | None:
    reference = str(request.settlement_reference or "").strip()
    channel = SettlementChannel.parse(request.settlement_channel)
    settled_date = str(request.settlement_date or "").strip()
    if not (reference and channel and settled_date):
        return None
    return SettlementEvidence(
        record_path=record_path,
        settled_date=settled_date,
        confirmation_reference=reference,
        channel=channel,
        attested_by="inbox_workflow",
    )


__all__ = [
    "FinancePaymentWorkflowPlan",
    "resolve_finance_payment_workflow",
]
