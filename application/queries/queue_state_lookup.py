from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from domain.process import QueueState


def _normalize_repo_path(path: object) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text.startswith("/"):
        text = f"/{text}"
    text = re.sub(r"/+", "/", text)
    return text.rstrip("/") or "/"


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _coerce_queue_state(entry: QueueState | Mapping[str, object]) -> QueueState | None:
    if isinstance(entry, QueueState):
        return entry
    return QueueState.from_marker_payload(entry)


def _entry_sort_key(entry: QueueState) -> tuple[str, int, str]:
    return (entry.batch_timestamp, entry.order_id, entry.path)


def _render_entry(entry: QueueState, index: int) -> str:
    return entry.render(index)


@dataclass(frozen=True, slots=True)
class QueueStateLookupQueryResult:
    message: str
    summary: str
    grounding_refs: tuple[str, ...]


def resolve_queue_state_lookup_query(
    entries: Sequence[QueueState | Mapping[str, object]],
    *,
    queue_reference: str,
    fallback_refs: Sequence[str] = (),
) -> QueueStateLookupQueryResult | None:
    if not entries or not str(queue_reference or "").strip():
        return None

    matches = [
        entry
        for raw_entry in entries
        if (entry := _coerce_queue_state(raw_entry)) is not None
        and entry.matches_reference(queue_reference)
    ]
    if not matches:
        return None

    matches = sorted(matches, key=_entry_sort_key, reverse=True)
    grounding_refs = tuple(
        dict.fromkeys(
            _normalize_repo_path(entry.path or "")
            for entry in matches
            if str(entry.path or "").strip()
        )
    )
    if not grounding_refs:
        grounding_refs = tuple(
            dict.fromkeys(_normalize_repo_path(ref) for ref in fallback_refs)
        )
    return QueueStateLookupQueryResult(
        message="\n".join(
            _render_entry(entry, index + 1) for index, entry in enumerate(matches)
        ),
        summary="resolved queue state lookup deterministically",
        grounding_refs=grounding_refs,
    )


def render_queue_state_lookup_result(
    entries: Sequence[QueueState | Mapping[str, object]],
    *,
    fallback_refs: Sequence[str] = (),
    summary: str = "resolved queue state lookup via closed-set candidate selection",
) -> QueueStateLookupQueryResult | None:
    matches = [
        entry
        for raw_entry in entries
        if (entry := _coerce_queue_state(raw_entry)) is not None
    ]
    if not matches:
        return None
    matches = sorted(matches, key=_entry_sort_key, reverse=True)
    grounding_refs = tuple(
        dict.fromkeys(
            _normalize_repo_path(entry.path or "")
            for entry in matches
            if str(entry.path or "").strip()
        )
    )
    if not grounding_refs:
        grounding_refs = tuple(
            dict.fromkeys(_normalize_repo_path(ref) for ref in fallback_refs)
        )
    return QueueStateLookupQueryResult(
        message="\n".join(
            _render_entry(entry, index + 1) for index, entry in enumerate(matches)
        ),
        summary=summary,
        grounding_refs=grounding_refs,
    )
