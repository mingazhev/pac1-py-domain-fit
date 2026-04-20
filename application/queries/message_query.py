from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from application.ports import QueryResolutionPort
from domain.cast import CastEntity
from domain.messages import MessageRecord, select_last_message_record


@dataclass(frozen=True, slots=True)
class MessageQueryResult:
    status: Literal["resolved", "clarify_missing"]
    message: str
    grounding_refs: tuple[str, ...]


def resolve_message_query(
    cast_records: Sequence[Mapping[str, Any]],
    cast_entities: Sequence[CastEntity],
    message_records: Sequence[MessageRecord],
    *,
    entity_reference: str,
    selection: str,
    property: str,
    fallback_text: str,
    cast_refs: Sequence[str],
    resolution_port: QueryResolutionPort | None,
) -> MessageQueryResult | None:
    rows = [dict(record) for record in cast_records]
    if not rows:
        return None

    if resolution_port is None or resolution_port.resolve_message_entity_candidate is None:
        return None
    entity_record = resolution_port.resolve_message_entity_candidate(
        rows,
        entity_reference,
        fallback_text,
    )
    if entity_record is None:
        return None

    entity = _typed_entity_for_candidate(cast_entities, entity_record)
    if entity is None:
        return None

    matching = [record for record in message_records if record.matches_entity(entity)]

    if selection == "last_recorded_message" or selection == "quote":
        selected = select_last_message_record(matching)
    else:
        selected = select_last_message_record(matching)

    entity_title = (
        str(
            entity_record.get("title")
            or entity_record.get("entity_slug")
            or "the requested entity"
        ).strip()
    )
    if selected is None:
        return MessageQueryResult(
            status="clarify_missing",
            message=f"No recorded message from {entity_title} was found in canonical message surfaces.",
            grounding_refs=_fallback_refs(cast_refs),
        )

    value = _extract_message_property(selected, property)
    if not value:
        return MessageQueryResult(
            status="clarify_missing",
            message=(
                f"The latest recorded message from {entity_title} has no "
                f"{property} value in canonical message surfaces."
            ),
            grounding_refs=_message_refs(cast_refs, selected.path),
        )

    return MessageQueryResult(
        status="resolved",
        message=value,
        grounding_refs=_message_refs(cast_refs, selected.path),
    )


def _extract_message_property(record: MessageRecord, property: str) -> str:
    value = getattr(record, property, None)
    if value is None:
        return ""
    return str(value).strip()


def _fallback_refs(cast_refs: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            _normalize_repo_path(ref) for ref in cast_refs if str(ref or "").strip()
        )
    )


def _message_refs(
    cast_refs: Sequence[str], message_path: str
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            [
                *(
                    _normalize_repo_path(ref)
                    for ref in cast_refs
                    if str(ref or "").strip()
                ),
                _normalize_repo_path(message_path),
            ]
        )
    )


def _normalize_repo_path(path: object) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text.startswith("/"):
        text = f"/{text}"
    text = re.sub(r"/+", "/", text)
    return text.rstrip("/") or "/"


def _typed_entity_for_candidate(
    cast_entities: Sequence[CastEntity],
    candidate: Mapping[str, Any],
) -> CastEntity | None:
    path = str(candidate.get("path") or "").strip()
    entity_slug = str(candidate.get("entity_slug") or "").strip()
    entity_id = str(candidate.get("entity_id") or "").strip()
    for entity in cast_entities:
        if path and str(entity.path or "").strip() == path:
            return entity
        if entity_slug and str(entity.entity_slug or "").strip() == entity_slug:
            return entity
        if entity_id and str(entity.entity_id or "").strip() == entity_id:
            return entity
    return None


__all__ = ["MessageQueryResult", "resolve_message_query"]
