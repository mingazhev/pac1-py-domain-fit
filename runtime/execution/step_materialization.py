from __future__ import annotations

from application.contracts import (
    FinanceMutationAction,
    OutboxDraftAction,
    finance_mutation_projection,
    finance_mutation_render,
    finance_mutation_sort,
)
from task_routing import (
    FinanceMutationCommand,
    OutboxDraftCommand,
    TypedStep,
    registered_step_types,
)


def materialize_typed_step(step: object) -> TypedStep | None:
    if isinstance(step, tuple(registered_step_types())):
        return step
    if isinstance(step, FinanceMutationAction):
        return FinanceMutationCommand(
            action=step.action,
            record_type=step.record_type,
            counterparty=step.counterparty,
            amount=step.amount,
            item_name=step.item_name,
            line_item_index=step.line_item_index,
            quantity=step.quantity,
            unit_price=step.unit_price,
            date=step.date,
            notes=step.notes,
            record_path=step.record_path,
            anchor_record_ref=step.anchor_record_ref,
            reference_number=step.reference_number,
            alias=step.alias,
            invoice_number=step.invoice_number,
            project=step.project,
            related_entity=step.related_entity,
            currency=step.currency,
            authorized_by=step.authorized_by,
            authorization_kind=step.authorization_kind,
            settlement_reference=step.settlement_reference,
            settlement_channel=step.settlement_channel,
            settlement_date=step.settlement_date,
            match_text=step.match_text,
            projection=finance_mutation_projection(step),
            sort=finance_mutation_sort(step),
            render=finance_mutation_render(step),
        )
    if isinstance(step, OutboxDraftAction):
        return OutboxDraftCommand(
            to=step.to,
            subject=step.subject,
            body=step.body,
            attachments=step.attachments,
            attachment_record_type=step.attachment_record_type,
            attachment_counterparty=step.attachment_counterparty,
            attachment_date=step.attachment_date,
            attachment_reference_number=step.attachment_reference_number,
            attachment_alias=step.attachment_alias,
            attachment_record_hint=step.attachment_record_hint,
            attachment_project=step.attachment_project,
            attachment_related_entity=step.attachment_related_entity,
            related_entities=step.related_entities,
            source_channel=step.source_channel,
            created_at=step.created_at,
            send_state=step.send_state,
            authorization_kind=step.authorization_kind,
            authorized_by=step.authorized_by,
        )
    return None


__all__ = ["materialize_typed_step"]
