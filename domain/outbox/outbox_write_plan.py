from __future__ import annotations

from dataclasses import dataclass

from .outbox_message import OutboxMessage


@dataclass(frozen=True, slots=True)
class OutboxWritePlan:
    message_filename: str
    message: OutboxMessage
    next_sequence: dict[str, int]
