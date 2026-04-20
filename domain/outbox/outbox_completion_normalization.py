from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OutboxCompletionNormalization:
    canonical_message: str
    grounding_refs: tuple[str, ...]
