from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from domain.cast import CastEntity
from domain.projects.catalog import (
    normalize_project_kind,
    normalize_project_lane,
    normalize_project_status,
    normalize_project_visibility,
)
from domain.projects import (
    GraphEdge,
    Project,
    ProjectGraphRole,
    ProjectSnapshotIdentity,
    SemanticReference,
    SemanticReferenceKind,
    parse_project_snapshot_identity,
)
from formats.markdown_records import (
    extract_markdown_bullet_values,
    parse_markdown_record_fields,
)


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _coerce_strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return tuple(part for part in parts if part)
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _text_contains_any(text: str, tokens: Sequence[str]) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    return any(token in normalized for token in tokens)


def _project_entity_semantic_terms(
    entity: CastEntity, project_text: str
) -> tuple[str, ...]:
    """Intentionally empty; loaders must not invent project-involvement
    aliases. Typed alias_terms on the canonical entity are the only
    truth the project loader may rely on."""

    _ = entity, project_text
    return ()


def _first_bullet_value(body: str, key: str) -> str:
    values = extract_markdown_bullet_values(body, key)
    return values[0] if values else ""


def _extract_project_start_date(
    raw: Mapping[str, object],
    body: str,
    *,
    snapshot_identity: ProjectSnapshotIdentity | None = None,
) -> str | None:
    for key in ("start_date", "started_on", "created_on", "project_started_on"):
        value = str(raw.get(key) or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return value
        for candidate in extract_markdown_bullet_values(body, key):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
                return candidate
    return (snapshot_identity or ProjectSnapshotIdentity()).authorized_start_date()


def _extract_project_metadata_value(
    raw: Mapping[str, object],
    body: str,
    *keys: str,
) -> str:
    for key in keys:
        value = str(raw.get(key) or "").strip()
        if value:
            return value
        candidate = _first_bullet_value(body, key)
        if candidate:
            return candidate
    return ""


def _coerce_graph_edges(value: object) -> tuple[GraphEdge, ...]:
    edges: list[GraphEdge] = []
    if not isinstance(value, (list, tuple)):
        return ()
    for item in value:
        if isinstance(item, GraphEdge):
            edges.append(item)
            continue
        if not isinstance(item, Mapping):
            continue
        raw_role = str(item.get("role") or "").strip() or ProjectGraphRole.LINKED_ENTITY.value
        try:
            role = ProjectGraphRole(raw_role)
        except ValueError:
            continue
        reference_payload = item.get("reference")
        if isinstance(reference_payload, SemanticReference):
            edges.append(GraphEdge(role=role, reference=reference_payload))
            continue
        if not isinstance(reference_payload, Mapping):
            continue
        raw_kind = (
            str(reference_payload.get("target_kind") or "").strip()
            or SemanticReferenceKind.ENTITY.value
        )
        try:
            target_kind = SemanticReferenceKind(raw_kind)
        except ValueError:
            continue
        target_id = str(reference_payload.get("target_id") or "").strip()
        if not target_id:
            continue
        edges.append(
            GraphEdge(
                role=role,
                reference=SemanticReference(
                    target_kind=target_kind,
                    target_id=target_id,
                    title=str(reference_payload.get("title") or "").strip(),
                    path=str(reference_payload.get("path") or "").strip(),
                ),
            )
        )
    return tuple(edges)


def project_from_mapping(raw: Mapping[str, object]) -> Project | None:
    raw_body = str(raw.get("body") or "")
    record_fields = parse_markdown_record_fields(raw_body)
    frontmatter = record_fields.fields
    body = record_fields.body.strip()
    path = str(raw.get("path") or "").strip()
    snapshot_identity = parse_project_snapshot_identity(
        raw.get("snapshot_root"),
        raw.get("project_path"),
    )
    title = str(
        raw.get("title")
        or frontmatter.get("title")
        or raw.get("project_name")
        or frontmatter.get("project_name")
        or ""
    ).strip()
    if not path or not title:
        return None
    status = str(raw.get("status") or frontmatter.get("status") or "").strip()
    alias = str(raw.get("alias") or frontmatter.get("alias") or "").strip()
    kind = normalize_project_kind(raw.get("kind") or frontmatter.get("kind"))
    lane = normalize_project_lane(raw.get("lane") or frontmatter.get("lane"))
    goal = str(raw.get("goal") or frontmatter.get("goal") or "").strip()
    next_step = str(raw.get("next_step") or frontmatter.get("next_step") or "").strip()
    merged_raw = dict(frontmatter)
    merged_raw.update(dict(raw))
    priority = _extract_project_metadata_value(merged_raw, body, "priority")
    visibility = normalize_project_visibility(
        _extract_project_metadata_value(merged_raw, body, "visibility")
    )
    updated_on = _extract_project_metadata_value(merged_raw, body, "updated_on", "updated on")
    owner_ids = (*_coerce_strings(frontmatter.get("owner_id")), *_coerce_strings(raw.get("owner_id")))
    linked_entities = (*_coerce_strings(frontmatter.get("linked_entities")), *_coerce_strings(raw.get("linked_entities")))
    participants = (*_coerce_strings(frontmatter.get("participants")), *_coerce_strings(raw.get("participants")))
    graph_edges = _coerce_graph_edges(raw.get("graph_edges"))
    descriptor_aliases = tuple(
        dict.fromkeys(
            alias
            for alias in _coerce_strings(raw.get("descriptor_aliases"))
            if str(alias).strip()
        )
    )
    alias_terms = tuple(
        dict.fromkeys(
            alias
            for alias in project_alias_terms(merged_raw)
            if str(alias).strip()
        )
    )
    start_date = str(
        raw.get("start_date")
        or frontmatter.get("start_date")
        or raw.get("started_on")
        or frontmatter.get("started_on")
        or raw.get("created_on")
        or frontmatter.get("created_on")
        or raw.get("project_started_on")
        or frontmatter.get("project_started_on")
        or ""
    ).strip()
    explicit_start_date = (
        start_date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_date) else None
    )
    resolved_start_date = (
        explicit_start_date
        if explicit_start_date is not None
        else snapshot_identity.authorized_start_date()
    )
    return Project(
        path=path,
        title=title,
        status=normalize_project_status(status),
        project_name=str(raw.get("project_name") or frontmatter.get("project_name") or "").strip(),
        alias=alias,
        kind=kind,
        lane=lane,
        goal=goal,
        next_step=next_step,
        body=body,
        alias_terms=alias_terms,
        descriptor_aliases=descriptor_aliases,
        owner_ids=tuple(dict.fromkeys(term for term in owner_ids if str(term).strip())),
        linked_entities=tuple(
            dict.fromkeys(term for term in linked_entities if str(term).strip())
        ),
        participants=tuple(
            dict.fromkeys(term for term in participants if str(term).strip())
        ),
        graph_edges=graph_edges,
        involvement_terms=tuple(
            dict.fromkeys(
                term
                for term in (
                    *_coerce_strings(frontmatter.get("entity_search_terms")),
                    *_coerce_strings(raw.get("entity_search_terms")),
                    *(
                        ()
                        if graph_edges
                        else (
                            *_coerce_strings(frontmatter.get("linked_entities")),
                            *_coerce_strings(raw.get("linked_entities")),
                            *_coerce_strings(frontmatter.get("participants")),
                            *_coerce_strings(raw.get("participants")),
                            *_coerce_strings(frontmatter.get("owner_id")),
                            *_coerce_strings(raw.get("owner_id")),
                        )
                    ),
                )
                if str(term).strip()
            )
        ),
        snapshot_identity=snapshot_identity,
        start_date=resolved_start_date,
        explicit_start_date=explicit_start_date,
        priority=priority,
        visibility=visibility,
        updated_on=updated_on
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", updated_on)
        else None,
    )


def projects_from_mappings(
    raw_records: Sequence[Mapping[str, object]],
) -> tuple[Project, ...]:
    return tuple(
        project
        for project in (project_from_mapping(raw) for raw in raw_records)
        if project is not None
    )


def project_to_mapping(project: Project) -> dict[str, object]:
    payload: dict[str, object] = {
        "path": project.path,
        "title": project.title,
        "project_name": project.project_name,
        "status": project.status,
        "alias": project.alias,
        "kind": project.kind,
        "lane": project.lane,
        "goal": project.goal,
        "next_step": project.next_step,
        "body": project.body,
        "alias_terms": project.alias_terms,
        "descriptor_aliases": project.descriptor_aliases,
        "owner_id": project.owner_ids,
        "linked_entities": project.linked_entities,
        "participants": project.participants,
        "graph_edges": tuple(
            {
                "role": edge.role.value,
                "reference": {
                    "target_kind": edge.reference.target_kind.value,
                    "target_id": edge.reference.target_id,
                    "title": edge.reference.title,
                    "path": edge.reference.path,
                },
            }
            for edge in project.graph_edges
        ),
        "snapshot_root": project.snapshot_identity.root_path,
        "snapshot_slug": project.snapshot_identity.snapshot_slug,
        "snapshot_date": project.snapshot_identity.snapshot_date or "",
        "entity_search_terms": project.involvement_terms,
    }
    if project.start_date:
        payload["start_date"] = project.start_date
    if project.priority:
        payload["priority"] = project.priority
    if project.visibility:
        payload["visibility"] = project.visibility
    if project.updated_on:
        payload["updated_on"] = project.updated_on
    return payload


def _prepare_project_payload(raw: Mapping[str, object]) -> dict[str, object]:
    body = str(raw.get("body") or "")
    payload: dict[str, object] = dict(raw)
    for key in (
        "status",
        "alias",
        "kind",
        "lane",
        "goal",
        "next_step",
        "priority",
        "visibility",
        "updated_on",
    ):
        current = str(payload.get(key) or "").strip()
        if not current:
            extracted = _first_bullet_value(body, key)
            if extracted:
                payload[key] = extracted

    owner_ids = [
        *_coerce_strings(raw.get("owner_id")),
        *extract_markdown_bullet_values(body, "owner_id"),
    ]
    linked_entities = [
        *_coerce_strings(raw.get("linked_entities")),
        *extract_markdown_bullet_values(body, "linked_entities"),
    ]
    participants = [
        *_coerce_strings(raw.get("participants")),
        *extract_markdown_bullet_values(body, "participants"),
    ]
    payload["owner_id"] = tuple(dict.fromkeys(term for term in owner_ids if term))
    payload["linked_entities"] = tuple(
        dict.fromkeys(term for term in linked_entities if term)
    )
    payload["participants"] = tuple(
        dict.fromkeys(term for term in participants if term)
    )

    snapshot_identity = parse_project_snapshot_identity(
        raw.get("project_path"),
        raw.get("path"),
    )
    if snapshot_identity.root_path:
        payload["snapshot_root"] = snapshot_identity.root_path
        payload["snapshot_slug"] = snapshot_identity.snapshot_slug
        if snapshot_identity.snapshot_date:
            payload["snapshot_date"] = snapshot_identity.snapshot_date
    explicit_only = _extract_explicit_project_start_date(raw, body)
    if explicit_only:
        payload["start_date"] = explicit_only
    else:
        payload.pop("start_date", None)
    return payload


def _extract_explicit_project_start_date(
    raw: Mapping[str, object],
    body: str,
) -> str | None:
    for key in ("start_date", "started_on", "created_on", "project_started_on"):
        value = str(raw.get(key) or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return value
        for candidate in extract_markdown_bullet_values(body, key):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
                return candidate
    return None


def project_alias_terms(raw: Mapping[str, object]) -> tuple[str, ...]:
    body = str(raw.get("body") or "")
    aliases: list[str] = list(_coerce_strings(raw.get("alias_terms")))
    for field in ("alias", "project_name", "title"):
        aliases.extend(_coerce_strings(raw.get(field)))
    aliases.extend(extract_markdown_bullet_values(body, "alias"))
    aliases.extend(extract_markdown_bullet_values(body, "project_name"))
    return tuple(dict.fromkeys(alias for alias in aliases if str(alias).strip()))
def build_projects(
    raw_records: Sequence[Mapping[str, object]],
    entities: Sequence[CastEntity] = (),
) -> tuple[Project, ...]:
    alias_by_entity_id: dict[str, tuple[str, ...]] = {}
    entity_by_lookup_key: dict[str, CastEntity] = {}
    for entity in entities:
        aliases = tuple(
            str(alias).strip()
            for alias in entity.stable_identity_terms
            if str(alias).strip()
        )
        if not aliases:
            continue
        for key in (entity.entity_id.strip(), entity.entity_slug.strip()):
            if key:
                alias_by_entity_id[key] = aliases
        for key in (
            entity.entity_id,
            entity.entity_slug,
            entity.title,
            *entity.stable_identity_terms,
        ):
            normalized_key = _normalize_text(key)
            if normalized_key:
                entity_by_lookup_key[normalized_key] = entity

    projects: list[Project] = []
    for raw in raw_records:
        payload = _prepare_project_payload(raw)
        body = str(raw.get("body") or "")
        alias_terms = tuple(
            dict.fromkeys(project_alias_terms(raw))
        )
        if alias_terms:
            payload["alias_terms"] = alias_terms
        descriptor_aliases = tuple(
            dict.fromkeys(
                _coerce_strings(payload.get("descriptor_aliases"))
            )
        )
        if descriptor_aliases:
            payload["descriptor_aliases"] = descriptor_aliases

        owner_ids = list(_coerce_strings(payload.get("owner_id")))
        linked_entities = list(_coerce_strings(payload.get("linked_entities")))
        participants = list(_coerce_strings(payload.get("participants")))

        graph_edges: list[GraphEdge] = []
        search_terms: list[str] = []
        project_text = " ".join(
            str(value).strip()
            for value in (
                payload.get("title"),
                payload.get("project_name"),
                payload.get("alias"),
                payload.get("kind"),
                payload.get("lane"),
                payload.get("goal"),
                payload.get("next_step"),
                body,
            )
            if str(value or "").strip()
        )
        for role, raw_values in (
            (ProjectGraphRole.OWNER, owner_ids),
            (ProjectGraphRole.LINKED_ENTITY, linked_entities),
            (ProjectGraphRole.PARTICIPANT, participants),
        ):
            for raw_key in raw_values:
                normalized_key = _normalize_text(raw_key)
                matched_entity = entity_by_lookup_key.get(normalized_key)
                if matched_entity is None and "." in str(raw_key):
                    matched_entity = entity_by_lookup_key.get(
                        _normalize_text(str(raw_key).split(".", 1)[-1])
                    )
                if matched_entity is None:
                    continue
                canonical_target_id = matched_entity.entity_id.strip() or (
                    f"entity.{matched_entity.entity_slug.strip()}"
                    if matched_entity.entity_slug.strip()
                    else ""
                )
                if not canonical_target_id:
                    continue
                graph_edges.append(
                    GraphEdge(
                        role=role,
                        reference=SemanticReference(
                            target_kind=SemanticReferenceKind.ENTITY,
                            target_id=canonical_target_id,
                            title=matched_entity.title,
                            path=f"/{str(matched_entity.path).lstrip('/')}",
                        ),
                    )
                )
                for lookup_key in (
                    canonical_target_id,
                    matched_entity.entity_slug.strip(),
                ):
                    aliases = alias_by_entity_id.get(lookup_key)
                    if aliases:
                        search_terms.extend(aliases)
                search_terms.extend(
                    (
                        canonical_target_id,
                        matched_entity.title,
                        *_project_entity_semantic_terms(matched_entity, project_text),
                    )
                )

        if not graph_edges:
            search_terms.extend((*owner_ids, *linked_entities, *participants))

        unique_search_terms = tuple(
            dict.fromkeys(term for term in search_terms if term)
        )
        if graph_edges:
            payload["graph_edges"] = tuple(dict.fromkeys(graph_edges))
        if unique_search_terms:
            payload["entity_search_terms"] = unique_search_terms

        project = project_from_mapping(payload)
        if project is not None:
            projects.append(project)

    return tuple(projects)
