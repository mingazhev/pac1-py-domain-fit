from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence


SenderVerificationStatus = Literal[
    "verified", "suspect_lookalike", "cross_account", "wrong_account", "unknown"
]


@dataclass(frozen=True, slots=True)
class SenderVerificationResult:
    status: SenderVerificationStatus
    reason: str = ""
    matched_canonical: str = ""


_LOOKALIKE_MAP: dict[str, str] = {
    "0": "o",
    "1": "l",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "8": "b",
}


def _normalize_lookalike(text: str) -> str:
    result: list[str] = []
    for ch in text.lower():
        result.append(_LOOKALIKE_MAP.get(ch, ch))
    return "".join(result)


def detect_sender_lookalike(
    sender: str,
    known_senders: Sequence[str],
) -> SenderVerificationResult:
    if not sender or not known_senders:
        return SenderVerificationResult(status="unknown")

    normalized_sender = _normalize_lookalike(sender)

    for known in known_senders:
        if sender == known:
            return SenderVerificationResult(
                status="verified",
                matched_canonical=known,
            )
        normalized_known = _normalize_lookalike(known)
        if normalized_sender == normalized_known and sender != known:
            return SenderVerificationResult(
                status="suspect_lookalike",
                reason=f"sender '{sender}' resembles known sender '{known}'",
                matched_canonical=known,
            )

    return SenderVerificationResult(status="unknown")


def detect_cross_account_request(
    sender: str,
    sender_account_id: str,
    target_account_id: str,
) -> SenderVerificationResult:
    if not sender_account_id or not target_account_id:
        return SenderVerificationResult(status="unknown")

    if sender_account_id != target_account_id:
        return SenderVerificationResult(
            status="cross_account",
            reason=(
                f"sender account '{sender_account_id}' differs from "
                f"target account '{target_account_id}'"
            ),
        )

    return SenderVerificationResult(status="verified", matched_canonical=sender)


def detect_wrong_account_finance_request(
    sender: str,
    sender_account_id: str,
    invoice_account_id: str,
) -> SenderVerificationResult:
    if not sender_account_id or not invoice_account_id:
        return SenderVerificationResult(status="unknown")

    if sender_account_id != invoice_account_id:
        return SenderVerificationResult(
            status="wrong_account",
            reason=(
                f"sender account '{sender_account_id}' does not own "
                f"invoice account '{invoice_account_id}'"
            ),
        )

    return SenderVerificationResult(status="verified", matched_canonical=sender)
