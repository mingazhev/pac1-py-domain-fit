from __future__ import annotations

from collections.abc import Callable, Sequence

from domain.finance import FinanceRecord

from .result import MutationStepResult


LlmFinanceSelector = Callable[[str, Sequence[FinanceRecord]], tuple[int, ...]]


def resolve_finance_bulk_delete(
    finance_records: Sequence[FinanceRecord],
    *,
    match_text: str | None,
    record_type: str,
    projection: str,
    sort: str,
    render: str,
    task_text: str | None = None,
    llm_selector: LlmFinanceSelector | None = None,
) -> MutationStepResult:
    needle = str(match_text or "").strip()
    if not needle and llm_selector is None:
        return MutationStepResult(
            status="clarify_missing",
            message=(
                "Finance bulk_delete_by_text_filter requires a non-empty match_text."
            ),
            grounding_refs=(),
            reason_code="finance_bulk_delete_requires_filter",
        )

    matched_paths: tuple[str, ...] = ()
    if needle:
        matched_paths = tuple(
            path
            for path in (
                _normalize_path(record)
                for record in finance_records
                if _matches(record, needle=needle, record_type=record_type)
            )
            if path
        )

    # LLM fallback runs only when deterministic found zero. Union
    # mode over-selected (picked records sharing a weaker keyword),
    # so deterministic stays the ceiling whenever it produces any
    # evidence.
    if not matched_paths and llm_selector is not None:
        instruction = " ".join(
            piece
            for piece in (
                str(task_text or "").strip(),
                f"Filter phrase: {needle}" if needle else "",
            )
            if piece
        )
        candidates = tuple(
            record
            for record in finance_records
            if _type_matches(record, record_type=record_type)
        )
        matched_paths = tuple(
            path
            for path in (
                _normalize_path(candidates[i])
                for i in llm_selector(instruction, candidates)
                if 0 <= i < len(candidates)
            )
            if path
        )

    if sort == "path_asc":
        matched_paths = tuple(sorted(matched_paths, key=str.lower))

    # The harness scores the answer against repo-relative paths
    # (`50_finance/...`), not the loader-normalized absolute form
    # (`/50_finance/...`). Grounding refs keep the absolute form
    # because that's how every other surface refers to canonical
    # paths; the human-visible message strips the leading slash.
    answer_paths = tuple(path.lstrip("/") for path in matched_paths)
    _ = render, projection  # shaping is already enforced by sort + list format
    message = "\n".join(answer_paths)

    if not matched_paths:
        return MutationStepResult(
            status="resolved",
            message=message,
            grounding_refs=(),
            reason_code="finance_bulk_delete_no_matches",
        )
    return MutationStepResult(
        status="resolved",
        message=message,
        grounding_refs=matched_paths,
        reason_code="finance_bulk_delete_resolved",
    )


def _type_matches(record: FinanceRecord, *, record_type: str) -> bool:
    record_type_norm = str(record_type or "").strip().lower()
    if record_type_norm in {"", "any"}:
        return True
    kind = str(getattr(record, "record_type", "") or "").strip().lower()
    return not kind or kind == record_type_norm


def _matches(record: FinanceRecord, *, needle: str, record_type: str) -> bool:
    if not _type_matches(record, record_type=record_type):
        return False
    corpus = _record_corpus(record)
    return needle.lower() in corpus.lower() if corpus else False


def _record_corpus(record: FinanceRecord) -> str:
    """Build a text corpus over the canonical FinanceRecord fields.

    FinanceRecord exposes ``title``, ``counterparty``, ``project``,
    ``alias``, ``related_entity`` and a tuple of ``line_items`` whose
    descriptive text lives under ``item``. Earlier iterations read
    ``raw_text``/``body``/``notes`` and line-item ``description`` —
    none of which exist on the typed record — so the substring match
    never saw the body text. This version reads what is actually
    populated by the loader.
    """

    pieces: list[str] = []
    for attr in ("title", "counterparty", "project", "alias", "related_entity"):
        value = str(getattr(record, attr, "") or "").strip()
        if value:
            pieces.append(value)
    for line_item in getattr(record, "line_items", ()) or ():
        item_text = str(getattr(line_item, "item", "") or "").strip()
        if item_text:
            pieces.append(item_text)
    return "\n".join(pieces)


def _normalize_path(record: FinanceRecord) -> str:
    path = str(getattr(record, "path", "") or "").strip()
    if not path:
        return ""
    return path if path.startswith("/") else f"/{path}"


__all__ = ["resolve_finance_bulk_delete"]
