"""Workspace persistence layer: scan, parse, and load domain objects from VM.

Consolidates the former `context_documents`, `context_scan`,
`context_resource_loader`, and `context_resource_assembly` modules.

Responsibilities:
- ``scan_workspace`` / ``WorkspaceScan``: inventory the repo (top-level entries,
  roots, layout, file paths).
- Document helpers (``parse_markdown_document``, ``belongs_to_*``,
  ``load_json_records``, etc.): parse markdown/JSON and classify paths by
  workspace role.
- Per-kind loaders (``load_cast_context``, ``load_project_context``, ...):
  turn parsed documents into typed domain objects and mapping records.
- ``assemble_workspace_runtime_resources`` / ``LoadedRuntimeResources``:
  coordinate the per-kind loaders given a set of ``needs``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from deterministic_ops import records_from_payload
from domain.finance import FinanceRecord
from domain.inbox import InboxItem
from domain.process import QueueState
from domain.workspace import WorkspaceLayout, resolve_workspace_layout
from formats.frontmatter import parse_frontmatter_with_mode
from formats.json_payloads import parse_json_value
from loaders.accounts import account_from_mapping, contacts_from_mappings
from loaders.cast import build_cast_entities, cast_entity_to_mapping
from loaders.capture import capture_records_from_mappings
from loaders.finance import finance_record_from_document
from loaders.messages import message_records_from_document
from loaders.projects import build_projects, project_to_mapping
from telemetry.trace import emit_runtime_exception
from runtime.io.vm_tools import (
    list_entries,
    normalize_repo_path,
    read_context_payload,
    read_text,
    walk_files,
)

try:
    from bitgn.vm.pcm_connect import PcmRuntimeClientSync
except ModuleNotFoundError:  # pragma: no cover - local test fallback only
    PcmRuntimeClientSync = Any  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Workspace scan
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkspaceScan:
    top_level: tuple[Any, ...]
    roots: tuple[str, ...]
    layout: WorkspaceLayout
    file_paths: tuple[str, ...]

    @property
    def markdown_paths(self) -> tuple[str, ...]:
        return tuple(
            path for path in self.file_paths if str(path).lower().endswith(".md")
        )

    @property
    def top_level_names(self) -> dict[str, Any]:
        return {
            PurePosixPath(str(entry.path)).name.lower(): entry for entry in self.top_level
        }


def scan_workspace(vm: Any, *, max_depth: int = 6) -> WorkspaceScan:
    top_level = tuple(list_top_level(vm))
    roots = tuple(entry.path for entry in top_level if entry.is_dir)
    if not roots:
        roots = ("/",)
    layout = resolve_workspace_layout(tuple(roots))
    file_paths = tuple(walk_files(vm, roots, max_depth=max_depth))
    return WorkspaceScan(
        top_level=top_level,
        roots=roots,
        layout=layout,
        file_paths=file_paths,
    )


@dataclass(frozen=True, slots=True)
class WorkspaceRuntimeSurface:
    """One-shot snapshot of workspace inventory + context payload.

    Concentrates the three independent reads the runtime needs at the
    start of every request (``scan_workspace`` + ``read_context_payload``
    + canonical document refs) so callers get a single, immutable handle
    instead of three parallel fetches.
    """

    scan: WorkspaceScan
    context_payload: dict[str, object]
    document_refs: tuple[str, ...]

    @property
    def layout(self) -> WorkspaceLayout:
        return self.scan.layout

    @property
    def file_paths(self) -> tuple[str, ...]:
        return self.scan.file_paths

    @property
    def markdown_paths(self) -> tuple[str, ...]:
        return self.scan.markdown_paths

    @property
    def top_level_names(self) -> dict[str, Any]:
        return self.scan.top_level_names


def load_workspace_runtime_surface(
    vm: PcmRuntimeClientSync,
    *,
    include_context_payload: bool = True,
) -> WorkspaceRuntimeSurface:
    scan = scan_workspace(vm)
    markdown_paths = scan.markdown_paths
    document_refs = tuple(
        dict.fromkeys(normalize_repo_path(path) for path in markdown_paths)
    )
    return WorkspaceRuntimeSurface(
        scan=scan,
        context_payload=read_context_payload(vm) if include_context_payload else {},
        document_refs=document_refs,
    )


# ---------------------------------------------------------------------------
# Document helpers: listing, classification, parsing
# ---------------------------------------------------------------------------


def list_top_level(vm) -> tuple:
    try:
        entries = list_entries(vm, "/")
    except Exception as exc:  # noqa: BLE001
        emit_runtime_exception(
            stage="context_persistence",
            operation="list_top_level",
            error=exc,
            extra={"path": "/"},
        )
        return ()
    return tuple(entry for entry in entries if entry.path.count("/") == 1)


def belongs_to_cast(path: str, layout: WorkspaceLayout) -> bool:
    return layout.path_has_role(normalize_repo_path(path), "cast")


def is_project_readme(path: str, layout: WorkspaceLayout) -> bool:
    normalized = normalize_repo_path(path)
    if PurePosixPath(normalized).name.lower() != "readme.md":
        return False
    return layout.path_has_role(normalized, "projects")


def belongs_to_finance(path: str, layout: WorkspaceLayout) -> bool:
    return layout.path_has_role(normalize_repo_path(path), "finance")


def belongs_to_inbox(path: str, layout: WorkspaceLayout) -> bool:
    normalized = normalize_repo_path(path)
    filename = PurePosixPath(normalized).name.upper()
    if filename in {"AGENTS.MD", "README.MD", "LANE.MD", "QUEUE.MD"}:
        return False
    return layout.path_has_role(normalized, "inbox")


def belongs_to_capture(path: str, layout: WorkspaceLayout) -> bool:
    return layout.path_has_role(normalize_repo_path(path), "capture")


def parse_markdown_document(text: str, path: str) -> dict[str, Any]:
    parsed = parse_frontmatter_with_mode(text, allow_invalid=True)
    frontmatter = dict(parsed.fields)
    normalized_path = normalize_repo_path(path)
    title = str(
        frontmatter.get("title")
        or frontmatter.get("name")
        or frontmatter.get("project_name")
        or ""
    ).strip()
    if not title:
        for raw_line in parsed.body.splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                break
    if not title:
        stem = PurePosixPath(normalized_path).stem
        title = stem.replace("_", " ").replace("-", " ").strip().title()
    return {
        **frontmatter,
        "path": normalized_path,
        "title": title,
        "name": frontmatter.get("project_name") or frontmatter.get("name") or title,
        "body": parsed.body.strip(),
        "raw_text": text,
        "frontmatter": frontmatter,
    }


def load_json_records(vm, singleton_path: str | None, directory_path: str | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if singleton_path:
        try:
            payload = parse_json_value(read_text(vm, singleton_path))
        except Exception as exc:  # noqa: BLE001
            emit_runtime_exception(
                stage="context_persistence",
                operation="load_json_singleton",
                error=exc,
                extra={"path": singleton_path},
            )
            payload = None
        if payload is not None:
            records.extend(
                dict(record)
                for record in records_from_payload(payload)
                if isinstance(record, Mapping)
            )
    if directory_path:
        try:
            entries = list_entries(vm, directory_path)
        except Exception as exc:  # noqa: BLE001
            emit_runtime_exception(
                stage="context_persistence",
                operation="list_json_directory",
                error=exc,
                extra={"path": directory_path},
            )
            return records
        for entry in entries:
            if entry.is_dir or not entry.path.lower().endswith(".json"):
                continue
            try:
                payload = parse_json_value(read_text(vm, entry.path))
            except Exception as exc:  # noqa: BLE001
                emit_runtime_exception(
                    stage="context_persistence",
                    operation="load_json_entry",
                    error=exc,
                    extra={"path": entry.path},
                )
                continue
            records.extend(
                dict(record)
                for record in records_from_payload(payload)
                if isinstance(record, Mapping)
            )
    return records


def queue_state_from_document(document: Mapping[str, Any]) -> QueueState | None:
    payload = dict(document.get("frontmatter") or {})
    payload["path"] = document.get("path")
    return QueueState.from_marker_payload(payload)


def inbox_item_from_document(document: Mapping[str, Any]) -> InboxItem | None:
    path = str(document.get("path") or "").strip()
    if not path:
        return None
    frontmatter = dict(document.get("frontmatter") or {})
    related_entities = coerce_tuple(frontmatter.get("related_entities"))
    related_projects = coerce_tuple(frontmatter.get("related_projects"))
    return InboxItem(
        path=normalize_repo_path(path),
        record_type=str(frontmatter.get("record_type") or "").strip(),
        subject=str(frontmatter.get("subject") or "").strip(),
        sender=str(frontmatter.get("sender") or frontmatter.get("from") or "").strip(),
        channel=str(frontmatter.get("channel") or "").strip(),
        body=str(document.get("body") or ""),
        to=coerce_tuple(frontmatter.get("to")),
        received_at=str(frontmatter.get("received_at") or "").strip(),
        cc=coerce_tuple(frontmatter.get("cc")),
        reply_to=str(frontmatter.get("reply_to") or "").strip(),
        source_channel=str(frontmatter.get("source_channel") or "").strip(),
        related_entities=related_entities,
        related_projects=related_projects,
    )


def capture_record_from_document(document: Mapping[str, Any]) -> dict[str, Any] | None:
    path = str(document.get("path") or "").strip()
    if not path:
        return None
    frontmatter = dict(document.get("frontmatter") or {})
    captured_on = str(
        frontmatter.get("captured_on")
        or frontmatter.get("date")
        or frontmatter.get("created_on")
        or ""
    ).strip()
    if not captured_on:
        return None
    return {
        "path": normalize_repo_path(path),
        "title": str(document.get("title") or frontmatter.get("title") or "").strip(),
        "captured_on": captured_on,
        "body": str(document.get("body") or "").strip(),
        "frontmatter": frontmatter,
    }


def coerce_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, Sequence):
        return tuple(str(item).strip() for item in value if str(item or "").strip())
    return ()


# ---------------------------------------------------------------------------
# Per-kind resource loaders
# ---------------------------------------------------------------------------


PrimeDocs = Callable[[Sequence[str]], list[dict[str, Any]]]


def load_cast_context(
    md_paths: Sequence[str],
    *,
    layout,
    prime_docs: PrimeDocs,
) -> tuple[tuple, tuple[dict[str, Any], ...]]:
    cast_docs = prime_docs(
        [
            path
            for path in md_paths
            if belongs_to_cast(path, layout)
            and PurePosixPath(path).name.lower() != "agents.md"
        ]
    )
    cast_entities = build_cast_entities(
        cast_docs,
        reference_date=datetime.now(timezone.utc).date(),
    )
    cast_records = tuple(cast_entity_to_mapping(entity) for entity in cast_entities)
    return cast_entities, cast_records


def load_project_context(
    md_paths: Sequence[str],
    *,
    layout,
    prime_docs: PrimeDocs,
    cast_entities: Sequence[object],
) -> tuple[tuple, tuple[dict[str, Any], ...]]:
    project_docs = prime_docs(
        [path for path in md_paths if is_project_readme(path, layout)]
    )
    projects = build_projects(project_docs, cast_entities)
    project_records = tuple(project_to_mapping(project) for project in projects)
    return projects, project_records


def load_finance_context(
    md_paths: Sequence[str],
    *,
    layout,
    prime_docs: PrimeDocs,
) -> tuple[FinanceRecord, ...]:
    finance_docs = prime_docs(
        [path for path in md_paths if belongs_to_finance(path, layout)]
    )
    return tuple(
        record
        for doc in finance_docs
        if (record := finance_record_from_document(doc)) is not None
    )


def load_accounts_context(
    vm,
    *,
    has_singleton: bool,
    has_directory: bool,
) -> tuple[tuple, tuple[dict[str, Any], ...]]:
    accounts = tuple(
        load_json_records(
            vm,
            "/accounts.json" if has_singleton else None,
            "/accounts" if has_directory else None,
        )
    )
    typed_accounts = tuple(
        account
        for account in (account_from_mapping(record) for record in accounts)
        if account is not None
    )
    return typed_accounts, accounts


def load_contacts_context(
    vm,
    *,
    has_singleton: bool,
    has_directory: bool,
) -> tuple[tuple, tuple[dict[str, Any], ...]]:
    contacts = tuple(
        load_json_records(
            vm,
            "/contacts.json" if has_singleton else None,
            "/contacts" if has_directory else None,
        )
    )
    typed_contacts = contacts_from_mappings(contacts)
    return typed_contacts, contacts


def load_message_and_queue_context(
    md_paths: Sequence[str],
    *,
    layout,
    prime_docs: PrimeDocs,
    include_messages: bool,
    include_queue: bool,
) -> tuple[tuple[Any, ...], tuple[QueueState, ...]]:
    all_docs = prime_docs(md_paths)
    message_records: tuple[Any, ...] = ()
    queue_states: tuple[QueueState, ...] = ()
    if include_messages:
        message_records = tuple(
            record
            for doc in all_docs
            for record in message_records_from_document(doc, layout=layout)
        )
    if include_queue:
        queue_states = tuple(
            state
            for doc in all_docs
            if (state := queue_state_from_document(doc)) is not None
        )
    return message_records, queue_states


def load_inbox_context(
    md_paths: Sequence[str],
    *,
    layout,
    prime_docs: PrimeDocs,
) -> tuple[InboxItem, ...]:
    inbox_docs = prime_docs([path for path in md_paths if belongs_to_inbox(path, layout)])
    return tuple(
        item
        for doc in inbox_docs
        if (item := inbox_item_from_document(doc)) is not None
    )


def load_capture_context(
    md_paths: Sequence[str],
    *,
    layout,
    prime_docs: PrimeDocs,
) -> tuple[tuple[dict[str, Any], ...], tuple]:
    capture_docs = prime_docs(
        [path for path in md_paths if belongs_to_capture(path, layout)]
    )
    capture_records = tuple(
        record
        for doc in capture_docs
        if (record := capture_record_from_document(doc)) is not None
    )
    capture_projections = capture_records_from_mappings(capture_records)
    return capture_records, capture_projections


# ---------------------------------------------------------------------------
# Resource assembly: orchestrate per-kind loaders based on needs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LoadedRuntimeResources:
    cast_entities: tuple = ()
    cast_records: tuple[dict[str, Any], ...] = ()
    projects: tuple = ()
    project_records: tuple[dict[str, Any], ...] = ()
    finance_records: tuple[FinanceRecord, ...] = ()
    typed_accounts: tuple = ()
    accounts: tuple[dict[str, Any], ...] = ()
    typed_contacts: tuple = ()
    contacts: tuple[dict[str, Any], ...] = ()
    message_records: tuple[Any, ...] = ()
    queue_states: tuple[QueueState, ...] = ()
    inbox_items: tuple[InboxItem, ...] = ()
    capture_records: tuple[dict[str, Any], ...] = ()
    capture_projections: tuple = ()


def assemble_workspace_runtime_resources(
    vm,
    *,
    md_paths: tuple[str, ...],
    layout,
    reader,
    needs: frozenset[str],
) -> LoadedRuntimeResources:
    cast_entities: tuple = ()
    cast_records: tuple[dict[str, Any], ...] = ()
    projects: tuple = ()
    project_records: tuple[dict[str, Any], ...] = ()
    finance_records: tuple[FinanceRecord, ...] = ()
    typed_accounts: tuple = ()
    accounts: tuple[dict[str, Any], ...] = ()
    typed_contacts: tuple = ()
    contacts: tuple[dict[str, Any], ...] = ()
    message_records: tuple[Any, ...] = ()
    queue_states: tuple[QueueState, ...] = ()
    inbox_items: tuple[InboxItem, ...] = ()
    capture_records: tuple[dict[str, Any], ...] = ()
    capture_projections: tuple = ()

    if "cast" in needs or "project" in needs:
        cast_entities, cast_records = load_cast_context(
            md_paths,
            layout=layout,
            prime_docs=reader.prime,
        )

    if "project" in needs:
        projects, project_records = load_project_context(
            md_paths,
            layout=layout,
            prime_docs=reader.prime,
            cast_entities=cast_entities,
        )

    if "finance" in needs:
        finance_records = load_finance_context(
            md_paths,
            layout=layout,
            prime_docs=reader.prime,
        )

    if "accounts" in needs:
        typed_accounts, accounts = load_accounts_context(
            vm,
            has_singleton=reader.has_top_level("accounts.json"),
            has_directory=reader.has_top_level("accounts"),
        )

    if "contacts" in needs:
        typed_contacts, contacts = load_contacts_context(
            vm,
            has_singleton=reader.has_top_level("contacts.json"),
            has_directory=reader.has_top_level("contacts"),
        )

    if "messages" in needs or "queue" in needs:
        message_records, queue_states = load_message_and_queue_context(
            md_paths,
            layout=layout,
            prime_docs=reader.prime,
            include_messages="messages" in needs,
            include_queue="queue" in needs,
        )

    if "inbox" in needs:
        inbox_items = load_inbox_context(
            md_paths,
            layout=layout,
            prime_docs=reader.prime,
        )

    if "capture" in needs:
        capture_records, capture_projections = load_capture_context(
            md_paths,
            layout=layout,
            prime_docs=reader.prime,
        )

    return LoadedRuntimeResources(
        cast_entities=cast_entities,
        cast_records=cast_records,
        projects=projects,
        project_records=project_records,
        finance_records=finance_records,
        typed_accounts=typed_accounts,
        accounts=accounts,
        typed_contacts=typed_contacts,
        contacts=contacts,
        message_records=message_records,
        queue_states=queue_states,
        inbox_items=inbox_items,
        capture_records=capture_records,
        capture_projections=capture_projections,
    )


__all__ = [
    "LoadedRuntimeResources",
    "WorkspaceScan",
    "assemble_workspace_runtime_resources",
    "belongs_to_capture",
    "belongs_to_cast",
    "belongs_to_finance",
    "belongs_to_inbox",
    "capture_record_from_document",
    "inbox_item_from_document",
    "is_project_readme",
    "list_top_level",
    "load_accounts_context",
    "load_capture_context",
    "load_cast_context",
    "load_contacts_context",
    "load_finance_context",
    "load_inbox_context",
    "load_json_records",
    "load_message_and_queue_context",
    "load_project_context",
    "parse_markdown_document",
    "queue_state_from_document",
    "scan_workspace",
]
