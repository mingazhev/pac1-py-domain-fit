"""Mutation persistence: VM writeback helpers + selection helpers.

Consolidates the former ``runtime.mutation_writeback`` and
``runtime.mutation_selection`` modules. All public names from both are
re-exported unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from application.context import RuntimeContext
from application.mutations import FinanceRecordWritePlan, MutationStepResult
from domain.finance import FinanceRecordIdentityCriteria, resolve_finance_attachment
from domain.process.queue_state import QueueMarker
from domain.workspace import DEFAULT_WORKSPACE_LAYOUT
from formats.frontmatter import merge_frontmatter_fields, strip_frontmatter
from formats.markdown_tables import coerce_markdown_number
from loaders.finance import extract_finance_line_items, extract_finance_metadata
from runtime.io.vm_tools import delete_path, read_text, write_text
from task_routing import OutboxDraftCommand
from telemetry.trace import emit_runtime_exception

_WORKFLOW_BY_ASSISTANT: dict[str, tuple[str, str]] = {
    "nora": ("nora_mcp", "vault2"),
    "nora_mcp": ("nora_mcp", "vault2"),
}

_FINANCE_METADATA_KEYS = (
    "record_type",
    "bill_id",
    "invoice_number",
    "alias",
    "purchased_on",
    "issued_on",
    "total_eur",
    "counterparty",
    "project",
    "related_entity",
    "payment_state",
    "settlement_reference",
    "settlement_channel",
    "settlement_date",
)


# ---------------------------------------------------------------------------
# Writeback helpers (formerly runtime.mutation_writeback)
# ---------------------------------------------------------------------------


def vm_delete_many(vm: Any, paths: tuple[str, ...]) -> None:
    for path in paths:
        try:
            delete_path(vm, path)
        except Exception as exc:  # noqa: BLE001
            emit_runtime_exception(
                stage="mutation_writeback",
                operation="delete_path",
                error=exc,
                extra={"path": path},
            )
            continue


def lift_finance_metadata(existing: str, path: str) -> dict[str, object]:
    try:
        body = strip_frontmatter(existing)
        metadata = extract_finance_metadata(body)
    except Exception as exc:  # noqa: BLE001
        emit_runtime_exception(
            stage="mutation_writeback",
            operation="extract_finance_metadata",
            error=exc,
            extra={"path": path},
        )
        metadata = {}
    updates: dict[str, object] = {}
    normalized_path = path.lower()
    if metadata:
        for key in _FINANCE_METADATA_KEYS:
            value = str(metadata.get(key) or "").strip()
            if value:
                updates[key] = value
        if "total_eur" in updates:
            coerced = coerce_markdown_number(updates["total_eur"])
            if coerced is not None:
                updates["total_eur"] = coerced
        try:
            lines = extract_finance_line_items(body)
        except Exception as exc:  # noqa: BLE001
            emit_runtime_exception(
                stage="mutation_writeback",
                operation="extract_finance_line_items",
                error=exc,
                extra={"path": path},
            )
            lines = ()
        rendered: list[dict[str, object]] = []
        for item in lines:
            item_name = str(item.get("item") or "").strip()
            if not item_name:
                continue
            entry: dict[str, object] = {"item": item_name}
            quantity = item.get("qty") if "qty" in item else item.get("quantity")
            if quantity is not None:
                entry["quantity"] = quantity
            if item.get("unit_eur") is not None:
                entry["unit_eur"] = item["unit_eur"]
            if item.get("line_eur") is not None:
                entry["line_eur"] = item["line_eur"]
            rendered.append(entry)
        if rendered:
            updates["lines"] = rendered
    if "record_type" not in updates:
        if "/invoices/" in normalized_path:
            updates["record_type"] = "invoice"
        elif "/purchases/" in normalized_path:
            updates["record_type"] = "bill"
    return updates


def vm_merge_frontmatter(
    vm: Any,
    path: str,
    updates: dict[str, str],
    *,
    layout=None,
) -> None:
    try:
        existing = read_text(vm, path)
    except Exception as exc:  # noqa: BLE001
        emit_runtime_exception(
            stage="mutation_writeback",
            operation="read_existing_frontmatter_target",
            error=exc,
            extra={"path": path},
        )
        return
    if not existing:
        return
    normalized_path = path.lower()
    is_finance = bool(
        normalized_path.endswith(".md")
        and (
            layout.path_has_role(path, "finance")
            if layout is not None
            else normalized_path.startswith(
                f"{(DEFAULT_WORKSPACE_LAYOUT.primary_finance_root() or '/finance').lower()}/"
            )
        )
    )
    combined: dict[str, object] = {}
    if is_finance:
        canonical = lift_finance_metadata(existing, path)
        if canonical:
            combined.update(canonical)
    combined.update(updates)
    if not combined:
        return
    try:
        merged = merge_frontmatter_fields(existing, combined)
    except Exception as exc:  # noqa: BLE001
        emit_runtime_exception(
            stage="mutation_writeback",
            operation="merge_frontmatter_fields",
            error=exc,
            extra={"path": path},
        )
        return
    try:
        write_text(vm, path, merged)
    except Exception as exc:  # noqa: BLE001
        emit_runtime_exception(
            stage="mutation_writeback",
            operation="write_merged_frontmatter",
            error=exc,
            extra={"path": path},
        )
        return


def vm_write_finance_content(
    vm: Any,
    path: str,
    content: str,
    *,
    extra_updates: dict[str, object] | None = None,
) -> None:
    combined = lift_finance_metadata(content, path)
    if extra_updates:
        combined.update(extra_updates)
    final_content = content
    if combined:
        try:
            final_content = merge_frontmatter_fields(content, combined)
        except Exception as exc:  # noqa: BLE001
            emit_runtime_exception(
                stage="mutation_writeback",
                operation="merge_written_finance_content",
                error=exc,
                extra={"path": path},
            )
            final_content = content
    try:
        write_text(vm, path, final_content)
    except Exception as exc:  # noqa: BLE001
        emit_runtime_exception(
            stage="mutation_writeback",
            operation="write_finance_content",
            error=exc,
            extra={"path": path},
        )
        return


def execute_finance_write_plan(
    vm: Any,
    plan: FinanceRecordWritePlan,
    *,
    layout,
) -> None:
    if vm is None or plan.result.status != "resolved" or not plan.result.grounding_refs:
        return
    path = plan.result.grounding_refs[0]
    if plan.rendered_content is not None:
        vm_write_finance_content(
            vm,
            path,
            plan.rendered_content,
            extra_updates=plan.frontmatter_updates,
        )
        return
    if plan.frontmatter_updates:
        vm_merge_frontmatter(
            vm,
            path,
            plan.frontmatter_updates,
            layout=layout,
        )


def vm_queue_stamp_markers(
    vm: Any,
    paths: tuple[str, ...],
    *,
    target: str | None,
    workflow_name: str | None,
    context_time: str,
) -> None:
    sorted_paths = tuple(sorted(paths, key=str.lower))
    if not sorted_paths:
        return

    raw_assistant = (target or "nora").strip().lower()
    default_workflow, default_target = _WORKFLOW_BY_ASSISTANT.get(
        raw_assistant, (f"{raw_assistant}_migration", raw_assistant)
    )
    effective_workflow = (workflow_name or default_workflow).strip() or default_workflow
    effective_target = default_target
    batch_timestamp = (context_time or "").strip() or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    for index, path in enumerate(sorted_paths, start=1):
        marker = QueueMarker.initial(
            workflow_name=effective_workflow,
            batch_timestamp=batch_timestamp,
            order_id=index,
            target=effective_target,
        )
        vm_merge_frontmatter(vm, path, marker.as_frontmatter_fields())


def collect_project_paths(
    result: MutationStepResult, context: RuntimeContext
) -> tuple[str, ...]:
    root = (result.message or "").strip()
    if not root:
        return ()
    prefix = root if root.endswith("/") else f"{root}/"
    paths = [
        ref
        for ref in context.document_refs
        if ref == root or ref.startswith(prefix)
    ]
    if root not in paths:
        paths.append(root)
    return tuple(dict.fromkeys(paths))


def read_existing_finance_record_text(
    vm: Any,
    record: object | None,
) -> str | None:
    if vm is None or record is None:
        return None
    path = str(getattr(record, "path", "") or "").strip()
    if not path:
        return None
    try:
        return read_text(vm, path)
    except Exception as exc:  # noqa: BLE001
        emit_runtime_exception(
            stage="mutation_writeback",
            operation="read_existing_finance_record",
            error=exc,
            extra={"path": path},
        )
        return None


# ---------------------------------------------------------------------------
# Selection helpers (formerly runtime.mutation_selection)
# ---------------------------------------------------------------------------


def build_finance_selector(gateway: Any, model: str | None):
    if gateway is None or not model:
        return None
    from task_routing.record_selector import llm_select_finance_records

    def _select(instruction: str, candidates):
        return llm_select_finance_records(
            gateway, model, instruction=instruction, records=candidates
        )

    return _select


def resolve_outbox_attachments(
    command: OutboxDraftCommand,
    *,
    task_text: str,
    context: RuntimeContext,
    gateway: Any,
    model: str | None,
) -> tuple[str, ...]:
    existing = tuple(
        str(path).strip()
        for path in command.attachments
        if str(path or "").strip()
    )
    deterministic = deterministic_outbox_attachments(
        command,
        context=context,
        task_text=task_text,
    )
    if existing and deterministic:
        return tuple(dict.fromkeys([*deterministic, *existing]))
    if existing:
        return existing
    if deterministic:
        return deterministic
    if gateway is None or not model or not context.finance_records:
        return existing
    if str(command.authorization_kind or "").strip() != "workflow_policy":
        return existing
    selector = build_finance_selector(gateway, model)
    if selector is None:
        return existing
    try:
        picked = selector(task_text, context.finance_records)
    except Exception as exc:  # noqa: BLE001
        emit_runtime_exception(
            stage="mutation_selection",
            operation="llm_select_finance_records",
            error=exc,
        )
        return existing
    selected_paths = tuple(
        str(context.finance_records[index].path or "").strip()
        for index in picked
        if isinstance(index, int)
        and 0 <= index < len(context.finance_records)
        and str(context.finance_records[index].path or "").strip()
    )
    if not selected_paths:
        return existing
    return tuple(dict.fromkeys(selected_paths))


def deterministic_outbox_attachments(
    command: OutboxDraftCommand,
    *,
    context: RuntimeContext,
    task_text: str = "",
) -> tuple[str, ...]:
    if not context.finance_records:
        return ()
    criteria = FinanceRecordIdentityCriteria(
        record_type=command.attachment_record_type,
        counterparty=str(command.attachment_counterparty or "").strip(),
        reference_number=str(command.attachment_reference_number or "").strip(),
        alias=str(command.attachment_alias or "").strip(),
        project=str(command.attachment_project or "").strip(),
        related_entity=str(command.attachment_related_entity or "").strip(),
        date=str(command.attachment_date or "").strip(),
    )
    path = resolve_finance_attachment(
        context.finance_records,
        criteria=criteria,
        record_hint=attachment_record_hint(command),
    )
    if not path:
        return ()
    return (path,)


def attachment_record_hint(
    command: OutboxDraftCommand,
) -> str:
    explicit = str(getattr(command, "attachment_record_hint", "") or "").strip()
    return explicit


__all__ = [
    "attachment_record_hint",
    "build_finance_selector",
    "collect_project_paths",
    "deterministic_outbox_attachments",
    "execute_finance_write_plan",
    "lift_finance_metadata",
    "read_existing_finance_record_text",
    "resolve_outbox_attachments",
    "vm_delete_many",
    "vm_merge_frontmatter",
    "vm_queue_stamp_markers",
    "vm_write_finance_content",
]
