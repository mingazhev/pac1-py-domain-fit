from __future__ import annotations

import re
from collections.abc import Sequence

from domain.projects.project import Project
from domain.projects.projections import (
    ProjectIdentityProjection,
    ProjectPropertyConsensusProjection,
    project_identity_projection_from_record,
    resolve_project_property,
)


def _normalize_project_text(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[_-]+", " ", text)
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalized_terms(values: Sequence[object]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            normalized
            for normalized in (
                _normalize_project_text(value)
                for value in values
            )
            if normalized
        )
    )


def _project_primary_terms(project: Project) -> tuple[str, ...]:
    return _normalized_terms((project.title, project.project_name, project.alias))


def _project_alias_terms(project: Project) -> tuple[str, ...]:
    return _normalized_terms(project.alias_terms)


def _project_descriptor_terms(project: Project) -> tuple[str, ...]:
    return _normalized_terms(project.descriptor_aliases)


def _matching_projections(
    project_records: Sequence[Project],
    query: str,
) -> tuple[ProjectIdentityProjection, ...]:
    normalized_query = _normalize_project_text(query)
    if not normalized_query:
        return ()
    variants = {normalized_query}
    core_matches: list[ProjectIdentityProjection] = []
    alias_matches: list[ProjectIdentityProjection] = []
    descriptor_matches: list[ProjectIdentityProjection] = []
    for project in project_records:
        projection = project_identity_projection_from_record(project)
        if projection is None:
            continue
        if variants.intersection(_project_primary_terms(project)):
            core_matches.append(projection)
            continue
        if variants.intersection(_project_alias_terms(project)):
            alias_matches.append(projection)
            continue
        if variants.intersection(_project_descriptor_terms(project)):
            descriptor_matches.append(projection)
    return tuple(core_matches or alias_matches or descriptor_matches)


def resolve_project_identity_projection(
    project_records: Sequence[Project],
    query: str,
    *,
    prefer_earliest_start_date: bool = False,
) -> ProjectIdentityProjection | None:
    matches = _matching_projections(project_records, query)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    if prefer_earliest_start_date:
        ordered = sorted(
            matches,
            key=lambda projection: (_project_projection_start_date(projection), projection.path),
        )
        return ordered[0] if ordered else None
    return None


def resolve_project_property_consensus(
    project_records: Sequence[Project],
    query: str,
    *,
    property_name: str,
) -> ProjectPropertyConsensusProjection | None:
    matches = _matching_projections(project_records, query)
    if len(matches) < 2:
        return None

    values: list[str] = []
    refs: list[str] = []
    for projection in matches:
        if property_name == "start_date":
            value = _project_projection_start_date(projection)
        else:
            value = resolve_project_property(projection, property_name)
        value = str(value or "").strip()
        if not value:
            return None
        values.append(value)
        if projection.path:
            refs.append(projection.path)
    if len(set(values)) != 1:
        return None
    return ProjectPropertyConsensusProjection(
        value=values[0],
        refs=tuple(dict.fromkeys(refs)),
    )


def _project_projection_start_date(projection: ProjectIdentityProjection) -> str:
    return str(resolve_project_property(projection, "start_date") or "").strip()


__all__ = [
    "resolve_project_identity_projection",
    "resolve_project_property_consensus",
]
