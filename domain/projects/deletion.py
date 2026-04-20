from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Sequence

from ._policy_shared import normalize_repo_path, project_start_date
from .project import Project


ProjectRecordResolver = Callable[[Sequence[Project], str], Project | None]


@dataclass(frozen=True, slots=True)
class ProjectCompareDeleteResolution:
    outcome: str  # "delete" | "clarify"
    compared_refs: tuple[str, ...] = ()
    delete_root: str | None = None
    clarification_message: str = ""
    clarification_summary: str = ""


def project_directory_delete_root(path: str) -> str | None:
    normalized_path = normalize_repo_path(path)
    pure_segments = tuple(segment for segment in normalized_path.split("/") if segment)
    if len(pure_segments) < 2:
        return None
    parent_name = pure_segments[-2].lower()
    if "project" not in parent_name:
        return None
    if pure_segments[-1].lower() == "readme.md":
        return None
    return normalized_path


def project_readme_delete_root(path: str) -> str | None:
    normalized_path = normalize_repo_path(path)
    pure_segments = tuple(segment for segment in normalized_path.split("/") if segment)
    if len(pure_segments) < 3:
        return None
    if pure_segments[-1].lower() != "readme.md":
        return None
    if "project" not in pure_segments[-3].lower():
        return None
    return f"/{'/'.join(pure_segments[:-1])}"


def project_record_root_path(project: Project) -> str | None:
    readme_path = normalize_repo_path(f"/{project.path or ''}")
    if readme_path.lower().endswith("/readme.md"):
        return readme_path.rsplit("/", 1)[0]
    return None


def resolve_project_compare_delete_resolution(
    *,
    first_query: str,
    second_query: str,
    project_records: Sequence[Project],
    record_resolver: ProjectRecordResolver,
) -> ProjectCompareDeleteResolution | None:
    first_record = record_resolver(project_records, first_query)
    second_record = record_resolver(project_records, second_query)
    compared_refs = tuple(
        dict.fromkeys(
            ref
            for ref in (
                normalize_repo_path(f"/{first_record.path or ''}")
                if first_record is not None
                else "",
                normalize_repo_path(f"/{second_record.path or ''}")
                if second_record is not None
                else "",
            )
            if ref
        )
    )
    if first_record is None or second_record is None:
        return ProjectCompareDeleteResolution(
            outcome="clarify",
            compared_refs=compared_refs,
            clarification_message="I could not resolve both canonical project records uniquely, so I cannot safely delete a project.",
            clarification_summary="clarified unresolved canonical project comparison before any delete",
        )

    first_date = project_start_date(first_record)
    second_date = project_start_date(second_record)
    if not first_date or not second_date:
        return ProjectCompareDeleteResolution(
            outcome="clarify",
            compared_refs=compared_refs,
            clarification_message="I could not ground both project start dates canonically, so I cannot safely delete a project.",
            clarification_summary="clarified missing canonical project start date before delete",
        )
    if first_date == second_date:
        return ProjectCompareDeleteResolution(
            outcome="clarify",
            compared_refs=compared_refs,
            clarification_message="Both projects have the same canonical start date, so there is no unique earlier project to delete.",
            clarification_summary="clarified equal canonical project start dates before delete",
        )

    earlier_record = first_record if first_date < second_date else second_record
    delete_root = project_record_root_path(earlier_record)
    if not delete_root:
        return ProjectCompareDeleteResolution(
            outcome="clarify",
            compared_refs=compared_refs,
            clarification_message="I identified the earlier project, but I could not derive a canonical project root path to delete.",
            clarification_summary="clarified missing canonical project root path before delete",
        )

    return ProjectCompareDeleteResolution(
        outcome="delete",
        compared_refs=compared_refs,
        delete_root=delete_root,
    )


__all__ = [
    "ProjectCompareDeleteResolution",
    "project_directory_delete_root",
    "project_readme_delete_root",
    "project_record_root_path",
    "resolve_project_compare_delete_resolution",
]
