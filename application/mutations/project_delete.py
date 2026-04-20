from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from application.ports import QueryResolutionPort
from domain.process import AuthorizationStamp
from domain.projects.deletion import project_record_root_path
from domain.projects.project import Project

from .result import MutationStepResult


def resolve_project_delete(
    project_records: Sequence[Mapping[str, Any]],
    projects: Sequence[Project],
    *,
    project_reference: str,
    authorization_kind: str | None,
    authorized_by: str | None,
    task_text: str,
    fallback_refs: Sequence[str],
    query_resolution_port: QueryResolutionPort | None,
) -> MutationStepResult:
    if AuthorizationStamp.from_fields(authorization_kind, authorized_by) is None:
        return MutationStepResult(
            status="blocked",
            message=(
                "Project deletion requires explicit authorization metadata on the "
                "typed mutation request."
            ),
            grounding_refs=tuple(ref for ref in fallback_refs if ref),
            reason_code="mutation_requires_authorization",
        )
    rows = [dict(record) for record in project_records]
    normalized = str(project_reference or "").strip()
    if not rows or not normalized:
        return MutationStepResult(
            status="clarify_missing",
            message="Could not resolve the canonical project to delete.",
            grounding_refs=(),
            reason_code="project_mutation_target_unresolved",
        )

    resolver = (
        query_resolution_port.resolve_project_candidate
        if query_resolution_port is not None
        else None
    )
    if resolver is None:
        return MutationStepResult(
            status="clarify_missing",
            message="Project deletion is missing a canonical project resolver.",
            grounding_refs=tuple(ref for ref in fallback_refs if ref),
            reason_code="project_mutation_target_unresolved",
        )

    candidate = resolver(rows, normalized, task_text)
    if candidate is None:
        return MutationStepResult(
            status="clarify_missing",
            message="Could not resolve a unique canonical project for the requested deletion.",
            grounding_refs=tuple(ref for ref in fallback_refs if ref),
            reason_code="project_mutation_target_unresolved",
        )

    project = _typed_project_for_candidate(projects, candidate)
    if project is None:
        return MutationStepResult(
            status="clarify_missing",
            message="Resolved project record is not canonically parseable.",
            grounding_refs=_refs(candidate, fallback_refs),
            reason_code="project_mutation_target_invalid",
        )

    delete_root = _delete_root(project)
    if delete_root is None:
        return MutationStepResult(
            status="clarify_missing",
            message="Could not derive a canonical project root path for deletion.",
            grounding_refs=_refs(candidate, fallback_refs),
            reason_code="project_mutation_target_invalid",
        )

    return MutationStepResult(
        status="resolved",
        message=delete_root,
        grounding_refs=_refs(candidate, fallback_refs),
        reason_code="project_mutation_resolved",
    )


def _delete_root(project: Project) -> str | None:
    return project_record_root_path(project)


def _refs(candidate: Mapping[str, Any], fallback: Sequence[str]) -> tuple[str, ...]:
    path = str(candidate.get("path") or "").strip()
    if path:
        return (f"/{path}" if not path.startswith("/") else path,)
    return tuple(ref for ref in fallback if ref)


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


__all__ = ["resolve_project_delete"]
