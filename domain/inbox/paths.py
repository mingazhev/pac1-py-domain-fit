from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import PurePosixPath


_PATH_TOKEN_RE = re.compile(
    r"(?<![@\w])(?:/?[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*\.[A-Za-z0-9._-]+)"
)


def _normalize_path(value: object) -> str:
    text = str(value).replace("\\", "/").strip()
    if not text:
        return ""
    while text.startswith("./"):
        text = text[2:]
    while "//" in text:
        text = text.replace("//", "/")
    normalized = PurePosixPath(text).as_posix()
    if normalized == ".":
        return ""
    return normalized.lstrip("/")


def _path_sort_key(value: object) -> tuple[str, ...]:
    normalized = _normalize_path(value)
    if not normalized:
        return ("",)
    return tuple(part.lower() for part in PurePosixPath(normalized).parts)


def extract_repo_local_targets(text: str) -> tuple[str, ...]:
    candidates: list[str] = []
    for match in _PATH_TOKEN_RE.finditer(text):
        prefix = text[max(0, match.start() - 10) : match.start()].lower()
        candidate = match.group(0).strip().strip(".,:;!?)(")
        if not candidate or "@" in candidate:
            continue
        lowered = candidate.lower()
        if prefix.endswith(("://", "mailto:")):
            continue
        if lowered.startswith("/") and ("http" in prefix or "mailto:" in prefix):
            continue
        if lowered.startswith(("http://", "https://", "mailto:")):
            continue
        candidates.append(candidate)
    return sort_repo_paths(candidates)


def sort_repo_paths(paths: Iterable[object]) -> tuple[str, ...]:
    return tuple(
        sorted(
            (_normalize_path(path) for path in paths if _normalize_path(path)),
            key=_path_sort_key,
        )
    )


__all__ = [
    "extract_repo_local_targets",
    "sort_repo_paths",
]
