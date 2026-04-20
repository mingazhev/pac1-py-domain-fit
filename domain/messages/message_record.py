from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from domain.cast import CastEntity
from domain.workspace import DEFAULT_WORKSPACE_LAYOUT, WorkspaceLayout


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


class MessageSurfaceKind(str, Enum):
    CHANNEL = "channel"
    THREAD = "thread"
    MEMORY = "memory"
    UNKNOWN = "unknown"

    @classmethod
    def from_path(cls, path: str, layout: WorkspaceLayout | None = None) -> MessageSurfaceKind:
        resolved_layout = DEFAULT_WORKSPACE_LAYOUT if layout is None else layout
        if resolved_layout.is_outbox_channel_path(path):
            return cls.CHANNEL
        if resolved_layout.is_knowledge_thread_path(path):
            return cls.THREAD
        if resolved_layout.path_has_role(path, "memory"):
            return cls.MEMORY
        return cls.UNKNOWN


@dataclass(frozen=True, slots=True)
class MessageRecord:
    path: str
    recorded_on: str = ""
    section_index: int = 0
    author: str = ""
    author_id: str = ""
    message: str = ""
    surface_kind: MessageSurfaceKind = MessageSurfaceKind.UNKNOWN

    def matches_entity(self, entity: CastEntity) -> bool:
        normalized_author_id = _normalize_text(self.author_id)
        if normalized_author_id and normalized_author_id in {
            _normalize_text(entity.entity_id),
            _normalize_text(entity.entity_slug),
            _normalize_text(f"entity.{entity.entity_slug}"),
        }:
            return True

        normalized_author = _normalize_text(self.author)
        if not normalized_author:
            return False
        return any(
            normalized_author == _normalize_text(term)
            for term in entity.canonical_terms
            if str(term or "").strip()
        )

    @property
    def sort_key(self) -> tuple[str, int, str]:
        return (self.recorded_on, self.section_index, self.path)
