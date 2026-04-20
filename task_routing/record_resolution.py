from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from typing import Any, Literal, Mapping, Sequence


@dataclass(frozen=True)
class ParsedQuery:
    raw: str
    normalized: str
    tokens: tuple[str, ...]
    content_tokens: tuple[str, ...]
    target_kind: Literal["account", "contact", "either"]
    desired_output: Literal["email", "legal_name", "full_name", "name", "unknown"]
    relationship_role: Literal["primary_contact", "account_manager", "unknown"]
    current_record_preferred: bool
    note_sensitive: bool
    note_conflict_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolutionCandidate:
    record: Mapping[str, Any]
    score: float
    matched_fields: tuple[str, ...] = ()
    matched_tokens: tuple[str, ...] = ()
    source_kind: Literal["structured", "note"] = "structured"
    label: str = ""


@dataclass(frozen=True)
class ResolutionResult:
    status: Literal["resolved", "clarify_multiple", "clarify_none"]
    candidate: Mapping[str, Any] | None
    candidates: tuple[ResolutionCandidate, ...] = ()
    query: ParsedQuery = field(default_factory=lambda: parse_query(""))


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[\u200b\u200c\u200d\u200e\u200f\ufeff]", "", normalized)
    normalized = re.sub(r"[\u202a-\u202e\u2066-\u2069]", "", normalized)
    normalized = re.sub(r"[^a-z0-9@._/+ -]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(token for token in re.findall(r"[a-z0-9]+", normalize_text(text)) if token)

def parse_query(query: str) -> ParsedQuery:
    normalized = normalize_text(query)
    tokens = tokenize(query)
    content_tokens = tokens

    return ParsedQuery(
        raw=query,
        normalized=normalized,
        tokens=tuple(tokens),
        content_tokens=content_tokens,
        target_kind="either",
        desired_output="unknown",
        relationship_role="unknown",
        current_record_preferred=False,
        note_sensitive=False,
        note_conflict_terms=(),
    )


def _infer_kind(record: Mapping[str, Any]) -> Literal["account", "contact", "note"]:
    if "text" in record and len(record) <= 3:
        return "note"
    if "contact_id" in record or ("email" in record and "legal_name" not in record):
        return "contact"
    return "account"


def _exact_identity_terms(record: Mapping[str, Any]) -> tuple[str, ...]:
    terms: list[str] = []
    for key in (
        "account_id",
        "contact_id",
        "legal_name",
        "display_name",
        "full_name",
        "name",
        "email",
        "title",
    ):
        normalized = normalize_text(str(record.get(key) or ""))
        if normalized:
            terms.append(normalized)
    return tuple(dict.fromkeys(terms))


def _query_identity_terms(query: ParsedQuery) -> tuple[str, ...]:
    terms: list[str] = []
    if query.normalized:
        terms.append(query.normalized)
    if query.content_tokens:
        terms.append(" ".join(query.content_tokens))
    return tuple(dict.fromkeys(term for term in terms if term))


def _resolve_unique_exact_candidate(
    rows: Sequence[Mapping[str, Any]],
    query: ParsedQuery,
) -> Mapping[str, Any] | None:
    query_terms = set(_query_identity_terms(query))
    if not query_terms:
        return None
    matches = [
        row
        for row in rows
        if query_terms & set(_exact_identity_terms(row))
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def resolve_records(
    rows: Sequence[Mapping[str, Any]],
    query: ParsedQuery | str,
    *,
    notes: Sequence[str] = (),
) -> ResolutionResult:
    parsed = parse_query(query) if isinstance(query, str) else query
    del notes
    query_terms = set(_query_identity_terms(parsed))
    if not query_terms:
        return ResolutionResult(status="clarify_none", candidate=None, candidates=(), query=parsed)
    matches = tuple(
        row for row in rows if query_terms & set(_exact_identity_terms(row))
    )
    if len(matches) == 1:
        return ResolutionResult(
            status="resolved",
            candidate=matches[0],
            candidates=(),
            query=parsed,
        )
    if len(matches) > 1:
        return ResolutionResult(
            status="clarify_multiple",
            candidate=None,
            candidates=(),
            query=parsed,
        )
    return ResolutionResult(status="clarify_none", candidate=None, candidates=(), query=parsed)


def _relationship_query(source_record: Mapping[str, Any], role: str) -> str:
    anchor = str(
        source_record.get("full_name")
        or source_record.get("display_name")
        or source_record.get("legal_name")
        or source_record.get("title")
        or source_record.get("email")
        or ""
    ).strip()
    if anchor:
        return f"{role} for {anchor}"
    return role


def resolve_related_record(
    rows: Sequence[Mapping[str, Any]],
    *,
    source_record: Mapping[str, Any],
    role: str,
    relationship_fields: Sequence[str],
    notes: Sequence[str] = (),
) -> ResolutionResult:
    relationship_values = [
        str(source_record.get(field) or "").strip()
        for field in relationship_fields
        if str(source_record.get(field) or "").strip()
    ]
    for value in relationship_values:
        normalized_value = normalize_text(value)
        for row in rows:
            label = normalize_text(
                str(
                    row.get("full_name")
                    or row.get("display_name")
                    or row.get("legal_name")
                    or row.get("title")
                    or row.get("email")
                    or ""
                )
            )
            if normalized_value and label and normalized_value == label:
                return ResolutionResult(
                    status="resolved",
                    candidate=row,
                    candidates=(),
                    query=parse_query(_relationship_query(source_record, role)),
                )
    del notes
    query = parse_query(_relationship_query(source_record, role))
    if relationship_values:
        return ResolutionResult(
            status="clarify_multiple",
            candidate=None,
            candidates=(),
            query=query,
        )
    return ResolutionResult(
        status="clarify_none",
        candidate=None,
        candidates=(),
        query=query,
    )


def resolve_primary_contact(
    rows: Sequence[Mapping[str, Any]],
    source_record: Mapping[str, Any],
    *,
    notes: Sequence[str] = (),
) -> ResolutionResult:
    return resolve_related_record(
        rows,
        source_record=source_record,
        role="primary contact",
        relationship_fields=("primary_contact", "contact_name", "contact"),
        notes=notes,
    )


def resolve_account_manager(
    rows: Sequence[Mapping[str, Any]],
    source_record: Mapping[str, Any],
    *,
    notes: Sequence[str] = (),
) -> ResolutionResult:
    return resolve_related_record(
        rows,
        source_record=source_record,
        role="account manager",
        relationship_fields=("account_manager", "manager_name", "owner"),
        notes=notes,
    )


__all__ = [
    "ParsedQuery",
    "ResolutionCandidate",
    "ResolutionResult",
    "normalize_text",
    "parse_query",
    "resolve_account_manager",
    "resolve_primary_contact",
    "resolve_records",
    "tokenize",
]
