"""Domain-layer resolution of finance anchor records via canonical paths.

Filesystem paths are first-class data in the finance domain (records have
canonical, policy-constrained paths in the vault). Path-substring matching
against a task's free text — when the task references the record by its
canonical path or filename — is therefore legitimate domain logic, not a
lexical free-text heuristic.

This module exposes :func:`resolve_exact_finance_anchor_by_path`, which
returns a canonical anchor path iff exactly one record's canonical path
(full path, root-relative path, or basename) appears as a substring of the
task text. Any ambiguity yields an empty string so that higher layers can
fall back to LLM-based resolution.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Iterable


def resolve_exact_finance_anchor_by_path(task_text: str, records: Iterable) -> str:
    """Return the canonical anchor path when the task text names exactly one record path.

    Matches a record when any of these appear as a substring of the lowercased
    task text:
      * canonical path (leading-slash form)
      * root-relative path (leading slash stripped)
      * basename (filename only)

    If the task text does not contain ``.md`` the function returns early — all
    canonical finance record paths end in ``.md``. Returns an empty string on
    zero matches, multiple distinct matches, or empty input.
    """

    lowered_task = str(task_text or "").strip().lower()
    if not lowered_task or ".md" not in lowered_task:
        return ""
    matches: list[str] = []
    for record in records:
        raw_path = str(getattr(record, "path", "") or "").strip()
        if not raw_path:
            continue
        canonical_path = raw_path if raw_path.startswith("/") else f"/{raw_path}"
        lowered_path = canonical_path.lower()
        lowered_relative = lowered_path.lstrip("/")
        lowered_name = PurePosixPath(lowered_path).name
        if (
            lowered_path in lowered_task
            or lowered_relative in lowered_task
            or (lowered_name and lowered_name in lowered_task)
        ):
            matches.append(canonical_path)
    unique_matches = tuple(dict.fromkeys(matches))
    if len(unique_matches) == 1:
        return unique_matches[0]
    return ""


__all__ = ["resolve_exact_finance_anchor_by_path"]
