from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from domain.cast import CastEntity
from application.executors import (
    resolve_finance_document_ingest_workflow,
    resolve_finance_payment_workflow,
    resolve_invoice_email_workflow,
)
from application.workflows.inbox_workflow import (
    FinanceDocumentIngestWorkflowStep,
    FinancePaymentWorkflowStep,
    InvoiceEmailWorkflowStep,
)
from domain.finance import FinanceRecord
from domain.inbox import InboxItem
from formats.finance_markdown import build_finance_frontmatter_updates
from formats.frontmatter import merge_frontmatter_fields
from formats.markdown_tables import coerce_markdown_number


@dataclass(frozen=True, slots=True)
class WorkflowWrite:
    path: str
    content: str


@dataclass(frozen=True, slots=True)
class InboxWorkflowExecutionPlan:
    status: Literal["invoke_command", "clarify_missing", "blocked", "resolved"]
    message: str
    reason_code: str
    grounding_refs: tuple[str, ...] = ()
    command: object | None = None
    writes: tuple[WorkflowWrite, ...] = ()


def plan_invoice_email_workflow_step(
    next_step: InvoiceEmailWorkflowStep,
    *,
    inbox_item: InboxItem | None,
    finance_records: Sequence[FinanceRecord],
    cast_entities: Sequence[CastEntity],
    available_channels: Sequence[str],
    workflow_interpretation_port=None,
) -> InboxWorkflowExecutionPlan:
    if inbox_item is None:
        refs = (next_step.evidence_ref,) if next_step.evidence_ref else ()
        return InboxWorkflowExecutionPlan(
            status="clarify_missing",
            message="Inbox invoice workflow lost its source inbox item.",
            reason_code="invoice_email_inbox_item_missing",
            grounding_refs=refs,
        )
    plan = resolve_invoice_email_workflow(
        request=next_step.request,
        inbox_item=inbox_item,
        finance_records=finance_records,
        cast_entities=cast_entities,
        available_channels=available_channels,
        resolve_cast_identity_subset=(
            workflow_interpretation_port.resolve_cast_identity_subset
            if workflow_interpretation_port is not None
            else None
        ),
        select_invoice_record_subset=(
            workflow_interpretation_port.select_finance_record_subset
            if workflow_interpretation_port is not None
            else None
        ),
    )
    refs = tuple(dict.fromkeys((*plan.grounding_refs, next_step.evidence_ref)))
    if plan.status == "blocked":
        return InboxWorkflowExecutionPlan(
            status="blocked",
            message=plan.message,
            reason_code=plan.reason_code,
            grounding_refs=refs,
        )
    if plan.command is None:
        return InboxWorkflowExecutionPlan(
            status="clarify_missing",
            message=plan.message,
            reason_code=plan.reason_code,
            grounding_refs=refs,
        )
    return InboxWorkflowExecutionPlan(
        status="invoke_command",
        message=plan.message,
        reason_code=plan.reason_code,
        grounding_refs=refs,
        command=plan.command,
    )


def plan_finance_payment_workflow_step(
    next_step: FinancePaymentWorkflowStep,
    *,
    finance_records: Sequence[FinanceRecord],
) -> InboxWorkflowExecutionPlan:
    plan = resolve_finance_payment_workflow(
        request=next_step.request,
        finance_records=finance_records,
    )
    refs = tuple(dict.fromkeys((*plan.grounding_refs, next_step.evidence_ref)))
    if plan.status == "blocked":
        return InboxWorkflowExecutionPlan(
            status="blocked",
            message=plan.message,
            reason_code=plan.reason_code,
            grounding_refs=refs,
        )
    if plan.command is None:
        return InboxWorkflowExecutionPlan(
            status="clarify_missing",
            message=plan.message,
            reason_code=plan.reason_code,
            grounding_refs=refs,
        )
    return InboxWorkflowExecutionPlan(
        status="invoke_command",
        message=plan.message,
        reason_code=plan.reason_code,
        grounding_refs=refs,
        command=plan.command,
    )


def plan_finance_document_ingest_workflow_step(
    next_step: FinanceDocumentIngestWorkflowStep,
    *,
    finance_records: Sequence[FinanceRecord],
    cast_entities: Sequence[CastEntity],
    read_note: Callable[[str], str],
    workflow_interpretation_port=None,
) -> InboxWorkflowExecutionPlan:
    plan = resolve_finance_document_ingest_workflow(
        request=next_step.request,
        finance_records=finance_records,
        cast_entities=cast_entities,
        select_finance_record_subset=(
            workflow_interpretation_port.select_finance_record_subset
            if workflow_interpretation_port is not None
            else None
        ),
        resolve_cast_identity_subset=(
            workflow_interpretation_port.resolve_cast_identity_subset
            if workflow_interpretation_port is not None
            else None
        ),
    )
    refs = tuple(dict.fromkeys((*plan.grounding_refs, next_step.evidence_ref)))
    if plan.status != "resolved" or not plan.target_paths:
        return InboxWorkflowExecutionPlan(
            status="clarify_missing",
            message=plan.message,
            reason_code=plan.reason_code,
            grounding_refs=refs,
        )
    explicit_targets = bool(next_step.request.target_paths)
    writes: list[WorkflowWrite] = []
    for path in plan.target_paths:
        resolved_path = _resolve_readable_finance_path(path, finance_records)
        try:
            note_text = read_note(resolved_path)
        except Exception:  # noqa: BLE001
            return InboxWorkflowExecutionPlan(
                status="clarify_missing",
                message=f"Finance document ingest could not read {resolved_path}.",
                reason_code="finance_document_ingest_target_unreadable",
                grounding_refs=refs,
            )
        updates = build_finance_frontmatter_updates(note_text, resolved_path)
        if updates is None:
            return InboxWorkflowExecutionPlan(
                status="clarify_missing",
                message=f"Finance document ingest could not derive canonical frontmatter from {resolved_path}.",
                reason_code=(
                    "finance_document_ingest_explicit_target_invalid"
                    if explicit_targets
                    else "finance_document_ingest_target_invalid"
                ),
                grounding_refs=refs,
            )
        if "total_eur" in updates:
            coerced_total = coerce_markdown_number(updates["total_eur"])
            if coerced_total is not None:
                updates["total_eur"] = coerced_total
        writes.append(
            WorkflowWrite(
                path=resolved_path,
                content=merge_frontmatter_fields(note_text, updates),
            )
        )
    return InboxWorkflowExecutionPlan(
        status="resolved",
        message=f"Processed OCR/frontmatter ingest for {len(writes)} finance note(s).",
        reason_code="finance_document_ingest_workflow_resolved",
        grounding_refs=tuple(dict.fromkeys((*tuple(write.path for write in writes), *refs))),
        writes=tuple(writes),
    )


def _normalize_repo_path(value: object) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    return text if text.startswith("/") else f"/{text}"

def _basename_variants(value: object) -> tuple[str, ...]:
    basename = PurePosixPath(_normalize_repo_path(value)).name
    if not basename:
        return ()
    variants = [basename]
    stripped = basename.lstrip("_")
    if stripped and stripped != basename:
        variants.append(stripped)
    if "__" in basename:
        _, suffix = basename.split("__", 1)
        if suffix:
            variants.append(suffix)
            stripped_suffix = suffix.lstrip("_")
            if stripped_suffix and stripped_suffix != suffix:
                variants.append(stripped_suffix)
    return tuple(dict.fromkeys(variant for variant in variants if variant))


def _resolve_readable_finance_path(
    requested_path: str,
    finance_records: Sequence[FinanceRecord],
) -> str:
    normalized_requested = _normalize_repo_path(requested_path)
    if not normalized_requested:
        return normalized_requested

    record_paths = tuple(
        _normalize_repo_path(record.path)
        for record in finance_records
        if _normalize_repo_path(record.path)
    )
    if normalized_requested in record_paths:
        return normalized_requested

    requested_variants = set(_basename_variants(normalized_requested))
    if not requested_variants:
        return normalized_requested
    candidates = tuple(
        path
        for path in record_paths
        if requested_variants & set(_basename_variants(path))
    )
    if len(candidates) == 1:
        return candidates[0]
    return normalized_requested


__all__ = [
    "InboxWorkflowExecutionPlan",
    "WorkflowWrite",
    "plan_finance_document_ingest_workflow_step",
    "plan_finance_payment_workflow_step",
    "plan_invoice_email_workflow_step",
]
