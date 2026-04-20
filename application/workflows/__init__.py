"""Typed workflow steps under the shared machine.

Workflow steps either terminate (done / clarify / blocked / unsupported)
or emit exactly one typed next step whose continuation must be typed,
grounded, and still inside loop policy. The next-step contract is
enforced by ``domain.process.decide_continue``.
"""

from .inbox_workflow import InboxWorkflowResult, resolve_inbox_workflow_step
from .inbox_execution import (
    InboxWorkflowExecutionPlan,
    WorkflowWrite,
    plan_finance_document_ingest_workflow_step,
    plan_finance_payment_workflow_step,
    plan_invoice_email_workflow_step,
)

__all__ = [
    "InboxWorkflowResult",
    "InboxWorkflowExecutionPlan",
    "WorkflowWrite",
    "plan_finance_document_ingest_workflow_step",
    "plan_finance_payment_workflow_step",
    "plan_invoice_email_workflow_step",
    "resolve_inbox_workflow_step",
]
