from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass


ResolverCandidate = dict[str, object] | None


@dataclass(frozen=True, slots=True)
class QueryResolutionPort:
    resolve_entity_candidate: Callable[
        [Sequence[Mapping[str, object]], str, str, bool],
        ResolverCandidate,
    ] | None = None
    resolve_message_entity_candidate: Callable[
        [Sequence[Mapping[str, object]], str, str],
        ResolverCandidate,
    ] | None = None
    resolve_project_subject_candidate: Callable[
        [Sequence[Mapping[str, object]], str, str],
        ResolverCandidate,
    ] | None = None
    resolve_project_candidate: Callable[
        [Sequence[Mapping[str, object]], str, str],
        ResolverCandidate,
    ] | None = None
