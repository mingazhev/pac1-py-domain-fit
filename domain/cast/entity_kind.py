from __future__ import annotations

from enum import Enum

from ._text import normalize_cast_text


class EntityKind(str, Enum):
    PERSON = "person"
    SYSTEM = "system"
    PET = "pet"
    ANIMAL = "animal"
    DEVICE = "device"
    SERVICE = "service"

    @classmethod
    def parse(cls, value: object) -> "EntityKind | None":
        normalized = normalize_cast_text(value)
        for member in cls:
            if normalized == member.value:
                return member
        return None
