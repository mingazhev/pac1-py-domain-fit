from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from domain.workspace import normalize_workspace_path


class ChannelTransportKind(str, Enum):
    EMAIL = "email"
    SIGNAL = "signal"
    SLACK = "slack"
    DISCORD = "discord"
    CALENDAR = "calendar"
    UNKNOWN = "unknown"

    @classmethod
    def from_value(cls, value: object) -> ChannelTransportKind:
        normalized = str(value or "").strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        return cls.UNKNOWN


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _tokenize(value: object) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(r"[a-z0-9]+", _normalize_text(value).lower())))


@dataclass(frozen=True, slots=True)
class ChannelDefinition:
    path: str
    title: str = ""
    alias: str = ""
    transport_kind: ChannelTransportKind = ChannelTransportKind.UNKNOWN
    address: str = ""
    created_on: str = ""
    participants: tuple[str, ...] = ()
    authority_trust_class: str = ""
    lane_anchor: str = ""

    def normalized_path(self) -> str:
        return normalize_workspace_path(self.path)

    def search_terms(self) -> tuple[str, ...]:
        values = (
            self.title,
            self.alias,
            self.address,
            self.authority_trust_class,
            self.lane_anchor,
            *self.participants,
            self.path,
        )
        return tuple(
            dict.fromkeys(_normalize_text(value) for value in values if _normalize_text(value))
        )

    def search_tokens(self) -> tuple[str, ...]:
        tokens: list[str] = []
        for value in self.search_terms():
            tokens.extend(_tokenize(value))
        return tuple(dict.fromkeys(tokens))


__all__ = [
    "ChannelDefinition",
    "ChannelTransportKind",
]
