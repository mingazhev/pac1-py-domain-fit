from __future__ import annotations

from enum import Enum
from typing import Any


class PaymentState(str, Enum):
    UNSETTLED = "unsettled"
    PAID = "paid"
    SETTLED = "settled"

    @classmethod
    def parse(cls, value: Any) -> PaymentState | None:
        if isinstance(value, cls):
            return value
        normalized = str(value or "").strip().lower()
        if not normalized:
            return None
        aliases = {
            "open": cls.UNSETTLED,
            "unpaid": cls.UNSETTLED,
            "unsettled": cls.UNSETTLED,
            "paid": cls.PAID,
            "settled": cls.SETTLED,
        }
        return aliases.get(normalized)


class SettlementChannel(str, Enum):
    BANK_TRANSFER = "bank_transfer"
    CARD = "card"
    CASH = "cash"
    MANUAL_ATTESTATION = "manual_attestation"

    @classmethod
    def parse(cls, value: Any) -> SettlementChannel | None:
        if isinstance(value, cls):
            return value
        normalized = str(value or "").strip().lower()
        if not normalized:
            return None
        aliases = {
            "bank_transfer": cls.BANK_TRANSFER,
            "bank transfer": cls.BANK_TRANSFER,
            "wire": cls.BANK_TRANSFER,
            "wire_transfer": cls.BANK_TRANSFER,
            "card": cls.CARD,
            "cash": cls.CASH,
            "manual_attestation": cls.MANUAL_ATTESTATION,
            "manual attestation": cls.MANUAL_ATTESTATION,
            "attested": cls.MANUAL_ATTESTATION,
        }
        return aliases.get(normalized)


def payment_state_text(value: PaymentState | str | None) -> str:
    if isinstance(value, PaymentState):
        return value.value
    parsed = PaymentState.parse(value)
    if parsed is not None:
        return parsed.value
    return str(value or "").strip()


def settlement_channel_text(value: SettlementChannel | str | None) -> str:
    if isinstance(value, SettlementChannel):
        return value.value
    parsed = SettlementChannel.parse(value)
    if parsed is not None:
        return parsed.value
    return str(value or "").strip()


__all__ = [
    "PaymentState",
    "SettlementChannel",
    "payment_state_text",
    "settlement_channel_text",
]
