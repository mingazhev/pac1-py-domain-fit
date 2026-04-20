from __future__ import annotations

from dataclasses import dataclass

from .cast_entity import CastEntity
from .entity_kind import EntityKind


@dataclass(frozen=True, slots=True)
class Service(CastEntity):
    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", EntityKind.SERVICE)
