"""Typed mutation handlers under the shared machine.

Each handler returns a ``MutationStepResult`` describing the typed,
postcheck-shaped outcome of one mutation step. The shared pipeline in
``runtime/mutation_execution.py`` owns the resolve → authorize → plan →
execute → postcheck → shape flow; handlers declare only the logic that
differs between typed variants.
"""

from .finance_bulk_delete import resolve_finance_bulk_delete
from .finance_create_record import resolve_finance_create_record
from .finance_update_bill import (
    FinanceRecordWritePlan,
    resolve_finance_update_bill,
    resolve_finance_update_record,
    resolve_finance_target_record,
)
from .outbox_draft import resolve_outbox_draft
from .project_delete import resolve_project_delete
from .queue_markdown import resolve_queue_markdown_mutation
from .result import MutationStepResult

__all__ = [
    "MutationStepResult",
    "FinanceRecordWritePlan",
    "resolve_finance_bulk_delete",
    "resolve_finance_create_record",
    "resolve_finance_update_bill",
    "resolve_finance_update_record",
    "resolve_finance_target_record",
    "resolve_outbox_draft",
    "resolve_project_delete",
    "resolve_queue_markdown_mutation",
]
