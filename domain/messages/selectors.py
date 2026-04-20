from __future__ import annotations

from collections.abc import Sequence

from .message_record import MessageRecord


def select_last_message_record(records: Sequence[MessageRecord]) -> MessageRecord | None:
    if not records:
        return None
    return max(records, key=lambda record: record.sort_key)
