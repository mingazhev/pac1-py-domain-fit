from __future__ import annotations

from dataclasses import dataclass

from .inbox_item import InboxItem


@dataclass(frozen=True, slots=True)
class TransportIdentity:
    sender: str
    recipients: tuple[str, ...]
    cc: tuple[str, ...]
    reply_to: str
    subject: str
    received_at: str


@dataclass(frozen=True, slots=True)
class TransportPolicyDecision:
    identity_source: str
    sender_from_header: str
    recipients_from_header: tuple[str, ...]
    body_override_rejected: bool = False
    reason: str = ""


@dataclass(frozen=True, slots=True)
class StructuredEmailSurface:
    transport: TransportIdentity
    body_text: str
    source_channel: str
    related_entities: tuple[str, ...]
    related_projects: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InboxEmailTransportPolicy:
    def extract_identity(self, item: InboxItem) -> TransportIdentity:
        return TransportIdentity(
            sender=item.sender,
            recipients=item.to,
            cc=item.cc,
            reply_to=item.reply_to,
            subject=item.subject,
            received_at=item.received_at,
        )

    def enforce_header_precedence(
        self,
        item: InboxItem,
        *,
        body_sender_hint: str = "",
        body_recipient_hints: tuple[str, ...] = (),
    ) -> TransportPolicyDecision:
        identity = self.extract_identity(item)
        body_override_rejected = False
        reasons: list[str] = []

        if body_sender_hint and body_sender_hint != identity.sender:
            body_override_rejected = True
            reasons.append("body sender hint ignored in favor of header 'from'")

        if body_recipient_hints:
            header_set = set(identity.recipients) | set(identity.cc)
            if identity.reply_to:
                header_set.add(identity.reply_to)
            override_candidates = tuple(
                hint for hint in body_recipient_hints if hint not in header_set
            )
            if override_candidates:
                body_override_rejected = True
                reasons.append(
                    "body recipient hints ignored in favor of header 'to'/'cc'"
                )

        return TransportPolicyDecision(
            identity_source="header",
            sender_from_header=identity.sender,
            recipients_from_header=identity.recipients,
            body_override_rejected=body_override_rejected,
            reason="; ".join(reasons),
        )

    def extract_structured_email_surface(
        self, item: InboxItem
    ) -> StructuredEmailSurface | None:
        if item.record_type != "inbound_email":
            return None
        return StructuredEmailSurface(
            transport=self.extract_identity(item),
            body_text=item.body,
            source_channel=item.source_channel,
            related_entities=item.related_entities,
            related_projects=item.related_projects,
        )


DEFAULT_INBOX_EMAIL_TRANSPORT_POLICY = InboxEmailTransportPolicy()


def extract_transport_identity(item: InboxItem) -> TransportIdentity:
    return DEFAULT_INBOX_EMAIL_TRANSPORT_POLICY.extract_identity(item)


def extract_structured_email_surface(item: InboxItem) -> StructuredEmailSurface | None:
    return DEFAULT_INBOX_EMAIL_TRANSPORT_POLICY.extract_structured_email_surface(item)


def enforce_header_precedence(
    item: InboxItem,
    *,
    body_sender_hint: str = "",
    body_recipient_hints: tuple[str, ...] = (),
) -> TransportPolicyDecision:
    return DEFAULT_INBOX_EMAIL_TRANSPORT_POLICY.enforce_header_precedence(
        item,
        body_sender_hint=body_sender_hint,
        body_recipient_hints=body_recipient_hints,
    )


def is_structured_email_record(item: InboxItem) -> bool:
    return item.record_type == "inbound_email"
