from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ._text import normalize_cast_text
from .cast_entity import CastEntity
from .contact_policy import resolve_cast_contact_policy


def _identity_key(value: object) -> str:
    return normalize_cast_text(value)


def _projection_from_entity(entity: CastEntity) -> CastIdentityProjection:
    kind = entity.kind.value if entity.kind is not None else ""
    return CastIdentityProjection(
        path=entity.path,
        title=entity.title,
        entity_id=entity.entity_id,
        entity_slug=entity.entity_slug,
        alias=entity.alias,
        identity_terms=entity.stable_identity_terms,
        alias_terms=entity.alias_terms,
        primary_contact_email=entity.primary_contact_email,
        relationship=entity.relationship,
        kind=kind,
    )


def _entity_match_terms(entity: CastEntity) -> tuple[str, ...]:
    kind = entity.kind.value if entity.kind is not None else ""
    return tuple(
        dict.fromkeys(
            term
            for term in (
                entity.entity_id,
                entity.entity_slug,
                entity.title,
                entity.alias,
                entity.primary_contact_email,
                entity.relationship,
                kind,
                *(entity.stable_identity_terms or ()),
                *(entity.relationship_alias_terms or ()),
                *(entity.descriptor_terms or ()),
                *(entity.alias_terms or ()),
            )
            if str(term or "").strip()
        )
    )


def _unique_match(
    entities: Iterable[CastEntity],
    *,
    query: str,
) -> CastEntity | None:
    key = _identity_key(query)
    if not key:
        return None
    matches: list[CastEntity] = []
    seen_paths: set[str] = set()
    for entity in entities:
        term_keys = {_identity_key(term) for term in _entity_match_terms(entity)}
        if key not in term_keys:
            continue
        path_key = _identity_key(entity.path)
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        matches.append(entity)
    if len(matches) != 1:
        return None
    return matches[0]


@dataclass(frozen=True, slots=True)
class CastIdentityProjection:
    path: str
    title: str
    entity_id: str
    entity_slug: str
    alias: str
    identity_terms: tuple[str, ...]
    alias_terms: tuple[str, ...]
    primary_contact_email: str
    relationship: str
    kind: str


@dataclass(frozen=True, slots=True)
class CanonicalContactProjection:
    entity: CastIdentityProjection
    email: str
    role: str


def resolve_cast_identity(
    records: Sequence[CastEntity],
    query: str,
) -> CastIdentityProjection | None:
    if not records:
        return None
    match = _unique_match(records, query=query)
    if match is None:
        return None
    return _projection_from_entity(match)


def resolve_cast_contact(
    records: Sequence[CastEntity],
    query: str,
    role: str = "primary_contact",
) -> CanonicalContactProjection | None:
    identity = resolve_cast_identity(records, query)
    if identity is None:
        return None
    entity = next(
        (
            candidate
            for candidate in records
            if str(candidate.path or "").strip() == identity.path
            or (
                identity.entity_slug
                and str(candidate.entity_slug or "").strip() == identity.entity_slug
            )
        ),
        None,
    )
    if entity is None:
        return None
    policy = resolve_cast_contact_policy(entity)
    email = str(identity.primary_contact_email or "").strip()
    if not email or not policy.canonical_email_allowed:
        return None
    return CanonicalContactProjection(
        entity=identity,
        email=email,
        role=str(role or "primary_contact").strip() or "primary_contact",
    )


def resolve_sender_canonical_entity(
    records: Sequence[CastEntity],
    email: str,
) -> CastIdentityProjection | None:
    if not records:
        return None
    normalized_email = _identity_key(email)
    if not normalized_email:
        return None
    matches = tuple(
        entity
        for entity in records
        if _identity_key(entity.primary_contact_email) == normalized_email
    )
    if len(matches) == 1:
        return _projection_from_entity(matches[0])
    canonical_matches = tuple(
        entity
        for entity in matches
        if resolve_cast_contact_policy(entity).canonical_email_expected
    )
    if len(canonical_matches) == 1:
        return _projection_from_entity(canonical_matches[0])
    return None


__all__ = [
    "CanonicalContactProjection",
    "CastIdentityProjection",
    "resolve_cast_contact",
    "resolve_cast_identity",
    "resolve_sender_canonical_entity",
]
