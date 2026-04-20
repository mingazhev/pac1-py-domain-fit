"""Outbox bounded context."""

from domain.record_references import RelatedRecordKind, RelatedRecordReference

from .draft_policy import (
    DEFAULT_OUTBOX_DRAFT_POLICY,
    DraftValidationResult,
    OutboxDraftPolicy,
    validate_draft_fields,
    validate_draft_filename,
)
from .outbox_completion_normalization import OutboxCompletionNormalization
from .outbox_message import OutboxMessage
from .outbox_write_plan import OutboxWritePlan
from .outbound_email_record import (
    ApprovalStatus,
    OutboundEmailRecord,
    SendState,
    is_duplicate_outbound,
    outbound_email_filename,
    parse_outbound_email_filename,
)
from .policy import (
    OutboxPayloadContractError,
    OutboxPayloadUnsupportedError,
    canonical_outbox_success_message,
    normalize_outbox_completion,
)
from .send_authority_policy import (
    DEFAULT_OUTBOX_SEND_AUTHORITY_POLICY,
    OutboxSendAuthorityPolicy,
    validate_send_authority,
)
from .write_planning import allocate_outbox_write

__all__ = [
    "ApprovalStatus",
    "DEFAULT_OUTBOX_DRAFT_POLICY",
    "DEFAULT_OUTBOX_SEND_AUTHORITY_POLICY",
    "DraftValidationResult",
    "OutboxCompletionNormalization",
    "OutboxDraftPolicy",
    "OutboxMessage",
    "OutboxPayloadContractError",
    "OutboxPayloadUnsupportedError",
    "OutboxSendAuthorityPolicy",
    "OutboxWritePlan",
    "OutboundEmailRecord",
    "RelatedRecordKind",
    "RelatedRecordReference",
    "SendState",
    "allocate_outbox_write",
    "canonical_outbox_success_message",
    "is_duplicate_outbound",
    "normalize_outbox_completion",
    "outbound_email_filename",
    "parse_outbound_email_filename",
    "validate_draft_fields",
    "validate_draft_filename",
    "validate_send_authority",
]
