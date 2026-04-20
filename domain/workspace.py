from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

WorkspaceRole = Literal[
    "inbox",
    "cast",
    "projects",
    "knowledge",
    "work",
    "finance",
    "outbox",
    "memory",
    "system",
    "process",
    "capture",
]

_ROLE_ORDER: tuple[WorkspaceRole, ...] = (
    "capture",
    "inbox",
    "cast",
    "projects",
    "knowledge",
    "work",
    "finance",
    "outbox",
    "memory",
    "system",
    "process",
)

_ROLE_ALIASES: dict[WorkspaceRole, tuple[str, ...]] = {
    "inbox": ("inbox",),
    "cast": ("cast", "entities"),
    "projects": ("projects", "project"),
    "knowledge": ("knowledge",),
    "work": ("work",),
    "finance": ("finance",),
    "outbox": ("outbox",),
    "memory": ("memory",),
    "system": ("system",),
    "process": ("process",),
    "capture": ("capture",),
}


def normalize_workspace_path(path: str) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        return "/"
    if not text.startswith("/"):
        text = f"/{text}"
    while "//" in text:
        text = text.replace("//", "/")
    if len(text) > 1:
        text = text.rstrip("/")
    return text or "/"


def _shape_root_name(path: str) -> str:
    normalized = normalize_workspace_path(path)
    name = normalized.rsplit("/", 1)[-1].lower()
    while name and name[0].isdigit():
        name = name[1:]
    return name.lstrip("_")


def _dedupe_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        normalized = normalize_workspace_path(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


@dataclass(frozen=True, slots=True)
class WorkspaceLayout:
    inbox: tuple[str, ...] = ()
    cast: tuple[str, ...] = ()
    projects: tuple[str, ...] = ()
    knowledge: tuple[str, ...] = ()
    work: tuple[str, ...] = ()
    finance: tuple[str, ...] = ()
    outbox: tuple[str, ...] = ()
    memory: tuple[str, ...] = ()
    system: tuple[str, ...] = ()
    process: tuple[str, ...] = ()
    capture: tuple[str, ...] = ()
    authority_files: tuple[str, ...] = (
        "/AGENTS.md",
        "/AGENTS.MD",
        "/CLAUDE.md",
        "/CLAUDE.MD",
    )

    def roots_for_role(self, role: WorkspaceRole) -> tuple[str, ...]:
        return tuple(getattr(self, role, ()))

    @property
    def entities(self) -> tuple[str, ...]:
        return self.cast

    def primary_root_for_role(self, role: WorkspaceRole) -> str | None:
        roots = self.roots_for_role(role)
        if not roots:
            return None
        return min(
            roots,
            key=lambda root: (
                0 if re.match(r"^\d", normalize_workspace_path(root).rsplit("/", 1)[-1]) else 1,
                len(normalize_workspace_path(root)),
                normalize_workspace_path(root),
            ),
        )

    def primary_project_root(self) -> str | None:
        return self.primary_root_for_role("projects")

    def primary_finance_root(self) -> str | None:
        return self.primary_root_for_role("finance")

    def primary_outbox_sink_root(self) -> str | None:
        root = self.primary_root_for_role("outbox")
        if root is None:
            return None
        normalized_root = normalize_workspace_path(root)
        if normalized_root.rsplit("/", 1)[-1].lower() == "outbox":
            return normalized_root
        return f"{normalized_root}/outbox"

    def semantic_role(self, path: str) -> WorkspaceRole | None:
        normalized = normalize_workspace_path(path)
        matches: list[tuple[int, WorkspaceRole]] = []
        for role in _ROLE_ORDER:
            for root in self.roots_for_role(role):
                normalized_root = normalize_workspace_path(root)
                if normalized == normalized_root or normalized.startswith(
                    f"{normalized_root}/"
                ):
                    matches.append((len(normalized_root), role))
        if not matches:
            return None
        matches.sort(key=lambda item: (-item[0], _ROLE_ORDER.index(item[1])))
        return matches[0][1]

    def path_has_role(self, path: str, role: WorkspaceRole) -> bool:
        return self.semantic_role(path) == role

    def is_inbox_path(self, path: str) -> bool:
        return self.path_has_role(path, "inbox")

    def untrusted_content_roots(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys([*self.inbox, *self.capture]))

    def outbox_sink_roots(self) -> tuple[str, ...]:
        roots: list[str] = []
        for root in self.outbox:
            normalized_root = normalize_workspace_path(root)
            roots.append(f"{normalized_root}/outbox")
            if normalized_root.rsplit("/", 1)[-1].lower() == "outbox":
                roots.append(normalized_root)
        return _dedupe_paths(tuple(roots))

    def is_outbox_message_path(self, path: str) -> bool:
        normalized = normalize_workspace_path(path)
        return any(
            normalized == root or normalized.startswith(f"{root}/")
            for root in self.outbox_sink_roots()
        )

    def is_outbox_channel_path(self, path: str) -> bool:
        normalized = normalize_workspace_path(path)
        return any(
            normalized == f"{root}/channels"
            or normalized.startswith(f"{root}/channels/")
            for root in self.outbox
        )

    def is_knowledge_thread_path(self, path: str) -> bool:
        normalized = normalize_workspace_path(path)
        return any(
            normalized == f"{root}/threads" or normalized.startswith(f"{root}/threads/")
            for root in self.knowledge
        )


def resolve_workspace_layout(discovered_roots: tuple[str, ...]) -> WorkspaceLayout:
    normalized_roots = _dedupe_paths(
        tuple(
            normalize_workspace_path(root)
            for root in discovered_roots
            if str(root or "").strip()
        )
    )
    resolved: dict[WorkspaceRole, list[str]] = {role: [] for role in _ROLE_ORDER}

    for root in normalized_roots:
        shaped_name = _shape_root_name(root)
        for role, aliases in _ROLE_ALIASES.items():
            if shaped_name in aliases:
                resolved[role].append(root)
                break

    # `capture` is semantically special for trust-boundary logic even when it
    # lives under a broader knowledge root instead of being a workspace root.
    for knowledge_root in resolved["knowledge"]:
        resolved["capture"].append(f"{knowledge_root}/capture")

    return WorkspaceLayout(
        inbox=_dedupe_paths(tuple(resolved["inbox"])),
        cast=_dedupe_paths(tuple(resolved["cast"])),
        projects=_dedupe_paths(tuple(resolved["projects"])),
        knowledge=_dedupe_paths(tuple(resolved["knowledge"])),
        work=_dedupe_paths(tuple(resolved["work"])),
        finance=_dedupe_paths(tuple(resolved["finance"])),
        outbox=_dedupe_paths(tuple(resolved["outbox"])),
        memory=_dedupe_paths(tuple(resolved["memory"])),
        system=_dedupe_paths(tuple(resolved["system"])),
        process=_dedupe_paths(tuple(resolved["process"])),
        capture=_dedupe_paths(tuple(resolved["capture"])),
    )


_NORA_ROOT_SCAN_DEPTH_POLICY: tuple[tuple[frozenset[str], int], ...] = (
    (frozenset({"system"}), 2),
    (frozenset({"project", "projects"}), 3),
    (frozenset({"knowledge", "work", "memory"}), 3),
)


def _workspace_root_tokens(path: str) -> frozenset[str]:
    shape_name = _shape_root_name(path)
    tokens = [token for token in re.split(r"[^a-z0-9]+", shape_name) if token]
    if shape_name and shape_name not in tokens:
        tokens.insert(0, shape_name)
    return frozenset(tokens)


def nora_root_scan_depth(path: str) -> int | None:
    """Return the Nora-queue scan depth for a workspace root, or ``None``.

    The Nora-queue workflow only walks workspace roots whose semantic role
    matches one of the Nora-supported buckets (system, project, knowledge,
    work, memory). Each bucket has a capped depth that reflects how the
    corpus is physically laid out, so the scan stays bounded. Roots outside
    these buckets return ``None`` so the caller can skip them entirely.
    """

    tokens = _workspace_root_tokens(path)
    for role_tokens, depth in _NORA_ROOT_SCAN_DEPTH_POLICY:
        if tokens & role_tokens:
            return depth
    return None


DEFAULT_WORKSPACE_LAYOUT = resolve_workspace_layout(
    (
        "/inbox",
        "/00_inbox",
        "/10_entities",
        "/40_projects",
        "/30_knowledge",
        "/20_work",
        "/50_finance",
        "/outbox",
        "/60_outbox",
        "/90_memory",
        "/99_system",
        "/99_process",
        "/01_capture",
    )
)


@dataclass(frozen=True, slots=True)
class WorkspacePolicies:
    """Canonical per-role workspace policy text (e.g. AGENTS.MD bodies).

    Each entry is the raw markdown body of the corresponding role's
    AGENTS.MD. Intent-specific prompts append the relevant slice so
    the LLM sees workspace-defined conventions (path formats,
    recipient-resolution rules, inbox etiquette) without duplicating
    them in code. ``root`` is the repo-root AGENTS.MD and is always
    included as a baseline so every prompt gets the folder map and
    the 'read nested AGENTS.MD files' rule.
    """

    inbox: str = ""
    cast: str = ""
    knowledge: str = ""
    work: str = ""
    finance: str = ""
    outbox: str = ""
    memory: str = ""
    system: str = ""
    process: str = ""
    capture: str = ""
    projects: str = ""
    root: str = ""
    extra_workflows: tuple[tuple[str, str], ...] = ()

    def for_role(self, role: WorkspaceRole) -> str:
        return str(getattr(self, role, "") or "")

    @property
    def is_empty(self) -> bool:
        if self.root:
            return False
        if self.projects:
            return False
        if self.extra_workflows:
            return False
        for role in _ROLE_ORDER:
            if str(getattr(self, role, "") or "").strip():
                return False
        return True


__all__ = [
    "DEFAULT_WORKSPACE_LAYOUT",
    "WorkspaceLayout",
    "WorkspacePolicies",
    "WorkspaceRole",
    "nora_root_scan_depth",
    "normalize_workspace_path",
    "resolve_workspace_layout",
]
