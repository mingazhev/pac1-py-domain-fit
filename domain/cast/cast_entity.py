from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from ._text import normalize_cast_text
from .entity_kind import EntityKind
from .important_dates import ImportantDateKind, parse_important_date_kind
from .relationship import (
    CastRelationship,
    expand_cast_relationship_aliases,
    normalize_cast_relationship_label,
    parse_cast_relationship,
)


@dataclass(frozen=True, slots=True)
class CastMilestone:
    label: str
    occurred_on: str
    kind: str = ImportantDateKind.MILESTONE.value

    @property
    def kind_enum(self) -> ImportantDateKind:
        parsed = parse_important_date_kind(self.kind)
        return parsed if parsed is not None else ImportantDateKind.MILESTONE

    @property
    def is_kind_preserving(self) -> bool:
        return parse_important_date_kind(self.kind) is not None


@dataclass(frozen=True, slots=True)
class CastEntity:
    path: str
    title: str
    entity_id: str = ""
    entity_slug: str = ""
    alias: str = ""
    kind: EntityKind | None = None
    relationship: str = ""
    birthday: str | None = None
    created_on: str | None = None
    milestones: tuple[CastMilestone, ...] = ()
    primary_contact_email: str = ""
    identity_terms: tuple[str, ...] = ()
    alias_terms: tuple[str, ...] = ()
    descriptor_terms: tuple[str, ...] = ()
    body: str = ""

    @property
    def important_dates(self) -> tuple[CastMilestone, ...]:
        return tuple(
            dict.fromkeys(
                (
                    *((CastMilestone(label="birthday", occurred_on=self.birthday, kind=ImportantDateKind.BIRTHDAY.value),) if self.birthday else ()),
                    *((CastMilestone(label="created_on", occurred_on=self.created_on, kind=ImportantDateKind.CREATED_ON.value),) if self.created_on else ()),
                    *(self.milestones or ()),
                )
            )
        )

    @property
    def canonical_terms(self) -> tuple[str, ...]:
        return tuple(
            term
            for term in (
                self.title,
                self.entity_slug,
                self.alias,
                self.entity_id,
                *(self.alias_terms or ()),
            )
            if str(term or "").strip()
        )

    @property
    def stable_identity_terms(self) -> tuple[str, ...]:
        if self.identity_terms:
            return self.identity_terms
        return tuple(
            dict.fromkeys(
                term
                for term in (
                    self.title,
                    self.entity_slug,
                    self.alias,
                    self.entity_id,
                )
                if str(term or "").strip()
            )
        )

    @property
    def relationship_alias_terms(self) -> tuple[str, ...]:
        return tuple(
            term
            for term in expand_cast_relationship_aliases(self.relationship)
            if str(term or "").strip()
        )

    @property
    def project_involvement_terms(self) -> tuple[str, ...]:
        excluded_relationship_terms = {
            normalize_cast_text(term)
            for term in self.relationship_alias_terms
            if normalize_cast_text(term)
        }
        terms: list[str] = []
        for candidate in (
            self.entity_id,
            f"entity.{self.entity_slug}" if self.entity_slug else "",
            self.entity_slug,
            self.title,
        ):
            normalized_candidate = normalize_cast_text(candidate)
            if not normalized_candidate:
                continue
            if normalized_candidate in excluded_relationship_terms:
                continue
            terms.append(normalized_candidate)
        for alias in self.alias_terms:
            normalized_alias = normalize_cast_text(alias)
            if not normalized_alias:
                continue
            alias_tokens = tuple(token for token in normalized_alias.split() if token)
            if len(alias_tokens) < 2:
                continue
            if normalized_alias in excluded_relationship_terms:
                continue
            terms.append(normalized_alias)
        return tuple(dict.fromkeys(terms))

    @property
    def normalized_relationship(self) -> str:
        return re.sub(r"[_\\-]+", " ", normalize_cast_relationship_label(self.relationship)).strip()

    @property
    def relationship_enum(self) -> CastRelationship | None:
        return parse_cast_relationship(self.relationship)

    @property
    def has_controlled_relationship(self) -> bool:
        return parse_cast_relationship(self.relationship) is not None

    def has_birthday(self) -> bool:
        return False

    def is_person(self) -> bool:
        return False

    def supports_birthday_tracking(self) -> bool:
        return False

    def next_birthday_after(self, reference_date: datetime) -> datetime | None:
        del reference_date
        return None

    def matches_email(self, sender_email: str) -> bool:
        normalized_sender = normalize_cast_text(sender_email)
        return bool(normalized_sender) and normalized_sender == normalize_cast_text(
            self.primary_contact_email
        )
