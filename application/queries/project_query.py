from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from application.ports import QueryResolutionPort
from application.resolvers import (
    resolve_project_identity_projection,
    resolve_project_property_consensus,
)
from domain.cast import CastEntity
from domain.projects import Project
from domain.projects import (
    ProjectStatus,
    project_grounding_projection,
    project_identity_projection_from_record,
    resolve_project_involvement_matches,
    resolve_project_property,
)


_MONTH_NAMES = {
    "01": "January",
    "02": "February",
    "03": "March",
    "04": "April",
    "05": "May",
    "06": "June",
    "07": "July",
    "08": "August",
    "09": "September",
    "10": "October",
    "11": "November",
    "12": "December",
}


@dataclass(frozen=True, slots=True)
class ProjectQueryResult:
    status: Literal["resolved", "clarify_missing"]
    message: str
    grounding_refs: tuple[str, ...]


def resolve_project_query(
    cast_records: Sequence[Mapping[str, Any]],
    cast_entities: Sequence[CastEntity],
    project_records: Sequence[Mapping[str, Any]],
    projects: Sequence[Project],
    *,
    variant: str,
    property: str,
    projection: str,
    sort: str,
    render: str,
    status_filter: str,
    entity_reference: str,
    output_format: str,
    task_text: str,
    fallback_text: str,
    fallback_refs: Sequence[str],
    project_roots: Sequence[str] = (),
    resolution_port: QueryResolutionPort | None,
) -> ProjectQueryResult | None:
    if variant == "membership_or_involvement":
        return _resolve_involvement(
            cast_records,
            cast_entities,
            projects,
            entity_reference=entity_reference,
            fallback_text=fallback_text,
            status_filter=status_filter,
            projection=projection,
            sort=sort,
            render=render,
            resolution_port=resolution_port,
        )

    return _resolve_scalar_property(
        project_records,
        projects,
        entity_reference=entity_reference,
        property=property,
        output_format=output_format,
        task_text=task_text,
        fallback_refs=fallback_refs,
        project_roots=project_roots,
        resolution_port=resolution_port,
    )


def _resolve_involvement(
    cast_records: Sequence[Mapping[str, Any]],
    cast_entities: Sequence[CastEntity],
    projects: Sequence[Project],
    *,
    entity_reference: str,
    fallback_text: str,
    status_filter: str,
    projection: str,
    sort: str,
    render: str,
    resolution_port: QueryResolutionPort | None,
) -> ProjectQueryResult | None:
    cast_rows = [dict(record) for record in cast_records]
    if not cast_rows or not projects:
        return None

    if resolution_port is None or resolution_port.resolve_project_subject_candidate is None:
        return None
    entity_record = resolution_port.resolve_project_subject_candidate(
        cast_rows,
        fallback_text,
        entity_reference,
    )
    if entity_record is None:
        return None

    typed_entity = _typed_entity_for_candidate(cast_entities, entity_record)
    if typed_entity is None:
        return None

    normalized_terms = typed_entity.project_involvement_terms
    if not normalized_terms:
        return None

    matched_projects = resolve_project_involvement_matches(
        projects,
        candidate_terms=normalized_terms,
        requested_statuses=_typed_statuses(status_filter),
    )
    allow_empty = render == "count"
    if not matched_projects and not allow_empty:
        return None

    titles = tuple(
        {
            project.display_title.strip()
            for project in matched_projects
            if project.display_title.strip()
        }
    )
    entity_title = (
        str(entity_record.get("title") or "").strip() or "the requested entity"
    )
    if sort == "title_asc":
        shaped_titles: tuple[str, ...] = tuple(sorted(titles, key=str.lower))
    else:
        shaped_titles = titles

    if render == "count":
        message = str(len(shaped_titles))
    elif not shaped_titles:
        message = f"{entity_title} is not listed on any matching projects."
    else:
        message = "\n".join(shaped_titles)

    grounding_refs = tuple(
        dict.fromkeys(
            ref
            for ref in (
                str(entity_record.get("path") or "").strip(),
                *(
                    str(project.path or "").strip()
                    for project in matched_projects
                    if str(project.path or "").strip()
                ),
            )
            if ref
        )
    )
    return ProjectQueryResult(
        status="resolved",
        message=message,
        grounding_refs=grounding_refs,
    )


def _resolve_scalar_property(
    project_records: Sequence[Mapping[str, Any]],
    projects: Sequence[Project],
    *,
    entity_reference: str,
    property: str,
    output_format: str,
    task_text: str,
    fallback_refs: Sequence[str],
    project_roots: Sequence[str],
    resolution_port: QueryResolutionPort | None,
) -> ProjectQueryResult | None:
    rows = [dict(record) for record in project_records]
    normalized_lookup = str(entity_reference or "").strip()
    normalized_property = str(property or "").strip()
    if not rows or not projects or not normalized_lookup or not normalized_property:
        return None

    candidate = None
    if normalized_property == "start_date":
        consensus = resolve_project_property_consensus(
            projects,
            normalized_lookup,
            property_name="start_date",
        )
        if consensus is not None:
            value = _format_date(consensus.value, output_format)
            return ProjectQueryResult(
                status="resolved",
                message=value,
                grounding_refs=consensus.refs or tuple(fallback_refs),
            )
        projection = resolve_project_identity_projection(
            projects,
            normalized_lookup,
            prefer_earliest_start_date=True,
        )
        if projection is not None:
            candidate = next(
                (
                    row
                    for row in rows
                    if str(row.get("path") or "").strip() == projection.path
                ),
                None,
            )
    if candidate is None:
        if resolution_port is None or resolution_port.resolve_project_candidate is None:
            return None
        candidate = resolution_port.resolve_project_candidate(
            rows,
            normalized_lookup,
            task_text,
        )
    if candidate is None:
        return None

    typed_project = _typed_project_for_candidate(projects, candidate)
    if typed_project is None:
        return None
    project = project_identity_projection_from_record(typed_project)
    if project is None:
        return None

    value = resolve_project_property(project, normalized_property)
    if not value:
        return None

    grounding_refs = project_grounding_projection(
        typed_project,
        property_name=property,
        fallback_refs=fallback_refs,
        project_roots=project_roots,
    ).refs

    if normalized_property in {"start_date", "updated_on"}:
        value = _format_date(value, output_format)

    return ProjectQueryResult(
        status="resolved",
        message=value,
        grounding_refs=grounding_refs,
    )

def _typed_statuses(status_filter: str) -> tuple[ProjectStatus, ...]:
    mapping = {
        "active": ProjectStatus.ACTIVE,
        "paused": ProjectStatus.PAUSED,
        "planned": ProjectStatus.PLANNED,
        "stalled": ProjectStatus.STALLED,
        "simmering": ProjectStatus.SIMMERING,
    }
    resolved = mapping.get(str(status_filter or "").strip().lower())
    return (resolved,) if resolved is not None else ()


def _typed_entity_for_candidate(
    cast_entities: Sequence[CastEntity],
    candidate: Mapping[str, Any],
) -> CastEntity | None:
    path = str(candidate.get("path") or "").strip()
    entity_slug = str(candidate.get("entity_slug") or "").strip()
    entity_id = str(candidate.get("entity_id") or "").strip()
    title = str(candidate.get("title") or "").strip().lower()
    for entity in cast_entities:
        if path and str(entity.path or "").strip() == path:
            return entity
        if entity_slug and str(entity.entity_slug or "").strip() == entity_slug:
            return entity
        if entity_id and str(entity.entity_id or "").strip() == entity_id:
            return entity
        if title and str(entity.title or "").strip().lower() == title:
            return entity
    return None


def _typed_project_for_candidate(
    projects: Sequence[Project],
    candidate: Mapping[str, Any],
) -> Project | None:
    path = str(candidate.get("path") or "").strip()
    project_path = str(candidate.get("project_path") or "").strip()
    title = str(candidate.get("title") or "").strip().lower()
    project_name = str(candidate.get("project_name") or "").strip().lower()
    alias = str(candidate.get("alias") or "").strip().lower()
    for project in projects:
        if path and str(project.path or "").strip() == path:
            return project
        if project_path and str(project.path or "").strip() == project_path:
            return project
        if title and str(project.title or "").strip().lower() == title:
            return project
        if project_name and str(project.project_name or "").strip().lower() == project_name:
            return project
        if alias and str(project.alias or "").strip().lower() == alias:
            return project
    return None


def _format_date(value: str, output_format: str) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(value or "").strip())
    if match is None:
        return str(value or "").strip()
    year, month, day = match.groups()
    if output_format == "dd-mm-yyyy":
        return f"{day}-{month}-{year}"
    if output_format == "mm/dd/yyyy":
        return f"{month}/{day}/{year}"
    if output_format == "month dd, yyyy":
        return f"{_MONTH_NAMES[month]} {day}, {year}"
    return f"{year}-{month}-{day}"


__all__ = ["ProjectQueryResult", "resolve_project_query"]
