from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FinanceMutationPresentation:
    projection: str = "default"
    sort: str = "default"
    render: str = "default"


@dataclass(frozen=True, slots=True)
class FinanceMutationAction:
    kind: str = field(default="finance_mutation", init=False)
    action: str = ""
    record_type: str = "any"
    counterparty: str | None = None
    amount: float | None = None
    item_name: str | None = None
    line_item_index: int | None = None
    quantity: float | None = None
    unit_price: float | None = None
    date: str | None = None
    notes: str | None = None
    record_path: str | None = None
    anchor_record_ref: str | None = None
    reference_number: str | None = None
    alias: str | None = None
    invoice_number: str | None = None
    project: str | None = None
    related_entity: str | None = None
    currency: str = "eur"
    authorized_by: str | None = None
    authorization_kind: str | None = None
    settlement_reference: str | None = None
    settlement_channel: str | None = None
    settlement_date: str | None = None
    match_text: str | None = None
    presentation: FinanceMutationPresentation | None = None


def finance_mutation_projection(action: FinanceMutationAction) -> str:
    return action.presentation.projection if action.presentation else "default"


def finance_mutation_sort(action: FinanceMutationAction) -> str:
    return action.presentation.sort if action.presentation else "default"


def finance_mutation_render(action: FinanceMutationAction) -> str:
    return action.presentation.render if action.presentation else "default"


@dataclass(frozen=True, slots=True)
class OutboxDraftAction:
    kind: str = field(default="outbox_draft", init=False)
    to: tuple[str, ...] = ()
    subject: str = ""
    body: str = ""
    attachments: tuple[str, ...] = ()
    attachment_record_type: str = "any"
    attachment_counterparty: str | None = None
    attachment_date: str | None = None
    attachment_reference_number: str | None = None
    attachment_alias: str | None = None
    attachment_record_hint: str | None = None
    attachment_project: str | None = None
    attachment_related_entity: str | None = None
    related_entities: tuple[str, ...] = ()
    source_channel: str | None = None
    created_at: str | None = None
    send_state: str = "draft"
    authorization_kind: str | None = None
    authorized_by: str | None = None


__all__ = [
    "FinanceMutationAction",
    "FinanceMutationPresentation",
    "OutboxDraftAction",
    "finance_mutation_projection",
    "finance_mutation_render",
    "finance_mutation_sort",
]
