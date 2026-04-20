from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .cast_entity import CastEntity


CAST_CANONICAL_PATH_PREFIX = "10_entities/cast/"


def _normalize_identity_path(path: object) -> str:
    return str(path or "").strip().lstrip("/").replace("\\", "/").lower()


def is_canonical_cast_path(path: object) -> bool:
    normalized = _normalize_identity_path(path)
    return normalized.startswith(CAST_CANONICAL_PATH_PREFIX)


CanonicalSource = Literal["cast", "accounts", "none"]


@dataclass(frozen=True, slots=True)
class CanonicalIdentityDecision:
    source: CanonicalSource
    cast_entity: CastEntity | None = None
    accounts_backstop_used: bool = False


def resolve_canonical_identity_source(
    *,
    cast_entity: CastEntity | None,
    account_record_present: bool = False,
) -> CanonicalIdentityDecision:
    if cast_entity is not None and is_canonical_cast_path(cast_entity.path):
        return CanonicalIdentityDecision(source="cast", cast_entity=cast_entity)
    if cast_entity is not None:
        return CanonicalIdentityDecision(source="cast", cast_entity=cast_entity)
    if account_record_present:
        return CanonicalIdentityDecision(source="accounts", accounts_backstop_used=True)
    return CanonicalIdentityDecision(source="none")


def assert_cast_displaces_accounts(
    cast_entities: Sequence[CastEntity],
    account_identity_keys: Sequence[str],
) -> tuple[str, ...]:
    displaced: list[str] = []
    cast_keys = {
        _normalize_identity_path(entity.entity_id)
        for entity in cast_entities
        if str(entity.entity_id or "").strip()
    }
    cast_keys.update(
        _normalize_identity_path(entity.entity_slug)
        for entity in cast_entities
        if str(entity.entity_slug or "").strip()
    )
    for raw_key in account_identity_keys:
        key = _normalize_identity_path(raw_key)
        if not key:
            continue
        if key in cast_keys:
            continue
        slug = re.sub(r"^entity\.", "", key)
        if slug in cast_keys:
            continue
        displaced.append(raw_key)
    return tuple(displaced)
