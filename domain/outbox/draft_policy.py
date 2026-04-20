from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from .outbound_email_record import (
    OutboundEmailRecord,
    SendState,
    outbound_email_filename,
)

_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_EXTERNAL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DraftValidationResult:
    valid: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class OutboxDraftPolicy:
    def validate_fields(self, record: OutboundEmailRecord) -> DraftValidationResult:
        if record.record_type != "outbound_email":
            return DraftValidationResult(
                valid=False, reason="record_type must be 'outbound_email'"
            )
        if not record.created_at:
            return DraftValidationResult(valid=False, reason="created_at is required")
        if not _RFC3339_RE.match(record.created_at):
            return DraftValidationResult(
                valid=False, reason=f"created_at must be RFC3339: '{record.created_at}'"
            )
        if not record.to:
            return DraftValidationResult(valid=False, reason="to must be non-empty")
        for recipient in record.to:
            if not _is_bare_email(recipient):
                return DraftValidationResult(
                    valid=False,
                    reason=f"recipient must be a bare email address: '{recipient}'",
                )
        if not record.subject:
            return DraftValidationResult(valid=False, reason="subject is required")
        if not record.attachments:
            return DraftValidationResult(
                valid=False, reason="attachments must be non-empty"
            )
        for attachment in record.attachments:
            if not attachment:
                return DraftValidationResult(
                    valid=False, reason="attachment path must not be empty"
                )
            if _EXTERNAL_RE.match(attachment):
                return DraftValidationResult(
                    valid=False,
                    reason=f"attachment must be workspace-relative: '{attachment}'",
                )
            normalized_attachment = attachment.replace("\\", "/").strip()
            if normalized_attachment.startswith("/"):
                return DraftValidationResult(
                    valid=False,
                    reason=f"attachment must be workspace-relative: '{attachment}'",
                )
            if normalized_attachment.startswith(
                "./"
            ) or normalized_attachment.startswith("../"):
                return DraftValidationResult(
                    valid=False,
                    reason=f"attachment must stay inside workspace root: '{attachment}'",
                )
            if "/../" in normalized_attachment or normalized_attachment == "..":
                return DraftValidationResult(
                    valid=False,
                    reason=f"attachment must stay inside workspace root: '{attachment}'",
                )
            if not normalized_attachment.split("/")[0].split(".")[0]:
                return DraftValidationResult(
                    valid=False, reason=f"attachment path is invalid: '{attachment}'"
                )
        if record.send_state not in (SendState.DRAFT, SendState.SENT, SendState.FAILED):
            return DraftValidationResult(
                valid=False,
                reason=f"send_state '{record.send_state.value}' is not valid",
            )
        return DraftValidationResult(valid=True)

    def validate_filename(self, record: OutboundEmailRecord) -> DraftValidationResult:
        if not record.path:
            return DraftValidationResult(
                valid=False, reason="path is required for filename validation"
            )
        actual_name = PurePosixPath(record.path).name
        if not actual_name.startswith("eml_") or not actual_name.endswith(".md"):
            return DraftValidationResult(
                valid=False,
                reason=f"filename '{actual_name}' must match eml_*.md pattern",
            )
        expected_name = outbound_email_filename(record.created_at)
        if actual_name != expected_name:
            return DraftValidationResult(
                valid=False,
                reason=f"filename '{actual_name}' does not match expected '{expected_name}'",
            )
        return DraftValidationResult(valid=True)


DEFAULT_OUTBOX_DRAFT_POLICY = OutboxDraftPolicy()


def validate_draft_fields(record: OutboundEmailRecord) -> DraftValidationResult:
    return DEFAULT_OUTBOX_DRAFT_POLICY.validate_fields(record)


def validate_draft_filename(record: OutboundEmailRecord) -> DraftValidationResult:
    return DEFAULT_OUTBOX_DRAFT_POLICY.validate_filename(record)


def _is_bare_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))
