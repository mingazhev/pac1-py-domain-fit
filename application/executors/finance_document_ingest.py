from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from application.contracts import FinanceDocumentIngestRequest
from application.resolvers import (
    finance_document_matches_family_reference,
    select_finance_documents_by_family_reference,
)
from domain.cast import CastEntity
from domain.cast import resolve_cast_identity
from domain.finance import FinanceRecord
from domain.inbox.finance_workflows import select_finance_documents_for_entity


_MAX_BULK_ENTITY_INGEST_TARGETS = 4


@dataclass(frozen=True, slots=True)
class FinanceDocumentIngestPlan:
    status: str
    message: str
    reason_code: str
    target_paths: tuple[str, ...] = ()
    grounding_refs: tuple[str, ...] = ()


def resolve_finance_document_ingest_workflow(
    *,
    request: FinanceDocumentIngestRequest,
    finance_records: Sequence[FinanceRecord],
    cast_entities: Sequence[CastEntity],
    select_finance_record_subset: Callable[[str, Sequence[FinanceRecord]], tuple[int, ...]] | None = None,
    resolve_cast_identity_subset: Callable[[str, Sequence[CastEntity]], object | None] | None = None,
) -> FinanceDocumentIngestPlan:
    explicit_paths = tuple(
        _normalize_path(path) for path in request.target_paths if _normalize_path(path)
    )
    if explicit_paths:
        explicit_paths = _narrow_explicit_paths_by_family_reference(
            explicit_paths,
            family_reference=request.family_reference,
            finance_records=finance_records,
            select_finance_record_subset=select_finance_record_subset,
        )
        if _has_explicit_path_collision(
            request.target_paths,
            finance_records=finance_records,
        ):
            return FinanceDocumentIngestPlan(
                status="clarify_missing",
                message=(
                    "Finance document ingest workflow could not normalize the "
                    "explicit finance note list into a unique canonical target "
                    "set; clarify the exact note paths before rewriting metadata."
                ),
                reason_code="finance_document_ingest_targets_ambiguous",
                grounding_refs=explicit_paths,
            )
        return FinanceDocumentIngestPlan(
            status="resolved",
            message="Prepared explicit finance document ingest targets.",
            reason_code="finance_document_ingest_targets_resolved",
            target_paths=explicit_paths,
            grounding_refs=explicit_paths,
        )
    entity_query = str(request.entity_query or "").strip()
    if not entity_query:
        return FinanceDocumentIngestPlan(
            status="clarify_missing",
            message=(
                "Finance document ingest workflow needs explicit finance note "
                "paths or an entity-scoped target."
            ),
            reason_code="finance_document_ingest_target_missing",
        )
    entity = resolve_cast_identity(cast_entities, entity_query)
    if entity is None and resolve_cast_identity_subset is not None:
        entity = resolve_cast_identity_subset(entity_query, cast_entities)
    if entity is None:
        return FinanceDocumentIngestPlan(
            status="clarify_missing",
            message=(
                "Finance document ingest workflow could not resolve the "
                "requested entity."
            ),
            reason_code="finance_document_ingest_entity_unresolved",
        )
    matched = select_finance_documents_for_entity(
        finance_records,
        entity=entity,
        record_type=request.record_type,
    )
    family_reference = str(request.family_reference or "").strip()
    if family_reference:
        hinted = select_finance_documents_by_family_reference(
            matched,
            family_reference=family_reference,
        )
        if not hinted and select_finance_record_subset is not None:
            hinted = _select_records_via_subset(
                instruction=family_reference,
                records=matched,
                select_finance_record_subset=select_finance_record_subset,
            )
        if not hinted:
            return FinanceDocumentIngestPlan(
                status="clarify_missing",
                message=(
                    "Finance document ingest workflow could not match the "
                    "requested invoice or bill family."
                ),
                reason_code="finance_document_ingest_family_unresolved",
            )
        matched = hinted
    target_paths = tuple(
        dict.fromkeys(
            _normalize_path(record.path)
            for record in matched
            if _normalize_path(record.path)
        )
    )
    if not target_paths:
        return FinanceDocumentIngestPlan(
            status="clarify_missing",
            message=(
                "Finance document ingest workflow found no canonical finance "
                "documents for the requested entity."
            ),
            reason_code="finance_document_ingest_targets_unresolved",
        )
    if request.target_scope == "all_matches" and (
        len(target_paths) > _MAX_BULK_ENTITY_INGEST_TARGETS and not family_reference
    ):
        return FinanceDocumentIngestPlan(
            status="clarify_missing",
            message=(
                "Finance document ingest workflow matched too many finance "
                "documents for one bulk rewrite; clarify the exact invoice or "
                "bill family before rewriting metadata."
            ),
            reason_code="finance_document_ingest_targets_ambiguous",
            grounding_refs=target_paths,
        )
    if len(target_paths) != 1 and request.target_scope != "all_matches":
        return FinanceDocumentIngestPlan(
            status="clarify_missing",
            message=(
                "Finance document ingest workflow matched multiple canonical "
                "finance documents; clarify the exact target note before "
                "rewriting metadata."
            ),
            reason_code="finance_document_ingest_targets_ambiguous",
            grounding_refs=target_paths,
        )
    return FinanceDocumentIngestPlan(
        status="resolved",
        message="Prepared entity-scoped finance document ingest targets.",
        reason_code="finance_document_ingest_targets_resolved",
        target_paths=target_paths,
        grounding_refs=target_paths,
    )

def _normalize_path(value: object) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    return text if text.startswith("/") else f"/{text}"


def _narrow_explicit_paths_by_family_reference(
    explicit_paths: Sequence[str],
    *,
    family_reference: str,
    finance_records: Sequence[FinanceRecord],
    select_finance_record_subset: Callable[[str, Sequence[FinanceRecord]], tuple[int, ...]] | None = None,
) -> tuple[str, ...]:
    term = str(family_reference or "").strip()
    if not term:
        return tuple(explicit_paths)
    record_by_path = {
        _normalize_path(getattr(record, "path", "") or ""): record
        for record in finance_records
        if _normalize_path(getattr(record, "path", "") or "")
    }
    matched_paths: list[str] = []
    candidate_records: list[FinanceRecord] = []
    for path in explicit_paths:
        record = record_by_path.get(path)
        if record is None:
            continue
        candidate_records.append(record)
        if not finance_document_matches_family_reference(record, term):
            continue
        matched_paths.append(path)
    if matched_paths:
        return tuple(dict.fromkeys(matched_paths))
    if select_finance_record_subset is None or not candidate_records:
        return tuple(explicit_paths)
    hinted = _select_records_via_subset(
        instruction=term,
        records=tuple(candidate_records),
        select_finance_record_subset=select_finance_record_subset,
    )
    narrowed = tuple(
        _normalize_path(record.path)
        for record in hinted
        if _normalize_path(record.path)
    )
    return narrowed or tuple(explicit_paths)


def _select_records_via_subset(
    *,
    instruction: str,
    records: Sequence[FinanceRecord],
    select_finance_record_subset: Callable[[str, Sequence[FinanceRecord]], tuple[int, ...]],
) -> tuple[FinanceRecord, ...]:
    indices = select_finance_record_subset(instruction, records)
    if not indices:
        return ()
    selected: list[FinanceRecord] = []
    for index in indices:
        if 0 <= index < len(records):
            selected.append(records[index])
    return tuple(dict.fromkeys(selected))


def _has_explicit_path_collision(
    raw_paths: Sequence[str],
    *,
    finance_records: Sequence[FinanceRecord],
) -> bool:
    non_empty_raw = tuple(path for path in raw_paths if str(path or "").strip())
    record_by_path = {
        _normalize_path(getattr(record, "path", "") or ""): _normalize_path(getattr(record, "path", "") or "")
        for record in finance_records
        if _normalize_path(getattr(record, "path", "") or "")
    }
    stem_index = {
        _normalize_path(getattr(record, "path", "") or "").rsplit("/", 1)[-1].lstrip("_"): _normalize_path(getattr(record, "path", "") or "")
        for record in finance_records
        if _normalize_path(getattr(record, "path", "") or "")
    }
    normalized_targets: list[str] = []
    for raw_path in non_empty_raw:
        normalized = _normalize_path(raw_path)
        resolved = record_by_path.get(normalized)
        if resolved is None:
            resolved = stem_index.get(normalized.rsplit("/", 1)[-1].lstrip("_"))
        normalized_targets.append(resolved or normalized)
    return len(set(normalized_targets)) != len(non_empty_raw)


__all__ = [
    "FinanceDocumentIngestPlan",
    "resolve_finance_document_ingest_workflow",
]
