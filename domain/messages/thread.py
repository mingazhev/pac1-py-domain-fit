from __future__ import annotations

from dataclasses import dataclass

from .message_record import MessageRecord


@dataclass(frozen=True, slots=True)
class ThreadRecord:
    path: str
    title: str
    body: str = ""
    messages: tuple[MessageRecord, ...] = ()
