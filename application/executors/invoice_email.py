from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from application.contracts import (
    InvoiceBundleRequest,
    InvoiceResendRequest,
    OutboxDraftAction,
)
from application.executors.invoice_channel_selection import (
    select_outbox_channel_for_invoices,
)
from application.executors.invoice_record_selection import (
    invoice_record_matches_entity,
    order_invoice_records_for_reply,
    select_invoice_bundle_records,
    select_invoice_resend_record,
)
from domain.cast import (
    CastEntity,
    CastIdentityProjection,
    resolve_cast_identity,
    resolve_sender_canonical_entity,
)
from domain.finance import FinanceRecord, Invoice
from domain.finance.entity_linking import finance_record_matches_entity
from domain.inbox import InboxItem


@dataclass(frozen=True, slots=True)
class InvoiceEmailWorkflowPlan:
    status: str
    message: str
    reason_code: str
    grounding_refs: tuple[str, ...] = ()
    command: object | None = None


def resolve_invoice_email_workflow(
    *,
    request: InvoiceResendRequest | InvoiceBundleRequest,
    inbox_item: InboxItem,
    finance_records: Sequence[FinanceRecord],
    cast_entities: Sequence[CastEntity],
    available_channels: Sequence[str] = (),
    resolve_cast_identity_subset: Callable[[str, Sequence[CastEntity]], CastIdentityProjection | None] | None = None,
    select_invoice_record_subset: Callable[[str, Sequence[Invoice]], tuple[int, ...]] | None = None,
) -> InvoiceEmailWorkflowPlan:
    invoices = tuple(
        record for record in finance_records if isinstance(record, Invoice)
    )
    if not invoices:
        return InvoiceEmailWorkflowPlan(
            status="clarify_missing",
            message="No canonical invoice records are loaded in context.",
            reason_code="invoice_email_records_missing",
        )

    channel = str(inbox_item.source_channel or inbox_item.channel or "").strip()

    if isinstance(request, InvoiceResendRequest):
        authorized_sender = _authorize_resend_sender(
            inbox_item,
            selected_record=None,
            cast_entities=cast_entities,
        )
        if authorized_sender is None and not _is_self_addressed(inbox_item):
            return InvoiceEmailWorkflowPlan(
                status="blocked",
                message=(
                    "Invoice resend workflow refused because the sender is not a "
                    "canonical authorized contact for deterministic disclosure."
                ),
                reason_code="invoice_email_sender_not_canonical",
            )
        selected = select_invoice_resend_record(
            invoices,
            mode=request.mode,
            counterparty=request.counterparty,
            target_date=request.target_date,
            record_hint=request.record_hint,
            select_invoice_record_subset=select_invoice_record_subset,
        )
        if selected is None:
            return InvoiceEmailWorkflowPlan(
                status="clarify_missing",
                message="No matching invoice record was found for the resend request.",
                reason_code="invoice_email_record_not_found",
            )
        authorized_sender = _authorize_resend_sender(
            inbox_item,
            selected_record=selected,
            cast_entities=cast_entities,
        )
        if authorized_sender is None and not _is_self_addressed(inbox_item):
            return InvoiceEmailWorkflowPlan(
                status="blocked",
                message=(
                    "Invoice resend workflow refused because the sender is not the "
                    "canonical contact for the requested invoice entity."
                ),
                reason_code="invoice_email_sender_not_authorized_for_record",
                grounding_refs=(selected.path,),
            )
        recipient = _resolve_resend_recipient(
            inbox_item,
            cast_entities=cast_entities,
            authorized_sender=authorized_sender,
        )
        if recipient is None:
            return InvoiceEmailWorkflowPlan(
                status="clarify_missing",
                message="Invoice resend workflow could not resolve a canonical reply recipient.",
                reason_code="invoice_email_recipient_unresolved",
                grounding_refs=(selected.path,),
            )
        selected_channel = channel or select_outbox_channel_for_invoices(
            available_channels, (selected,)
        )
        command = OutboxDraftAction(
            to=(recipient,),
            subject=_reply_subject(
                inbox_item.subject,
                fallback=f"Invoice from {selected.counterparty}",
            ),
            body=_resend_body(selected),
            attachments=(selected.path.lstrip("/"),),
            related_entities=_related_entities((selected,)),
            source_channel=selected_channel,
        )
        return InvoiceEmailWorkflowPlan(
            status="resolved",
            message="Prepared deterministic invoice resend draft.",
            reason_code="invoice_email_workflow_resolved",
            grounding_refs=(selected.path,),
            command=command,
        )

    if isinstance(request, InvoiceBundleRequest):
        if not _is_self_addressed(inbox_item):
            return InvoiceEmailWorkflowPlan(
                status="blocked",
                message=(
                    "Invoice bundle workflow is only allowed for self-addressed "
                    "internal inbox notes."
                ),
                reason_code="invoice_email_bundle_external_sender_blocked",
            )
        linked_entity = _resolve_bundle_target_entity(
            cast_entities,
            request.target_query,
            invoices=invoices,
            inbox_body=inbox_item.body,
            resolve_cast_identity_subset=resolve_cast_identity_subset,
        )
        selected_from_subset: tuple[Invoice, ...] = ()
        if linked_entity is None and select_invoice_record_subset is not None:
            selected_from_subset = _select_bundle_records_via_subset(
                invoices,
                request=request,
                inbox_body=inbox_item.body,
                select_invoice_record_subset=select_invoice_record_subset,
            )
        if linked_entity is None and not selected_from_subset:
            return InvoiceEmailWorkflowPlan(
                status="clarify_missing",
                message="Invoice bundle workflow could not resolve a canonical linked entity.",
                reason_code="invoice_email_bundle_target_unresolved",
            )
        if linked_entity is not None:
            selected = select_invoice_bundle_records(
                invoices,
                linked_entity,
                count=request.count,
                selection_mode=request.selection_mode,
                attachment_order=request.attachment_order,
            )
            if not selected and select_invoice_record_subset is not None:
                selected = _select_bundle_records_via_subset(
                    invoices,
                    request=request,
                    inbox_body=inbox_item.body,
                    select_invoice_record_subset=select_invoice_record_subset,
                )
        else:
            selected = order_invoice_records_for_reply(
                selected_from_subset,
                attachment_order=request.attachment_order,
            )
        if not selected:
            return InvoiceEmailWorkflowPlan(
                status="clarify_missing",
                message="No matching invoices were found for the requested bundle.",
                reason_code="invoice_email_bundle_empty",
            )
        ordered = order_invoice_records_for_reply(
            selected,
            attachment_order=request.attachment_order,
        )
        selected_channel = channel or select_outbox_channel_for_invoices(
            available_channels, ordered
        )
        command = OutboxDraftAction(
            to=(str(inbox_item.sender or "").strip(),),
            subject=_reply_subject(
                inbox_item.subject,
                fallback=(
                    f"Invoices linked to {linked_entity.title}"
                    if linked_entity is not None
                    else f"Invoices linked to {request.target_query}"
                ),
            ),
            body=_bundle_body(
                len(ordered),
                linked_entity.title if linked_entity is not None else request.target_query,
            ),
            attachments=tuple(record.path.lstrip("/") for record in ordered),
            related_entities=_related_entities(
                ordered,
                extra=((linked_entity.entity_slug,) if linked_entity is not None else ()),
            ),
            source_channel=selected_channel,
        )
        return InvoiceEmailWorkflowPlan(
            status="resolved",
            message="Prepared deterministic invoice bundle draft.",
            reason_code="invoice_email_workflow_resolved",
            grounding_refs=tuple(record.path for record in ordered),
            command=command,
        )

    return InvoiceEmailWorkflowPlan(
        status="clarify_missing",
        message="Inbox invoice workflow request is unknown.",
        reason_code="invoice_email_workflow_unknown",
    )


def _authorize_resend_sender(
    inbox_item: InboxItem,
    *,
    selected_record: Invoice | None,
    cast_entities: Sequence[CastEntity],
) -> str | None:
    sender = resolve_sender_canonical_entity(cast_entities, inbox_item.sender)
    if sender is None:
        return None
    sender_email = str(sender.primary_contact_email or "").strip()
    if not sender_email:
        return None
    if selected_record is None:
        return sender_email
    if invoice_record_matches_entity(selected_record, sender):
        return sender_email
    return None


def _resolve_resend_recipient(
    inbox_item: InboxItem,
    *,
    cast_entities: Sequence[CastEntity],
    authorized_sender: str | None,
) -> str | None:
    if not _is_self_addressed(inbox_item):
        return str(authorized_sender or "").strip() or None
    sender_email = str(inbox_item.sender or "").strip()
    if sender_email:
        return sender_email
    sender = resolve_sender_canonical_entity(cast_entities, inbox_item.sender)
    return str(sender.primary_contact_email or "").strip() or None


def _is_self_addressed(item: InboxItem) -> bool:
    sender = str(item.sender or "").strip().lower()
    recipients = tuple(
        str(address or "").strip().lower()
        for address in (item.to or ())
        if str(address or "").strip()
    )
    if not sender or not recipients:
        return False
    return all(address == sender for address in recipients)


def _resolve_bundle_target_entity(
    cast_entities: Sequence[CastEntity],
    target_query: str,
    *,
    invoices: Sequence[Invoice] = (),
    inbox_body: str = "",
    resolve_cast_identity_subset: Callable[[str, Sequence[CastEntity]], CastIdentityProjection | None] | None = None,
) -> CastIdentityProjection | None:
    linked_entities = _invoice_linked_entities(cast_entities, invoices=invoices)
    linked_entities_with_invoice_context = _entities_with_linked_invoice_context(
        linked_entities,
        invoices=invoices,
    )
    cast_entities_with_invoice_context = _entities_with_linked_invoice_context(
        cast_entities,
        invoices=invoices,
    )
    exact = resolve_cast_identity(cast_entities, target_query)
    if exact is not None:
        return exact
    if linked_entities:
        linked_exact = resolve_cast_identity(linked_entities, target_query)
        if linked_exact is not None:
            return linked_exact
    rich_instruction = _bundle_target_resolution_instruction(
        target_query,
        inbox_body=inbox_body,
    )
    if resolve_cast_identity_subset is not None and rich_instruction:
        if linked_entities:
            selected = resolve_cast_identity_subset(
                rich_instruction, linked_entities_with_invoice_context
            )
            if selected is not None:
                return selected
        selected = resolve_cast_identity_subset(
            rich_instruction, cast_entities_with_invoice_context
        )
        if selected is not None:
            return selected
    if linked_entities and resolve_cast_identity_subset is not None:
        selected = resolve_cast_identity_subset(
            str(target_query or "").strip(), linked_entities_with_invoice_context
        )
        if selected is not None:
            return selected
    if resolve_cast_identity_subset is not None:
        selected = resolve_cast_identity_subset(
            str(target_query or "").strip(), cast_entities_with_invoice_context
        )
        if selected is not None:
            return selected
    return None


def _reply_subject(subject: str, *, fallback: str) -> str:
    cleaned = str(subject or "").strip()
    if not cleaned:
        return fallback
    if cleaned.startswith("Re: "):
        return cleaned
    return f"Re: {cleaned}"


def _invoice_linked_entities(
    cast_entities: Sequence[CastEntity],
    *,
    invoices: Sequence[Invoice],
) -> tuple[CastEntity, ...]:
    if not invoices or not cast_entities:
        return ()
    matched: list[CastEntity] = []
    for entity in cast_entities:
        if any(finance_record_matches_entity(invoice, entity) for invoice in invoices):
            matched.append(entity)
    return tuple(dict.fromkeys(matched))


def _bundle_target_resolution_instruction(
    target_query: object,
    *,
    inbox_body: object,
) -> str:
    query = str(target_query or "").strip()
    body = str(inbox_body or "").strip()
    if not query:
        return ""
    if not body:
        return query
    return (
        "Resolve the target entity for this invoice bundle request.\n"
        f"Target query: {query}\n"
        f"Inbox body: {body}"
    )


def _bundle_invoice_selection_instruction(
    request: InvoiceBundleRequest,
    *,
    inbox_body: str,
) -> str:
    query = str(request.target_query or "").strip()
    body = str(inbox_body or "").strip()
    return (
        "Select the invoices that belong to the entity described by this invoice bundle request. "
        "Use the target query and inbox body. Ignore the requested count and attachment order at "
        "this stage; identify every invoice that clearly belongs to the target entity even when "
        "there are fewer matching invoices than requested. Be strict and return only invoices "
        "clearly linked to that entity.\n"
        f"Target query: {query}\n"
        f"Inbox body: {body}"
    ).strip()


def _select_bundle_records_via_subset(
    invoices: Sequence[Invoice],
    *,
    request: InvoiceBundleRequest,
    inbox_body: str,
    select_invoice_record_subset: Callable[[str, Sequence[Invoice]], tuple[int, ...]],
) -> tuple[Invoice, ...]:
    instruction = _bundle_invoice_selection_instruction(request, inbox_body=inbox_body)
    picked = select_invoice_record_subset(instruction, invoices)
    selected = tuple(
        invoices[index]
        for index in picked
        if isinstance(index, int) and 0 <= index < len(invoices)
    )
    if not selected:
        return ()
    ordered = sorted(selected, key=lambda item: (item.date, item.path))
    if request.selection_mode == "latest":
        selected_slice = tuple(reversed(ordered[-request.count :]))
    else:
        selected_slice = tuple(ordered[: request.count])
    return selected_slice


def _entities_with_linked_invoice_context(
    entities: Sequence[CastEntity],
    *,
    invoices: Sequence[Invoice],
) -> tuple[CastEntity, ...]:
    if not entities or not invoices:
        return tuple(entities)
    enriched: list[CastEntity] = []
    for entity in entities:
        counterparties = _linked_invoice_counterparties(entity, invoices=invoices)
        if not counterparties:
            enriched.append(entity)
            continue
        invoice_context = "Linked invoice counterparties: " + ", ".join(counterparties)
        merged_body = str(entity.body or "").strip()
        if merged_body:
            merged_body = f"{merged_body}\n{invoice_context}"
        else:
            merged_body = invoice_context
        enriched.append(replace(entity, body=merged_body))
    return tuple(enriched)


def _linked_invoice_counterparties(
    entity: CastEntity,
    *,
    invoices: Sequence[Invoice],
) -> tuple[str, ...]:
    entity_keys = {
        str(entity.entity_slug or "").strip().lower(),
        str(entity.entity_id or "").strip().lower(),
        str(entity.title or "").strip().lower(),
    }
    if not any(entity_keys):
        return ()
    counterparties: list[str] = []
    for invoice in invoices:
        related = str(invoice.related_entity or "").strip().lower()
        if not related or related not in entity_keys:
            continue
        counterparty = str(invoice.counterparty or "").strip()
        if counterparty:
            counterparties.append(counterparty)
    return tuple(dict.fromkeys(counterparties))


def _resend_body(record: Invoice) -> str:
    if str(record.date or "").strip():
        return (
            "Attached is the requested invoice"
            f" from {record.counterparty} dated {record.date}."
        )
    return f"Attached is the requested invoice from {record.counterparty}."


def _bundle_body(count: int, entity_title: str) -> str:
    noun = "invoice" if count == 1 else "invoices"
    return f"Attached are the requested {count} {noun} linked to {entity_title}."


def _related_entities(
    records: Sequence[Invoice],
    *,
    extra: Sequence[str] = (),
) -> tuple[str, ...]:
    values: list[str] = []
    for record in records:
        related = str(record.related_entity or "").strip()
        if related:
            values.append(related)
    for value in extra:
        cleaned = str(value or "").strip()
        if cleaned:
            values.append(cleaned)
    return tuple(dict.fromkeys(values))


__all__ = [
    "InvoiceEmailWorkflowPlan",
    "resolve_invoice_email_workflow",
]
