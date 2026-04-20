from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from domain.inbox import sort_repo_paths


DEFAULT_PENDING_INBOX_IGNORED_FILENAMES = frozenset(
    {"readme.md", "agents.md", "claude.md"}
)


def _normalize_filename(path: object) -> str:
    normalized = str(path).replace("\\", "/").strip()
    if not normalized:
        return ""
    return PurePosixPath(normalized).name.lower()


def is_pending_inbox_item_path(
    path: object,
    *,
    ignored_filenames: frozenset[str] = DEFAULT_PENDING_INBOX_IGNORED_FILENAMES,
) -> bool:
    filename = _normalize_filename(path)
    return bool(filename) and filename not in ignored_filenames


@dataclass(frozen=True, slots=True)
class PendingInboxSelection:
    ordered_paths: tuple[str, ...]

    @property
    def next_path(self) -> str | None:
        return self.ordered_paths[0] if self.ordered_paths else None


def select_pending_inbox_paths(
    candidate_paths: Iterable[object],
    *,
    ignored_filenames: frozenset[str] = DEFAULT_PENDING_INBOX_IGNORED_FILENAMES,
) -> PendingInboxSelection:
    pending_paths = tuple(
        path
        for path in sort_repo_paths(candidate_paths)
        if is_pending_inbox_item_path(path, ignored_filenames=ignored_filenames)
    )
    return PendingInboxSelection(ordered_paths=pending_paths)
