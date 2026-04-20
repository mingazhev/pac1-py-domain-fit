"""Mutation step dispatch + per-command handlers.

Consolidates the former ``runtime.mutation_pipeline`` (dispatch) and
``runtime.mutation_handlers`` (per-command handlers) modules.
"""

from __future__ import annotations

from typing import Any

from application.context import RuntimeContext
from application.mutations import (
    resolve_finance_bulk_delete,
    resolve_finance_create_record,
    resolve_finance_target_record,
    resolve_finance_update_record,
    resolve_outbox_draft,
    resolve_project_delete,
    resolve_queue_markdown_mutation,
)
from application.ports import QueryResolutionPort
from domain.process import decide_blocked
from runtime.authorization.authorization import (
    command_has_authorization,
    missing_authorization_result,
)
from runtime.io.mutation_persistence import (
    build_finance_selector,
    collect_project_paths,
    execute_finance_write_plan,
    read_existing_finance_record_text,
    resolve_outbox_attachments,
    vm_delete_many,
    vm_queue_stamp_markers,
)
from runtime.io.mutation_result_mapping import (
    MutationExecutionResult,
    map_fallback_result,
    map_mutation_result,
    run_mutation_fallback,
    unsupported_mutation,
)
from runtime.io.vm_tools import write_text
from task_routing import (
    FinanceMutationCommand,
    OutboxDraftCommand,
    ProjectMutationCommand,
    QueueMutationCommand,
    StepPolicyClass,
    TypedStep,
    contract_for_command,
)
from telemetry.trace import emit_runtime_exception


# ---------------------------------------------------------------------------
# Dispatch (formerly runtime.mutation_pipeline)
# ---------------------------------------------------------------------------


def execute_mutation_step(
    command: TypedStep,
    *,
    task_text: str,
    context: RuntimeContext,
    query_resolution_port: QueryResolutionPort | None,
    vm: Any = None,
    gateway: Any = None,
    model: str | None = None,
) -> MutationExecutionResult:
    contract = contract_for_command(command)
    if contract.policy_class is StepPolicyClass.AUTHZ_REQUIRED:
        blocker = _check_authorization(command)
        if blocker is not None:
            return blocker

    if isinstance(command, QueueMutationCommand):
        return handle_queue_mutation(
            command,
            context=context,
            vm=vm,
        )

    if isinstance(command, OutboxDraftCommand):
        return handle_outbox_draft(
            command,
            task_text=task_text,
            context=context,
            vm=vm,
            gateway=gateway,
            model=model,
        )

    if isinstance(command, ProjectMutationCommand):
        return handle_project_mutation(
            command,
            task_text=task_text,
            context=context,
            query_resolution_port=query_resolution_port,
            vm=vm,
        )

    if isinstance(command, FinanceMutationCommand):
        return handle_finance_mutation(
            command,
            task_text=task_text,
            context=context,
            vm=vm,
            gateway=gateway,
            model=model,
        )

    return unsupported_mutation("mutation_step_unsupported")


def _check_authorization(command: TypedStep) -> MutationExecutionResult | None:
    if not command_has_authorization(command):
        return missing_authorization_result()
    return None


# ---------------------------------------------------------------------------
# Per-command handlers (formerly runtime.mutation_handlers)
# ---------------------------------------------------------------------------


def handle_queue_mutation(
    command: QueueMutationCommand,
    *,
    context: RuntimeContext,
    vm: Any,
) -> MutationExecutionResult:
    result = resolve_queue_markdown_mutation(
        context.queue_states,
        target_names=command.target_names,
        document_refs=context.document_refs,
    )
    if result.status == "resolved" and vm is not None and result.grounding_refs:
        vm_queue_stamp_markers(
            vm,
            result.grounding_refs,
            target=command.target_workflow,
            workflow_name=command.workflow_name,
            context_time=str(
                context.context_payload.get("time")
                if context.context_payload
                else ""
            ),
        )
    return map_mutation_result(result)


def handle_outbox_draft(
    command: OutboxDraftCommand,
    *,
    task_text: str,
    context: RuntimeContext,
    vm: Any,
    gateway: Any,
    model: str | None,
) -> MutationExecutionResult:
    attachments = resolve_outbox_attachments(
        command,
        task_text=task_text,
        context=context,
        gateway=gateway,
        model=model,
    )
    result, path, content = resolve_outbox_draft(
        to=command.to,
        subject=command.subject,
        body=command.body,
        attachments=attachments,
        related_entities=command.related_entities,
        source_channel=command.source_channel,
        created_at=command.created_at,
        send_state=command.send_state,
        context_payload=context.context_payload,
        outbox_root=context.workspace_layout.primary_outbox_sink_root(),
    )
    if result.status == "resolved" and vm is not None and path and content is not None:
        try:
            write_text(vm, path, content)
        except Exception as exc:  # noqa: BLE001
            emit_runtime_exception(
                stage="mutation_handlers",
                operation="write_outbox_draft",
                error=exc,
                extra={"path": path},
            )
    return map_mutation_result(result)


def handle_project_mutation(
    command: ProjectMutationCommand,
    *,
    task_text: str,
    context: RuntimeContext,
    query_resolution_port: QueryResolutionPort | None,
    vm: Any,
) -> MutationExecutionResult:
    if command.action != "delete":
        return unsupported_mutation("project_mutation_variant_unsupported")
    result = resolve_project_delete(
        context.project_records,
        context.projects,
        project_reference=command.project_reference,
        authorization_kind=command.authorization_kind,
        authorized_by=command.authorized_by,
        task_text=task_text,
        fallback_refs=context.document_refs,
        query_resolution_port=query_resolution_port,
    )
    if result.status == "resolved" and vm is not None:
        vm_delete_many(vm, collect_project_paths(result, context))
    return map_mutation_result(result)


def handle_finance_mutation(
    command: FinanceMutationCommand,
    *,
    task_text: str,
    context: RuntimeContext,
    vm: Any,
    gateway: Any,
    model: str | None,
) -> MutationExecutionResult:
    if command.action in {"create_invoice", "create_bill"}:
        result, path, content = resolve_finance_create_record(
            context.finance_records,
            action=command.action,
            record_type=command.record_type,
            counterparty=command.counterparty,
            amount=command.amount,
            alias=command.alias,
            invoice_number=command.invoice_number,
            date=command.date,
            project=command.project,
            related_entity=command.related_entity,
            notes=command.notes,
            line_items=command.line_items,
            currency=command.currency,
            finance_root=context.workspace_layout.primary_finance_root(),
        )
        if result.status == "resolved" and vm is not None and path and content is not None:
            try:
                write_text(vm, path, content)
            except Exception as exc:  # noqa: BLE001
                emit_runtime_exception(
                    stage="mutation_handlers",
                    operation="write_finance_create_record",
                    error=exc,
                    extra={"path": path},
                )
        return map_mutation_result(result)
    if command.action == "bulk_delete_by_text_filter":
        llm_selector = build_finance_selector(gateway, model)
        result = resolve_finance_bulk_delete(
            context.finance_records,
            match_text=command.match_text,
            record_type=command.record_type,
            projection=command.projection,
            sort=command.sort,
            render=command.render,
            task_text=task_text,
            llm_selector=llm_selector,
        )
        if result.status == "resolved" and vm is not None and result.grounding_refs:
            vm_delete_many(vm, result.grounding_refs)
        return map_mutation_result(result)
    if command.action in {
        "update_bill",
        "update_invoice",
        "add_line_item",
        "remove_line_item",
        "mark_paid",
        "settle_payment",
        "adjust_amount",
    }:
        resolved_record = resolve_finance_target_record(
            context.finance_records,
            action=command.action,
            record_type=command.record_type,
            record_path=command.record_path,
            anchor_record_ref=command.anchor_record_ref,
            reference_number=command.reference_number or command.invoice_number,
            counterparty=command.counterparty,
            alias=command.alias,
            project=command.project,
            related_entity=command.related_entity,
            date=command.date,
            amount=command.amount,
        )
        existing_record_text = read_existing_finance_record_text(vm, resolved_record)
        plan = resolve_finance_update_record(
            context.finance_records,
            action=command.action,
            record_type=command.record_type,
            record_path=command.record_path,
            anchor_record_ref=command.anchor_record_ref,
            reference_number=command.reference_number or command.invoice_number,
            counterparty=command.counterparty,
            alias=command.alias,
            project=command.project,
            related_entity=command.related_entity,
            authorization_kind=command.authorization_kind,
            authorized_by=command.authorized_by,
            settlement_reference=command.settlement_reference,
            settlement_channel=command.settlement_channel,
            settlement_date=command.settlement_date,
            amount=command.amount,
            date=command.date,
            notes=command.notes,
            item_name=command.item_name,
            line_item_index=command.line_item_index,
            quantity=command.quantity,
            unit_price=command.unit_price,
            existing_record_text=existing_record_text,
            resolved_record=resolved_record,
        )
        execute_finance_write_plan(
            vm,
            plan,
            layout=context.workspace_layout,
        )
        return map_mutation_result(plan.result)
    # NORTH_STAR: the mutation fallback invokes an LLM replanner. Gate on
    # authorization BEFORE that LLM call so unauthorized commands can never
    # reach the semantic stage via this escape hatch.
    if not command_has_authorization(command):
        return MutationExecutionResult(
            decision=decide_blocked(
                reason_code="unauthorized_for_fallback",
                llm_stage=None,
            ),
            message=(
                "This mutation cannot fall back to LLM replanning because "
                "the typed command carries no AuthorizationStamp. Authorize "
                "the command at the orchestrator or workflow boundary before "
                "retrying."
            ),
            refs=(),
        )
    fallback = run_mutation_fallback(
        command,
        task_text=task_text,
        gateway=gateway,
        model=model,
        vm=vm,
        context=context,
    )
    if fallback is not None:
        return map_fallback_result(
            fallback,
            vm=vm,
            context=context,
        )
    return unsupported_mutation("finance_mutation_variant_unsupported")


__all__ = [
    "MutationExecutionResult",
    "execute_mutation_step",
    "handle_finance_mutation",
    "handle_outbox_draft",
    "handle_project_mutation",
    "handle_queue_mutation",
]
