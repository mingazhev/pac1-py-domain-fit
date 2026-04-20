from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from domain.cast.cast_entity import CastEntity
from domain.cast.contact_policy import resolve_cast_contact_policy

from .cast_registry import CastRegistry


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


@dataclass(frozen=True, slots=True)
class ContactIdentity:
    """Typed contact identity derived from the canonical cast roster.

    ``canonical_email_expected`` mirrors the cast contact policy. The
    registry uses this flag to decide whether a sender email is allowed to
    participate in the canonical-sender whitelist — instead of letting
    loader heuristics or LLM prompting decide.
    """

    entity_id: str
    display_name: str
    primary_email: str
    canonical_email_expected: bool
    source_path: str = ""

    def is_canonical_sender(self) -> bool:
        return self.canonical_email_expected and bool(self.primary_email)


@dataclass(frozen=True, slots=True)
class ContactRegistry:
    """Typed contact/sender roster backing the canonical-email trust gate.

    Phase 9 treats the canonical-email gate as policy, not as loader magic:
    the registry is the single place that decides which email is a canonical
    sender, based on the cast roster and each entity's contact policy.
    """

    contacts: tuple[ContactIdentity, ...]
    _by_entity_id: Mapping[str, ContactIdentity] = field(repr=False)
    _by_email: Mapping[str, tuple[ContactIdentity, ...]] = field(repr=False)
    _canonical_sender_roster: frozenset[str] = field(repr=False)

    @classmethod
    def build(cls, entities: Iterable[CastEntity]) -> ContactRegistry:
        contacts: list[ContactIdentity] = []
        by_entity_id: dict[str, ContactIdentity] = {}
        by_email: dict[str, list[ContactIdentity]] = {}
        canonical_emails: set[str] = set()

        for entity in entities:
            email = entity.primary_contact_email.strip()
            policy = resolve_cast_contact_policy(entity)
            contact = ContactIdentity(
                entity_id=entity.entity_id.strip(),
                display_name=entity.title.strip(),
                primary_email=email,
                canonical_email_expected=policy.canonical_email_expected,
                source_path=entity.path,
            )
            contacts.append(contact)

            entity_key = _normalize(contact.entity_id)
            if entity_key and entity_key not in by_entity_id:
                by_entity_id[entity_key] = contact

            email_key = _normalize(email)
            if email_key:
                by_email.setdefault(email_key, []).append(contact)
                if contact.is_canonical_sender():
                    canonical_emails.add(email_key)

        return cls(
            contacts=tuple(contacts),
            _by_entity_id=MappingProxyType(dict(by_entity_id)),
            _by_email=MappingProxyType(
                {key: tuple(values) for key, values in by_email.items()}
            ),
            _canonical_sender_roster=frozenset(canonical_emails),
        )

    @classmethod
    def from_cast_registry(cls, registry: CastRegistry) -> ContactRegistry:
        return cls.build(registry.entities)

    def __iter__(self):
        return iter(self.contacts)

    def __len__(self) -> int:
        return len(self.contacts)

    def by_entity_id(self, entity_id: str) -> ContactIdentity | None:
        return self._by_entity_id.get(_normalize(entity_id))

    def by_email(self, email: str) -> tuple[ContactIdentity, ...]:
        return self._by_email.get(_normalize(email), ())

    def canonical_sender_roster(self) -> frozenset[str]:
        """Explicit whitelist of emails that may act as canonical senders."""

        return self._canonical_sender_roster

    def is_canonical_sender(self, email: str) -> bool:
        return _normalize(email) in self._canonical_sender_roster


__all__ = ["ContactIdentity", "ContactRegistry"]
