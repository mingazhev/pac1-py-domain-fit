from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

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
from .graph import GraphEdge, ProjectGraphRole, SemanticReference
from .snapshot import (
    ProjectSnapshotIdentity,
    ProjectVersionIdentity,
    build_project_version_identity,
)
from .visibility import VisibilityPolicy, resolve_visibility_policy


GENERIC_INVOLVEMENT_ROLE_TOKENS = {
    "advisor",
    "client",
    "friend",
    "lead",
    "manager",
    "partner",
    "server",
    "system",
}


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


@dataclass(frozen=True, slots=True)
class Project:
    path: str
    title: str
    status: str | ProjectStatus = ""
    project_name: str = ""
    alias: str = ""
    kind: str | ProjectKind = ""
    lane: str | ProjectLane = ""
    goal: str = ""
    next_step: str = ""
    body: str = ""
    alias_terms: tuple[str, ...] = ()
    descriptor_aliases: tuple[str, ...] = ()
    owner_ids: tuple[str, ...] = ()
    linked_entities: tuple[str, ...] = ()
    participants: tuple[str, ...] = ()
    graph_edges: tuple[GraphEdge, ...] = ()
    involvement_terms: tuple[str, ...] = ()
    snapshot_identity: ProjectSnapshotIdentity = ProjectSnapshotIdentity()
    start_date: str | None = None
    explicit_start_date: str | None = None
    priority: str = ""
    visibility: str | ProjectVisibility = ""
    updated_on: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", normalize_project_status(self.status))
        object.__setattr__(self, "kind", normalize_project_kind(self.kind))
        object.__setattr__(self, "lane", normalize_project_lane(self.lane))
        object.__setattr__(self, "visibility", normalize_project_visibility(self.visibility))

    @property
    def display_title(self) -> str:
        return self.title or self.project_name

    @property
    def normalized_involvement_terms(self) -> tuple[str, ...]:
        graph_terms = [
            term
            for edge in self.graph_edges
            for term in (
                edge.reference.target_id,
                edge.reference.title,
            )
            if str(term or "").strip()
        ]
        terms = [
            *(graph_terms if self.graph_edges else (*self.owner_ids, *self.linked_entities, *self.participants)),
            *self.involvement_terms,
        ]
        normalized_terms: list[str] = []
        for term in terms:
            normalized_term = _normalize(term)
            if not normalized_term:
                continue
            tokens = tuple(part for part in normalized_term.split(" ") if part)
            if len(tokens) == 1 and tokens[0] in GENERIC_INVOLVEMENT_ROLE_TOKENS:
                continue
            normalized_terms.append(normalized_term)
        return tuple(dict.fromkeys(normalized_terms))

    @property
    def kind_enum(self) -> ProjectKind | None:
        return parse_project_kind(self.kind)

    @property
    def lane_enum(self) -> ProjectLane | None:
        return parse_project_lane(self.lane)

    @property
    def status_enum(self) -> ProjectStatus | None:
        return parse_project_status(self.status)

    @property
    def visibility_enum(self) -> ProjectVisibility | None:
        return parse_project_visibility(self.visibility)

    @property
    def visibility_policy(self) -> VisibilityPolicy:
        return resolve_visibility_policy(self.visibility)

    def require_kind_enum(self) -> ProjectKind:
        return parse_project_kind_strict(self.kind)

    def require_lane_enum(self) -> ProjectLane:
        return parse_project_lane_strict(self.lane)

    def require_status_enum(self) -> ProjectStatus:
        return parse_project_status_strict(self.status)

    def require_visibility_enum(self) -> ProjectVisibility:
        return parse_project_visibility_strict(self.visibility)

    @property
    def has_controlled_kind(self) -> bool:
        return parse_project_kind(self.kind) is not None

    @property
    def has_controlled_lane(self) -> bool:
        return parse_project_lane(self.lane) is not None

    @property
    def has_controlled_visibility(self) -> bool:
        return parse_project_visibility(self.visibility) is not None

    def _typed_references_for(self, role: ProjectGraphRole) -> tuple[SemanticReference, ...]:
        return tuple(edge.reference for edge in self.graph_edges if edge.role is role)

    @property
    def owner_references(self) -> tuple[SemanticReference, ...]:
        return self._typed_references_for(ProjectGraphRole.OWNER)

    @property
    def linked_entity_references(self) -> tuple[SemanticReference, ...]:
        return self._typed_references_for(ProjectGraphRole.LINKED_ENTITY)

    @property
    def participant_references(self) -> tuple[SemanticReference, ...]:
        return self._typed_references_for(ProjectGraphRole.PARTICIPANT)

    @property
    def has_typed_linked_entities(self) -> bool:
        return bool(self.linked_entity_references)

    @property
    def version_identity(self) -> ProjectVersionIdentity:
        explicit = self.explicit_start_date
        if explicit is None and self.start_date and (
            self.snapshot_identity.snapshot_date is None
            or self.start_date != self.snapshot_identity.snapshot_date
        ):
            explicit = self.start_date
        return build_project_version_identity(
            explicit_start_date=explicit,
            snapshot_identity=self.snapshot_identity,
        )

    @property
    def authoritative_start_date(self) -> str | None:
        return self.version_identity.authoritative_start_date

    @property
    def has_authoritative_start_date(self) -> bool:
        return self.version_identity.is_authoritative

    @property
    def snapshot_version_marker(self) -> str | None:
        return self.snapshot_identity.snapshot_date

    @property
    def start_date_is_snapshot_derived(self) -> bool:
        if not self.start_date:
            return False
        if self.explicit_start_date is not None:
            return False
        return (
            self.snapshot_identity.snapshot_date is not None
            and self.start_date == self.snapshot_identity.snapshot_date
        )

    def has_status(self, status: ProjectStatus | str) -> bool:
        normalized = (
            status.value
            if isinstance(status, ProjectStatus)
            else normalize_project_status(status)
        )
        return self.status == normalized

    def involves_any_term(self, candidate_terms: Sequence[str]) -> bool:
        searchable = set(self.normalized_involvement_terms)
        return any(term in searchable for term in candidate_terms if term)
