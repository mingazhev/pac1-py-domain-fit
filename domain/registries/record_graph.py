from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from domain.cast.cast_entity import CastEntity
from domain.finance.finance_record import FinanceRecord
from domain.projects.graph import ProjectGraphRole
from domain.projects.project import Project

from .cast_registry import CastRegistry
from .contact_registry import ContactRegistry
from .finance_registry import FinanceRegistry
from .project_registry import ProjectRegistry


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


@dataclass(frozen=True, slots=True)
class CrossContextRecordGraph:
    """Cross-registry join surface.

    Owns the explicit traversal edges between bounded contexts:

    - entity -> projects (owner / linked_entity / participant)
    - entity -> finance records (via related_entity display name)
    - project -> finance records (via project display name)

    Callers that previously re-looped over flat sequences to answer "which
    projects involve person X" or "which invoices mention project Y" go
    through this graph and rely on the pre-built reverse indexes each
    registry already owns.
    """

    cast: CastRegistry
    projects: ProjectRegistry
    finance: FinanceRegistry
    contacts: ContactRegistry

    @classmethod
    def build(
        cls,
        *,
        entities: Iterable[CastEntity] = (),
        projects: Iterable[Project] = (),
        finance_records: Iterable[FinanceRecord] = (),
    ) -> CrossContextRecordGraph:
        cast = CastRegistry.build(entities)
        project_registry = ProjectRegistry.build(projects)
        finance_registry = FinanceRegistry.build(finance_records)
        contacts = ContactRegistry.from_cast_registry(cast)
        return cls(
            cast=cast,
            projects=project_registry,
            finance=finance_registry,
            contacts=contacts,
        )

    def projects_for_entity(
        self,
        entity_id: str,
        *,
        role: ProjectGraphRole | None = None,
    ) -> tuple[Project, ...]:
        return self.projects.projects_for_entity(entity_id, role=role)

    def finance_records_for_entity(self, entity: CastEntity | str) -> tuple[FinanceRecord, ...]:
        """Finance records that reference the entity via display name.

        The primary reconciliation path is the cast title. Entity ids are also
        accepted so callers can hand the graph whatever identifier they hold.
        """

        display_names: list[str] = []
        if isinstance(entity, CastEntity):
            display_names.append(entity.title)
            display_names.extend(entity.alias_terms)
        else:
            resolved = self.cast.by_entity_id(entity) or self.cast.by_slug(entity)
            if resolved is not None:
                display_names.append(resolved.title)
                display_names.extend(resolved.alias_terms)
            else:
                display_names.append(str(entity))

        seen: set[str] = set()
        results: list[FinanceRecord] = []
        for name in display_names:
            for record in self.finance.records_for_related_entity(name):
                path_key = _normalize(record.path)
                if path_key and path_key in seen:
                    continue
                seen.add(path_key)
                results.append(record)
        return tuple(results)

    def finance_records_for_project(self, project: Project | str) -> tuple[FinanceRecord, ...]:
        if isinstance(project, Project):
            names = (project.project_name, project.title, project.alias)
        else:
            resolved = self.projects.by_identity_key(project) or self.projects.by_path(project)
            if resolved is not None:
                names = (resolved.project_name, resolved.title, resolved.alias)
            else:
                names = (str(project),)

        seen: set[str] = set()
        results: list[FinanceRecord] = []
        for name in names:
            for record in self.finance.records_for_project(name):
                path_key = _normalize(record.path)
                if path_key and path_key in seen:
                    continue
                seen.add(path_key)
                results.append(record)
        return tuple(results)


__all__ = ["CrossContextRecordGraph"]
