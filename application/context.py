from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.accounts import Account, Contact
from domain.cast import CastEntity
from domain.capture import CaptureRecordProjection
from domain.finance import FinanceRecord
from domain.inbox import InboxItem
from domain.process import QueueState
from domain.projects import Project
from domain.workspace import WorkspaceLayout, WorkspacePolicies


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    context_payload: dict[str, object]
    workspace_layout: WorkspaceLayout
    cast_entities: tuple[CastEntity, ...]
    cast_records: tuple[dict[str, Any], ...]
    projects: tuple[Project, ...]
    project_records: tuple[dict[str, Any], ...]
    finance_records: tuple[FinanceRecord, ...]
    typed_accounts: tuple[Account, ...]
    accounts: tuple[dict[str, Any], ...]
    typed_contacts: tuple[Contact, ...]
    contacts: tuple[dict[str, Any], ...]
    message_records: tuple[Any, ...]
    queue_states: tuple[QueueState, ...]
    inbox_items: tuple[InboxItem, ...]
    capture_projections: tuple[CaptureRecordProjection, ...]
    capture_records: tuple[dict[str, Any], ...]
    document_refs: tuple[str, ...]
    workspace_policies: WorkspacePolicies = WorkspacePolicies()


__all__ = ["RuntimeContext"]
