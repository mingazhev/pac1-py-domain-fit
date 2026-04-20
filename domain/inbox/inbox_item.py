from __future__ import annotations

from dataclasses import dataclass

from domain.record_references import (
    RelatedRecordReference,
    build_related_record_references,
    partition_related_record_references,
)


@dataclass(frozen=True, slots=True)
class InboxItem:
    path: str
    record_type: str = ""
    subject: str = ""
    sender: str = ""
    channel: str = ""
    body: str = ""
    to: tuple[str, ...] = ()
    received_at: str = ""
    cc: tuple[str, ...] = ()
    reply_to: str = ""
    source_channel: str = ""
    related_entities: tuple[str, ...] = ()
    related_projects: tuple[str, ...] = ()
    related_references: tuple[RelatedRecordReference, ...] = ()

    def __post_init__(self) -> None:
        if self.related_references:
            if not self.related_entities and not self.related_projects:
                related_entities, related_projects = partition_related_record_references(
                    self.related_references
                )
                object.__setattr__(self, "related_entities", related_entities)
                object.__setattr__(self, "related_projects", related_projects)
            return
        object.__setattr__(
            self,
            "related_references",
            build_related_record_references(
                self.related_entities,
                self.related_projects,
            ),
        )
