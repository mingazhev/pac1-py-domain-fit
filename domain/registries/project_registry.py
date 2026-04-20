from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from domain.projects.graph import ProjectGraphRole, SemanticReferenceKind
from domain.projects.status_policy import project_identity_key
from domain.projects.project import Project


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _freeze_single(mapping: dict[str, Project]) -> Mapping[str, Project]:
    return MappingProxyType(dict(mapping))


def _freeze_multi(
    mapping: dict[str, list[Project]],
) -> Mapping[str, tuple[Project, ...]]:
    return MappingProxyType({key: tuple(values) for key, values in mapping.items()})


@dataclass(frozen=True, slots=True)
class ProjectRegistry:
    """Explicit read-model index over a canonical ``Project`` collection.

    Provides two seams Phase 9 calls out explicitly:

    - forward index: canonical identity key / path / alias term → project
    - reverse index: ``SemanticReference`` target id → projects that reference
      it, split by graph role (owner / linked_entity / participant). This is
      the cross-entity-resolution gap the phase narrows.
    """

    projects: tuple[Project, ...]
    _by_identity_key: Mapping[str, Project] = field(repr=False)
    _by_path: Mapping[str, Project] = field(repr=False)
    _by_alias_term: Mapping[str, tuple[Project, ...]] = field(repr=False)
    _reverse_role_index: Mapping[
        ProjectGraphRole, Mapping[str, tuple[Project, ...]]
    ] = field(repr=False)
    _reverse_any_role_index: Mapping[str, tuple[Project, ...]] = field(repr=False)

    @classmethod
    def build(cls, projects: Iterable[Project]) -> ProjectRegistry:
        project_tuple = tuple(projects)

        by_identity: dict[str, Project] = {}
        by_path: dict[str, Project] = {}
        by_alias: dict[str, list[Project]] = {}
        role_buckets: dict[ProjectGraphRole, dict[str, list[Project]]] = {
            role: {} for role in ProjectGraphRole
        }
        any_role_bucket: dict[str, list[Project]] = {}

        for project in project_tuple:
            identity_key = project_identity_key(project)
            if identity_key and identity_key not in by_identity:
                by_identity[identity_key] = project
            path_key = _normalize(project.path)
            if path_key and path_key not in by_path:
                by_path[path_key] = project
            for term in (project.title, project.project_name, project.alias, *project.alias_terms):
                alias_key = _normalize(term)
                if not alias_key:
                    continue
                by_alias.setdefault(alias_key, []).append(project)

            for edge in project.graph_edges:
                if edge.reference.target_kind is not SemanticReferenceKind.ENTITY:
                    continue
                target_key = _normalize(edge.reference.target_id)
                if not target_key:
                    continue
                role_buckets[edge.role].setdefault(target_key, []).append(project)
                any_role_bucket.setdefault(target_key, []).append(project)

            for owner_id in project.owner_ids:
                normalized = _normalize(owner_id)
                if normalized and project not in role_buckets[ProjectGraphRole.OWNER].get(
                    normalized, []
                ):
                    role_buckets[ProjectGraphRole.OWNER].setdefault(normalized, []).append(project)
                    any_role_bucket.setdefault(normalized, []).append(project)
            for linked in project.linked_entities:
                normalized = _normalize(linked)
                if normalized and project not in role_buckets[
                    ProjectGraphRole.LINKED_ENTITY
                ].get(normalized, []):
                    role_buckets[ProjectGraphRole.LINKED_ENTITY].setdefault(
                        normalized, []
                    ).append(project)
                    any_role_bucket.setdefault(normalized, []).append(project)
            for participant in project.participants:
                normalized = _normalize(participant)
                if normalized and project not in role_buckets[
                    ProjectGraphRole.PARTICIPANT
                ].get(normalized, []):
                    role_buckets[ProjectGraphRole.PARTICIPANT].setdefault(
                        normalized, []
                    ).append(project)
                    any_role_bucket.setdefault(normalized, []).append(project)

        frozen_reverse = MappingProxyType(
            {role: _freeze_multi(bucket) for role, bucket in role_buckets.items()}
        )
        frozen_any_reverse = _freeze_multi(
            {key: list(dict.fromkeys(values)) for key, values in any_role_bucket.items()}
        )

        return cls(
            projects=project_tuple,
            _by_identity_key=_freeze_single(by_identity),
            _by_path=_freeze_single(by_path),
            _by_alias_term=_freeze_multi(by_alias),
            _reverse_role_index=frozen_reverse,
            _reverse_any_role_index=frozen_any_reverse,
        )

    def __iter__(self):
        return iter(self.projects)

    def __len__(self) -> int:
        return len(self.projects)

    def by_identity_key(self, identity_key: str) -> Project | None:
        return self._by_identity_key.get(_normalize(identity_key))

    def by_path(self, path: str) -> Project | None:
        return self._by_path.get(_normalize(path))

    def by_alias_term(self, term: str) -> tuple[Project, ...]:
        return self._by_alias_term.get(_normalize(term), ())

    def projects_for_entity(
        self,
        entity_id: str,
        *,
        role: ProjectGraphRole | None = None,
    ) -> tuple[Project, ...]:
        """Reverse index: projects that reference a given entity.

        Accepts any identity term the project graph edges or legacy id lists
        actually record: canonical entity id, slug, alias, display name. With
        no ``role``, returns the union across owner/linked/participant roles.
        """

        key = _normalize(entity_id)
        if not key:
            return ()
        if role is None:
            return self._reverse_any_role_index.get(key, ())
        return self._reverse_role_index[role].get(key, ())

    def all_identity_keys(self) -> tuple[str, ...]:
        return tuple(self._by_identity_key)

    def projects_for_any_of(self, entity_ids: Sequence[str]) -> tuple[Project, ...]:
        seen: set[str] = set()
        ordered: list[Project] = []
        for entity_id in entity_ids:
            for project in self.projects_for_entity(entity_id):
                path_key = _normalize(project.path) or project_identity_key(project)
                if path_key in seen:
                    continue
                seen.add(path_key)
                ordered.append(project)
        return tuple(ordered)


__all__ = ["ProjectRegistry"]
