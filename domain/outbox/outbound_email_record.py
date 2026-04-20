from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Literal

from domain.record_references import (
    RelatedRecordReference,
    build_related_record_references,
    partition_related_record_references,
)


class SendState(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    FAILED = "failed"


ApprovalStatus = Literal["pending", "approved", "rejected", "not_required"]


@dataclass(frozen=True, slots=True)
class OutboundEmailRecord:
    path: str = ""
    record_type: str = "outbound_email"
    created_at: str = ""
    send_state: SendState = SendState.DRAFT
    from_address: str = ""
    to: tuple[str, ...] = ()
    subject: str = ""
    body: str = ""
    attachments: tuple[str, ...] = ()
    related_entities: tuple[str, ...] = ()
    related_projects: tuple[str, ...] = ()
    related_references: tuple[RelatedRecordReference, ...] = ()
    source_channel: str = ""
    message_id: str = ""
    approval_status: ApprovalStatus = "not_required"
    channel_owner: str = ""

    def __post_init__(self) -> None:
        if self.related_references:
            if not self.related_entities and not self.related_projects:
                related_entities, related_projects = partition_related_record_references(
                    self.related_references
                )
                object.__setattr__(self, "related_entities", related_entities)
                object.__setattr__(self, "related_projects", related_projects)
            return
        object.__setattr__(
            self,
            "related_references",
            build_related_record_references(
                self.related_entities,
                self.related_projects,
            ),
        )

    @property
    def is_draft(self) -> bool:
        return self.send_state == SendState.DRAFT

    @property
    def is_sent(self) -> bool:
        return self.send_state == SendState.SENT


def outbound_email_filename(created_at: str) -> str:
    timestamp = created_at.strip().replace(":", "-")
    return f"eml_{timestamp}.md"


def parse_outbound_email_filename(filename: str) -> str | None:
    stem = PurePosixPath(filename).stem
    if not stem.startswith("eml_") or not stem.endswith("Z"):
        return None
    timestamp_part = stem[4:]
    t_index = timestamp_part.find("T")
    if t_index < 0:
        return None
    date_part = timestamp_part[:t_index]
    time_part = timestamp_part[t_index + 1 : -1]
    time_restored = time_part.replace("-", ":")
    return f"{date_part}T{time_restored}Z"


def is_duplicate_outbound(
    candidate: OutboundEmailRecord,
    existing: Sequence[OutboundEmailRecord],
) -> bool:
    if candidate.message_id:
        return any(
            record.message_id == candidate.message_id
            for record in existing
            if record.message_id
        )
    if not candidate.to or not candidate.subject:
        return False
    return any(
        record.to == candidate.to
        and record.subject == candidate.subject
        and record.attachments == candidate.attachments
        for record in existing
    )
