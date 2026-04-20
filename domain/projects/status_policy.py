from __future__ import annotations

import re
from collections.abc import Sequence

from ._policy_shared import project_start_date
from .catalog import ProjectStatus, normalize_project_status
from .project import Project


_PROJECT_STATUS_PRIORITY = {
    ProjectStatus.ACTIVE.value: 5,
    ProjectStatus.SIMMERING.value: 4,
    ProjectStatus.PLANNED.value: 3,
    ProjectStatus.PAUSED.value: 2,
    ProjectStatus.STALLED.value: 1,
}


def _normalize_project_identity_value(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[_-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def project_identity_key(project: Project) -> str:
    for candidate in (project.alias, project.project_name, project.display_title):
        normalized = _normalize_project_identity_value(candidate)
        if normalized:
            return normalized
    return _normalize_project_identity_value(project.path)


def project_status_priority(project: Project) -> int:
    return _PROJECT_STATUS_PRIORITY.get(normalize_project_status(project.status), 0)


def select_canonical_project(projects: Sequence[Project]) -> Project | None:
    candidates = [project for project in projects if project is not None]
    if not candidates:
        return None

    identity_keys = {project_identity_key(project) for project in candidates}
    if len(identity_keys) != 1:
        return None

    return max(
        candidates,
        key=lambda project: (
            project_status_priority(project),
            project_start_date(project),
            _normalize_project_identity_value(project.path),
        ),
    )


__all__ = [
    "project_identity_key",
    "project_status_priority",
    "select_canonical_project",
]
