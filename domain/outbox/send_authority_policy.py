from __future__ import annotations

import re
from dataclasses import dataclass

from .draft_policy import DraftValidationResult
from .outbound_email_record import OutboundEmailRecord


_BARE_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(frozen=True, slots=True)
class OutboxSendAuthorityPolicy:
    def validate(self, record: OutboundEmailRecord) -> DraftValidationResult:
        sender = str(record.from_address or "").strip()
        if not sender:
            return DraftValidationResult(valid=False, reason="from_address is required")
        if not _BARE_EMAIL_RE.fullmatch(sender):
            return DraftValidationResult(
                valid=False,
                reason=f"from_address must be a bare email address: '{record.from_address}'",
            )
        if not str(record.source_channel or "").strip():
            return DraftValidationResult(
                valid=False,
                reason="source_channel is required for outbound email authority",
            )
        return DraftValidationResult(valid=True)


DEFAULT_OUTBOX_SEND_AUTHORITY_POLICY = OutboxSendAuthorityPolicy()


def validate_send_authority(record: OutboundEmailRecord) -> DraftValidationResult:
    return DEFAULT_OUTBOX_SEND_AUTHORITY_POLICY.validate(record)
