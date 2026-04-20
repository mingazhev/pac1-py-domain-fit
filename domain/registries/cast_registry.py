from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from domain.cast.cast_entity import CastEntity
from domain.cast.contact_policy import resolve_cast_contact_policy


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _freeze_single(mapping: dict[str, CastEntity]) -> Mapping[str, CastEntity]:
    return MappingProxyType(dict(mapping))


def _freeze_multi(
    mapping: dict[str, list[CastEntity]],
) -> Mapping[str, tuple[CastEntity, ...]]:
    return MappingProxyType({key: tuple(values) for key, values in mapping.items()})


@dataclass(frozen=True, slots=True)
class CastRegistry:
    """Explicit read-model index over a canonical ``CastEntity`` collection.

    Replaces ad-hoc ``for entity in entities`` scans at call sites with
    pre-built dictionaries keyed by canonical id, slug, alias phrase, and
    primary contact email. Reverse joins from other registries (projects,
    finance) use these indexes to resolve display strings to canonical
    cast identity without re-normalizing on every hit.
    """

    entities: tuple[CastEntity, ...]
    _by_entity_id: Mapping[str, CastEntity] = field(repr=False)
    _by_slug: Mapping[str, CastEntity] = field(repr=False)
    _by_alias_term: Mapping[str, tuple[CastEntity, ...]] = field(repr=False)
    _by_path: Mapping[str, CastEntity] = field(repr=False)
    _by_email: Mapping[str, tuple[CastEntity, ...]] = field(repr=False)
    _canonical_email_roster: frozenset[str] = field(repr=False)

    @classmethod
    def build(cls, entities: Iterable[CastEntity]) -> CastRegistry:
        entity_tuple = tuple(entities)

        by_id: dict[str, CastEntity] = {}
        by_slug: dict[str, CastEntity] = {}
        by_path: dict[str, CastEntity] = {}
        by_alias: dict[str, list[CastEntity]] = {}
        by_email: dict[str, list[CastEntity]] = {}
        canonical_emails: set[str] = set()

        for entity in entity_tuple:
            entity_id_key = _normalize(entity.entity_id)
            if entity_id_key and entity_id_key not in by_id:
                by_id[entity_id_key] = entity
            slug_key = _normalize(entity.entity_slug)
            if slug_key and slug_key not in by_slug:
                by_slug[slug_key] = entity
            path_key = _normalize(entity.path)
            if path_key and path_key not in by_path:
                by_path[path_key] = entity
            for term in entity.canonical_terms:
                alias_key = _normalize(term)
                if not alias_key:
                    continue
                by_alias.setdefault(alias_key, []).append(entity)

            email_key = _normalize(entity.primary_contact_email)
            if email_key:
                by_email.setdefault(email_key, []).append(entity)
                if resolve_cast_contact_policy(entity).canonical_email_expected:
                    canonical_emails.add(email_key)

        return cls(
            entities=entity_tuple,
            _by_entity_id=_freeze_single(by_id),
            _by_slug=_freeze_single(by_slug),
            _by_alias_term=_freeze_multi(by_alias),
            _by_path=_freeze_single(by_path),
            _by_email=_freeze_multi(by_email),
            _canonical_email_roster=frozenset(canonical_emails),
        )

    def __iter__(self):
        return iter(self.entities)

    def __len__(self) -> int:
        return len(self.entities)

    def __contains__(self, entity_id: object) -> bool:
        return _normalize(entity_id) in self._by_entity_id

    def by_entity_id(self, entity_id: str) -> CastEntity | None:
        return self._by_entity_id.get(_normalize(entity_id))

    def by_slug(self, slug: str) -> CastEntity | None:
        return self._by_slug.get(_normalize(slug))

    def by_path(self, path: str) -> CastEntity | None:
        return self._by_path.get(_normalize(path))

    def by_alias_term(self, term: str) -> tuple[CastEntity, ...]:
        return self._by_alias_term.get(_normalize(term), ())

    def by_email(self, email: str) -> tuple[CastEntity, ...]:
        return self._by_email.get(_normalize(email), ())

    def resolve_by_email(self, email: str) -> CastEntity | None:
        matches = self.by_email(email)
        if len(matches) == 1:
            return matches[0]
        if not matches:
            return None
        canonical_matches = tuple(
            entity
            for entity in matches
            if resolve_cast_contact_policy(entity).canonical_email_expected
        )
        if len(canonical_matches) == 1:
            return canonical_matches[0]
        return None

    def canonical_email_roster(self) -> frozenset[str]:
        """Whitelist of canonical sender emails backed by the cast roster."""

        return self._canonical_email_roster

    def is_canonical_email(self, email: str) -> bool:
        return _normalize(email) in self._canonical_email_roster

    def all_entity_ids(self) -> tuple[str, ...]:
        return tuple(self._by_entity_id)

    def entities_for_ids(self, entity_ids: Sequence[str]) -> tuple[CastEntity, ...]:
        seen: set[str] = set()
        resolved: list[CastEntity] = []
        for entity_id in entity_ids:
            key = _normalize(entity_id)
            if not key or key in seen:
                continue
            entity = self._by_entity_id.get(key)
            if entity is None:
                continue
            seen.add(key)
            resolved.append(entity)
        return tuple(resolved)


__all__ = ["CastRegistry"]
