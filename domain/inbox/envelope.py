from __future__ import annotations

from dataclasses import dataclass

from .inbox_item import InboxItem


@dataclass(frozen=True, slots=True)
class InboxMessageEnvelope:
    """Trust-relevant envelope distilled from an :class:`InboxItem`.

    Captures only the fields the inbox classifier needs to interpret
    sender context when judging whether a body is legitimate workspace
    work, a counterparty self-service request, or an exfiltration
    attempt. Keeping this separate from the raw ``InboxItem`` means the
    classifier prompt stays focused on trust signals rather than the
    full record representation.

    ``sender_canonical_entity`` is the name/slug of the cast entity
    whose ``primary_contact_email`` matches the envelope's sender
    address, or ``None`` when no canonical match exists. The classifier
    uses this to distinguish a legitimate counterparty self-service
    resend (canonical match present) from a look-alike address
    attempting to elicit the same disclosure.
    """

    sender: str = ""
    to: tuple[str, ...] = ()
    subject: str = ""
    channel: str = ""
    sender_canonical_entity: str | None = None

    @property
    def self_addressed(self) -> bool:
        sender = self.sender.strip().lower()
        if not sender:
            return False
        recipients = tuple(addr.strip().lower() for addr in self.to if addr)
        if not recipients:
            return False
        return all(addr == sender for addr in recipients)

    @property
    def sender_is_canonical(self) -> bool:
        return bool(str(self.sender_canonical_entity or "").strip())

    def as_prompt_context(self) -> str:
        lines: list[str] = []
        if self.sender:
            lines.append(f"From: {self.sender}")
        if self.to:
            lines.append(f"To: {', '.join(self.to)}")
        if self.subject:
            lines.append(f"Subject: {self.subject}")
        if self.channel:
            lines.append(f"Channel: {self.channel}")
        if self.sender and self.to:
            lines.append(
                "Self-addressed: "
                + ("true" if self.self_addressed else "false")
            )
        if self.sender:
            if self.sender_canonical_entity:
                lines.append(
                    "Sender-canonical: true (matches "
                    f"primary_contact_email of {self.sender_canonical_entity})"
                )
            else:
                lines.append(
                    "Sender-canonical: false (no cast entity has this as "
                    "primary_contact_email)"
                )
        return "\n".join(lines)


def envelope_from_inbox_item(
    item: InboxItem,
    *,
    sender_canonical_entity: str | None = None,
) -> InboxMessageEnvelope:
    return InboxMessageEnvelope(
        sender=str(item.sender or "").strip(),
        to=tuple(
            addr.strip()
            for addr in (item.to or ())
            if str(addr or "").strip()
        ),
        subject=str(item.subject or "").strip(),
        channel=str(item.channel or item.source_channel or "").strip(),
        sender_canonical_entity=sender_canonical_entity,
    )


__all__ = ["InboxMessageEnvelope", "envelope_from_inbox_item"]
