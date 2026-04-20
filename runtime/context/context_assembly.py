"""Entry-point for executable step context: what is needed, how to read it.

Consolidates the former `context_loader`, `context_needs`, and
`context_reading` modules.

Responsibilities:
- ``needed_kinds_for_intent`` / ``needed_kinds_for_command``: map a typed
  command/intent to the minimal set of context kinds that must be loaded.
- ``ContextDocumentReader`` / ``build_context_document_reader``: cached
  parser/reader adapter that turns VM markdown paths into parsed documents.
- ``load_runtime_context``: compose a ``RuntimeContext`` for the step by
  scanning the workspace, building the reader, and delegating to the
  persistence layer to assemble per-kind resources.
- ``load_workspace_policies``: lightweight AGENTS.MD policy loading used
  before typed extraction runs.
"""

from __future__ import annotations

from typing import Any

from application.context import RuntimeContext
try:
    from bitgn.vm.pcm_connect import PcmRuntimeClientSync
except ModuleNotFoundError:  # pragma: no cover - local test fallback only
    PcmRuntimeClientSync = Any  # type: ignore[assignment]

from domain.workspace import WorkspacePolicies
from runtime.context.context_persistence import (
    assemble_workspace_runtime_resources,
    load_workspace_runtime_surface,
    queue_state_from_document,
)
from runtime.context.context_reader import ContextDocumentReader, build_context_document_reader
from runtime.context.context_needs import (
    ALL_CONTEXT_KINDS,
    ContextKind,
    needed_kinds_for_command,
    needed_kinds_for_intent,
)
from runtime.context.workspace_policy_loader import load_workspace_policies_from_paths

def load_runtime_context(
    vm: PcmRuntimeClientSync,
    *,
    needed_kinds: frozenset[ContextKind] | None = None,
) -> RuntimeContext:
    surface = load_workspace_runtime_surface(vm)
    layout = surface.layout

    needs = needed_kinds if needed_kinds is not None else ALL_CONTEXT_KINDS
    reader = build_context_document_reader(
        vm,
        top_level_names=surface.top_level_names,
    )

    resources = assemble_workspace_runtime_resources(
        vm,
        md_paths=surface.markdown_paths,
        layout=layout,
        reader=reader,
        needs=needs,
    )

    workspace_policies = load_workspace_policies_from_paths(
        vm,
        layout=layout,
        file_paths=surface.file_paths,
    )

    return RuntimeContext(
        context_payload=surface.context_payload,
        workspace_layout=layout,
        cast_entities=resources.cast_entities,
        cast_records=resources.cast_records,
        projects=resources.projects,
        project_records=resources.project_records,
        finance_records=resources.finance_records,
        typed_accounts=resources.typed_accounts,
        accounts=resources.accounts,
        typed_contacts=resources.typed_contacts,
        contacts=resources.contacts,
        message_records=resources.message_records,
        queue_states=resources.queue_states,
        inbox_items=resources.inbox_items,
        capture_projections=resources.capture_projections,
        capture_records=resources.capture_records,
        document_refs=surface.document_refs,
        workspace_policies=workspace_policies,
    )


def load_workspace_policies(vm: "PcmRuntimeClientSync") -> WorkspacePolicies:
    """Public helper: load AGENTS.MD policy surface without full context.

    The orchestrator needs these before typed extraction runs so the
    LLM sees workspace conventions; loading the full context is
    intentionally deferred until after routing decides which kinds
    are needed.
    """

    surface = load_workspace_runtime_surface(vm, include_context_payload=False)
    return load_workspace_policies_from_paths(
        vm,
        layout=surface.layout,
        file_paths=surface.file_paths,
    )


def _queue_state_from_document(document: dict[str, Any]):
    return queue_state_from_document(document)


__all__ = [
    "ContextDocumentReader",
    "build_context_document_reader",
    "load_runtime_context",
    "load_workspace_policies",
    "needed_kinds_for_command",
    "needed_kinds_for_intent",
]
