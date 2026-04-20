from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from ._policy_shared import normalize_repo_path
from .project import Project


@dataclass(frozen=True, slots=True)
class ProjectIdentityProjection:
    path: str
    title: str
    project_name: str
    alias: str
    status: str
    kind: str
    lane: str
    priority: str
    visibility: str
    start_date: str
    updated_on: str
    goal: str
    next_step: str
    owner_ids: tuple[str, ...]
    linked_entities: tuple[str, ...]
    participants: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectGroundingProjection:
    refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectPropertyConsensusProjection:
    value: str
    refs: tuple[str, ...]

def project_identity_projection_from_record(
    project: Project,
) -> ProjectIdentityProjection | None:
    return ProjectIdentityProjection(
        path=str(project.path or "").strip(),
        title=str(project.title or "").strip(),
        project_name=str(project.project_name or "").strip(),
        alias=str(project.alias or "").strip(),
        status=str(project.status or "").strip(),
        kind=str(project.kind or "").strip(),
        lane=str(project.lane or "").strip(),
        priority=str(project.priority or "").strip(),
        visibility=str(project.visibility or "").strip(),
        start_date=str(project.start_date or "").strip(),
        updated_on=str(project.updated_on or "").strip(),
        goal=str(project.goal or "").strip(),
        next_step=str(project.next_step or "").strip(),
        owner_ids=tuple(str(item).strip() for item in project.owner_ids if str(item or "").strip()),
        linked_entities=tuple(
            str(item).strip() for item in project.linked_entities if str(item or "").strip()
        ),
        participants=tuple(
            str(item).strip() for item in project.participants if str(item or "").strip()
        ),
    )


def resolve_project_property(
    project: ProjectIdentityProjection,
    property_name: str,
) -> str:
    if property_name == "title":
        return project.title
    if property_name == "project_name":
        return project.project_name
    if property_name == "alias":
        return project.alias
    if property_name == "status":
        return project.status
    if property_name == "kind":
        return project.kind
    if property_name == "lane":
        return project.lane
    if property_name == "priority":
        return project.priority
    if property_name == "visibility":
        return project.visibility
    if property_name == "start_date":
        return project.start_date
    if property_name == "updated_on":
        return project.updated_on
    if property_name == "goal":
        return project.goal
    if property_name == "next_step":
        return project.next_step
    if property_name == "owner_ids":
        return "\n".join(project.owner_ids)
    if property_name == "linked_entities":
        return "\n".join(project.linked_entities)
    if property_name == "participants":
        return "\n".join(project.participants)
    return ""


def project_grounding_projection(
    project: Project,
    *,
    property_name: str,
    fallback_refs: Sequence[str],
    project_roots: Sequence[str],
) -> ProjectGroundingProjection:
    refs: list[str] = []
    normalized_roots = tuple(
        _normalize_repo_path(root)
        for root in project_roots
        if str(root or "").strip()
    )
    normalized = _normalize_repo_path(project.path)
    if normalized not in {"", "/"}:
        if (
            property_name == "start_date"
            and not normalized.lower().endswith("/readme.md")
            and any(
                normalized == root or normalized.startswith(f"{root}/")
                for root in normalized_roots
            )
            and "." not in PurePosixPath(normalized).name
        ):
            normalized = f"{normalized}/README.MD"
        refs.append(normalized)
    fallback_normalized = tuple(
        normalized
        for normalized in (
            _normalize_repo_path(ref) for ref in fallback_refs if str(ref or "").strip()
        )
        if normalized
    )
    if not refs:
        refs.extend(fallback_normalized)
    elif property_name == "start_date":
        refs.extend(fallback_normalized)
    if not refs and property_name == "start_date" and normalized_roots:
        refs.append(f"{normalized_roots[0]}/README.MD")
    return ProjectGroundingProjection(refs=tuple(dict.fromkeys(refs)))


def _normalize_repo_path(path: object) -> str:
    return normalize_repo_path(path)

__all__ = [
    "ProjectGroundingProjection",
    "ProjectIdentityProjection",
    "ProjectPropertyConsensusProjection",
    "project_grounding_projection",
    "project_identity_projection_from_record",
    "resolve_project_property",
]
