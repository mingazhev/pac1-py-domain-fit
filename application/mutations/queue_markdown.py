from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePosixPath

from domain.process import QueueState

from .result import MutationStepResult


def resolve_queue_markdown_mutation(
    queue_states: Sequence[QueueState],
    *,
    target_names: Sequence[str],
    document_refs: Sequence[str],
) -> MutationStepResult:
    requested = _clean_targets(target_names)
    if not requested:
        return MutationStepResult(
            status="clarify_missing",
            message="Queue mutation requires at least one explicit markdown target.",
            grounding_refs=(),
            reason_code="queue_mutation_requires_targets",
        )

    state_paths = tuple(_normalize(state.path) for state in queue_states if state.path)
    ref_paths = tuple(_normalize(ref) for ref in document_refs if ref)

    resolved: list[str] = []
    missing: list[str] = []
    for target in requested:
        canonical = _match_target(target, state_paths, ref_paths)
        if canonical is None:
            missing.append(target)
        else:
            resolved.append(canonical)

    if not resolved:
        return MutationStepResult(
            status="clarify_missing",
            message=(
                "No canonical queue markdown docs matched the requested targets: "
                + ", ".join(missing)
            ),
            grounding_refs=(),
            reason_code="queue_mutation_targets_unresolved",
        )

    sorted_paths = tuple(sorted(dict.fromkeys(resolved), key=str.lower))
    if missing:
        reason = "queue_mutation_partial_resolution"
    else:
        reason = "queue_mutation_resolved"
    return MutationStepResult(
        status="resolved",
        message="\n".join(sorted_paths),
        grounding_refs=sorted_paths,
        reason_code=reason,
    )


def _clean_targets(targets: Sequence[str]) -> tuple[str, ...]:
    cleaned: list[str] = []
    for raw in targets:
        value = str(raw or "").strip()
        if not value:
            continue
        if not value.lower().endswith(".md"):
            continue
        cleaned.append(value)
    return tuple(dict.fromkeys(cleaned))


def _normalize(path: object) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        return ""
    if not text.startswith("/"):
        text = f"/{text}"
    while "//" in text:
        text = text.replace("//", "/")
    return text.rstrip("/") or "/"


def _match_target(
    target: str,
    state_paths: Sequence[str],
    ref_paths: Sequence[str],
) -> str | None:
    normalized_target = _normalize(target)
    basename = PurePosixPath(normalized_target).name.lower()
    if not normalized_target:
        return None

    for candidate in state_paths:
        if candidate == normalized_target:
            return candidate

    for candidate in ref_paths:
        if candidate == normalized_target:
            return candidate

    for candidate in state_paths:
        if PurePosixPath(candidate).name.lower() == basename:
            return candidate
    for candidate in ref_paths:
        if PurePosixPath(candidate).name.lower() == basename:
            return candidate
    return None


__all__ = ["resolve_queue_markdown_mutation"]
