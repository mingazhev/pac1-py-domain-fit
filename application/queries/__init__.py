"""Cross-context read-only queries.

The typed-step surface exposes three unified query facades:

- ``resolve_entity_query`` — entity scalar/list/aggregate properties.
- ``resolve_project_query`` — project scalar properties and
  membership/involvement with typed shaping.
- ``resolve_message_query`` — message property lookup with typed
  selection.

Account, contact, finance, and queue-state lookups remain as their own
modules because their policy/shape is materially different.
"""

from .account_lookup import (
    AccountLookupQueryResult,
    render_account_lookup_result,
    resolve_account_lookup_query,
)
from .capture_lookup import CaptureLookupQueryResult, resolve_capture_lookup_query
from .contact_lookup import (
    ContactLookupQueryResult,
    render_contact_lookup_result,
    resolve_contact_lookup_query,
)
from .entity_query import EntityQueryResult, resolve_entity_query
from .finance_lookup import FinanceLookupQueryResult, resolve_finance_lookup_query
from .message_query import MessageQueryResult, resolve_message_query
from .project_query import ProjectQueryResult, resolve_project_query
from .queue_state_lookup import (
    QueueStateLookupQueryResult,
    render_queue_state_lookup_result,
    resolve_queue_state_lookup_query,
)

__all__ = [
    "AccountLookupQueryResult",
    "CaptureLookupQueryResult",
    "ContactLookupQueryResult",
    "EntityQueryResult",
    "FinanceLookupQueryResult",
    "MessageQueryResult",
    "ProjectQueryResult",
    "QueueStateLookupQueryResult",
    "render_account_lookup_result",
    "render_contact_lookup_result",
    "render_queue_state_lookup_result",
    "resolve_account_lookup_query",
    "resolve_capture_lookup_query",
    "resolve_contact_lookup_query",
    "resolve_entity_query",
    "resolve_finance_lookup_query",
    "resolve_message_query",
    "resolve_project_query",
    "resolve_queue_state_lookup_query",
]
