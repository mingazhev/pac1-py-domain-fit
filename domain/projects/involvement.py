from __future__ import annotations

from collections.abc import Sequence

from .catalog import ProjectStatus
from .project import Project


def resolve_project_involvement_matches(
    projects: Sequence[Project],
    *,
    candidate_terms: Sequence[str],
    requested_statuses: Sequence[ProjectStatus] = (),
) -> tuple[Project, ...]:
    normalized_terms = tuple(str(term or "").strip().lower() for term in candidate_terms if str(term or "").strip())
    if not normalized_terms:
        return ()

    matched: list[Project] = []
    for project in projects:
        if not project.display_title:
            continue
        if requested_statuses and not any(project.has_status(status) for status in requested_statuses):
            continue
        if not project.normalized_involvement_terms:
            continue
        if project.involves_any_term(normalized_terms):
            matched.append(project)
    return tuple(matched)
