from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal


InboxTrustStatus = Literal["admin", "valid", "blacklist", "unlisted"]
ChannelTrustLevel = Literal["verified", "known", "unverified", "untrusted"]


@dataclass(frozen=True, slots=True)
class SenderTrust:
    status: InboxTrustStatus
    familiar: bool = False
    trusted: bool = False
    authority: str = "none"
    trust_class: str = "unknown"
    allowed_mutation: bool = False
    consume_otp: bool = False
    channel_trust: ChannelTrustLevel = "unverified"


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return default


def _trust_from_legacy_status(status: InboxTrustStatus) -> SenderTrust:
    if status == "blacklist":
        return SenderTrust(
            status="blacklist",
            familiar=True,
            trusted=False,
            authority="blocked",
            trust_class="blocked",
            allowed_mutation=False,
            channel_trust="untrusted",
        )
    if status == "admin":
        return SenderTrust(
            status="admin",
            familiar=True,
            trusted=True,
            authority="admin",
            trust_class="work-trusted",
            allowed_mutation=True,
            channel_trust="verified",
        )
    if status == "valid":
        return SenderTrust(
            status="valid",
            familiar=True,
            trusted=False,
            authority="lane-authorized",
            trust_class="work-known",
            allowed_mutation=True,
            channel_trust="known",
        )
    return SenderTrust(
        status="unlisted",
        familiar=False,
        trusted=False,
        authority="none",
        trust_class="unknown",
        allowed_mutation=False,
        channel_trust="unverified",
    )


def _resolve_sender_trust_entry(
    entry: InboxTrustStatus | Mapping[str, Any] | object,
) -> SenderTrust:
    if isinstance(entry, Mapping):
        raw_status = str(entry.get("status") or "unlisted").strip().lower()
        status: InboxTrustStatus = (
            raw_status
            if raw_status in {"admin", "valid", "blacklist", "unlisted"}
            else "unlisted"
        )
        base = _trust_from_legacy_status(status)
        authority = str(entry.get("authority") or base.authority).strip() or base.authority
        trust_class = str(entry.get("trust_class") or base.trust_class).strip() or base.trust_class
        return SenderTrust(
            status=status,
            familiar=_coerce_bool(entry.get("familiar"), base.familiar),
            trusted=_coerce_bool(entry.get("trusted"), base.trusted),
            authority=authority,
            trust_class=trust_class,
            allowed_mutation=_coerce_bool(
                entry.get("allowed_mutation"),
                base.allowed_mutation,
            ),
            consume_otp=False,
            channel_trust=base.channel_trust,
        )
    if isinstance(entry, str) and entry in {"admin", "valid", "blacklist", "unlisted"}:
        return _trust_from_legacy_status(entry)
    return _trust_from_legacy_status("unlisted")


def classify_sender_trust(
    handle: str,
    roster: Mapping[str, InboxTrustStatus | Mapping[str, Any]],
    *,
    message_text: str = "",
    otp_tokens: Sequence[str] = (),
) -> SenderTrust:
    trust = _resolve_sender_trust_entry(roster.get(handle, "unlisted"))
    if trust.status == "blacklist":
        return trust
    if trust.allowed_mutation:
        return trust

    for token in otp_tokens:
        if token and token in message_text:
            return SenderTrust(
                status="valid",
                familiar=trust.familiar,
                trusted=True,
                authority="otp-authorized",
                trust_class="otp-verified",
                allowed_mutation=True,
                consume_otp=True,
                channel_trust="verified",
            )
    return trust


__all__ = [
    "ChannelTrustLevel",
    "InboxTrustStatus",
    "SenderTrust",
    "classify_sender_trust",
]
