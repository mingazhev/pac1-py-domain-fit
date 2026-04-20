"""Project Catalog bounded context."""

from .catalog import (
    ProjectKind,
    ProjectLane,
    ProjectStatus,
    ProjectVisibility,
    normalize_project_kind,
    normalize_project_lane,
    normalize_project_status,
    normalize_project_visibility,
    parse_project_kind,
    parse_project_kind_strict,
    parse_project_lane,
    parse_project_lane_strict,
    parse_project_status,
    parse_project_status_strict,
    parse_project_visibility,
    parse_project_visibility_strict,
)
from .deletion import (
    ProjectCompareDeleteResolution,
    project_directory_delete_root,
    project_readme_delete_root,
    project_record_root_path,
    resolve_project_compare_delete_resolution,
)
from .graph import GraphEdge, ProjectGraphRole, SemanticReference, SemanticReferenceKind
from .involvement import (
    resolve_project_involvement_matches,
)
from .project import Project
from .projections import (
    ProjectGroundingProjection,
    ProjectIdentityProjection,
    ProjectPropertyConsensusProjection,
    project_grounding_projection,
    project_identity_projection_from_record,
    resolve_project_property,
)
from .snapshot import (
    ProjectSnapshotIdentity,
    ProjectVersionIdentity,
    build_project_version_identity,
    parse_project_snapshot_identity,
)
from .status_policy import (
    project_identity_key,
    project_status_priority,
    select_canonical_project,
)
from .visibility import VisibilityPolicy, resolve_visibility_policy

__all__ = [
    "GraphEdge",
    "Project",
    "ProjectCompareDeleteResolution",
    "ProjectGraphRole",
    "ProjectGroundingProjection",
    "ProjectKind",
    "ProjectLane",
    "ProjectIdentityProjection",
    "ProjectPropertyConsensusProjection",
    "ProjectSnapshotIdentity",
    "ProjectStatus",
    "ProjectVersionIdentity",
    "ProjectVisibility",
    "SemanticReference",
    "SemanticReferenceKind",
    "VisibilityPolicy",
    "build_project_version_identity",
    "normalize_project_kind",
    "normalize_project_lane",
    "normalize_project_status",
    "normalize_project_visibility",
    "parse_project_kind",
    "parse_project_kind_strict",
    "parse_project_lane",
    "parse_project_lane_strict",
    "parse_project_snapshot_identity",
    "parse_project_status",
    "parse_project_status_strict",
    "parse_project_visibility",
    "parse_project_visibility_strict",
    "project_grounding_projection",
    "project_directory_delete_root",
    "project_identity_key",
    "project_readme_delete_root",
    "project_record_root_path",
    "project_status_priority",
    "project_identity_projection_from_record",
    "resolve_project_compare_delete_resolution",
    "resolve_project_involvement_matches",
    "resolve_project_property",
    "resolve_visibility_policy",
    "select_canonical_project",
]
