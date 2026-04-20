from __future__ import annotations

from dataclasses import dataclass

from .cast_entity import CastEntity
from .entity_kind import EntityKind


@dataclass(frozen=True, slots=True)
class CastContactPolicy:
    canonical_email_expected: bool
    canonical_email_allowed: bool = True


def resolve_cast_contact_policy(entity: CastEntity) -> CastContactPolicy:
    if entity.kind == EntityKind.PERSON:
        return CastContactPolicy(canonical_email_expected=True)
    return CastContactPolicy(canonical_email_expected=False)
