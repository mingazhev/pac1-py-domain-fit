"""Generic LLM fallback selectors over canonical records.

When every deterministic resolver misses, the machine hands a
numbered list of canonical candidates plus the user instruction to a
typed LLM predicate. The LLM picks either a single match or a subset
(with confidence), or returns no match. Callers supply the
per-record summarization plus the scoped system prompt; the
selector itself stays fully generic.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, Field

from formats.markdown_records import extract_markdown_prose_snippet

from .gateway import StructuredExtractionGateway
from .llm_port import GatewayBackedLlmPort
from .prompt_registry import PROMPTS

Summarizer = Callable[[object, int], str]


class RecordSinglePick(BaseModel):
    matched_index: int | None = Field(
        default=None,
        description="Index into the candidate list (0-based) or null if no match.",
    )
    confidence: Literal["high", "medium", "low"] = "low"
    reason: str = Field(default="", description="One short sentence.")


class RecordSubsetPick(BaseModel):
    matched_indices: list[int] = Field(
        default_factory=list,
        description="0-based indices; empty when nothing matches.",
    )
    confidence: Literal["high", "medium", "low"] = "low"
    reason: str = Field(default="", description="One short sentence.")


def _listing(
    candidates: Sequence[object],
    summarize: Summarizer,
    *,
    max_candidates: int,
) -> tuple[list[object], str]:
    limited = list(candidates)[:max_candidates]
    listing = "\n".join(
        summarize(record, index) for index, record in enumerate(limited)
    )
    return limited, listing


def select_single(
    gateway: StructuredExtractionGateway,
    model: str,
    *,
    instruction: str,
    candidates: Sequence[object],
    summarize: Summarizer,
    system_prompt: str,
    accept_confidence: frozenset[str] = frozenset({"high", "medium"}),
    max_candidates: int = 50,
    max_completion_tokens: int = 256,
) -> object | None:
    text = str(instruction or "").strip()
    if not text or not candidates:
        return None
    limited, listing = _listing(
        candidates, summarize, max_candidates=max_candidates
    )
    payload = f"Instruction: {text}\n\nCandidates:\n{listing}"
    llm_port = GatewayBackedLlmPort(gateway, model)
    parsed = llm_port.select_from_set(
        stage="record_select_single",
        role="selector",
        response_format=RecordSinglePick,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload},
        ],
        max_completion_tokens=max_completion_tokens,
    )
    if parsed is None:
        return None
    if parsed.matched_index is None:
        return None
    if parsed.confidence not in accept_confidence:
        return None
    index = parsed.matched_index
    if index < 0 or index >= len(limited):
        return None
    return limited[index]


def select_subset(
    gateway: StructuredExtractionGateway,
    model: str,
    *,
    instruction: str,
    candidates: Sequence[object],
    summarize: Summarizer,
    system_prompt: str,
    accept_confidence: frozenset[str] = frozenset({"high", "medium"}),
    max_candidates: int = 80,
    max_completion_tokens: int = 400,
) -> tuple[int, ...]:
    text = str(instruction or "").strip()
    if not text or not candidates:
        return ()
    limited, listing = _listing(
        candidates, summarize, max_candidates=max_candidates
    )
    payload = f"Instruction: {text}\n\nCandidates:\n{listing}"
    llm_port = GatewayBackedLlmPort(gateway, model)
    parsed = llm_port.select_from_set(
        stage="record_select_subset",
        role="selector",
        response_format=RecordSubsetPick,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload},
        ],
        max_completion_tokens=max_completion_tokens,
    )
    if parsed is None:
        return ()
    if parsed.confidence not in accept_confidence:
        return ()
    return tuple(
        index
        for index in parsed.matched_indices
        if isinstance(index, int) and 0 <= index < len(limited)
    )


# --------------------------------------------------------------------------
# Domain-specific summarizers. Scoped prompts live in prompt_registry.
# --------------------------------------------------------------------------


def _cast_summary(record: object, index: int) -> str:
    record_map: Mapping[str, object] = record if isinstance(record, Mapping) else {}
    parts = [str(record_map.get("title") or "").strip()]
    entity_slug = str(record_map.get("entity_slug") or "").strip()
    if entity_slug:
        parts.append(f"slug: {entity_slug}")
    entity_id = str(record_map.get("entity_id") or "").strip()
    if entity_id:
        parts.append(f"id: {entity_id}")
    aliases = record_map.get("alias_terms") or record_map.get("alias") or ()
    if isinstance(aliases, (list, tuple)):
        alias_text = ", ".join(str(a).strip() for a in aliases if str(a).strip())
    else:
        alias_text = str(aliases or "").strip()
    if alias_text:
        parts.append(f"aliases: {alias_text}")
    identity_terms = record_map.get("identity_terms") or ()
    if isinstance(identity_terms, (list, tuple)):
        identity_text = ", ".join(
            str(item).strip() for item in identity_terms if str(item).strip()
        )
        if identity_text:
            parts.append(f"identity: {identity_text}")
    involvement_terms = record_map.get("project_involvement_terms") or ()
    if isinstance(involvement_terms, (list, tuple)):
        involvement_text = ", ".join(
            str(item).strip() for item in involvement_terms if str(item).strip()
        )
        if involvement_text:
            parts.append(f"project terms: {involvement_text}")
    relationship = str(record_map.get("relationship") or "").strip()
    if relationship:
        parts.append(f"relationship: {relationship}")
    relationship_aliases = record_map.get("relationship_alias_terms") or ()
    if isinstance(relationship_aliases, (list, tuple)):
        relationship_alias_text = ", ".join(
            str(item).strip()
            for item in relationship_aliases
            if str(item).strip()
        )
        if relationship_alias_text:
            parts.append(f"relationship aliases: {relationship_alias_text}")
    descriptor_terms = record_map.get("descriptor_terms") or ()
    if isinstance(descriptor_terms, (list, tuple)):
        descriptor_text = ", ".join(
            str(item).strip()
            for item in descriptor_terms
            if str(item).strip()
        )
        if descriptor_text:
            parts.append(f"descriptors: {descriptor_text}")
    kind = str(record_map.get("kind") or "").strip()
    if kind:
        parts.append(f"kind: {kind}")
    email = str(record_map.get("primary_contact_email") or record_map.get("email") or "").strip()
    if email:
        parts.append(f"email: {email}")
    finance_counterparties = record_map.get("finance_counterparties") or ()
    if isinstance(finance_counterparties, (list, tuple)):
        finance_counterparty_text = ", ".join(
            str(item).strip()
            for item in finance_counterparties
            if str(item).strip()
        )
        if finance_counterparty_text:
            parts.append(f"linked finance counterparties: {finance_counterparty_text}")
    body = " ".join(str(record_map.get("body") or "").split())
    if body:
        parts.append(f"body: {body[:420]}")
    body = " | ".join(piece for piece in parts if piece)
    return f"[{index}] {body}"


def _project_summary(record: object, index: int) -> str:
    record_map: Mapping[str, object] = record if isinstance(record, Mapping) else {}
    parts = [
        str(record_map.get("title") or record_map.get("project_name") or "").strip()
    ]
    alias = str(record_map.get("alias") or "").strip()
    if alias:
        parts.append(f"alias: {alias}")
    kind = str(record_map.get("kind") or "").strip()
    if kind:
        parts.append(f"kind: {kind}")
    lane = str(record_map.get("lane") or "").strip()
    if lane:
        parts.append(f"lane: {lane}")
    alias_terms = record_map.get("alias_terms")
    if isinstance(alias_terms, (list, tuple)):
        alias_text = ", ".join(
            str(item).strip() for item in alias_terms if str(item or "").strip()
        )
        if alias_text:
            parts.append(f"aliases: {alias_text[:180]}")
    descriptor_aliases = record_map.get("descriptor_aliases")
    if isinstance(descriptor_aliases, (list, tuple)):
        descriptor_text = ", ".join(
            str(item).strip()
            for item in descriptor_aliases
            if str(item or "").strip()
        )
        if descriptor_text:
            parts.append(f"descriptors: {descriptor_text[:180]}")
    linked_entities = record_map.get("linked_entities")
    if isinstance(linked_entities, (list, tuple)):
        linked_text = ", ".join(
            str(item).strip()
            for item in linked_entities
            if str(item or "").strip()
        )
        if linked_text:
            parts.append(f"linked: {linked_text[:180]}")
    participants = record_map.get("participants")
    if isinstance(participants, (list, tuple)):
        participant_text = ", ".join(
            str(item).strip()
            for item in participants
            if str(item or "").strip()
        )
        if participant_text:
            parts.append(f"participants: {participant_text[:180]}")
    goal = str(record_map.get("goal") or "").strip()
    if goal:
        parts.append(f"goal: {goal[:140]}")
    next_step = str(record_map.get("next_step") or "").strip()
    if next_step:
        parts.append(f"next: {next_step[:140]}")
    body = str(record_map.get("body") or "").strip()
    prose = extract_markdown_prose_snippet(body, max_chars=220)
    if prose:
        parts.append(f"body: {prose}")
    path = str(record_map.get("path") or "").strip()
    if path:
        parts.append(f"path: {path}")
    body = " | ".join(piece for piece in parts if piece)
    return f"[{index}] {body}"


def _finance_summary(record: object, index: int) -> str:
    path = str(getattr(record, "path", "") or "")
    kind = str(getattr(record, "record_type", "") or "")
    record_date = str(getattr(record, "date", "") or "")
    counterparty = ""
    try:
        counterparty = str(getattr(record, "counterparty", "") or "")
    except Exception:  # noqa: BLE001
        counterparty = ""
    items = getattr(record, "line_items", None) or ()
    item_descriptions: list[str] = []
    for item in items:
        label = str(
            getattr(item, "item", "") or getattr(item, "description", "") or ""
        ).strip()
        if not label:
            continue
        quantity = getattr(item, "quantity", None)
        unit = getattr(item, "unit_eur", None)
        line = getattr(item, "line_eur", None)
        parts = [label]
        if quantity is not None:
            parts.append(f"qty={quantity}")
        if unit is not None:
            parts.append(f"unit={unit}")
        if line is not None:
            parts.append(f"line={line}")
        item_descriptions.append(" ".join(parts))
    raw_text = str(getattr(record, "raw_text", "") or "")
    parts = [f"[{index}] {path}"]
    if kind:
        parts.append(f"type={kind}")
    if record_date:
        parts.append(f"date={record_date}")
    if counterparty:
        parts.append(f"counterparty={counterparty}")
    related_entity = str(getattr(record, "related_entity", "") or "").strip()
    if related_entity:
        parts.append(f"related_entity={related_entity}")
    if item_descriptions:
        parts.append("items=" + "; ".join(item_descriptions[:8]))
    if not item_descriptions and raw_text:
        parts.append("notes=" + raw_text[:240].replace("\n", " "))
    return " | ".join(parts)


def _account_summary(record: object, index: int) -> str:
    record_map: Mapping[str, object] = record if isinstance(record, Mapping) else {}
    parts = [
        str(
            record_map.get("display_name")
            or record_map.get("legal_name")
            or record_map.get("name")
            or ""
        ).strip()
    ]
    legal_name = str(record_map.get("legal_name") or "").strip()
    if legal_name and legal_name not in parts:
        parts.append(f"legal_name: {legal_name}")
    account_id = str(record_map.get("account_id") or "").strip()
    if account_id:
        parts.append(f"account_id: {account_id}")
    country = str(record_map.get("country") or "").strip()
    if country:
        parts.append(f"country: {country}")
    industry = str(record_map.get("industry") or "").strip()
    if industry:
        parts.append(f"industry: {industry}")
    body = " | ".join(piece for piece in parts if piece)
    return f"[{index}] {body}"


def _contact_summary(record: object, index: int) -> str:
    record_map: Mapping[str, object] = record if isinstance(record, Mapping) else {}
    parts = [
        str(
            record_map.get("full_name")
            or record_map.get("display_name")
            or record_map.get("title")
            or ""
        ).strip()
    ]
    email = str(record_map.get("email") or "").strip()
    if email:
        parts.append(f"email: {email}")
    title = str(record_map.get("title") or "").strip()
    if title and title not in parts:
        parts.append(f"title: {title}")
    contact_id = str(record_map.get("contact_id") or "").strip()
    if contact_id:
        parts.append(f"contact_id: {contact_id}")
    account_name = str(record_map.get("account_name") or "").strip()
    if account_name:
        parts.append(f"account: {account_name}")
    body = " | ".join(piece for piece in parts if piece)
    return f"[{index}] {body}"


def _queue_summary(record: object, index: int) -> str:
    record_map: Mapping[str, object] = record if isinstance(record, Mapping) else {}
    if not record_map:
        record_map = {
            "path": str(getattr(record, "path", "") or "").strip(),
            "batch_timestamp": str(getattr(record, "batch_timestamp", "") or "").strip(),
            "order_id": str(getattr(record, "order_id", "") or "").strip(),
            "state": str(getattr(record, "state", "") or "").strip(),
            "queue_reference": str(getattr(record, "queue_reference", "") or "").strip(),
        }
    parts = [str(record_map.get("path") or "").strip()]
    batch_timestamp = str(record_map.get("batch_timestamp") or "").strip()
    if batch_timestamp:
        parts.append(f"batch={batch_timestamp}")
    order_id = str(record_map.get("order_id") or "").strip()
    if order_id:
        parts.append(f"order={order_id}")
    state = str(record_map.get("state") or "").strip()
    if state:
        parts.append(f"state={state}")
    queue_reference = str(record_map.get("queue_reference") or "").strip()
    if queue_reference:
        parts.append(f"queue={queue_reference}")
    body = " | ".join(piece for piece in parts if piece)
    return f"[{index}] {body}"


def llm_resolve_cast_record(
    gateway: StructuredExtractionGateway,
    model: str,
    cast_records: Sequence[Mapping[str, object]],
    query: str,
    *,
    accept_confidence: frozenset[str] = frozenset({"high", "medium"}),
) -> Mapping[str, object] | None:
    match = select_single(
        gateway,
        model,
        instruction=query,
        candidates=cast_records,
        summarize=_cast_summary,
        system_prompt=PROMPTS["record_select_single:cast"],
        accept_confidence=accept_confidence,
    )
    return match if isinstance(match, Mapping) else None


def llm_resolve_project_record(
    gateway: StructuredExtractionGateway,
    model: str,
    project_records: Sequence[Mapping[str, object]],
    query: str,
    *,
    accept_confidence: frozenset[str] = frozenset({"high", "medium"}),
) -> Mapping[str, object] | None:
    match = select_single(
        gateway,
        model,
        instruction=query,
        candidates=project_records,
        summarize=_project_summary,
        system_prompt=PROMPTS["record_select_single:project"],
        accept_confidence=accept_confidence,
    )
    return match if isinstance(match, Mapping) else None


def llm_resolve_account_record(
    gateway: StructuredExtractionGateway,
    model: str,
    account_records: Sequence[Mapping[str, object]],
    query: str,
) -> Mapping[str, object] | None:
    match = select_single(
        gateway,
        model,
        instruction=query,
        candidates=account_records,
        summarize=_account_summary,
        system_prompt=PROMPTS["record_select_single:account"],
    )
    return match if isinstance(match, Mapping) else None


def llm_resolve_contact_record(
    gateway: StructuredExtractionGateway,
    model: str,
    contact_records: Sequence[Mapping[str, object]],
    query: str,
) -> Mapping[str, object] | None:
    match = select_single(
        gateway,
        model,
        instruction=query,
        candidates=contact_records,
        summarize=_contact_summary,
        system_prompt=PROMPTS["record_select_single:contact"],
    )
    return match if isinstance(match, Mapping) else None


def llm_select_queue_entries(
    gateway: StructuredExtractionGateway,
    model: str,
    *,
    instruction: str,
    entries: Sequence[object],
) -> tuple[int, ...]:
    return select_subset(
        gateway,
        model,
        instruction=instruction,
        candidates=entries,
        summarize=_queue_summary,
        system_prompt=PROMPTS["record_select_subset:queue"],
    )


def llm_select_finance_records(
    gateway: StructuredExtractionGateway,
    model: str,
    *,
    instruction: str,
    records: Sequence[object],
    accept_confidence: frozenset[str] = frozenset({"high", "medium"}),
) -> tuple[int, ...]:
    return select_subset(
        gateway,
        model,
        instruction=instruction,
        candidates=records,
        summarize=_finance_summary,
        system_prompt=PROMPTS["record_select_subset:finance"],
        accept_confidence=accept_confidence,
    )


def llm_resolve_finance_record(
    gateway: StructuredExtractionGateway,
    model: str,
    *,
    instruction: str,
    records: Sequence[object],
    accept_confidence: frozenset[str] = frozenset({"high", "medium"}),
) -> object | None:
    return select_single(
        gateway,
        model,
        instruction=instruction,
        candidates=records,
        summarize=_finance_summary,
        system_prompt=PROMPTS["record_select_single:finance"],
        accept_confidence=accept_confidence,
    )


__all__ = [
    "RecordSinglePick",
    "RecordSubsetPick",
    "llm_resolve_account_record",
    "llm_resolve_cast_record",
    "llm_resolve_contact_record",
    "llm_resolve_finance_record",
    "llm_resolve_project_record",
    "llm_select_queue_entries",
    "llm_select_finance_records",
    "select_single",
    "select_subset",
]
