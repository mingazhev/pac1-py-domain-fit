from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping


RecordCandidate = Mapping[str, Any] | dict[str, Any] | None
RecordResolver = Callable[[list[dict[str, Any]], str], RecordCandidate]

@dataclass(frozen=True, slots=True)
class CastResolverSet:
    exact_resolve: RecordResolver
    llm_resolve: RecordResolver


@dataclass(frozen=True, slots=True)
class ProjectResolverSet:
    exact_resolve: RecordResolver
    llm_resolve: RecordResolver


def resolve_entity_candidate(
    cast_records: list[dict[str, Any]],
    *,
    lookup_text: str,
    fallback_text: str,
    self_reference: bool = False,
    resolvers: CastResolverSet,
) -> dict[str, Any] | None:
    candidate = _resolve_self_candidate(cast_records) if self_reference else None
    if candidate is not None:
        return candidate
    candidate = resolvers.exact_resolve(cast_records, lookup_text)
    if candidate is None and lookup_text != fallback_text:
        candidate = resolvers.llm_resolve(cast_records, fallback_text)
    if candidate is None:
        candidate = resolvers.llm_resolve(cast_records, lookup_text)
    return dict(candidate) if candidate is not None else None


def _resolve_self_candidate(
    cast_records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    matches = [
        dict(record)
        for record in cast_records
        if _normalize_query_text(record.get("relationship")) == "self"
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def resolve_message_entity_candidate(
    cast_records: list[dict[str, Any]],
    *,
    entity_query: str,
    fallback_text: str,
    resolvers: CastResolverSet,
) -> dict[str, Any] | None:
    candidate = resolvers.exact_resolve(cast_records, entity_query)
    if candidate is None:
        candidate = resolvers.llm_resolve(cast_records, entity_query)
    if candidate is None and entity_query != fallback_text:
        candidate = resolvers.llm_resolve(cast_records, fallback_text)
    return dict(candidate) if candidate is not None else None


def resolve_project_subject_candidate(
    cast_records: list[dict[str, Any]],
    *,
    task_text: str,
    lookup_text: str,
    resolvers: CastResolverSet,
) -> dict[str, Any] | None:
    candidate = resolvers.exact_resolve(cast_records, lookup_text)
    if candidate is None and lookup_text != task_text:
        candidate = resolvers.llm_resolve(cast_records, task_text)
    if candidate is None:
        candidate = resolvers.llm_resolve(cast_records, lookup_text)
    return dict(candidate) if candidate is not None else None


def resolve_project_candidate(
    project_records: list[dict[str, Any]],
    *,
    lookup_text: str,
    task_text: str,
    resolvers: ProjectResolverSet,
) -> dict[str, Any] | None:
    candidate = resolvers.exact_resolve(project_records, lookup_text)
    if candidate is None and lookup_text != task_text:
        candidate = resolvers.llm_resolve(project_records, task_text)
    if candidate is None:
        candidate = resolvers.llm_resolve(project_records, lookup_text)
    return dict(candidate) if candidate is not None else None


def _normalize_query_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


resolve_birthday_candidate = resolve_entity_candidate
resolve_message_quote_candidate = resolve_message_entity_candidate
resolve_project_involvement_candidate = resolve_project_subject_candidate
resolve_project_start_date_candidate = resolve_project_candidate
