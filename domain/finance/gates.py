"""Finance mutation authorization gate.

Finance mutations that trigger real-money movement (pay, settle, mark paid)
must pass an explicit authorization gate carrying `PaymentAuthorization` and,
where the gate requires it, `SettlementEvidence`. This module is the typed
wiring between mutation *actions* and the gate objects in `identity.py` so
runtime callers never evaluate the gate by string inspection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .identity import PaymentAuthorization, SettlementEvidence


MutationAction = Literal[
    "create_invoice",
    "update_invoice",
    "create_bill",
    "update_bill",
    "add_line_item",
    "remove_line_item",
    "adjust_amount",
    "mark_paid",
    "settle_payment",
]


BANK_ACTION_ACTIONS: frozenset[str] = frozenset({"mark_paid", "settle_payment"})


def is_bank_action(action: str) -> bool:
    return action in BANK_ACTION_ACTIONS


@dataclass(frozen=True, slots=True)
class PaymentGateDecision:
    """Result of evaluating the authorization gate for a mutation action."""

    decision: Literal["approved", "blocked", "not_required"]
    reason: str = ""

    def is_approved(self) -> bool:
        return self.decision == "approved"

    def is_blocked(self) -> bool:
        return self.decision == "blocked"

    def is_not_required(self) -> bool:
        return self.decision == "not_required"


def evaluate_payment_gate(
    action: str,
    *,
    authorization: PaymentAuthorization | None = None,
    settlement_evidence: SettlementEvidence | None = None,
) -> PaymentGateDecision:
    """Evaluate whether a finance mutation may proceed.

    - Non-bank actions return `not_required` — authorization is neither
      requested nor consulted. This is the explicit opposite of silently
      allowing bank-action drift.
    - Bank actions require an `approved` `PaymentAuthorization`. If the
      authorization also requires settlement evidence, that evidence must be
      present. Missing pieces fail closed with an explicit reason.
    """

    if not is_bank_action(action):
        return PaymentGateDecision(decision="not_required")

    if authorization is None:
        return PaymentGateDecision(
            decision="blocked",
            reason="payment_authorization_missing",
        )
    if not authorization.is_approved():
        return PaymentGateDecision(
            decision="blocked",
            reason=authorization.block_reason or "payment_authorization_not_approved",
        )
    if authorization.requires_settlement_evidence and settlement_evidence is None:
        return PaymentGateDecision(
            decision="blocked",
            reason="settlement_evidence_missing",
        )
    return PaymentGateDecision(decision="approved")
