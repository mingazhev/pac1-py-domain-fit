from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .sender_trust import SenderTrust


RequestRiskLevel = Literal["read_only", "disclosure", "mutation", "destructive"]


@dataclass(frozen=True, slots=True)
class InboxTrustDecision:
    allowed: bool
    risk_level: RequestRiskLevel
    reason: str = ""
    requires_proof: bool = False


def enforce_inbox_trust(
    trust: SenderTrust,
    risk: RequestRiskLevel,
    *,
    channel_requires_proof: bool = False,
) -> InboxTrustDecision:
    """Invariant trust-policy check.

    ``risk`` must be produced upstream by a typed classifier or another
    explicit adapter policy. The domain layer does not perform phrase
    matching.
    """
    if trust.status == "blacklist":
        return InboxTrustDecision(
            allowed=False,
            risk_level=risk,
            reason="sender is blacklisted",
        )

    if channel_requires_proof and not trust.consume_otp and trust.authority not in (
        "admin",
        "otp-authorized",
    ):
        return InboxTrustDecision(
            allowed=False,
            risk_level=risk,
            reason="channel requires proof but none provided",
            requires_proof=True,
        )

    if risk == "destructive":
        if trust.authority != "admin":
            return InboxTrustDecision(
                allowed=False,
                risk_level=risk,
                reason="destructive requests require admin authority",
            )

    if risk == "disclosure":
        if not trust.trusted and trust.authority not in ("admin", "otp-authorized"):
            return InboxTrustDecision(
                allowed=False,
                risk_level=risk,
                reason="disclosure requests require trusted status or OTP verification",
            )

    if risk == "mutation":
        if not trust.allowed_mutation:
            return InboxTrustDecision(
                allowed=False,
                risk_level=risk,
                reason="mutation requests require mutation permission",
            )

    return InboxTrustDecision(
        allowed=True,
        risk_level=risk,
    )
