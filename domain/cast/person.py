from __future__ import annotations

from dataclasses import dataclass

from .entity_kind import EntityKind
from .living_entity import LivingCastEntity


@dataclass(frozen=True, slots=True)
class Person(LivingCastEntity):
    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", EntityKind.PERSON)

    def is_person(self) -> bool:
        return True
