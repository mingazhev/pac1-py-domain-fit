from __future__ import annotations

from task_routing import (
    AccountLookupCommand,
    CaptureLookupCommand,
    ContactLookupCommand,
    EntityQueryCommand,
    FinanceLookupCommand,
    FinanceMutationCommand,
    InboxProcessNextCommand,
    MessageQueryCommand,
    OutboxDraftCommand,
    ProjectMutationCommand,
    ProjectQueryCommand,
    QueueMutationCommand,
    QueueStateLookupCommand,
    TaskIntent,
    TypedStep,
)


ContextKind = str

ALL_CONTEXT_KINDS: frozenset[ContextKind] = frozenset(
    {
        "cast",
        "project",
        "finance",
        "accounts",
        "contacts",
        "messages",
        "queue",
        "inbox",
        "capture",
    }
)


INTENT_KIND_MAP: dict[TaskIntent, frozenset[str]] = {
    TaskIntent.ACCOUNT_LOOKUP: frozenset({"accounts"}),
    TaskIntent.CONTACT_LOOKUP: frozenset({"accounts", "contacts"}),
    TaskIntent.CAPTURE_LOOKUP: frozenset({"capture"}),
    TaskIntent.ENTITY_QUERY: frozenset({"cast"}),
    TaskIntent.PROJECT_QUERY: frozenset({"cast", "project"}),
    TaskIntent.PROJECT_MUTATION: frozenset({"cast", "project"}),
    TaskIntent.MESSAGE_QUERY: frozenset({"cast", "messages"}),
    TaskIntent.FINANCE_LOOKUP: frozenset({"cast", "finance"}),
    TaskIntent.FINANCE_MUTATION: frozenset({"cast", "finance"}),
    TaskIntent.QUEUE_STATE_LOOKUP: frozenset({"queue"}),
    TaskIntent.QUEUE_MUTATION: frozenset({"queue"}),
    TaskIntent.OUTBOX_DRAFT: frozenset({"cast", "contacts"}),
}

INBOX_CONTEXT_KINDS = frozenset(
    {
        "cast",
        "project",
        "finance",
        "messages",
        "queue",
        "inbox",
        "capture",
        "accounts",
        "contacts",
    }
)


COMMAND_INTENT_MAP: dict[type, TaskIntent] = {
    AccountLookupCommand: TaskIntent.ACCOUNT_LOOKUP,
    ContactLookupCommand: TaskIntent.CONTACT_LOOKUP,
    CaptureLookupCommand: TaskIntent.CAPTURE_LOOKUP,
    ProjectQueryCommand: TaskIntent.PROJECT_QUERY,
    ProjectMutationCommand: TaskIntent.PROJECT_MUTATION,
    EntityQueryCommand: TaskIntent.ENTITY_QUERY,
    MessageQueryCommand: TaskIntent.MESSAGE_QUERY,
    FinanceLookupCommand: TaskIntent.FINANCE_LOOKUP,
    FinanceMutationCommand: TaskIntent.FINANCE_MUTATION,
    QueueStateLookupCommand: TaskIntent.QUEUE_STATE_LOOKUP,
    QueueMutationCommand: TaskIntent.QUEUE_MUTATION,
    OutboxDraftCommand: TaskIntent.OUTBOX_DRAFT,
    InboxProcessNextCommand: TaskIntent.INBOX_PROCESS_NEXT,
}


def needed_kinds_for_intent(intent: TaskIntent) -> frozenset[str]:
    if intent in {TaskIntent.INBOX_PROCESS_NEXT, TaskIntent.INBOX_WORKFLOW}:
        return INBOX_CONTEXT_KINDS
    return INTENT_KIND_MAP.get(intent, frozenset())


def needed_kinds_for_command(command: TypedStep) -> frozenset[str]:
    intent = COMMAND_INTENT_MAP.get(type(command))
    if intent is None:
        return frozenset()
    return needed_kinds_for_intent(intent)


__all__ = [
    "ALL_CONTEXT_KINDS",
    "COMMAND_INTENT_MAP",
    "ContextKind",
    "INBOX_CONTEXT_KINDS",
    "INTENT_KIND_MAP",
    "needed_kinds_for_command",
    "needed_kinds_for_intent",
]
