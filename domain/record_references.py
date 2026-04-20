from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from enum import Enum


class RelatedRecordKind(str, Enum):
    ENTITY = "entity"
    PROJECT = "project"


@dataclass(frozen=True, slots=True)
class RelatedRecordReference:
    kind: RelatedRecordKind
    target_id: str


def parse_related_record_reference(value: object) -> RelatedRecordReference | None:
    text = str(value or "").strip().lower()
    if text.startswith("entity.") and len(text) > len("entity."):
        return RelatedRecordReference(RelatedRecordKind.ENTITY, text)
    if text.startswith("project.") and len(text) > len("project."):
        return RelatedRecordReference(RelatedRecordKind.PROJECT, text)
    return None


def build_related_record_references(
    related_entities: Iterable[object] = (),
    related_projects: Iterable[object] = (),
) -> tuple[RelatedRecordReference, ...]:
    references: list[RelatedRecordReference] = []
    seen: set[tuple[RelatedRecordKind, str]] = set()
    for raw_value in related_entities:
        reference = parse_related_record_reference(raw_value)
        if reference is None or reference.kind != RelatedRecordKind.ENTITY:
            continue
        key = (reference.kind, reference.target_id)
        if key in seen:
            continue
        seen.add(key)
        references.append(reference)
    for raw_value in related_projects:
        reference = parse_related_record_reference(raw_value)
        if reference is None or reference.kind != RelatedRecordKind.PROJECT:
            continue
        key = (reference.kind, reference.target_id)
        if key in seen:
            continue
        seen.add(key)
        references.append(reference)
    return tuple(references)


def partition_related_record_references(
    references: Iterable[RelatedRecordReference],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    entity_ids: list[str] = []
    project_ids: list[str] = []
    for reference in references:
        if reference.kind == RelatedRecordKind.ENTITY:
            entity_ids.append(reference.target_id)
        elif reference.kind == RelatedRecordKind.PROJECT:
            project_ids.append(reference.target_id)
    return tuple(entity_ids), tuple(project_ids)


def filter_related_record_references(
    references: Iterable[RelatedRecordReference],
    *,
    valid_entity_ids: Collection[str] | None = None,
    valid_project_ids: Collection[str] | None = None,
) -> tuple[RelatedRecordReference, ...]:
    normalized_valid_entity_ids = (
        {str(value).strip().lower() for value in valid_entity_ids if str(value).strip()}
        if valid_entity_ids is not None
        else None
    )
    normalized_valid_project_ids = (
        {str(value).strip().lower() for value in valid_project_ids if str(value).strip()}
        if valid_project_ids is not None
        else None
    )
    filtered: list[RelatedRecordReference] = []
    for reference in references:
        if reference.kind == RelatedRecordKind.ENTITY:
            if (
                normalized_valid_entity_ids is not None
                and reference.target_id not in normalized_valid_entity_ids
            ):
                continue
        elif reference.kind == RelatedRecordKind.PROJECT:
            if (
                normalized_valid_project_ids is not None
                and reference.target_id not in normalized_valid_project_ids
            ):
                continue
        filtered.append(reference)
    return tuple(filtered)
