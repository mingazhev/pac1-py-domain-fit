from __future__ import annotations

from enum import Enum
from typing import Any


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    PLANNED = "planned"
    STALLED = "stalled"
    SIMMERING = "simmering"


class ProjectKind(str, Enum):
    DAY_JOB = "day_job"
    FAMILY = "family"
    HOBBY = "hobby"
    HOUSE_SYSTEM = "house_system"
    STARTUP = "startup"


class ProjectLane(str, Enum):
    DAY_JOB = "day_job"
    FAMILY = "family"
    HOBBY = "hobby"
    HOME_SYSTEMS = "home_systems"
    STARTUP = "startup"


class ProjectVisibility(str, Enum):
    HOUSEHOLD = "household"
    LOCAL_ONLY = "local_only"
    PRIVATE = "private"
    SCOPED_CLIENT = "scoped_client"
    SCOPED_WORK = "scoped_work"


def _normalize_project_token(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value or "").strip().lower()
    return str(value or "").strip().lower()


def normalize_project_status(value: Any) -> str:
    parsed = parse_project_status(value)
    return parsed.value if parsed is not None else _normalize_project_token(value)


def parse_project_status(value: Any) -> ProjectStatus | None:
    parsed = _parse_project_enum(value, ProjectStatus)
    return parsed if isinstance(parsed, ProjectStatus) else None


def _parse_project_enum(value: Any, enum_type: type[Enum]) -> Enum | None:
    normalized = _normalize_project_token(value)
    for member in enum_type:
        if member.value == normalized:
            return member
    return None


def parse_project_kind(value: Any) -> ProjectKind | None:
    parsed = _parse_project_enum(value, ProjectKind)
    return parsed if isinstance(parsed, ProjectKind) else None


def normalize_project_kind(value: Any) -> str:
    parsed = parse_project_kind(value)
    return parsed.value if parsed is not None else _normalize_project_token(value)


def parse_project_lane(value: Any) -> ProjectLane | None:
    parsed = _parse_project_enum(value, ProjectLane)
    return parsed if isinstance(parsed, ProjectLane) else None


def normalize_project_lane(value: Any) -> str:
    parsed = parse_project_lane(value)
    return parsed.value if parsed is not None else _normalize_project_token(value)


def parse_project_visibility(value: Any) -> ProjectVisibility | None:
    parsed = _parse_project_enum(value, ProjectVisibility)
    return parsed if isinstance(parsed, ProjectVisibility) else None


def normalize_project_visibility(value: Any) -> str:
    parsed = parse_project_visibility(value)
    return parsed.value if parsed is not None else _normalize_project_token(value)


def parse_project_status_strict(value: Any) -> ProjectStatus:
    parsed = parse_project_status(value)
    if parsed is None:
        raise ValueError(f"project status {value!r} is not in the controlled vocabulary")
    return parsed


def parse_project_kind_strict(value: Any) -> ProjectKind:
    parsed = parse_project_kind(value)
    if parsed is None:
        raise ValueError(f"project kind {value!r} is not in the controlled vocabulary")
    return parsed


def parse_project_lane_strict(value: Any) -> ProjectLane:
    parsed = parse_project_lane(value)
    if parsed is None:
        raise ValueError(f"project lane {value!r} is not in the controlled vocabulary")
    return parsed


def parse_project_visibility_strict(value: Any) -> ProjectVisibility:
    parsed = parse_project_visibility(value)
    if parsed is None:
        raise ValueError(
            f"project visibility {value!r} is not in the controlled vocabulary"
        )
    return parsed
