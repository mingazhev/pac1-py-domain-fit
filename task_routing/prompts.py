from __future__ import annotations

from typing import Type

from pydantic import BaseModel

from domain.workspace import WorkspacePolicies

from .model import (
    AccountLookupRequest,
    CaptureLookupRequest,
    ContactLookupRequest,
    EntityQueryRequest,
    FinanceLookupRequest,
    FinanceMutationRequest,
    FollowUpRescheduleRequest,
    FollowUpSendRequest,
    InboxEmailLookupRequest,
    InboxProcessNextRequest,
    MessageQueryRequest,
    OutboundEmailLookupRequest,
    OutboxDraftRequest,
    ProjectMutationRequest,
    ProjectQueryRequest,
    QueueMutationRequest,
    QueueStateLookupRequest,
    TaskIntent,
    TaskRouteDecision,
)


def request_model_for_decision(decision: TaskRouteDecision) -> Type[BaseModel] | None:
    if decision.intent == TaskIntent.ACCOUNT_LOOKUP:
        return AccountLookupRequest
    if decision.intent == TaskIntent.CONTACT_LOOKUP:
        return ContactLookupRequest
    if decision.intent == TaskIntent.CAPTURE_LOOKUP:
        return CaptureLookupRequest
    if decision.intent == TaskIntent.PROJECT_QUERY:
        return ProjectQueryRequest
    if decision.intent == TaskIntent.ENTITY_QUERY:
        return EntityQueryRequest
    if decision.intent == TaskIntent.MESSAGE_QUERY:
        return MessageQueryRequest
    if decision.intent == TaskIntent.OUTBOUND_EMAIL_LOOKUP:
        return OutboundEmailLookupRequest
    if decision.intent in {TaskIntent.INBOX_PROCESS_NEXT, TaskIntent.INBOX_WORKFLOW}:
        return InboxProcessNextRequest
    if decision.intent == TaskIntent.INBOX_EMAIL_LOOKUP:
        return InboxEmailLookupRequest
    if decision.intent == TaskIntent.QUEUE_STATE_LOOKUP:
        return QueueStateLookupRequest
    if decision.intent == TaskIntent.FINANCE_LOOKUP:
        return FinanceLookupRequest
    if decision.intent == TaskIntent.FINANCE_MUTATION:
        return FinanceMutationRequest
    if decision.intent == TaskIntent.PROJECT_MUTATION:
        return ProjectMutationRequest
    if decision.intent == TaskIntent.OUTBOX_DRAFT:
        return OutboxDraftRequest
    if decision.intent == TaskIntent.QUEUE_MUTATION:
        return QueueMutationRequest
    if decision.intent == TaskIntent.FOLLOW_UP_SEND:
        return FollowUpSendRequest
    if decision.intent == TaskIntent.FOLLOW_UP_RESCHEDULE:
        return FollowUpRescheduleRequest
    return None
_PRECEDENCE_NOTE = (
    "Precedence: folder-scoped AGENTS.MD OVERRIDES the root policy on "
    "any conflict — apply the most specific lane's rules first."
)


def _folder_policies_for_intent(
    intent: TaskIntent,
    policies: WorkspacePolicies,
) -> list[tuple[str, str]]:
    """Return (label, body) pairs of folder-scoped policies relevant
    to the intent, ordered most-specific to least-specific.

    Callers present these AFTER the root policy and flag that they
    override the root on any conflict.
    """

    out: list[tuple[str, str]] = []
    add = lambda label, body: body and out.append((label, body))

    if intent in {
        TaskIntent.OUTBOX_DRAFT,
        TaskIntent.OUTBOUND_EMAIL_LOOKUP,
        TaskIntent.FOLLOW_UP_SEND,
        TaskIntent.FOLLOW_UP_RESCHEDULE,
    }:
        add("Outbox folder policy (AGENTS.MD)", policies.outbox)
        add("Cast/entities folder policy (AGENTS.MD)", policies.cast)
        for name, body in policies.extra_workflows:
            if "sending-email" in name:
                add(f"Workflow doc — {name}", body)
    elif intent in {
        TaskIntent.INBOX_PROCESS_NEXT,
        TaskIntent.INBOX_EMAIL_LOOKUP,
        TaskIntent.INBOX_WORKFLOW,
    }:
        add("Inbox folder policy (AGENTS.MD)", policies.inbox)
        for name, body in policies.extra_workflows:
            if "processing-inbox-email" in name:
                add(f"Workflow doc — {name}", body)
    elif intent in {
        TaskIntent.FINANCE_LOOKUP,
        TaskIntent.FINANCE_MUTATION,
    }:
        add("Finance folder policy (AGENTS.MD)", policies.finance)
    elif intent in {
        TaskIntent.PROJECT_QUERY,
        TaskIntent.PROJECT_MUTATION,
    }:
        add("Projects folder policy (AGENTS.MD)", policies.projects)
        add("Work folder policy (AGENTS.MD)", policies.work)
        add("Cast/entities folder policy (AGENTS.MD)", policies.cast)
    elif intent in {
        TaskIntent.ACCOUNT_LOOKUP,
        TaskIntent.CONTACT_LOOKUP,
        TaskIntent.ENTITY_QUERY,
        TaskIntent.MESSAGE_QUERY,
    }:
        add("Cast/entities folder policy (AGENTS.MD)", policies.cast)
    elif intent == TaskIntent.CAPTURE_LOOKUP:
        add("Capture folder policy (AGENTS.MD)", policies.capture)
        add("Knowledge folder policy (AGENTS.MD)", policies.knowledge)
    elif intent in {
        TaskIntent.QUEUE_MUTATION,
        TaskIntent.QUEUE_STATE_LOOKUP,
    }:
        add("System folder policy (AGENTS.MD)", policies.system)

    return out


def _policy_snippet_for_intent(
    decision: TaskRouteDecision,
    policies: WorkspacePolicies | None,
) -> str:
    if policies is None or policies.is_empty:
        return ""

    folder_policies = _folder_policies_for_intent(decision.intent, policies)
    segments: list[str] = []
    if policies.root:
        segments.append(
            f"Root workspace policy (AGENTS.MD at repo root):\n{policies.root}"
        )
    for label, body in folder_policies:
        segments.append(f"{label}:\n{body}")
    if policies.root and folder_policies:
        segments.append(_PRECEDENCE_NOTE)
    return "\n\n".join(segments)


def build_extraction_prompt(
    decision: TaskRouteDecision,
    *,
    workspace_policies: WorkspacePolicies | None = None,
    finance_record_index: str = "",
) -> str:
    base = _build_extraction_prompt_base(decision)
    snippet = _policy_snippet_for_intent(decision, workspace_policies)
    index_snippet = _finance_index_snippet_for_intent(
        decision, finance_record_index
    )
    pieces = [base]
    if snippet:
        pieces.append(snippet)
    if index_snippet:
        pieces.append(index_snippet)
    return "\n\n".join(pieces)


def _finance_index_snippet_for_intent(
    decision: TaskRouteDecision, finance_record_index: str
) -> str:
    body = str(finance_record_index or "").strip()
    if not body:
        return ""
    if decision.intent not in {
        TaskIntent.OUTBOX_DRAFT,
        TaskIntent.OUTBOUND_EMAIL_LOOKUP,
        TaskIntent.FOLLOW_UP_SEND,
    }:
        return ""
    return (
        "Canonical finance record index (path; kind; date; counterparty; "
        "amount). Use these paths — and ONLY these paths — when choosing "
        "invoice/bill attachments. Never invent paths.\n" + body
    )


def _build_extraction_prompt_base(decision: TaskRouteDecision) -> str:
    if decision.intent == TaskIntent.ACCOUNT_LOOKUP:
        return (
            "Extract a strict request for an account lookup. "
            "Use `query` for the human account description exactly as the user supplied it. "
            "Set `output_field` to `legal_name`, `display_name`, or `account_id` based on the requested answer. "
            "If the task is non-English, include `translated_text` with the English translation."
        )
    if decision.intent == TaskIntent.CONTACT_LOOKUP:
        return (
            "Extract a strict request for a contact lookup. "
            "Use `query` for the human account or contact description exactly as the user supplied it. "
            "Set `relationship_role` to `primary_contact` or `account_manager` only when the task explicitly asks for that relationship; otherwise `direct`. "
            "Set `output_field` to `email`, `full_name`, or `title` based on the requested answer. "
            "If the task is non-English, include `translated_text` with the English translation."
        )
    if decision.intent == TaskIntent.CAPTURE_LOOKUP:
        return (
            "Extract a strict request for a capture lookup by relative date. "
            "Use `relative_date_phrase` for the user's phrase such as `3 days ago`, `yesterday`, or `today`. "
            "Set `output_field` to `filename` only when the user asks for the filename or which file; "
            "set it to `context_note` only when the user asks to summarize or otherwise use the article as context; "
            "set it to `date` only when the user asks for the resolved date itself; otherwise use `title`. "
            "If the task is non-English, include `translated_text` with the English translation."
        )
    if decision.intent == TaskIntent.PROJECT_QUERY:
        return (
            "Extract a typed project query. `entity_reference` is the "
            "canonical project name or alias, stripped of leading wrapper "
            "words like 'the' and 'project', and stripped of output-"
            "format chatter. Produce the exact canonical form you would "
            "type to grep the repo, not the user's conversational phrasing. "
            "Preserve possessive or relationship-shaped references instead of "
            "collapsing them to a bare generic noun. "
            "`variant` partitions the query: `membership_or_involvement` "
            "covers 'which projects is X involved in / how many' phrasings; "
            "`scalar_property` covers every other canonical property. "
            "`property` is always one of the closed allowlist; pick the one "
            "the user asked about. When `variant=membership_or_involvement`, "
            "use `projection`, `sort`, and `render` to encode collection "
            "shaping explicitly; use `render=count` only when the task asks "
            "how many. `status_filter` stays `any` unless the task "
            "explicitly constrains project status. `anchor_record_ref` is "
            "only set when the task points at a canonical record path and "
            "omits direct counterparty wording. If the task is non-English, "
            "include `translated_text`."
        )
    if decision.intent == TaskIntent.ENTITY_QUERY:
        return (
            "Extract a typed entity query. `entity_reference` is the "
            "canonical name, alias, or relationship phrase of the person, "
            "system, or pet exactly as needed to resolve the intended "
            "entity. Preserve meaningful qualifiers from the user's phrase "
            "instead of stripping articles or possessives mechanically. "
            "For pets and systems, prefer a clear species/title like "
            "'dog' only when that is actually the user's intended "
            "reference. "
            "Preserve possessive family or relationship references such as "
            "`Jordan's mom` or `Avery's husband`; do not collapse them to "
            "just the anchor person's name. "
            "Set `self_reference=true` only when the user is explicitly "
            "referring to themself (`I`, `me`, `my birthday`, `my alias`, "
            "etc.); when you do, set `entity_reference` to `self`. "
            "`variant` is `scalar_property` for a single-value answer, "
            "`list_property` for canonical collections, and "
            "`aggregate_property` for rollups such as "
            "`next_upcoming_birthday` across cast records; set "
            "`aggregate` to the closed enum value when and only when the "
            "variant is aggregate. Use `aggregate_filter=people_only` only "
            "when the user explicitly asks whose/person/people birthday is "
            "next; otherwise leave `aggregate_filter=any`. `property` is always one of the closed "
            "allowlist. If the task is non-English, include "
            "`translated_text`."
        )
    if decision.intent == TaskIntent.MESSAGE_QUERY:
        return (
            "Extract a typed message query. `entity_reference` is the person "
            "or system exactly as the user refers to them. `selection` is "
            "`quote` only when the task explicitly asks for a verbatim quote; "
            "otherwise `last_recorded_message`. `property` is one of the "
            "closed allowlist of canonical message fields. If the task is "
            "non-English, include `translated_text`."
        )
    if decision.intent == TaskIntent.OUTBOUND_EMAIL_LOOKUP:
        return (
            "Extract a strict request for an outbound email lookup. "
            "Use `query` for the requested search text. "
            "Set `include_state` to one of: `draft`, `sent` tuples, or leave default. "
            "If the task is non-English, include `translated_text` with the English translation."
        )
    if decision.intent in {TaskIntent.INBOX_PROCESS_NEXT, TaskIntent.INBOX_WORKFLOW}:
        return (
            "Extract a strict request for processing the next inbox item. "
            "Set `filename_only` to true only when the user asks for the inbox filename or path only; otherwise false. "
            "If the task is non-English, include `translated_text` with the English translation."
        )
    if decision.intent == TaskIntent.INBOX_EMAIL_LOOKUP:
        return (
            "Extract a strict request for an inbox email lookup. "
            "Use `query` for the requested inbox email search text. "
            "If the task is non-English, include `translated_text` with the English translation."
        )
    if decision.intent == TaskIntent.QUEUE_STATE_LOOKUP:
        return (
            "Extract a strict request for a queue-state lookup. "
            "Use `queue_reference` for the queue or workflow-state name exactly as the user refers to it. "
            "If the task is non-English, include `translated_text` with the English translation."
        )
    if decision.intent == TaskIntent.FINANCE_LOOKUP:
        return (
            "Extract a strict request for a finance ledger lookup. "
            "Choose `action` from: `counterparty_total`, `service_line_total`, `record_date`, "
            "`record_total`, `settlement_status`, `settlement_reference`, `line_item_count`, "
            "`line_item_quantity`, `line_item_price`, `line_item_total`. "
            "Action meanings: `counterparty_total` is the total across the relevant bill/invoice "
            "family for one counterparty; `service_line_total` is the revenue/amount for one named "
            "service line or service project across records; `record_total` is the total on one "
            "single bill/invoice record; `line_item_price` is the per-unit price of one named line "
            "item; `line_item_total` is the full amount of one matching line item on the targeted "
            "record or record family. "
            "Set `record_type` to `bill` or `invoice` only when the task explicitly constrains it; otherwise `any`. "
            "Use `counterparty` for the vendor or client name when present. "
            "Use `reference_number`, `alias`, `project`, and `related_entity` only when the task explicitly names those canonical identity fields. "
            "Use `item_name` for the specific line item, service line, or named service project when present. "
            "Use `date_range_start` and `date_range_end` for explicit range windows. "
            "Use `since_date` for open-ended 'since X' service-line or named service-project revenue queries. "
            "Use `relative_days_ago` only when the task explicitly uses relative-day wording. "
            "Use `amount_hints` only for numeric hints that help identify the right record or line item. "
            "Set `anchor_record_ref` only when the task points at one canonical record path or anchor reference. "
            "Set `output_format` to one of: `iso`, `dd-mm-yyyy`, `mm/dd/yyyy`, `month dd, yyyy`. "
            "Do not invent canonical ids, project titles, or normalized counterparties. "
            "If the task is non-English, include `translated_text` with the English translation. "
            "Return only fields required by the schema."
        )
    if decision.intent == TaskIntent.FINANCE_MUTATION:
        return (
            "Extract a typed finance record mutation. `action` is one of "
            "the closed allowlist.\n"
            "For `create_invoice` / `create_bill`: fill `date` (ISO YYYY-"
            "MM-DD), `counterparty` (exact vendor/client name), `amount` "
            "(total in euros as a number), `alias` (short snake_case slug "
            "derived from the deal/project, e.g. 'client_portal_phase_two' "
            "or 'hardware_parts_nozzle_and_inserts'), `project` (canonical "
            "project title when known), `related_entity` (entity slug "
            "when one is referenced), and `line_items` (list of {item, "
            "qty, unit_eur}); set `invoice_number` (e.g. 'inv_0002') only "
            "when the task explicitly names it — otherwise leave null and "
            "the writer will compute the next number per alias.\n"
            "For `bulk_delete_by_text_filter`: set `match_text` (the "
            "user's literal match phrase) and the typed `projection` / "
            "`sort` / `render` shaping fields.\n"
            "For `update_bill` / `mark_paid` / `settle_payment`: set "
            "`record_path` or `anchor_record_ref` when the task points "
            "at a canonical record. Otherwise fill any canonical identity "
            "fields the task really supplies: `counterparty`, `date`, "
            "`reference_number` (invoice number or bill id), `alias`, "
            "`project`, `related_entity`, and `record_type` when the "
            "task explicitly constrains it. Leave `record_type=any` when "
            "the task does not constrain invoice vs bill. Settlement "
            "evidence (`settlement_reference`, `settlement_channel`, "
            "`settlement_date`) and `authorization_kind` / "
            "`authorized_by` must appear only when the request explicitly "
            "attests them. For `remove_line_item`, use `line_item_index` "
            "when the user specifies an explicit ordinal or index like "
            "`first`, `second`, or `#2`; otherwise use the exact canonical "
            "`item_name`.\n"
            "If the task is non-English, include `translated_text`."
        )
    if decision.intent == TaskIntent.PROJECT_MUTATION:
        return (
            "Extract a typed project mutation. `action` is `delete`. "
            "`project_reference` is the project description exactly as the "
            "user supplied it. `authorization_kind` and `authorized_by` must "
            "appear only when the task explicitly authorizes deletion; "
            "otherwise the mutation pipeline will block on missing authz. "
            "If the task is non-English, include `translated_text`."
        )
    if decision.intent == TaskIntent.OUTBOX_DRAFT:
        return (
            "Extract a typed outbox email draft. `to` is the list of "
            "recipient email addresses named by the task. `subject` and "
            "`body` must be non-empty; compose a concise professional "
            "English email body if the task only provides intent. "
            "`attachments` is the list of canonical workspace file paths "
            "to attach (no leading slash); include only paths the task "
            "explicitly names. When the task asks to resend or attach a "
            "finance document without naming its canonical path, leave "
            "`attachments` empty and instead fill the finance attachment "
            "identity fields: `attachment_record_type`, "
            "`attachment_counterparty`, `attachment_date`, "
            "`attachment_reference_number`, `attachment_alias`, "
            "`attachment_record_hint`, "
            "`attachment_project`, `attachment_related_entity`. Use only "
            "identity fields the task really gives or that are implied by "
            "the inbox sender / quoted request context; never invent a "
            "canonical path. When the request names an invoice family or "
            "workstream phrase, copy that phrase into "
            "`attachment_record_hint` so the deterministic attachment "
            "resolver can choose the right canonical record family. "
            "`related_entities` is the list of canonical "
            "entity identifiers referenced (e.g. entity.name_slug). "
            "`source_channel` is the canonical channel path when the "
            "task names one (e.g. 60_outbox/channels/helios_client_email"
            ".md). `created_at` is an ISO-8601 UTC timestamp when "
            "supplied; otherwise leave null and the writer will derive "
            "from runtime context. `send_state` stays `draft` unless the "
            "task explicitly claims the message has been sent. If the "
            "task is non-English, include `translated_text`."
        )
    if decision.intent == TaskIntent.QUEUE_MUTATION:
        return (
            "Extract a typed queue mutation request. `target_names` "
            "holds only markdown filenames or repo-like markdown paths "
            "named by the user verbatim; no canonical-path invention, "
            "no non-md entries. `target_workflow` is the destination "
            "system the user is queueing these docs to (for example "
            "'nora', 'vault2'); copy it in lower-case without prefixes. "
            "`workflow_name` is the canonical workflow identifier if "
            "the task names it (e.g. 'nora_mcp'); otherwise leave null "
            "and the writer will derive a default from target_workflow. "
            "If the task is non-English, include `translated_text`."
        )
    if decision.intent == TaskIntent.FOLLOW_UP_SEND:
        return (
            "Extract a strict request for a follow-up send workflow. "
            "Use `target_entity` for the recipient description exactly as the user supplied it. "
            "Use `subject` and `body` only when the task explicitly gives them. "
            "Set `channel` to `email`, `sms`, or `telegram` only when the task explicitly specifies it; otherwise keep `email`. "
            "If the task is non-English, include `translated_text` with the English translation."
        )
    if decision.intent == TaskIntent.FOLLOW_UP_RESCHEDULE:
        return (
            "Extract a strict request for a follow-up reschedule workflow. "
            "Use `target_entity` for the recipient or thread target exactly as the user supplied it. "
            "Use `original_scheduled_date`, `new_date`, and `reason` only when the task explicitly provides them. "
            "Do not invent schedule dates or reasons. "
            "If the task is non-English, include `translated_text` with the English translation."
        )
    return "No strict extraction schema is defined for this intent."
