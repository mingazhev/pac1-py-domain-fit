from __future__ import annotations

from enum import Enum
from typing import Literal, TypeAlias

from pydantic import BaseModel, Field, field_validator, model_validator


class TaskDomain(str, Enum):
    ACCOUNTS = "accounts"
    PROJECTS = "projects"
    ENTITIES = "entities"
    CAPTURE = "capture"
    MESSAGES = "messages"
    FINANCE = "finance"
    INBOX = "inbox"
    OUTBOX = "outbox"
    PROCESS = "process"
    FOLLOW_UP = "follow_up"
    INTEGRATION = "integration"
    UNKNOWN = "unknown"


class TaskIntent(str, Enum):
    ACCOUNT_LOOKUP = "account_lookup"
    CONTACT_LOOKUP = "contact_lookup"
    CAPTURE_LOOKUP = "capture_lookup"
    PROJECT_QUERY = "project_query"
    PROJECT_MUTATION = "project_mutation"
    ENTITY_QUERY = "entity_query"
    MESSAGE_QUERY = "message_query"
    OUTBOUND_EMAIL_LOOKUP = "outbound_email_lookup"
    OUTBOX_DRAFT = "outbox_draft"
    FINANCE_LOOKUP = "finance_lookup"
    FINANCE_MUTATION = "finance_mutation"
    QUEUE_MUTATION = "queue_mutation"
    INBOX_PROCESS_NEXT = "inbox_process_next"
    INBOX_EMAIL_LOOKUP = "inbox_email_lookup"
    QUEUE_STATE_LOOKUP = "queue_state_lookup"
    INBOX_WORKFLOW = "inbox_workflow"
    FOLLOW_UP_SEND = "follow_up_send"
    FOLLOW_UP_RESCHEDULE = "follow_up_reschedule"
    CONTACT_SYNC = "contact_sync"
    REPORT_PUBLISH = "report_publish"
    CALENDAR_EVENT_CREATE = "calendar_event_create"
    UNKNOWN = "unknown"


class RouteConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskRouteDecision(BaseModel):
    domain: TaskDomain = TaskDomain.UNKNOWN
    intent: TaskIntent = TaskIntent.UNKNOWN
    confidence: RouteConfidence = RouteConfidence.LOW

    @property
    def supports_typed_extraction(self) -> bool:
        return self.intent in {
            TaskIntent.ACCOUNT_LOOKUP,
            TaskIntent.CONTACT_LOOKUP,
            TaskIntent.CAPTURE_LOOKUP,
            TaskIntent.PROJECT_QUERY,
            TaskIntent.ENTITY_QUERY,
            TaskIntent.MESSAGE_QUERY,
            TaskIntent.OUTBOUND_EMAIL_LOOKUP,
            TaskIntent.FINANCE_LOOKUP,
            TaskIntent.FINANCE_MUTATION,
            TaskIntent.QUEUE_MUTATION,
            TaskIntent.INBOX_PROCESS_NEXT,
            TaskIntent.INBOX_EMAIL_LOOKUP,
            TaskIntent.QUEUE_STATE_LOOKUP,
            TaskIntent.FOLLOW_UP_SEND,
            TaskIntent.FOLLOW_UP_RESCHEDULE,
        }


class RoutedRequestBase(BaseModel):
    translated_text: str | None = None


class AccountLookupRequest(RoutedRequestBase):
    kind: Literal["account_lookup"] = "account_lookup"
    query: str = Field(min_length=1)
    output_field: Literal["legal_name", "display_name", "account_id"] = "legal_name"


class ContactLookupRequest(RoutedRequestBase):
    kind: Literal["contact_lookup"] = "contact_lookup"
    query: str = Field(min_length=1)
    relationship_role: Literal["direct", "primary_contact", "account_manager"] = (
        "direct"
    )
    output_field: Literal["email", "full_name", "title"] = "email"


class CaptureLookupRequest(RoutedRequestBase):
    kind: Literal["capture_lookup"] = "capture_lookup"
    relative_date_phrase: str = Field(min_length=1)
    output_field: Literal["title", "filename", "context_note", "date"] = "title"


ProjectProperty = Literal[
    "title",
    "project_name",
    "alias",
    "status",
    "kind",
    "lane",
    "priority",
    "visibility",
    "start_date",
    "updated_on",
    "goal",
    "next_step",
    "owner_ids",
    "linked_entities",
    "participants",
]


class ProjectQueryRequest(RoutedRequestBase):
    kind: Literal["project_query"] = "project_query"
    entity_reference: str = Field(min_length=1)
    variant: Literal["scalar_property", "membership_or_involvement"] = "scalar_property"
    property: ProjectProperty = "start_date"
    projection: Literal["default", "title_only"] = "default"
    sort: Literal["default", "title_asc"] = "default"
    render: Literal["default", "line_list", "count"] = "default"
    status_filter: Literal[
        "any", "active", "paused", "planned", "stalled", "simmering"
    ] = "any"
    output_format: Literal["iso", "dd-mm-yyyy", "mm/dd/yyyy", "month dd, yyyy"] = "iso"
    anchor_record_ref: str | None = None

    @field_validator(
        "variant", "property", "projection", "sort", "render",
        "status_filter", "output_format",
        mode="before",
    )
    @classmethod
    def _lowercase_closed_enums(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @model_validator(mode="after")
    def _shaping_requires_involvement(self) -> "ProjectQueryRequest":
        if self.variant == "scalar_property" and self.render == "count":
            raise ValueError(
                "render=count is only valid when variant=membership_or_involvement"
            )
        return self


EntityProperty = Literal[
    "title",
    "entity_id",
    "entity_slug",
    "alias",
    "primary_contact_email",
    "kind",
    "relationship",
    "birthday",
    "created_on",
    "milestones",
    "important_dates",
    "alias_terms",
    "identity_terms",
]


class EntityQueryRequest(RoutedRequestBase):
    kind: Literal["entity_query"] = "entity_query"
    entity_reference: str = Field(min_length=1)
    self_reference: bool = False
    variant: Literal["scalar_property", "list_property", "aggregate_property"] = (
        "scalar_property"
    )
    property: EntityProperty = "birthday"
    aggregate: Literal["next_upcoming_birthday"] | None = None
    aggregate_filter: Literal["any", "people_only"] = "any"
    output_format: Literal["iso", "dd-mm-yyyy", "mm/dd/yyyy", "month dd, yyyy"] = "iso"

    @field_validator(
        "variant", "property", "aggregate", "aggregate_filter", "output_format",
        mode="before",
    )
    @classmethod
    def _lowercase_closed_enums(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @model_validator(mode="after")
    def _aggregate_matches_variant(self) -> "EntityQueryRequest":
        if self.self_reference and str(self.entity_reference or "").strip().lower() != "self":
            object.__setattr__(self, "self_reference", False)
        if self.variant == "aggregate_property" and self.aggregate is None:
            raise ValueError(
                "aggregate_property variant requires a typed aggregate value"
            )
        if self.variant == "aggregate_property":
            return self
        if self.variant != "aggregate_property" and self.aggregate is not None:
            raise ValueError(
                "aggregate is only valid when variant=aggregate_property"
            )
        if self.aggregate_filter != "any":
            raise ValueError(
                "aggregate_filter is only valid when variant=aggregate_property"
            )
        return self


MessageProperty = Literal[
    "message",
    "recorded_on",
    "author",
    "author_id",
    "surface_kind",
]


class MessageQueryRequest(RoutedRequestBase):
    kind: Literal["message_query"] = "message_query"
    entity_reference: str = Field(min_length=1)
    selection: Literal["last_recorded_message", "quote"] = "last_recorded_message"
    property: MessageProperty = "message"


class FinanceLookupRequest(RoutedRequestBase):
    kind: Literal["finance_lookup"] = "finance_lookup"
    action: Literal[
        "counterparty_total",
        "service_line_total",
        "record_date",
        "record_total",
        "settlement_status",
        "settlement_reference",
        "line_item_count",
        "line_item_quantity",
        "line_item_price",
        "line_item_total",
    ]
    record_type: Literal["any", "bill", "invoice"] = "any"
    counterparty: str | None = None
    reference_number: str | None = None
    alias: str | None = None
    project: str | None = None
    related_entity: str | None = None
    item_name: str | None = None
    date_range_start: str | None = None
    date_range_end: str | None = None
    since_date: str | None = None
    relative_days_ago: int | None = None
    amount_hints: tuple[float, ...] = ()
    anchor_record_ref: str | None = None
    output_format: Literal["iso", "dd-mm-yyyy", "mm/dd/yyyy", "month dd, yyyy"] = "iso"


class FinanceLineItemDraft(BaseModel):
    item: str = Field(min_length=1)
    qty: float = 1
    unit_eur: float = 0


class FinanceMutationRequest(RoutedRequestBase):
    kind: Literal["finance_mutation"] = "finance_mutation"
    action: Literal[
        "create_invoice",
        "update_invoice",
        "create_bill",
        "update_bill",
        "add_line_item",
        "remove_line_item",
        "adjust_amount",
        "mark_paid",
        "settle_payment",
        "bulk_delete_by_text_filter",
    ]
    record_type: Literal["invoice", "bill", "any"] = "any"
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
    currency: Literal["eur"] = "eur"
    line_items: tuple[FinanceLineItemDraft, ...] = ()
    authorized_by: str | None = None
    authorization_kind: Literal[
        "explicit_user_confirmation",
        "workflow_policy",
        "pre_authorized_series",
    ] | None = None
    settlement_reference: str | None = None
    settlement_channel: Literal[
        "bank_transfer",
        "card",
        "cash",
        "manual_attestation",
    ] | None = None
    settlement_date: str | None = None
    match_text: str | None = None
    projection: Literal["default", "file_path_only"] = "default"
    sort: Literal["default", "path_asc"] = "default"
    render: Literal["default", "line_list"] = "default"

    @model_validator(mode="after")
    def _bulk_delete_requires_filter(self) -> "FinanceMutationRequest":
        if self.action == "bulk_delete_by_text_filter" and not (self.match_text or "").strip():
            raise ValueError(
                "bulk_delete_by_text_filter requires a non-empty match_text"
            )
        if self.action != "bulk_delete_by_text_filter" and self.match_text is not None:
            raise ValueError(
                "match_text is only valid for bulk_delete_by_text_filter"
            )
        if (
            self.action == "update_bill"
            and self.settlement_channel
            and not (self.settlement_reference or "").strip()
        ):
            raise ValueError(
                "settlement_channel requires settlement_reference"
            )
        if self.action == "remove_line_item":
            if self.line_item_index is None and not (self.item_name or "").strip():
                raise ValueError(
                    "remove_line_item requires line_item_index or item_name"
                )
        elif self.line_item_index is not None:
            raise ValueError(
                "line_item_index is only valid for remove_line_item"
            )
        return self


class ProjectMutationRequest(RoutedRequestBase):
    kind: Literal["project_mutation"] = "project_mutation"
    action: Literal["delete"] = "delete"
    project_reference: str = Field(min_length=1)
    authorization_kind: Literal[
        "explicit_user_confirmation",
        "workflow_policy",
    ] | None = None
    authorized_by: str | None = None


class QueueMutationRequest(RoutedRequestBase):
    kind: Literal["queue_mutation"] = "queue_mutation"
    target_names: tuple[str, ...] = ()
    target_workflow: str | None = None
    workflow_name: str | None = None
    authorization_kind: Literal[
        "explicit_user_confirmation",
        "workflow_policy",
    ] | None = None
    authorized_by: str | None = None


class OutboundEmailLookupRequest(RoutedRequestBase):
    kind: Literal["outbound_email_lookup"] = "outbound_email_lookup"
    query: str = Field(min_length=1)
    include_state: tuple[str, ...] = ("draft", "sent")


class InboxProcessNextRequest(RoutedRequestBase):
    kind: Literal["inbox_process_next"] = "inbox_process_next"
    filename_only: bool = False


class InboxEmailLookupRequest(RoutedRequestBase):
    kind: Literal["inbox_email_lookup"] = "inbox_email_lookup"
    query: str = Field(min_length=1)


class QueueStateLookupRequest(RoutedRequestBase):
    kind: Literal["queue_state_lookup"] = "queue_state_lookup"
    queue_reference: str = Field(min_length=1)


class FollowUpSendRequest(RoutedRequestBase):
    kind: Literal["follow_up_send"] = "follow_up_send"
    target_entity: str = Field(min_length=1)
    subject: str | None = None
    body: str | None = None
    channel: Literal["email", "sms", "telegram"] = "email"


class OutboxDraftRequest(RoutedRequestBase):
    """Compose a canonical outbound email draft into ``/60_outbox/outbox/``.

    LLM fills every field; the deterministic writer composes the
    canonical YAML+body markdown and writes it at a path derived from
    ``created_at``.
    """

    kind: Literal["outbox_draft"] = "outbox_draft"
    to: tuple[str, ...] = ()
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)
    attachments: tuple[str, ...] = ()
    attachment_record_type: Literal["invoice", "bill", "any"] = "any"
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
    send_state: Literal["draft", "sent"] = "draft"
    authorization_kind: Literal[
        "explicit_user_confirmation",
        "workflow_policy",
    ] | None = None
    authorized_by: str | None = None

    @model_validator(mode="after")
    def _requires_recipient(self) -> "OutboxDraftRequest":
        if not self.to:
            raise ValueError(
                "OutboxDraftRequest requires at least one recipient in `to`"
            )
        return self


class FollowUpRescheduleRequest(RoutedRequestBase):
    kind: Literal["follow_up_reschedule"] = "follow_up_reschedule"
    target_entity: str = Field(min_length=1)
    original_scheduled_date: str | None = None
    new_date: str | None = None
    reason: str | None = None


TypedTaskRequest: TypeAlias = (
    AccountLookupRequest
    | ContactLookupRequest
    | CaptureLookupRequest
    | ProjectQueryRequest
    | ProjectMutationRequest
    | EntityQueryRequest
    | MessageQueryRequest
    | FinanceLookupRequest
    | FinanceMutationRequest
    | OutboundEmailLookupRequest
    | OutboxDraftRequest
    | QueueMutationRequest
    | InboxProcessNextRequest
    | InboxEmailLookupRequest
    | QueueStateLookupRequest
    | FollowUpSendRequest
    | FollowUpRescheduleRequest
)
