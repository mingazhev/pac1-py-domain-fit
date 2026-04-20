from __future__ import annotations

from application.ports import QueryResolutionPort
from application.resolvers import resolve_project_identity_projection
from domain.cast import resolve_cast_identity
from domain.finance import FinanceRecord
from task_routing import (
    CastResolverSet,
    ProjectResolverSet,
    resolve_entity_candidate,
    resolve_message_entity_candidate,
    resolve_project_candidate,
    resolve_project_subject_candidate,
)


def _cast_record_identity_keys(record: dict[str, object]) -> set[str]:
    keys: set[str] = set()
    for field_name in (
        "path",
        "title",
        "entity_slug",
        "entity_id",
        "primary_contact_email",
        "email",
        "alias",
        "relationship",
    ):
        value = str(record.get(field_name) or "").strip().lower()
        if value:
            keys.add(value)
    for field_name in ("identity_terms", "alias_terms", "relationship_alias_terms"):
        raw = record.get(field_name) or ()
        if isinstance(raw, (list, tuple)):
            for item in raw:
                value = str(item or "").strip().lower()
                if value:
                    keys.add(value)
    return keys


def _derive_finance_counterparties_for_cast_records(
    cast_records: list[dict[str, object]],
    finance_records: tuple[FinanceRecord, ...],
) -> list[dict[str, object]]:
    if not cast_records or not finance_records:
        return cast_records
    counterparties_by_index: dict[int, set[str]] = {}
    identity_keys = [_cast_record_identity_keys(record) for record in cast_records]
    for finance_record in finance_records:
        related_entity = str(getattr(finance_record, "related_entity", "") or "").strip().lower()
        counterparty = str(getattr(finance_record, "counterparty", "") or "").strip()
        if not related_entity or not counterparty:
            continue
        for index, record_keys in enumerate(identity_keys):
            if related_entity not in record_keys:
                continue
            counterparties_by_index.setdefault(index, set()).add(counterparty)
    if not counterparties_by_index:
        return cast_records
    enriched: list[dict[str, object]] = []
    for index, record in enumerate(cast_records):
        counterparties = counterparties_by_index.get(index)
        if not counterparties:
            enriched.append(record)
            continue
        updated = dict(record)
        updated["finance_counterparties"] = tuple(sorted(counterparties))
        enriched.append(updated)
    return enriched


def _projection_project_resolver(project_records, query):
    from loaders.projects import projects_from_mappings

    typed_records = projects_from_mappings(project_records)
    projection = resolve_project_identity_projection(typed_records, query)
    if projection is None:
        return None
    path = str(projection.path or "").strip()
    title = str(projection.title or "").strip()
    alias = str(projection.alias or "").strip()
    for record in project_records:
        if path and str(record.get("path") or "").strip() == path:
            return dict(record)
        if alias and str(record.get("alias") or "").strip() == alias:
            return dict(record)
        if title and str(record.get("title") or "").strip() == title:
            return dict(record)
    return None

def _projection_cast_resolver(cast_records, query):
    from loaders.cast import cast_entities_from_mappings

    typed_records = cast_entities_from_mappings(cast_records)
    projection = resolve_cast_identity(typed_records, query)
    if projection is None:
        return None
    path = str(projection.path or "").strip()
    entity_slug = str(projection.entity_slug or "").strip()
    entity_id = str(projection.entity_id or "").strip()
    for record in cast_records:
        if path and str(record.get("path") or "").strip() == path:
            return dict(record)
        if entity_slug and str(record.get("entity_slug") or "").strip() == entity_slug:
            return dict(record)
        if entity_id and str(record.get("entity_id") or "").strip() == entity_id:
            return dict(record)
    return None


def build_cast_resolvers(
    gateway: object | None,
    model: str | None,
    *,
    finance_records: tuple[FinanceRecord, ...] = (),
) -> CastResolverSet:
    if gateway is not None and model:
        from task_routing.record_selector import llm_resolve_cast_record

        def _llm_cast(cast_records, query):
            enriched_records = _derive_finance_counterparties_for_cast_records(
                [dict(record) for record in cast_records],
                finance_records,
            )
            return llm_resolve_cast_record(
                gateway,
                model,
                enriched_records,
                query,
                accept_confidence=frozenset({"high", "medium", "low"}),
            )

        llm_resolver = _llm_cast
    else:
        llm_resolver = lambda *_args, **_kwargs: None  # noqa: E731
    return CastResolverSet(
        exact_resolve=_projection_cast_resolver,
        llm_resolve=llm_resolver,
    )


def build_project_resolvers(
    gateway: object | None, model: str | None
) -> ProjectResolverSet:
    if gateway is not None and model:
        from task_routing.record_selector import llm_resolve_project_record

        def _llm_project(project_records, query):
            return llm_resolve_project_record(
                gateway,
                model,
                project_records,
                query,
                accept_confidence=frozenset({"high", "medium", "low"}),
            )

        llm_resolver = _llm_project
    else:
        llm_resolver = lambda *_args, **_kwargs: None  # noqa: E731

    return ProjectResolverSet(
        exact_resolve=_projection_project_resolver,
        llm_resolve=llm_resolver,
    )


def build_query_resolution_port(
    cast_resolvers: CastResolverSet,
    project_resolvers: ProjectResolverSet,
) -> QueryResolutionPort:
    def _resolve_entity_candidate(
        cast_records,
        lookup_text: str,
        fallback_text: str,
        self_reference: bool = False,
    ) -> dict[str, object] | None:
        return resolve_entity_candidate(
            [dict(record) for record in cast_records],
            lookup_text=lookup_text,
            fallback_text=fallback_text,
            self_reference=self_reference,
            resolvers=cast_resolvers,
        )

    def _resolve_message_entity_candidate(
        cast_records,
        entity_query: str,
        fallback_text: str,
    ) -> dict[str, object] | None:
        return resolve_message_entity_candidate(
            [dict(record) for record in cast_records],
            entity_query=entity_query,
            fallback_text=fallback_text,
            resolvers=cast_resolvers,
        )

    def _resolve_project_subject_candidate(
        cast_records,
        task_text: str,
        lookup_text: str,
    ) -> dict[str, object] | None:
        return resolve_project_subject_candidate(
            [dict(record) for record in cast_records],
            task_text=task_text,
            lookup_text=lookup_text,
            resolvers=cast_resolvers,
        )

    def _resolve_project_candidate(
        project_records,
        lookup_text: str,
        task_text: str,
    ) -> dict[str, object] | None:
        return resolve_project_candidate(
            [dict(record) for record in project_records],
            lookup_text=lookup_text,
            task_text=task_text,
            resolvers=project_resolvers,
        )

    return QueryResolutionPort(
        resolve_entity_candidate=_resolve_entity_candidate,
        resolve_message_entity_candidate=_resolve_message_entity_candidate,
        resolve_project_subject_candidate=_resolve_project_subject_candidate,
        resolve_project_candidate=_resolve_project_candidate,
    )


__all__ = [
    "build_cast_resolvers",
    "build_project_resolvers",
    "build_query_resolution_port",
]
