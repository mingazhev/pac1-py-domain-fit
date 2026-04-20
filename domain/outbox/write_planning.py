from __future__ import annotations

from .outbox_message import OutboxMessage
from .outbox_write_plan import OutboxWritePlan


def allocate_outbox_write(current_id: int, message: OutboxMessage) -> OutboxWritePlan:
    return OutboxWritePlan(
        message_filename=f"{current_id}.json",
        message=message,
        next_sequence={"id": current_id + 1},
    )


__all__ = ["allocate_outbox_write"]
