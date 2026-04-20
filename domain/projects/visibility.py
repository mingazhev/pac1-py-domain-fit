from __future__ import annotations

from dataclasses import dataclass

from .catalog import ProjectVisibility, parse_project_visibility


@dataclass(frozen=True, slots=True)
class VisibilityPolicy:
    level: ProjectVisibility | None

    @property
    def is_local_only(self) -> bool:
        return self.level == ProjectVisibility.LOCAL_ONLY

    @property
    def is_private(self) -> bool:
        return self.level == ProjectVisibility.PRIVATE

    @property
    def is_household(self) -> bool:
        return self.level == ProjectVisibility.HOUSEHOLD

    @property
    def is_scoped(self) -> bool:
        return self.level in {
            ProjectVisibility.SCOPED_CLIENT,
            ProjectVisibility.SCOPED_WORK,
        }


def resolve_visibility_policy(value: object) -> VisibilityPolicy:
    return VisibilityPolicy(level=parse_project_visibility(value))
