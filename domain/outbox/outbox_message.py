from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    to: str = ""
    cc: str = ""
    bcc: str = ""
    subject: str = ""
    body: str = ""
    attachments: tuple[str, ...] = ()
    sent: bool = False
